"""Paths and result checks for the Codex adapter."""

import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TOOLS = ROOT / "tools"
THREAD_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
SHA = re.compile(r"[0-9a-f]{40}")


class Refused(RuntimeError):
    pass


def run(*args, cwd=None, env=None, timeout=45):
    return subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, timeout=timeout,
                          capture_output=True, encoding="utf-8", errors="replace")


def terminal(result, marker=None):
    code = getattr(result, "returncode", None)
    if type(code) is not int or code != 0:
        return False
    if marker is None:
        return True
    output = getattr(result, "stdout", None)
    if not isinstance(output, str) or not output.splitlines():
        return False
    line = output.splitlines()[-1]
    return line == marker or line.startswith(marker + " ")


def require(result, label, marker=None):
    if not terminal(result, marker):
        detail = (getattr(result, "stderr", "") or getattr(result, "stdout", "") or "").strip()
        raise Refused(f"{label}: 未取得通過結果。{detail[-1200:]}")
    return result.stdout.strip()


def git(repo, *args, timeout=45):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    return require(run("git", "--no-replace-objects", "-C", repo, *args, env=env, timeout=timeout), "Git")


def checkout(path, timeout=45):
    return Path(git(path, "rev-parse", "--show-toplevel", timeout=timeout)).resolve()


def primary(path, timeout=45):
    listing = git(path, "worktree", "list", "--porcelain", timeout=timeout).splitlines()
    first = listing[0] if listing else ""
    if not first.startswith("worktree "):
        raise Refused("找不到主要工作目錄")
    return Path(first[9:]).resolve()


def contained(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def tool(name, *args, cwd=None, timeout=45):
    return run(sys.executable, "-I", "-B", "-X", "utf8", TOOLS / (name + ".py"), *args,
               cwd=cwd, timeout=timeout)


def specification(director, timeout=45):
    return require(tool("spec_gate", "check", "--brief", director / "BRIEF.md", timeout=timeout),
                   "規格關卡", "SPEC_GATE: PASS")


def base_common():
    sys.path.insert(0, str(TOOLS))
    try:
        import _common
        return _common
    finally:
        sys.path.pop(0)
