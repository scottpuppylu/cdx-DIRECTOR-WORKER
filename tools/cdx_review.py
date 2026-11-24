"""Run Codex native review over a sealed work-order range."""

from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid

from cdx_common import (THREAD_ID, Refused, atomic_write, detached_checkout, git, json_bytes, stamp, state_path)
from cdx_rpc import AppServer
from cdx_work import approved_brief, dispatch_check, sealed_ref


REVIEW_FEATURES = ("apps", "plugins", "hooks")
REVIEW_OVERRIDES = (*(f"features.{name}=false" for name in REVIEW_FEATURES),
                    'web_search="disabled"', "mcp_servers={}")


def review_connections(server, cwd):
    config = server.call("config/read", {"cwd": str(cwd)}).get("config") or {}
    features = config.get("features") or {}
    definitions = config.get("mcp_servers")
    if (config.get("web_search") != "disabled" or not isinstance(definitions, dict) or
            any(not isinstance(item, dict) or item.get("enabled") is not False for item in definitions.values()) or
            any(features.get(name) is not False for name in REVIEW_FEATURES)):
        raise Refused("Review requires confirmed MCP, plugins, Hooks, apps and web search isolation")
    servers = server.call("mcpServerStatus/list", {"limit": 100})
    rows = servers.get("data")
    if (not isinstance(rows, list) or servers.get("nextCursor") or any(
            not isinstance(row, dict) or row.get("name") not in definitions or
            any(row.get(key) for key in ("runtimeStatus", "tools", "resources", "resourceTemplates"))
            for row in rows)):
        raise Refused("Review runtime still exposes an MCP server")


@contextmanager
def review_server(executable, cwd, observer, *, env=None):
    with ExitStack() as stack:
        server = stack.enter_context(AppServer(executable, cwd, observer, env=env, overrides=REVIEW_OVERRIDES))
        config = server.call("config/read", {"cwd": str(cwd)}).get("config") or {}
        definitions = config.get("mcp_servers")
        if not isinstance(definitions, dict):
            raise Refused("App Server did not disclose effective MCP settings")
        names = [name for name, item in definitions.items() if not isinstance(item, dict) or item.get("enabled") is not False]
        if names:
            if not all(re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in names):
                raise Refused("Review cannot safely override a configured MCP server name")
            stack.close()
            overrides = (*REVIEW_OVERRIDES, *(f"mcp_servers.{name}.enabled=false" for name in names))
            server = stack.enter_context(AppServer(executable, cwd, observer, env=env, overrides=overrides))
        review_connections(server, cwd)
        yield server


def review_target(repo, state, spec, candidate):
    dispatch_check(state, spec)
    approved_brief(state, spec)
    ref = sealed_ref(spec, candidate)
    if git(repo, "for-each-ref", "--format=%(objectname)", ref) != candidate:
        raise Refused("Seal the full candidate before native review")
    base = spec["base"]
    git(repo, "merge-base", "--is-ancestor", base, candidate)
    diff = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--binary", base, candidate, "--",
               raw=True)
    return {"order": spec["order_id"], "order_sha256": spec["sha"], "sealed_ref": ref,
            "base": base, "candidate": candidate, "diff_sha256": hashlib.sha256(diff).hexdigest()}


def review_turn(server, checkout, base, timeout, record, save, events):
    result = server.call("thread/start", {"cwd": str(checkout), "ephemeral": True,
                                          "sandbox": "read-only", "approvalPolicy": "never"})
    thread = result["thread"]
    sandbox = result.get("sandbox", {})
    if (not THREAD_ID.fullmatch(thread.get("id", "")) or Path(thread["cwd"]).resolve() != checkout or
            sandbox.get("type") != "readOnly" or sandbox.get("networkAccess", False) is not False or
            result.get("approvalPolicy") != "never"):
        raise Refused("App Server did not confirm the isolated read-only review thread")
    thread_id = thread["id"]
    record["thread"] = thread_id
    save()
    response = server.call("review/start", {"threadId": thread_id, "delivery": "inline",
                                           "target": {"type": "baseBranch", "branch": base}})
    if response.get("reviewThreadId") != thread_id:
        raise Refused("Native review was attributed to a different thread")
    turn_id = response["turn"]["id"]
    record["turn"] = turn_id
    save()

    def completed(message):
        params = message.get("params", {})
        return (message.get("method") == "turn/completed" and params.get("threadId") == thread_id and
                params.get("turn", {}).get("id") == turn_id)

    final = next((message for message in events if completed(message)), None)
    if final is None:
        final = server.receive(completed, timeout, "native review completion")
    record["native_status"] = final["params"]["turn"]["status"]
    for message in events:
        params = message.get("params", {})
        item = params.get("item", {})
        if (message.get("method") == "item/completed" and params.get("threadId") == thread_id and
                params.get("turnId") == turn_id and item.get("type") == "exitedReviewMode"):
            record["review"] = item["review"]


def native_review(repo, state, spec, candidate, executable, timeout, preflight):
    target = review_target(repo, state, spec, candidate)
    record = dict(target, schema=1, id=str(uuid.uuid4()), started=stamp(), state="RUNNING")
    path = state_path(state, "reviews", "native", spec["order_id"], f"{record['id']}.json")

    def save():
        atomic_write(path, json_bytes(record))

    save()
    try:
        with detached_checkout(repo, candidate) as worker:
            if (git(worker, "merge-base", "HEAD", target["base"]) != target["base"] or
                    git(worker, "status", "--porcelain", "--untracked-files=all")):
                raise Refused("Native review checkout does not match the sealed range")
            events = []
            with review_server(executable, worker, events.append) as server:
                preflight(server, state)
                review_turn(server, worker, target["base"], timeout, record, save, events)
            if (git(worker, "rev-parse", "HEAD") != candidate or
                    git(worker, "status", "--porcelain", "--untracked-files=all") or
                    review_target(repo, state, spec, candidate) != target):
                raise Refused("The source of the native review changed during the attempt")
        terminal = record.get("native_status")
        if terminal == "completed" and record.get("review"):
            record["state"] = "RECORDED"
        else:
            record["state"] = terminal.upper() if terminal in ("failed", "interrupted") else "UNKNOWN"
    except (KeyboardInterrupt, OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError):
        record["state"] = "UNKNOWN"
        print(f"Native review receipt: {path}")
        raise
    finally:
        record["finished"] = stamp()
        save()
    print(json.dumps({**record, "receipt": str(path)}, ensure_ascii=False))
    return 0 if record["state"] == "RECORDED" else 2
