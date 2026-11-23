"""Record selected Codex App Server and Hook events in the upstream hash-chain format."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_log
from cdx_common import report_error


def number(value):
    return value if type(value) is int and value >= 0 else None


def usage_counts(data):
    return {name: number(data.get(name)) for name in
            ("inputTokens", "cachedInputTokens", "outputTokens", "reasoningOutputTokens", "totalTokens")}


def app_fields(message):
    method, params = message.get("method"), message.get("params", {})
    thread = params.get("threadId")
    if not isinstance(thread, str):
        return None
    result = {"source": "codex-app-server", "session_id": thread, "turn_id": params.get("turnId")}
    if method == "thread/tokenUsage/updated":
        usage = params.get("tokenUsage", {})
        return dict(result, kind="usage", usage=usage_counts(usage.get("total", {})),
                    last=usage_counts(usage.get("last", {})), context_window=number(usage.get("modelContextWindow")))
    if method in ("turn/started", "turn/completed"):
        turn = params.get("turn", {})
        return dict(result, kind=method, turn_id=turn.get("id"), status=turn.get("status"))
    if isinstance(method, str) and method.endswith("/requestApproval"):
        return dict(result, kind="approval-request", tool=method, tool_use_id=params.get("itemId"),
                    result={"status": "unverified"})
    if method not in ("item/started", "item/completed"):
        return None
    item = params.get("item", {})
    types = {"commandExecution": "Bash", "fileChange": "apply_patch", "dynamicToolCall": "dynamic",
             "mcpToolCall": "MCP", "contextCompaction": "compact", "collabToolCall": "collaboration"}
    item_type = item.get("type")
    if not isinstance(item_type, str) or item_type not in types:
        return None
    output = {"status": "unverified"}
    status, code = item.get("status"), item.get("exitCode")
    if method == "item/started":
        output["status"] = "running"
    elif item_type == "commandExecution" and type(code) is int and status in ("completed", "failed"):
        output = {"status": "ok" if code == 0 and status == "completed" else "error", "exit_code": code}
    elif status in ("failed", "declined", "rejected"):
        output["status"] = "error"
    argument = item.get("command")
    return dict(result, kind="result" if method == "item/completed" else "call", tool=types[item_type],
                tool_use_id=item.get("id"), input=audit_log.summary({"command": argument} if argument else {}),
                result=output, native_status=status)


def append_app(path, event):
    fields = app_fields(event)
    if fields:
        audit_log.append_entry(path, fields)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("log", type=Path)
    build = sub.add_parser("build", help="project App Server JSONL events into a new audit file")
    build.add_argument("events", type=Path)
    build.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            entries, parse_problem = audit_log.load(args.log)
            problem = parse_problem or audit_log.chain_problem(entries)
            if problem:
                raise RuntimeError(problem)
            print(f"CDX_AUDIT OK entries={len(entries)}")
            return 0
        args.out.touch(exist_ok=False)
        count = 0
        with args.events.open(encoding="utf-8-sig") as source:
            for line in source:
                if line.strip():
                    projected = app_fields(json.loads(line))
                    if projected:
                        audit_log.append_entry(args.out, projected)
                        count += 1
        print(f"CDX_AUDIT imported={count} out={args.out}")
        return 0
    except (OSError, ValueError, RuntimeError, TypeError, audit_log.CannotRun) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
