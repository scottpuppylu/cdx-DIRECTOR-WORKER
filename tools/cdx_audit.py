"""Record selected Codex App Server and Hook events in the upstream hash-chain format."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_log
from cdx_common import Refused, THREAD_ID, report_error
from cdx_gates import invoke, tail


def number(value):
    return value if type(value) is int and value >= 0 else None


def usage_counts(data):
    return {name: number(data.get(name)) for name in
            ("inputTokens", "cachedInputTokens", "outputTokens", "reasoningOutputTokens", "totalTokens")}


def object_field(data, key):
    item = data.get(key)
    return item if isinstance(item, dict) else {}


def app_fields(message):
    if not isinstance(message, dict):
        raise ValueError("App Server event is not an object")
    method, params = message.get("method"), object_field(message, "params")
    thread = params.get("threadId")
    if not isinstance(thread, str):
        return None
    result = {"source": "codex-app-server", "session_id": thread, "turn_id": params.get("turnId")}
    if method == "thread/tokenUsage/updated":
        usage = object_field(params, "tokenUsage")
        if not usage:
            return None
        return dict(result, kind="usage", usage=usage_counts(object_field(usage, "total")),
                    last=usage_counts(object_field(usage, "last")), context_window=number(usage.get("modelContextWindow")))
    if method in ("turn/started", "turn/completed"):
        turn = object_field(params, "turn")
        return dict(result, kind=method, turn_id=turn.get("id"), status=turn.get("status"))
    if isinstance(method, str) and method.endswith("/requestApproval"):
        return dict(result, kind="approval-request", tool=method, tool_use_id=params.get("itemId"),
                    result={"status": "unverified"})
    if method not in ("item/started", "item/completed"):
        return None
    item = object_field(params, "item")
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
    if not isinstance(item.get("id"), str) or not isinstance(params.get("turnId"), str):
        return None
    return dict(result, kind="result" if method == "item/completed" else "call", tool=types[item_type],
                tool_use_id=item.get("id"), input=audit_log.summary({"command": argument} if argument else {}),
                result=output, native_status=status)


def append_app(path, event):
    fields = app_fields(event)
    if fields:
        audit_log.append_entry(path, fields)


def verified_entries(path):
    previous = audit_log.GENESIS
    with path.open(encoding="utf-8", newline="") as source:
        for sequence, line in enumerate(source, 1):
            if not line.endswith("\n"):
                raise ValueError(f"line={sequence}: incomplete audit record")
            entry = json.loads(line)
            if not isinstance(entry, dict) or type(entry.get("seq")) is not int or entry["seq"] != sequence:
                raise ValueError(f"line={sequence}: unexpected sequence")
            if entry.get("prev") != previous or entry.get("hash") != audit_log.digest(entry):
                raise ValueError(f"seq={sequence}: hash does not match the line or previous entry")
            previous = entry["hash"]
            yield entry


def build_log(events, output):
    if output.exists():
        raise FileExistsError(output)
    digest = hashlib.sha256()
    previous, seq, lines, byte_count = audit_log.GENESIS, 0, 0, 0
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def write(handle, fields):
        nonlocal seq, previous
        seq += 1
        entry = dict(fields, seq=seq, prev=previous, ts=now)
        previous = entry["hash"] = audit_log.digest(entry)
        handle.write(audit_log.canonical(entry).encode("utf-8") + b"\n")

    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".cdx-audit-", delete=False) as stage:
        staging = Path(stage.name)
        try:
            with events.open("rb") as source:
                for raw in source:
                    lines += 1
                    byte_count += len(raw)
                    digest.update(raw)
                    if raw.strip():
                        projected = app_fields(json.loads(raw.decode("utf-8-sig" if lines == 1 else "utf-8")))
                        if projected:
                            write(stage, projected)
            imported = seq
            write(stage, {"kind": "rebuild", "source": "codex-app-server-jsonl",
                          "sha256": digest.hexdigest(), "lines": lines, "bytes": byte_count, "imported": imported})
            stage.flush()
            os.fsync(stage.fileno())
            stage.close()
            # Commit the validated file in one step. Never replace an output another process just created.
            os.link(staging, output)
        finally:
            stage.close()
            staging.unlink()
    return imported


def audit_status(path):
    started = set()
    results = {}
    for entry in verified_entries(path):
        identity = tuple(entry.get(k) for k in ("session_id", "turn_id", "tool_use_id"))
        if entry.get("source") != "codex-app-server" or not all(isinstance(key, str) and key for key in identity):
            continue
        if entry.get("kind") == "call":
            started.add(identity)
        elif entry.get("kind") == "result":
            kind = object_field(entry, "result").get("status")
            if kind not in ("ok", "error"):
                kind = "unverified"
            if identity in results and results[identity] != kind:
                kind = "unverified"
            results[identity] = kind
    counts = Counter(results.values())
    return {"observed_calls": len(started), "without_terminal": len(started.difference(results)),
            "terminal_without_start": len(results.keys() - started), "ok": counts["ok"],
            "error": counts["error"], "unverified": counts["unverified"]}


def check_report(report, log, session, anchor, *, strict=False):
    if not THREAD_ID.fullmatch(session):
        raise Refused("Supply the worker's complete session UUID")
    with tempfile.TemporaryDirectory(prefix="cdxdw-audit-proof-") as folder:
        root = Path(folder)
        raw = log.read_bytes()
        copy = root / "audit.jsonl"
        copy.write_bytes(raw)
        entries = list(verified_entries(copy))
        text = anchor.read_text(encoding="utf-8-sig")
        problems, matches = audit_log.anchor_problems(list(enumerate(entries, 1)), text, log)
        head = entries[-1] if entries else {"seq": 0, "hash": audit_log.GENESIS}
        pinned = any(audit_log.same_file(name, log) and int(sequence) == head["seq"] and digest == head["hash"]
                     for name, sequence, digest in audit_log.HEAD_LINE.findall(text))
        if problems or not matches or not pinned:
            raise Refused("Outside anchor must verify the complete current audit prefix: " + ", ".join(problems))
        report_bytes = report.read_bytes()
        sessions = re.findall(r"^[ \t]*SESSION_ID[ \t]*:[ \t]*(\S+)[ \t]*\r?$",
                              report_bytes.decode("utf-8-sig"), re.M)
        if sessions != [session]:
            raise Refused("Task report must name the same observed worker session")
        report_copy = root / "report.md"
        report_copy.write_bytes(report_bytes)
        result = invoke("report_vs_audit.py", ["--report", str(report_copy), "--log", str(copy), "--session", session])
        output = result.stdout.decode("utf-8", errors="replace")
    ledger = re.findall(r"^REPORT_VS_AUDIT: PASS claims=(\d+) ok=(\d+).*?\bunverified=(\d+)", output, re.M)
    complete = (len(ledger) == 1 and int(ledger[0][0]) > 0 and ledger[0][0] == ledger[0][1] and
                ledger[0][2] == "0")
    return {"outcome": "PASS" if result.returncode == 0 and (complete or not strict) else "FAIL",
            "claims_verified": complete, "observation": tail(result), "session": session, "audit_head": head["hash"],
            "audit_sha256": hashlib.sha256(raw).hexdigest(), "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "anchor_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("log", type=Path)
    status = sub.add_parser("status", help="summarize matched calls and known terminal outcomes")
    status.add_argument("log", type=Path)
    build = sub.add_parser("build", help="project App Server JSONL events into a new audit file")
    build.add_argument("events", type=Path)
    build.add_argument("--out", type=Path, required=True)
    compare = sub.add_parser("report", help="compare claims against a hash-chained, externally anchored log")
    for name in ("report", "log", "anchor"):
        compare.add_argument("--" + name, type=Path, required=True)
    compare.add_argument("--session", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            print(f"CDX_AUDIT OK entries={sum(1 for _ in verified_entries(args.log))}")
            return 0
        if args.command == "status":
            print(json.dumps(audit_status(args.log), indent=2))
            return 0
        if args.command == "report":
            result = check_report(args.report, args.log, args.session, args.anchor, strict=True)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["outcome"] == "PASS" else 2
        count = build_log(args.events, args.out)
        print(f"CDX_AUDIT imported={count} out={args.out}")
        return 0
    except (OSError, ValueError, RuntimeError, TypeError, audit_log.CannotRun) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
