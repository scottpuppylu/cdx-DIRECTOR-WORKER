"""Attach a verified DW handoff to a Codex Desktop worktree."""

import hashlib
from pathlib import Path
import shutil

from cdx_rpc import AppServer
from cdx_setup import enable_hooks, path_at
from runtime import (SHA, THREAD_ID, Refused, base_common, checkout, git, primary, require, specification, tool)


def verify_chat(worktree, thread, executable):
    binary = executable or shutil.which("codex")
    if not binary:
        raise Refused("找不到 Codex CLI，無法核對對話")
    with AppServer(binary, worktree) as server:
        chat = server.call("thread/read", {"threadId": thread, "includeTurns": False}).get("thread")
    if not isinstance(chat, dict) or chat.get("id") != thread or not isinstance(chat.get("cwd"), str):
        raise Refused("Codex 沒有確認指定的對話")
    if Path(chat["cwd"]).resolve() != worktree or chat.get("status", {}).get("type") not in ("idle", "notLoaded"):
        raise Refused("請等對話閒置，並確認它已在目標工作樹")


def attach(repo, director, destination, candidate, thread=None, executable=None):
    worktree = checkout(destination)
    if Path(destination).resolve() != worktree or worktree == repo or primary(worktree) != repo:
        raise Refused("選擇同一專案的隔離工作樹")
    if thread is not None and not THREAD_ID.fullmatch(thread):
        raise Refused("需要有效的 Desktop 對話 UUID")
    if not SHA.fullmatch(candidate) or git(worktree, "rev-parse", "HEAD") != candidate:
        raise Refused("工作樹需要在已確認的完整候選 SHA")
    if git(worktree, "status", "--porcelain", "--untracked-files=all"):
        raise Refused("工作樹有尚未核對的修改")
    specification(director)
    manifest = path_at(director, "HANDOFF_MANIFEST.md")
    before = manifest.read_bytes()
    require(tool("handoff", "verify", "--director", director, "--repo", repo),
            "交接清單", "HANDOFF_VERIFY: PASS")
    if thread:
        verify_chat(worktree, thread, executable)
    if (manifest.read_bytes() != before or git(worktree, "rev-parse", "HEAD") != candidate
            or git(worktree, "status", "--porcelain", "--untracked-files=all")):
        raise Refused("驗證時交接清單或候選已變更")
    enable_hooks(worktree, director)
    result = {"checkout": str(worktree), "candidate": candidate, "thread": thread,
              "manifest_sha256": hashlib.sha256(before).hexdigest(), "index": str(director / "INDEX.md")}
    destination = path_at(director, "codex-desktop", hashlib.sha256(str(worktree).encode()).hexdigest() + ".json")
    base_common().write_json_atomic(destination, result)
    return result
