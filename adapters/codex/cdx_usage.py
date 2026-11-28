"""Adapt Codex JSONL event fields to the common usage accounting."""

import json

from runtime import base_common

EXEC_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
RPC_FIELDS = ("inputTokens", "cachedInputTokens", "outputTokens", "reasoningOutputTokens", "totalTokens")


def usage_report(path, kind):
    common = base_common()
    invalid = []
    turns = 0
    totals = dict.fromkeys(EXEC_FIELDS, 0)
    observed = set()
    threads = {}
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("Codex 事件需要 JSON 物件")
            if kind == "exec" and event.get("type") == "turn.completed":
                turns += 1
                usage = event.get("usage")
                if usage is None:
                    invalid.append(("usage", "missing object"))
                if isinstance(usage, dict):
                    observed.update(field for field in EXEC_FIELDS if usage.get(field) is not None)
                for field, value in zip(EXEC_FIELDS, common.usage_numbers(usage, EXEC_FIELDS, "usage.", invalid)):
                    totals[field] += value
            elif kind == "app-server" and event.get("method") == "thread/tokenUsage/updated":
                data = event.get("params")
                if not isinstance(data, dict) or not isinstance(data.get("threadId"), str):
                    raise ValueError("Codex 用量事件缺少對話 ID")
                usage = data.get("tokenUsage")
                if not isinstance(usage, dict):
                    invalid.append(("tokenUsage", "missing or invalid object"))
                    usage = {}
                reported = {stage: dict(zip(RPC_FIELDS, common.usage_numbers(
                    usage.get(stage), RPC_FIELDS, stage + ".", invalid))) for stage in ("total", "last")}
                thread = threads.setdefault(data["threadId"], {"usage_events": 0})
                thread.update(reported)
                thread["usage_events"] += 1
                thread["context_window"] = common.usage_number(
                    usage.get("modelContextWindow"), "modelContextWindow", invalid) or None
    facts = common.usage_partial(invalid)
    facts["status"] = "partial" if invalid else ("observed" if turns or threads else "unknown")
    if kind == "exec":
        return dict(facts, source="codex-exec-jsonl", completed_turns=turns,
                    total={field: totals[field] if field in observed else None for field in EXEC_FIELDS} if turns else None)
    return dict(facts, source="codex-app-server", threads=threads)
