"""Project identity and local state shared by cdx commands."""

from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
POINTER = "director-work-cdx.json"
ORDER_ID = re.compile(r"WO-[0-9]+", re.ASCII)
THREAD_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.ASCII)
SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)


class Refused(RuntimeError):
    pass


def git(repo, *args, raw=False):
    proc = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *args],
                          capture_output=True, timeout=90)
    if proc.returncode:
        raise Refused(proc.stderr.decode("utf-8", errors="replace").strip() or f"git {args[0]} exited {proc.returncode}")
    return proc.stdout if raw else proc.stdout.decode("utf-8", errors="replace").rstrip("\r\n")


def checkout(path):
    return Path(git(Path(path).resolve(), "rev-parse", "--show-toplevel")).resolve()


def common_dir(path):
    return Path(git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()


def primary_checkout(path):
    first = git(path, "worktree", "list", "--porcelain", "-z").split("\0", 1)[0]
    if not first.startswith("worktree "):
        raise Refused("Git did not report a primary worktree")
    return Path(first[len("worktree "):]).resolve()


def within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def read_json(path):
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise Refused(f"Expected a JSON object: {path}")
    return value


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".cdx-", delete=False) as handle:
        temp = Path(handle.name)
        try:
            handle.write(data)
        except BaseException:
            handle.close()
            temp.unlink()
            raise
    try:
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


@contextmanager
def lock(path):
    try:
        path.mkdir()
    except FileExistsError as error:
        raise Refused(f"Operation in progress or interrupted. Inspect before removing lock: {path}") from error
    try:
        yield
    finally:
        path.rmdir()


def stamp():
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")


def load_project(repo):
    root = checkout(repo)
    common = common_dir(root)
    pointer = read_json(common / POINTER)
    state = Path(pointer["state"]).resolve(strict=True)
    project = read_json(state / "PROJECT.json")
    if (pointer.get("schema") != 1 or project.get("schema") != 1 or
            Path(project["git_common_dir"]).resolve() != common):
        raise Refused("cdx project identity does not match the Git common directory")
    return root, state, project


def state_path(state, *parts):
    path = state.joinpath(*parts)
    if path != path.resolve() or not within(path, state):
        raise Refused(f"Path escapes or redirects within cdx state: {path}")
    return path


def report_error(error):
    import sys
    print(f"cdx: {error}", file=sys.stderr)
    return 2
