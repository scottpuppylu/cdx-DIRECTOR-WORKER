"""Probe the installed Codex App Server against disposable local fixtures."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from cdx_rpc import AppServer, RPCError
from cdx_review import review_turn


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-C", str(repo), "-c", "core.hooksPath=.git/no-hooks", *args],
        encoding="utf-8", stderr=subprocess.PIPE, timeout=15,
    ).strip()


def create_fixture(root):
    repo, worker = root / "總監 base", root / "施工 worker"
    skill = repo / ".agents" / "skills" / "dw-probe"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: dw-probe\ndescription: Identify the disposable work-order probe.\n---\n\n"
        "This is a discovery fixture.\n", encoding="utf-8",
    )
    (repo / "AGENTS.md").write_text("# Disposable Codex fixture\n", encoding="utf-8")
    (repo / ".codex").mkdir()
    (repo / ".codex" / "hooks.json").write_text(json.dumps({"hooks": {"SessionStart": [{
        "matcher": "^compact$", "hooks": [{"type": "command", "command": "echo DW_PROBE"}],
    }]}}), encoding="utf-8")
    git(repo, "init", "-b", "main", "--template=")
    git(repo, "add", "--", ".")
    git(repo, "-c", "user.name=DW Probe", "-c", "user.email=dw-probe@example.invalid",
        "-c", "commit.gpgSign=false", "commit", "-m", "Add probe fixture")
    git(repo, "worktree", "add", "--detach", str(worker), "HEAD")
    return repo, worker


def sandbox_check(server, worker, policy_type):
    marker = worker / (policy_type + ".txt")
    command = [sys.executable, "-I", "-c",
               "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text('probe')", str(marker)]
    try:
        response = server.call("command/exec", {"command": command, "cwd": str(worker),
                               "timeoutMs": 10000, "sandboxPolicy": {"type": policy_type}})
    except RPCError as error:
        return {"rpc_code": error.code, "marker_written": marker.is_file()}
    return {"exit": response["exitCode"], "marker_written": marker.is_file()}


class FixtureProvider(BaseHTTPRequestHandler):
    """Return deterministic Responses streams without reaching a model service."""

    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/v1/responses":
            self.send_error(404)
            return
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        functions = {tool.get("name") for tool in request.get("tools", []) if tool.get("type") == "function"}
        native = getattr(self.server, "native_review", False)
        if not native:
            self.server.shell_tools = sorted(name for name in functions if name and ("shell" in name or "exec" in name))
        tool_results = [item for item in request.get("input", []) if item.get("type") == "function_call_output"]
        has_result = bool(tool_results)
        content = {"type": "output_text", "text": "DW_PROBE_OK", "annotations": []}
        if native:
            self.server.review_input = json.dumps(request.get("input", []))
            content["text"] = json.dumps({"findings": [], "overall_correctness": "patch is correct",
                                          "overall_explanation": "DW_NATIVE_REVIEW_FIXTURE",
                                          "overall_confidence_score": 1.0})
        item = {"id": "msg_probe", "type": "message", "role": "assistant",
                "status": "completed", "content": [content]}
        response_id = "resp_probe_final"
        command_tools = {"exec_command": "cmd", "shell_command": "command"}
        command_tool = next((name for name in command_tools if name in functions), None)
        if command_tool and not has_result and not native:
            code = 'python -c "import sys; print(42); sys.exit(7)"'
            item = {"id": "fc_probe", "call_id": "call_probe", "type": "function_call",
                    "name": command_tool, "arguments": json.dumps({command_tools[command_tool]: code}),
                    "status": "completed"}
            response_id = "resp_probe_tool"
            output = [{"type": "response.output_item.added", "item": dict(item, status="in_progress")},
                      {"type": "response.output_item.done", "item": item}]
        else:
            if not native:
                self.server.fixture_tool_results = [item.get("output") for item in tool_results
                                                    if item.get("call_id") == "call_probe"]
            output = [
                {"type": "response.output_item.added", "item": dict(item, status="in_progress", content=[])},
                {"type": "response.output_text.delta", "item_id": item["id"], "output_index": 0,
                 "content_index": 0, "delta": content["text"]},
                {"type": "response.output_item.done", "item": item},
            ]
        events = [
            {"type": "response.created", "response": {"id": response_id}},
            *output,
            {"type": "response.completed", "response": {"id": response_id, "usage": {
                "input_tokens": 80, "input_tokens_details": {"cached_tokens": 60},
                "output_tokens": 5, "output_tokens_details": {"reasoning_tokens": 2}, "total_tokens": 85,
            }}},
        ]
        data = "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def event_check(server, thread_id, events):
    result = server.call("turn/start", {"threadId": thread_id, "input": [
        {"type": "text", "text": "Return the disposable fixture result."},
    ]})
    turn_id = result["turn"]["id"]
    def completed(message):
        params = message.get("params", {})
        return (message.get("method") == "turn/completed" and params.get("threadId") == thread_id and
                params.get("turn", {}).get("id") == turn_id)

    if not any(completed(message) for message in events):
        server.receive(completed, 25, "fixture turn events")
    summary = {}
    for event in events:
        if completed(event):
            summary["status"] = event["params"]["turn"]["status"]
            continue
        params = event.get("params", {})
        if params.get("threadId") != thread_id or params.get("turnId") != turn_id:
            continue
        if event["method"] == "thread/tokenUsage/updated":
            totals = params["tokenUsage"]["last"]
            summary["usage"] = {name: totals.get(name) for name in
                                ("inputTokens", "cachedInputTokens", "outputTokens", "totalTokens")}
        elif event["method"] == "item/completed":
            item = params["item"]
            if item["type"] == "agentMessage":
                summary["fixture_message"] = item.get("text") == "DW_PROBE_OK"
            elif item["type"] == "commandExecution":
                summary["command_execution"] = {"status": item.get("status"), "exit": item.get("exitCode")}
    if summary.get("status") != "completed" or not summary.get("fixture_message"):
        raise RuntimeError("Loopback fixture did not finish successfully")
    return summary


def native_probe(codex, worker, env, provider):
    base = git(worker, "rev-parse", "HEAD")
    for name in ("first.txt", "second.txt"):
        (worker / name).write_text(name + "\n", encoding="utf-8")
        git(worker, "add", "--", name)
        git(worker, "-c", "user.name=DW Probe", "-c", "user.email=dw-probe@example.invalid",
            "-c", "commit.gpgSign=false", "commit", "-m", name)
    events = []
    result = {}
    provider.native_review = True
    with AppServer(codex, worker, events.append, env=env) as server:
        review_turn(server, worker, base, 25, result, lambda: None, events)
    summary = {"terminal": result.get("native_status"), "received_review": bool(result.get("review")),
               "base_in_model_input": base in getattr(provider, "review_input", ""),
               "commits_from_base": int(git(worker, "rev-list", "--count", base + "..HEAD"))}
    if summary != {"terminal": "completed", "received_review": True, "base_in_model_input": True,
                   "commits_from_base": 2}:
        raise RuntimeError(f"Native review protocol mismatch: {summary}")
    return summary


def probe(codex, root, provider, native_review=False):
    repo, worker = create_fixture(root)
    codex_data = root / "codex data"
    codex_data.mkdir()
    config = (
        'model = "dw-fixture"\nmodel_provider = "dw_fixture"\n'
        '[model_providers.dw_fixture]\nname = "Disposable loopback fixture"\n'
        f'base_url = "http://127.0.0.1:{provider.server_port}/v1"\nwire_api = "responses"\n'
        'requires_openai_auth = false\nrequest_max_retries = 0\nstream_max_retries = 0\n'
        + "".join(f"\n[projects.{json.dumps(str(path), ensure_ascii=False)}]\n"
                  'trust_level = "trusted"\n' for path in (repo, worker))
    )
    (codex_data / "config.toml").write_text(config, encoding="utf-8")
    # Give this subprocess its own Codex configuration and thread store.
    env = dict(os.environ, CODEX_HOME=str(codex_data))
    env["NO_PROXY"] = ",".join(filter(None, [env.get("NO_PROXY"), "127.0.0.1"]))
    observed = []
    with AppServer(codex, repo, observed.append, env=env) as server:
        skills = server.call("skills/list", {"cwds": [str(repo), str(worker)], "forceReload": True})
        hooks = server.call("hooks/list", {"cwds": [str(repo), str(worker)]})
        thread = server.call("thread/start", {"cwd": str(worker), "ephemeral": False,
                                                "sandbox": "read-only", "approvalPolicy": "never"})
        worker_thread_id = thread["thread"]["id"]
        summary = {
            "cli": subprocess.check_output([codex, "--version"], encoding="utf-8", timeout=10).strip(),
            "project_skill": [any(s["name"] == "dw-probe" and s["enabled"] for s in row["skills"])
                              for row in skills["data"]],
            "project_hook": [[{"event": h["eventName"], "trust": h["trustStatus"]}
                              for h in row["hooks"] if h.get("command") == "echo DW_PROBE"]
                             for row in hooks["data"]],
            "thread_cwd_is_worker": Path(thread["thread"]["cwd"]).resolve() == worker.resolve(),
            "worker_agents_loaded": any(Path(path).resolve() == (worker / "AGENTS.md").resolve()
                                        for path in thread.get("instructionSources", [])),
            "windows_sandbox_readiness": (server.call("windowsSandbox/readiness", {})
                                           if os.name == "nt" else None),
            "sandbox": {mode: sandbox_check(server, worker, mode)
                        for mode in ("readOnly", "workspaceWrite")},
            "loopback_turn": event_check(server, worker_thread_id, observed),
        }
    with AppServer(codex, repo, env=env) as server:
        read = server.call("thread/read", {"threadId": worker_thread_id, "includeTurns": False})
        history = server.call("thread/turns/list", {"threadId": worker_thread_id, "limit": 1, "itemsView": "full"})
        resumed = server.call("thread/resume", {"threadId": worker_thread_id, "excludeTurns": True})
        summary["resume_from_new_server"] = {
            "read_only_lookup": read["thread"]["id"] == worker_thread_id,
            "same_thread": resumed["thread"]["id"] == worker_thread_id,
            "same_worktree": Path(resumed["thread"]["cwd"]).resolve() == worker.resolve(),
            "latest_turn_status": history["data"][0]["status"] if history["data"] else None,
        }
    if native_review:
        summary["native_review"] = native_probe(codex, worker, env, provider)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-review", action="store_true")
    args = parser.parse_args()
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("codex executable not found on PATH")
    temp = Path(tempfile.gettempdir()).resolve()
    with tempfile.TemporaryDirectory(prefix="director-codex-probe-", dir=temp) as disposable:
        root = Path(disposable).resolve()
        if root.parent != temp or not root.name.startswith("director-codex-probe-"):
            raise RuntimeError("Unexpected temporary fixture location")
        with ThreadingHTTPServer(("127.0.0.1", 0), FixtureProvider) as provider:
            threading.Thread(target=provider.serve_forever, daemon=True).start()
            try:
                result = probe(codex, root, provider, args.native_review)
                result["loopback_turn"]["available_shell_tools"] = getattr(provider, "shell_tools", [])
                tool_results = getattr(provider, "fixture_tool_results", [])
                result["loopback_turn"]["tool_returned"] = bool(tool_results)
                result["loopback_turn"]["tool_policy_blocked"] = any("blocked by policy" in str(output)
                                                                     for output in tool_results)
                print(json.dumps(result, ensure_ascii=False, indent=2))
            finally:
                provider.shutdown()


if __name__ == "__main__":
    main()
