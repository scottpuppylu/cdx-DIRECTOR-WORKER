"""Translate Codex tool events to the shared specification gate."""

import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime import Refused, checkout, contained, primary, specification

PATCH_PATH = re.compile(r"^\*\*\* (?:Add File|Delete File|Update File|Move to): (.+)$", re.M)
READ_COMMANDS = {"ls", "pwd", "rg", "grep", "cat", "get-location", "get-content",
                 "get-item", "get-childitem", "select-string", "test-path"}
READ_TOOLS = {"Read", "Glob", "Grep", "WebSearch", "WebFetch", "update_plan",
              "request_user_input", "request_user_input_async"}
PROTECTED = {".git", ".codex", ".github", "agents.md", ".gitignore"}
STATE_PROTECTED = {"adapters", "tools", "brief-history", "director_work.json"}
OPERATOR_ONLY = re.compile(
    r"(?i)\b(?:push|publish|deploy|release|clean|stash|remove-item|rm|rmdir|del)\b|"
    r"\b(?:spec_gate\.py|gate_check\.py)\b.*(?:\bapprove\b|--snapshot)|"
    r"\bgit\s+(?:reset|tag|config)\b|(?:--force|--hard)\b"
)


def denial(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def command_words(command):
    if not isinstance(command, str) or re.search(r"[\r\n;&|<>%`$]", command):
        return []
    try:
        return shlex.split(command)
    except ValueError:
        return []


def readonly(words):
    if not words or any(arg.startswith(("--output", "--ext-diff", "--textconv", "--paginate", "--pre",
                                        "--hostname", "--upload-pack")) for arg in words[1:]):
        return False
    head = words[0].casefold()
    if head in READ_COMMANDS:
        return True
    if head != "git" or len(words) < 2:
        return False
    if words[1] == "worktree":
        return words[2:3] == ["list"]
    if words[1] == "branch":
        return words[2:] in ([], ["--list"], ["--show-current"])
    return words[1] in {"status", "log", "show", "rev-parse", "diff", "ls-files", "ls-tree"}


def check_tool(call, director, work):
    name = call.get("tool_name")
    data = call.get("tool_input")
    if name in READ_TOOLS:
        return {}
    if not isinstance(data, dict):
        return denial("工具內容無法讀取，先停下這個動作。")
    if name in ("apply_patch", "Edit", "Write"):
        patch = data.get("command")
        paths = PATCH_PATH.findall(patch) if isinstance(patch, str) else []
        if not paths:
            return denial("無法確認修改的檔案。")
        state_only = True
        for path in paths:
            target = (work / path).resolve()
            if contained(target, director):
                parts = {part.casefold() for part in target.relative_to(director).parts}
                if parts & STATE_PROTECTED or target.suffix.casefold() not in (".md", ".txt", ".json", ".jsonl"):
                    return denial("閘門程式、快照及專案設定由操作者維護。")
            elif (not contained(target, work) or
                  {part.casefold() for part in target.relative_to(work).parts} & PROTECTED):
                return denial("修改超出本工作樹，或觸及受管理的設定。")
            else:
                state_only = False
        if state_only:
            return {}
    elif name == "Bash":
        command = data.get("command")
        words = command_words(command)
        if readonly(words):
            return {}
        if not words or OPERATOR_ONLY.search(command):
            return denial("請由操作者在終端機完成發布、管理指令或複合命令。")
    elif name not in ("Agent", "spawn_agent", "send_input", "EnterWorktree", "create_worktree"):
        return denial("這個工具的寫入範圍未登記。")
    specification(director, timeout=5)
    return {}


def respond(call, director):
    event = call.get("hook_event_name")
    if event not in ("PreToolUse", "SessionStart", "PostCompact"):
        return {}
    work = checkout(call["cwd"], timeout=2)
    if primary(work, timeout=2) != director.parent or director.name != "DIRECTOR":
        raise Refused("這個 Hook 和目前專案的 DIRECTOR 不相符")
    if event == "PreToolUse":
        return check_tool(call, director, work)
    message = f"讀 {director / 'INDEX.md'}，照它接手，不要重問已確認的需求。"
    if event == "PostCompact":
        return {"systemMessage": message}
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": message}}


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--director", required=True, type=Path)
    args = parser.parse_args()
    event = "PreToolUse"
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise Refused("Hook 輸入須為 JSON 物件")
        event = data.get("hook_event_name", event)
        result = respond(data, args.director.resolve(strict=True))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result = denial(str(error)) if event == "PreToolUse" else {"systemMessage": f"cdxdw: {error}"}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
