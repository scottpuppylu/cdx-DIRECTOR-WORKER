"""Summarize cdx App Server usage or a Codex CLI JSONL run."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdx_audit import verified_entries
from cdx_common import report_error


def summarize_app(path):
    threads = {}
    for item in verified_entries(path):
        if item.get("kind") != "usage":
            continue
        key = item["session_id"]
        current = threads.setdefault(key, {"usage_events": 0, "max_last_input_tokens": None})
        current["usage_events"] += 1
        current["total"] = item["usage"]
        current["context_window"] = item.get("context_window")
        tokens = item["last"].get("inputTokens")
        if type(tokens) is int:
            current["max_last_input_tokens"] = max(current["max_last_input_tokens"] or 0, tokens)
    return {"source": "codex-app-server", "threads": threads, "status": "observed" if threads else "unknown"}


def summarize_cli(path):
    totals = {field: 0 for field in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")}
    missing = set()
    turns = 0
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("type") != "turn.completed":
                continue
            turns += 1
            data = event.get("usage", {})
            for field in totals:
                value = data.get(field)
                if type(value) is int and value >= 0:
                    totals[field] += value
                else:
                    missing.add(field)
    return {"source": "codex-exec-jsonl", "completed_turns": turns,
            "total": {key: value if turns and key not in missing else None for key, value in totals.items()}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--format", choices=("app-server", "exec"), default="app-server")
    args = parser.parse_args(argv)
    try:
        summarize = summarize_app if args.format == "app-server" else summarize_cli
        print(json.dumps(summarize(args.file), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
