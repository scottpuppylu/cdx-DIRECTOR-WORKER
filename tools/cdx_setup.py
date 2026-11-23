"""Install cdx in a Git project without changing its user-level Codex settings."""

import argparse
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdx_common import (POINTER, ROOT, Refused, atomic_write, checkout, common_dir, git, json_bytes,
                        lock, primary_checkout, read_json, report_error, stamp, state_path, within)


BEGIN, END = b"<!-- cdx:begin -->", b"<!-- cdx:end -->"
STOCK = ("README.md", "PURPOSE.md", "BOOTSTRAP.md", "VERSION", "LICENSE", "director_work.example.json",
         "CODEX-PORT.md", "CHANGELOG.md", "CHANGELOG-upstream.md", ".agents/plugins/marketplace.json")
FOLDERS = ("orders", "reviews", "work", "evidence", "audit", "sessions", "brief-history", "order-history")


def installed_files():
    paths = [ROOT / name for name in STOCK]
    for name in ("docs", "tools", "templates", "plugin", "research"):
        paths.extend(p for p in (ROOT / name).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix != ".pyc")
    return sorted(paths)


def initial_files(state, repo, mode):
    return {
        state / "DIRECTOR_LOG.md": f"# DIRECTOR_LOG\n\n{stamp()} | CDX_SETUP | {mode}\n",
        state / "DIRECTOR_STATE.md": (f"# DIRECTOR_STATE\n\nPROJECT: {repo}\nMODE: {mode}\n"
                                       "PENDING_METHOD: chat + PO_PENDING.md\n"),
        state / "RESUME_STATE.md": ("PROGRESS: cdx initialized\nDOING: confirm project requirements\n"
                                   "NEXT_STEP: read PO_PENDING.md and confirm BRIEF.md\nCOMMS: NONE\n\n"
                                   f"# RESUME_STATE — DIRECTOR\nUPDATED: {stamp()}\n"),
        state / "PO_PENDING.md": "# PO 待決與回覆\n\n## 未結\n\n## 已結\n",
        state / "ACTIVE_WORKSTREAMS.md": "# 工作線\n\n| WO | Branch | Thread | Status |\n|---|---|---|---|\n",
        state / "PENDING_SENDS.md": "# 待送訊息\n",
        state / "MECHANISMS.md": ("# 機制\n\n- `cdx.py doctor` 查看專案、Hook 信任、沙箱狀態。\n"
                                  "- `cdx.py session status` 對帳工單、Git worktree 和 thread。\n"),
        state / "DECISION_REGISTER.md": (ROOT / "templates" / "DECISION_REGISTER.md").read_text(encoding="utf-8"),
    }


def config_with_hooks(path, kit):
    data = read_json(path) if path.exists() else {"hooks": {}}
    events = data.setdefault("hooks", {})
    if not isinstance(events, dict):
        raise Refused("Existing .codex/hooks.json has no hooks object")
    entry = str(kit / "tools" / "cdx_hook.py")
    if os.name == "nt" and any(char in entry for char in '"%$`!\r\n'):
        raise Refused("The Windows hook path contains shell metacharacters. Choose another state path.")
    command = shlex.join(["python3", "-I", "-B", "-X", "utf8", entry])
    for event, matcher in {"SessionStart": "^(startup|resume|compact)$", "PreToolUse": ".*",
                           "PostToolUse": ".*"}.items():
        label = f"cdx DIRECTOR-WORK {event}"
        item = {"type": "command", "command": command, "timeout": 8, "statusMessage": label}
        if os.name == "nt":
            item["commandWindows"] = f'python -I -B -X utf8 "{entry}"'
            item["command"] = item["commandWindows"]
        groups = events.setdefault(event, [])
        if not isinstance(groups, list):
            raise Refused(f"Existing Hook groups are invalid: {event}")
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise Refused(f"Existing Hook handlers are invalid: {event}")
        generated = {"matcher": matcher, "hooks": [item]}
        owned = [i for i, group in enumerate(groups) if len(group["hooks"]) == 1
                 and isinstance(group["hooks"][0], dict) and group["hooks"][0].get("statusMessage") == label]
        if len(owned) > 1:
            raise Refused(f"There are multiple cdx Hook groups: {event}")
        if owned:
            groups[owned[0]] = generated
        else:
            groups.append(generated)
    return json_bytes(data)


def plan(args):
    repo = checkout(args.repo)
    common = common_dir(repo)
    if primary_checkout(repo) != repo:
        raise Refused("Run setup from the main checkout; linked worktrees share its configuration")
    pointer = common / POINTER
    registered = read_json(pointer) if pointer.exists() else None
    previous = Path(registered["state"]).resolve() if registered else None
    state = Path(args.state).resolve() if args.state else previous or repo.with_name(f"DIRECTOR-{repo.name}")
    if previous and previous != state:
        raise Refused(f"Project already uses {previous}; preserve it before changing its location")
    if within(state, repo) or within(repo, state) or within(state, common):
        raise Refused("State and the project checkout must be separate directories")
    owner = state_path(state, "PROJECT.json")
    existing = read_json(owner) if owner.exists() else None
    if (state.exists() and not existing and any(state.iterdir())) or (
            existing and (existing.get("schema") != 1 or Path(existing["git_common_dir"]).resolve() != common)):
        raise Refused(f"State belongs to another workflow or project: {state}")

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    kit = state_path(state, "runtime", version)
    use_hooks = args.hooks or bool(existing and existing.get("hooks"))
    mode = (existing or {}).get("mode", args.mode)
    manifest = dict((existing or {}).get("managed_skills", {}))
    files = []
    for source in installed_files():
        target = state_path(kit, *source.relative_to(ROOT).parts)
        data = source.read_bytes()
        if target.exists() and target.read_bytes() != data:
            raise Refused(f"Runtime {version} contains changed files: {target}")
        if not target.exists():
            files.append((target, data))

    for source in sorted((ROOT / "plugin" / "cdx" / "skills").glob("*/SKILL.md")):
        filename = f".agents/skills/{source.parent.name}/SKILL.md"
        target = state_path(repo, *filename.split("/"))
        data = source.read_bytes()
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
            section = (ROOT / "templates" / "AGENTS_PROJECT_SECTION.md").read_bytes()
            files.append((target, current + (b"\n\n" if current else b"") + section))
    if use_hooks:
        target = state_path(repo, ".codex", "hooks.json")
        files.append((target, config_with_hooks(target, kit)))
        # Generated commands point to this machine's runtime. Keep new Hook configs local to Git.
        exclude = state_path(common, "info", "exclude")
        rules = exclude.read_bytes() if exclude.exists() else b""
        pattern = b"/.codex/hooks.json"
        if pattern not in rules.splitlines():
            files.append((exclude, rules + (b"\n" if rules and not rules.endswith(b"\n") else b"")
                          + b"# cdx machine-local Hook config\n" + pattern + b"\n"))

    for path, content in initial_files(state, repo, mode).items():
        if not state_path(state, path.name).exists():
            files.append((path, content.encode("utf-8")))
    config = state_path(state, "director_work.json")
    if not config.exists():
        data = read_json(ROOT / "director_work.example.json")
        data["mode"] = mode
        files.append((config, json_bytes(data)))
    metadata = {"schema": 1, "git_common_dir": str(common), "repo": str(repo), "kit": str(kit),
                "version": version, "mode": mode, "hooks": use_hooks, "managed_skills": manifest}
    return state, owner, pointer, metadata, files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--state", help="existing or new cdx state path, outside the checkout")
    parser.add_argument("--mode", choices=("general", "beginner"), default="general")
    parser.add_argument("--hooks", action="store_true", help="configure project hooks for user review and trust")
    parser.add_argument("--agents", action="store_true", help="add the managed section to project AGENTS.md")
    parser.add_argument("--apply", action="store_true", help="create files; default is a dry run")
    args = parser.parse_args(argv)
    try:
        if not args.apply:
            state, _, _, meta, files = plan(args)
            print(f"CDX_SETUP PLAN state={state} version={meta['version']} files={len(files)} hooks={meta['hooks']}")
            return 0
        common = common_dir(checkout(args.repo))
        with lock(common / "cdx-setup.lock"):
            state, owner, pointer, meta, files = plan(args)
            # Reserve the state for this project before writing the kit. Interrupted installs are retryable.
            if not owner.exists():
                atomic_write(owner, json_bytes(meta))
            for folder in FOLDERS:
                state_path(state, folder).mkdir(parents=True, exist_ok=True)
            changed = 0
            for path, data in files:
                if not path.exists() or path.read_bytes() != data:
                    atomic_write(path, data)
                    changed += 1
            atomic_write(owner, json_bytes(meta))
            atomic_write(pointer, json_bytes({"schema": 1, "state": str(state)}))
        print(f"CDX_SETUP COMPLETE state={state} version={meta['version']} changed={changed} hooks={meta['hooks']}")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
