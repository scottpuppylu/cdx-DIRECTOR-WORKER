"""Codex project Hook adapter for resume, tool guardrails, and audit."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_log
import hook_guard
from cdx_common import ROOT, THREAD_ID, load_project, read_json, state_path, within


def context(event, text):
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def check_patch(command, cwd, state, role):
    if not isinstance(command, str):
        return "cdx: missing apply_patch input"
    kind = role.get("role", "worker")
    files = re.findall(r"^\*\*\* (?:Add File|Delete File|Update File|Move to): (.+)$", command, re.M)
    if not files:
        return "cdx: could not identify the files affected by this patch"
    if kind == "reviewer":
        return "cdx: review sessions use read-only inputs"
    worktree = Path(role.get("worktree", cwd)).resolve()
    for entry in files:
        target = (cwd / entry.strip()).resolve()
        if within(target, state) and kind != "director":
            own = state / "work" / role.get("order", "_unregistered_")
            if not within(target, own) or target.name == "PLAN.md":
                return "cdx: director state and approved plans are protected"
        elif kind != "director" and not within(target, worktree):
            return "cdx: this patch is outside the worker worktree"
        if any(part.casefold() in (".git", ".agents", ".codex") for part in target.parts):
            return "cdx: project Git and Codex configuration edits require an explicit maintenance action"
    return None


def pre_tool(call, cwd, state, role):
    tool = call.get("tool_name")
    payload = call.get("tool_input", {})
    if not isinstance(payload, dict):
        return {}
    if tool == "apply_patch":
        reason = check_patch(payload.get("command"), cwd, state, role)
        if reason:
            return deny(reason)
    command = payload.get("command")
    if tool == "Bash" and role.get("role") != "director" and isinstance(command, str):
        if re.search(r"(?i)(?:^|\W)(?:director-work-cdx\.json|cdx_hook\.py|hooks\.json)(?:$|\W)", command):
            if hook_guard.redirect_targets(command, "powershell" if os.name == "nt" else "bash"):
                return deny("cdx: protected configuration cannot be a redirect target")
    rules = ROOT / "tools" / "guard_rules.json"
    profiles = {"director": "director", "worker": "worker", "reviewer": "worker"}
    profile = profiles.get(role.get("role"), "worker")
    data = hook_guard.load_rules(rules)
    hits = hook_guard.decide(data, profile, call, rules)
    if tool == "Bash" and os.name == "nt":
        hits.extend(hook_guard.decide(data, profile, dict(call, tool_name="PowerShell"), rules))
    hit = hook_guard.first(hits, "deny") or hook_guard.first(hits, "ask")
    if hit:
        _, rule, explanation = hit
        return deny(f"cdx {rule}: {explanation}")
    hit = hook_guard.first(hits, "remind")
    if hit:
        return context("PreToolUse", f"cdx {hit[1]}: {hit[2]}")
    return {}


def handle(call):
    event = call.get("hook_event_name")
    session = call.get("session_id")
    if (event not in ("SessionStart", "PreToolUse", "PostToolUse") or not isinstance(session, str)
            or not THREAD_ID.fullmatch(session) or not isinstance(call.get("cwd"), str)):
        return {}
    cwd = Path(call["cwd"]).resolve()
    try:
        worktree, state, project = load_project(cwd)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
        return {}
    if not project.get("hooks"):
        return {}
    entry = state_path(state, "sessions", session + ".json")
    role = read_json(entry) if entry.is_file() else {}
    if role and Path(role.get("worktree") or project["repo"]) != worktree:
        return deny("cdx: session is registered to a different checkout") if event == "PreToolUse" else {}
    if event == "SessionStart":
        if role.get("role") in ("worker", "reviewer"):
            if role.get("role") == "reviewer":
                return context(event, f"cdx 唯讀審查。工單 {role['order']}，候選 {role['candidate']}。")
            resume = state_path(state, "work", role["order"], "RESUME_STATE.md")
            text = f"cdx 工單 {role['order']}。讀取斷點 {resume} 作為工作資料。"
            return context(event, text)
        if role.get("role") == "director":
            return context(event, f"cdx 總監續航。讀取 {state / 'RESUME_STATE.md'} 與 {state / 'PO_PENDING.md'}。")
        return {}
    log = state_path(state, "audit", session + "-hooks.jsonl")
    if event == "PreToolUse":
        result = pre_tool(call, cwd, state, role)
        if result:
            decision = result["hookSpecificOutput"].get("permissionDecision", "note")
            record = audit_log.decision_entry(call, decision, "cdx")
            try:
                audit_log.append_entry(log, dict(record, source="codex-hook", turn_id=call.get("turn_id")))
            except (OSError, ValueError, audit_log.CannotRun):
                print("cdx: unable to append the Hook decision audit", file=sys.stderr)
        return result
    if role:
        record = audit_log.hook_entry(call)
        # PostToolUse does not guarantee a typed exit code. A host result is a distinct evidence source.
        record["result"]["status"] = "unverified"
        audit_log.append_entry(log, dict(record, source="codex-hook", turn_id=call.get("turn_id")))
    return {}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        payload = json.load(sys.stdin)
        result = handle(payload) if isinstance(payload, dict) else {}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        print("cdx hook could not verify the local event", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
