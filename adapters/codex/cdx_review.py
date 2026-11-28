"""Codex native Review isolation. The base owns delivery judgments and snapshots."""

from contextlib import ExitStack, contextmanager
from pathlib import Path
import re

from cdx_rpc import AppServer
from runtime import Refused, THREAD_ID


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


def review_turn(server, checkout, base, timeout, record, save, events, model=None):
    options = {"cwd": str(checkout), "ephemeral": True, "sandbox": "read-only", "approvalPolicy": "never"}
    if model:
        options["model"] = model
    result = server.call("thread/start", options)
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
