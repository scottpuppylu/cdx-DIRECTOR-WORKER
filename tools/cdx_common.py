"""Project identity and local state shared by cdx commands."""

from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
POINTER = "director-work-cdx.json"
ORDER_ID = re.compile(r"WO-[0-9]+", re.ASCII)
THREAD_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.ASCII)
SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+-cdx\.[0-9]+", re.ASCII)
STATE_SCHEMA = 2
GIT_LOCATION = {"GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_QUARANTINE_PATH",
                "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"}


class Refused(RuntimeError):
    pass


def git_environment():
    return {key: value for key, value in os.environ.items() if key.upper() not in GIT_LOCATION and
            not key.upper().startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}


def git(repo, *args, raw=False):
    proc = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *args],
                          capture_output=True, timeout=90, env=git_environment())
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
            handle.flush()
            os.fsync(handle.fileno())
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
    # Keep the OS lock file in place so contenders always open the same inode.
    # The separate suffix also preserves directories left by older runtimes.
    path = state_path(path.parent, path.name + ".guard")
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            acquire()
        except OSError as error:
            raise Refused(f"Operation is locked by another process: {path}") from error
        yield


def executor():
    return {"kind": "local-host", "platform": platform.system(), "machine": platform.node(),
            "python": platform.python_version(), "filesystem_isolation": "unverified"}


def check_environment():
    # Toolchain discovery and OS basics. Project secrets and arbitrary session variables are excluded.
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TMPDIR", "TEMP", "TMP",
               "LANG", "LC_ALL", "LC_CTYPE", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


@contextmanager
def detached_checkout(repo, commit):
    with tempfile.TemporaryDirectory(prefix="cdxdw-checkout-") as folder:
        root = Path(folder).resolve()
        worker = root / "candidate"
        git(repo, "-c", "core.hooksPath=" + str(root / "no-hooks"), "worktree", "add",
            "--detach", "--", str(worker), commit)
        try:
            yield worker
        finally:
            git(repo, "worktree", "remove", "--force", "--", str(worker))


def stamp():
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")


def executing_version():
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def load_project(repo, *, diagnostic=False):
    root = checkout(repo)
    common = common_dir(root)
    pointer = read_json(state_path(common, POINTER))
    state = Path(pointer["state"])
    if not state.is_absolute() or state != state.resolve(strict=True):
        raise Refused("cdxdw state path is not a canonical local directory")
    project = read_json(state_path(state, "PROJECT.json"))
    main = Path(project["repo"])
    version = project.get("version", "")
    schema = project.get("schema")
    if (schema not in (1, STATE_SCHEMA) or pointer.get("schema") != schema or
            Path(project["git_common_dir"]) != common or main != primary_checkout(root) or
            within(state, main) or within(main, state) or within(state, common) or within(common, state) or
            not VERSION.fullmatch(version) or Path(project["kit"]) != state_path(state, "runtime", version)):
        raise Refused("cdx project identity does not match the Git common directory")
    if not diagnostic and (schema != STATE_SCHEMA or executing_version() != version):
        raise Refused(f"Active runtime is {version}. Use {state / 'cdxdw.py'} after setup has completed.")
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
