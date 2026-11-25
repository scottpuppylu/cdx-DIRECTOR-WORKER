"""Install cdxdw in a Git project using project-level Codex settings."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import re
import shutil
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdx_common import (POINTER, ROOT, STATE_SCHEMA, VERSION, Refused, atomic_write, checkout, common_dir, git, json_bytes,
                        lock, primary_checkout, read_json, report_error, stamp, state_path, within)
from cdx_manifest import checked_files


BEGIN, END = b"<!-- cdx:begin -->", b"<!-- cdx:end -->"
FOLDERS = ("orders", "reviews", "work", "evidence", "audit", "sessions", "brief-history", "order-history")


def initial_files(state, repo, mode, decision_template):
    return {
        state / "DIRECTOR_LOG.md": f"# DIRECTOR_LOG\n\n{stamp()} | CDX_SETUP | {mode}\n",
        state / "DIRECTOR_STATE.md": (f"# DIRECTOR_STATE\n\nPROJECT: {repo}\nMODE: {mode}\n"
                                       "PENDING_METHOD: chat + PO_PENDING.md\n"),
        state / "RESUME_STATE.md": ("PROGRESS: cdxdw initialized\nDOING: confirm project requirements\n"
                                   "NEXT_STEP: read PO_PENDING.md and confirm BRIEF.md\nCOMMS: NONE\n\n"
                                   f"# RESUME_STATE — DIRECTOR\nUPDATED: {stamp()}\n"),
        state / "PO_PENDING.md": "# PO 待決與回覆\n\n## 未結\n\n## 已結\n",
        state / "ACTIVE_WORKSTREAMS.md": "# 工作線\n\n| WO | Branch | Thread | Status |\n|---|---|---|---|\n",
        state / "PENDING_SENDS.md": "# 待送訊息\n",
        state / "MECHANISMS.md": ("# 機制\n\n- `cdxdw.py doctor` 查看專案、Hook 信任、沙箱狀態。\n"
                                  "- `cdxdw.py session status` 對帳工單、Git worktree 和 thread。\n"),
        state / "DECISION_REGISTER.md": decision_template,
    }


def hook_commands(kit):
    entry = str(kit / "tools" / "cdx_hook.py")
    if os.name == "nt" and any(char in entry for char in '"%$`!\r\n'):
        raise Refused("The Windows hook path contains shell metacharacters. Choose another state path.")
    if os.name == "nt":
        command = f'python -I -B -X utf8 "{entry}"'
        return {"command": command, "commandWindows": command}
    return {"command": shlex.join(["python3", "-I", "-B", "-X", "utf8", entry])}


def config_with_hooks(path, kit, enabled=True):
    raw = path.read_bytes() if path.exists() else None
    data = read_json(path) if raw is not None else {"hooks": {}}
    if not enabled and raw is not None and "hooks" not in data:
        return raw
    before = json_bytes(data)
    events = data.setdefault("hooks", {})
    if not isinstance(events, dict):
        raise Refused("Existing .codex/hooks.json has no hooks object")
    commands = hook_commands(kit)
    known = [commands]
    if kit.parent.is_dir():
        known.extend(hook_commands(state_path(kit.parent, path.name)) for path in kit.parent.iterdir()
                     if VERSION.fullmatch(path.name) and path.is_dir() and not path.is_symlink())
    for event, matcher in {"SessionStart": "^(startup|resume|compact)$", "PostCompact": "^(manual|auto)$",
                           "UserPromptSubmit": ".*", "PreToolUse": ".*", "PostToolUse": ".*"}.items():
        label = f"cdx DIRECTOR-WORK {event}"
        item = {"type": "command", "timeout": 8, "statusMessage": label, **commands}
        groups = events.get(event, [])
        if not isinstance(groups, list):
            raise Refused(f"Existing Hook groups are invalid: {event}")
        owned = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise Refused(f"Existing Hook handlers are invalid: {event}")
            owned.extend((group, handler) for handler in group["hooks"]
                         if isinstance(handler, dict) and handler.get("statusMessage") == label)
        if len(owned) > 1:
            raise Refused(f"There are multiple cdx Hook groups: {event}")
        if owned:
            group, handler = owned[0]
            actual = {key: handler[key] for key in ("command", "commandWindows") if key in handler}
            if handler.get("type") != "command" or actual not in known:
                raise Refused(f"Existing cdx Hook command is locally modified: {path} ({event})")
            if enabled:
                handler.update(commands)
            else:
                group["hooks"].remove(handler)
                if not group["hooks"]:
                    groups.remove(group)
        elif enabled:
            events.setdefault(event, []).append({"matcher": matcher, "hooks": [item]})
    updated = json_bytes(data)
    return raw if raw is not None and before == updated else updated


def destination(args):
    repo = checkout(args.repo)
    common = common_dir(repo)
    if primary_checkout(repo) != repo:
        raise Refused("Run setup from the main checkout; linked worktrees share its configuration")
    pointer = state_path(common, POINTER)
    registered = read_json(pointer) if pointer.exists() else None
    previous = Path(registered["state"]).resolve() if registered else None
    state = Path(args.state).resolve() if args.state else previous or repo.with_name(f"DIRECTOR-{repo.name}")
    if previous and previous != state:
        raise Refused(f"Project already uses {previous}; preserve it before changing its location")
    if within(state, repo) or within(repo, state) or within(state, common) or within(common, state):
        raise Refused("State and the project checkout must be separate directories")
    return repo, common, pointer, state


def version_key(version):
    if not VERSION.fullmatch(version):
        raise Refused("Invalid cdxdw runtime version")
    return tuple(map(int, re.findall(r"[0-9]+", version)))


def plan(args, target=None):
    repo, common, pointer, state = target or destination(args)
    owner = state_path(state, "PROJECT.json")
    existing = read_json(owner) if owner.exists() else None
    if (state.exists() and not existing and any(state.iterdir())) or (
            existing and (existing.get("schema") not in (1, STATE_SCHEMA) or Path(existing["git_common_dir"]) != common
                          or Path(existing["repo"]) != repo)):
        raise Refused(f"State belongs to another workflow or project: {state}")

    bundle = dict(checked_files(ROOT))
    version = bundle[ROOT / "VERSION"].decode("utf-8").strip()
    if existing and version_key(version) < version_key(existing["version"]):
        raise Refused(f"Installed runtime {existing['version']} is newer than this kit")
    kit = state_path(state, "runtime", version)
    use_hooks = args.hooks if args.hooks is not None else bool(existing and existing.get("hooks"))
    mode = (existing or {}).get("mode", args.mode)
    manifest = dict((existing or {}).get("managed_skills", {}))
    files = []
    for source, data in bundle.items():
        target = state_path(kit, *source.relative_to(ROOT).parts)
        if target.exists() and target.read_bytes() != data:
            raise Refused(f"Runtime {version} contains changed files: {target}")
        if not target.exists():
            files.append((target, data))

    skill_root = ROOT / "plugin" / "cdx" / "skills"
    for source in sorted(path for path in bundle if path.name == "SKILL.md" and path.parent.parent == skill_root):
        filename = f".agents/skills/{source.parent.name}/SKILL.md"
        target = state_path(repo, *filename.split("/"))
        data = bundle[source]
        if target.exists() and target.read_bytes() != data:
            if hashlib.sha256(target.read_bytes()).hexdigest() != manifest.get(filename):
                raise Refused(f"Existing skill is not managed by cdx or contains local edits: {target}")
        manifest[filename] = hashlib.sha256(data).hexdigest()
        files.append((target, data))

    if args.agents:
        target = state_path(repo, "AGENTS.md")
        current = target.read_bytes() if target.exists() else b""
        if (BEGIN in current) != (END in current):
            raise Refused("Incomplete cdx markers in AGENTS.md")
        if BEGIN not in current:
            section = bundle[ROOT / "templates" / "AGENTS_PROJECT_SECTION.md"]
            files.append((target, current + (b"\n\n" if current else b"") + section))
    if use_hooks or args.hooks is False:
        target = state_path(repo, ".codex", "hooks.json")
        if use_hooks or target.is_file():
            files.append((target, config_with_hooks(target, kit, enabled=use_hooks)))
    if use_hooks:
        # Generated commands point to this machine's runtime. Keep new Hook configs local to Git.
        exclude = state_path(common, "info", "exclude")
        rules = exclude.read_bytes() if exclude.exists() else b""
        pattern = b"/.codex/hooks.json"
        if pattern not in rules.splitlines():
            files.append((exclude, rules + (b"\n" if rules and not rules.endswith(b"\n") else b"")
                          + b"# cdx machine-local Hook config\n" + pattern + b"\n"))

    decision_template = bundle[ROOT / "templates" / "DECISION_REGISTER.md"].decode("utf-8")
    for path, content in initial_files(state, repo, mode, decision_template).items():
        if not state_path(state, path.name).exists():
            files.append((path, content.encode("utf-8")))
    config = state_path(state, "director_work.json")
    if not config.exists():
        data = json.loads(bundle[ROOT / "director_work.example.json"].decode("utf-8-sig"))
        data["mode"] = mode
        files.append((config, json_bytes(data)))
    files.append((state_path(state, "cdxdw.py"), bundle[ROOT / "tools" / "cdx_launcher.py"]))
    metadata = {"schema": STATE_SCHEMA, "git_common_dir": str(common), "repo": str(repo), "kit": str(kit),
                "version": version, "mode": mode, "hooks": use_hooks, "managed_skills": manifest}
    return state, owner, pointer, metadata, files


def backup_legacy(state, repo, pointer, files):
    backup = state_path(state, "migrations", "schema-1")
    if backup.is_dir():
        return
    backup.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=backup.parent, prefix=".cdx-migration-") as folder:
        stage = Path(folder) / "snapshot"
        shutil.copytree(state, stage / "state", symlinks=True,
                        ignore=lambda base, names: {name for name in names if name.endswith(".guard") or
                        (Path(base) == state and name in ("runtime", "migrations"))})
        atomic_write(stage / "git-pointer.json", pointer.read_bytes())
        atomic_write(stage / "candidate-refs.txt", git(repo, "for-each-ref", "--format=%(refname) %(objectname)",
                                                       "refs/cdxdw/", raw=True))
        previous_files = {}
        for path, data in files:
            if within(path, repo) and (not path.is_file() or path.read_bytes() != data):
                relative = path.relative_to(repo)
                previous_files[relative.as_posix()] = path.is_file()
                if path.is_file():
                    atomic_write(stage / "checkout" / relative, path.read_bytes())
        atomic_write(stage / "checkout-paths.json", json_bytes({"previously_existed": previous_files}))
        os.replace(stage, backup)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--state", help="existing or new cdx state path, outside the checkout")
    parser.add_argument("--mode", choices=("general", "beginner"), default="general")
    hooks = parser.add_mutually_exclusive_group()
    hooks.add_argument("--hooks", dest="hooks", action="store_true", default=None,
                       help="configure project hooks for user review and trust")
    hooks.add_argument("--no-hooks", dest="hooks", action="store_false", help="remove only managed hooks at this checkout")
    parser.add_argument("--agents", action="store_true", help="add the managed section to project AGENTS.md")
    parser.add_argument("--apply", action="store_true", help="create files; default is a dry run")
    args = parser.parse_args(argv)
    try:
        if not args.apply:
            state, _, _, meta, files = plan(args)
            print(f"CDX_SETUP PLAN state={state} version={meta['version']} files={len(files)} hooks={meta['hooks']}")
            repo = Path(meta["repo"])
            tracked = set(git(repo, "ls-files", "-z").split("\0"))
            for path, data in files:
                if within(path, Path(meta["kit"])) or (path.is_file() and path.read_bytes() == data):
                    continue
                relative = path.relative_to(repo).as_posix() if within(path, repo) else None
                print(f"  {'tracked' if relative in tracked else 'local'} {path}")
            return 0
        common = common_dir(checkout(args.repo))
        with lock(common / "cdx-setup.lock"):
            target = destination(args)
            state = target[3]
            state.parent.mkdir(parents=True, exist_ok=True)
            identity = hashlib.sha256(os.path.normcase(str(state)).encode("utf-8")).hexdigest()[:24]
            with lock(state.parent / f".cdx-install-{identity}.lock"):
                state, owner, pointer, meta, files = plan(args, target)
                if owner.is_file() and read_json(owner).get("schema") == 1:
                    if pointer.is_file():
                        backup_legacy(state, target[0], pointer, files)
                    atomic_write(pointer, json_bytes({"schema": STATE_SCHEMA, "state": str(state)}))
                # Reserve the state before the first scaffold write, even when another repo uses --state.
                if not owner.exists():
                    atomic_write(owner, json_bytes(meta))
                for folder in FOLDERS:
                    state_path(state, folder).mkdir(parents=True, exist_ok=True)
                changed = 0
                kit = Path(meta["kit"])
                if not kit.exists():
                    kit.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(dir=kit.parent, prefix=".cdx-runtime-") as stage:
                        staged = Path(stage) / "kit"
                        for path, data in files:
                            if within(path, kit):
                                atomic_write(staged / path.relative_to(kit), data)
                                changed += 1
                        os.replace(staged, kit)
                    files = [(path, data) for path, data in files if not within(path, kit)]
                for path, data in files:
                    if not path.exists() or path.read_bytes() != data:
                        atomic_write(path, data)
                        changed += 1
                for path, data in ((owner, json_bytes(meta)),
                                   (pointer, json_bytes({"schema": STATE_SCHEMA, "state": str(state)}))):
                    if not path.exists() or path.read_bytes() != data:
                        atomic_write(path, data)
        print(f"CDX_SETUP COMPLETE state={state} version={meta['version']} changed={changed} hooks={meta['hooks']}")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
