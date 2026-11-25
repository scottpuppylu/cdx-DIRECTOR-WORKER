"""Compare Desktop handoff state and attach a verified isolated destination checkout."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdx_common import (SHA, THREAD_ID, Refused, atomic_write, checkout, common_dir, executing_version, git, json_bytes, load_project,
                        lock, primary_checkout, read_json, report_error, state_path, within)
from cdx_gates import file_hash
from cdx_setup import config_with_hooks, version_key
from cdx_work import active_order, approved_brief, bind_desktop_chat, field, order_file_id, spec_review, sync_worker


def repository_id(repo):
    origin = git(repo, "config", "--get", "remote.origin.url") if "origin" in git(repo, "remote").splitlines() else ""
    github = re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?/?",
                          origin)
    return hashlib.sha256(("github.com/" + github[1].casefold() if github else origin).encode()).hexdigest() if origin else None


def workspace(worker):
    changes = {}
    for name, extra in (("staged", ["--cached"]), ("working", [])):
        raw = git(worker, "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--binary",
                  "--src-prefix=a/", "--dst-prefix=b/", *extra, "HEAD", "--", raw=True)
        changes[name] = hashlib.sha256(raw).hexdigest()
    names = git(worker, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    changes["untracked"] = {name: file_hash(state_path(worker, *name.split("/"))) for name in sorted(set(names) - {""})}
    return {"head": git(worker, "rev-parse", "HEAD"), **changes}


def state_inventory(state, order_id, snapshot, brief, *, receiving=None):
    paths = {"PO_PENDING.md", "DECISION_REGISTER.md", "DIRECTOR_LOG.md", "RESUME_STATE.md", snapshot}
    if brief:
        paths.add(brief)
    paths.update(f"sessions/{order_id}-{role}.json" for role in ("worker", "reviewer"))
    journals = sorted(state_path(state, "acceptance", order_id).glob("*/*.json"))
    for journal in journals:
        paths.add(journal.relative_to(state).as_posix())
        for attempt in read_json(journal)["attempts"]:
            digest = attempt.get("reply_sha256")
            if digest is not None:
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise Refused("Invalid PO reply fingerprint in the handoff journal")
                raw_reply = f"po-replies/{digest}.txt"
                raw_path = state_path(state, "po-replies", f"{digest}.txt")
                if raw_path.is_file() and file_hash(raw_path) != digest:
                    raise Refused(f"PO reply does not match its recorded digest: {raw_reply}")
                paths.add(raw_reply)
    for folder, pattern in (("reviews", f"{order_id}-*"), (f"reviews/spec-history/{order_id}", "*"),
                            (f"reviews/receipt-history/{order_id}", "*"), (f"reviews/native/{order_id}", "*"),
                            (f"reviews/plan-history/{order_id}", "*"),
                            ("audit", f"{order_id}-*.jsonl"), (f"work/{order_id}", "**/*")):
        directory = state_path(state, *folder.split("/"))
        paths.update(path.relative_to(state).as_posix() for path in directory.glob(pattern)
                     if path.is_file() and not (path.name.endswith(".guard") or path.name == "HANDOFF.json"))
    for path in state_path(state, "sessions", "attempts").glob("*.json"):
        if read_json(path).get("order") == order_id:
            paths.add(path.relative_to(state).as_posix())
    for path in state_path(state, "sessions").glob("*.json"):
        record = read_json(path)
        if record.get("order") == order_id and (receiving is None or record.get("handoff") != receiving):
            paths.add(path.relative_to(state).as_posix())
            thread = record.get("thread")
            if isinstance(thread, str) and THREAD_ID.fullmatch(thread):
                for name in (f"audit/{thread}-hooks.jsonl", f"sessions/compact/{thread}.json"):
                    if state_path(state, *name.split("/")).is_file():
                        paths.add(name)
    inventory = {}
    for name in sorted(paths):
        path = state_path(state, *name.split("/"))
        inventory[name] = file_hash(path) if path.is_file() else None
    return inventory


def refs(repo, order_id):
    prefix = f"refs/cdxdw/candidates/{order_id}/"
    return dict(line.split(" ", 1) for line in git(repo, "for-each-ref", "--format=%(refname) %(objectname)",
                                                  prefix).splitlines())


def acceptance_policy(state):
    config = read_json(state_path(state, "director_work.json"))
    return {"cdx_require_brief_pins": config.get("cdx_require_brief_pins") is True,
            "verdict_self_check": config.get("verdict_self_check", "off"),
            "trace_id_pattern": config.get("trace_id_pattern", r"^(B|DD|OD)-\d+$")}


def export(repo, state, spec):
    worker = spec["checkout"]
    if checkout(worker) != worker or common_dir(worker) != common_dir(repo):
        raise Refused("Handoff source does not belong to the registered Git project")
    snapshot = spec["path"].relative_to(state).as_posix()
    brief_path = approved_brief(state, spec)
    spec_review(state, spec)
    brief = brief_path.relative_to(state).as_posix() if brief_path else None
    inventory = state_inventory(state, spec["order_id"], snapshot, brief)
    missing = sorted(name for name, digest in inventory.items()
                     if digest is None and name.startswith("po-replies/"))
    if missing:
        raise Refused(f"Missing original PO replies: {', '.join(missing)}")
    work = workspace(worker)
    seals = refs(repo, spec["order_id"])
    if (inventory != state_inventory(state, spec["order_id"], snapshot, brief) or
            work != workspace(worker) or seals != refs(repo, spec["order_id"])):
        raise Refused("Handoff source changed during export. Pause writes and retry.")
    policy = acceptance_policy(state)
    return {"schema": 3, "id": str(uuid.uuid4()), "order": spec["order_id"], "filename": spec["file"],
            "order_sha256": spec["sha"], "base": spec["base"], "snapshot": snapshot,
            "repository": repository_id(repo), "source_common": str(common_dir(repo)),
            "workspace": work, "refs": seals, "brief": brief, "state": inventory, "policy": policy,
            "policy_sha256": hashlib.sha256(json_bytes(policy)).hexdigest(), "minimum_runtime": executing_version()}


def verify(repo, state, worker, receipt, project=None):
    order_id = receipt["order"]
    if receipt["schema"] in (1, 2):
        raise Refused("Legacy handoff manifest does not attest to acceptance policy. Export a new manifest.")
    if (receipt["schema"] != 3 or not re.fullmatch(r"WO-\d+", order_id) or not SHA.fullmatch(receipt["base"]) or
            not re.fullmatch(r"[0-9a-f]{64}", receipt["order_sha256"]) or
            not re.fullmatch(rf"(?:order-history|orders)/{order_id}(?:-[A-Za-z0-9_.-]+)?\.md", receipt["snapshot"])):
        raise Refused("Invalid handoff manifest")
    brief = receipt["brief"]
    if brief is not None and not re.fullmatch(r"BRIEF\.md|brief-history/[\w.-]+\.md", brief):
        raise Refused("Invalid approved brief in the handoff manifest")
    source_is_local = str(common_dir(repo)) == receipt["source_common"]
    if ((not source_is_local and not receipt["repository"]) or repository_id(repo) != receipt["repository"] or
            common_dir(worker) != common_dir(repo)):
        raise Refused("Handoff destination repository does not match")
    git(repo, "merge-base", "--is-ancestor", receipt["base"], receipt["workspace"]["head"])
    expected = state_inventory(state, order_id, receipt["snapshot"], brief, receiving=receipt["id"])
    changes = workspace(worker)
    issues = sorted(key for key in set(expected) | set(receipt["state"])
                    if key not in expected or key not in receipt["state"] or expected[key] != receipt["state"][key])
    name_refs = refs(repo, order_id)
    wrong_refs = [name for name, head in receipt["refs"].items() if name_refs.get(name) != head]
    different = [key for key in changes if changes[key] != receipt["workspace"].get(key)]
    source_policy = receipt["policy"]
    if hashlib.sha256(json_bytes(source_policy)).hexdigest() != receipt["policy_sha256"]:
        raise Refused("Handoff acceptance policy fingerprint does not match")
    target_policy = acceptance_policy(state)
    policy_issues = {key: {"expected": source_policy.get(key), "current": target_policy.get(key)}
                     for key in sorted(source_policy.keys() | target_policy.keys())
                     if source_policy.get(key) != target_policy.get(key)}
    runtime_issues = []
    current_version = project["version"] if project else executing_version()
    if version_key(current_version) < version_key(receipt["minimum_runtime"]):
        runtime_issues.append(f"Upgrade receiving runtime {current_version} to {receipt['minimum_runtime']}")
    skills = (project or {}).get("managed_skills", {})
    unsynced = []
    for name, digest in skills.items():
        path = state_path(worker, *name.split("/"))
        if not path.is_file() or file_hash(path) != digest:
            unsynced.append(name)
    hook_setup = "DISABLED" if project else "NOT_INSPECTED"
    if project and project.get("hooks"):
        name = ".codex/hooks.json"
        path = state_path(worker, ".codex", "hooks.json")
        tracked = bool(git(worker, "ls-files", "--", name) or git(worker, "ls-tree", "HEAD", "--", name))
        try:
            updated = config_with_hooks(path, Path(project["kit"]))
            current = path.is_file() and path.read_bytes() == updated
            hook_setup = "CURRENT" if current else "TRACKED_SETUP_REQUIRED" if tracked else "SYNC_REQUIRED"
        except Refused:
            hook_setup = "LOCAL_REVIEW_REQUIRED"
    return {"outcome": "MISMATCH" if issues or wrong_refs or different or policy_issues or runtime_issues else "MATCH",
            "handoff": receipt["id"], "order": order_id, "state_mismatches": issues,
            "checkout_mismatches": different, "missing_or_changed_refs": wrong_refs,
            "policy_mismatches": policy_issues, "runtime_mismatches": runtime_issues,
            "worker_sync": "REQUIRED" if unsynced or hook_setup == "SYNC_REQUIRED" else
                           ("CURRENT" if project else "NOT_INSPECTED"),
            "missing_or_changed_managed_skills": unsynced, "hook_setup": hook_setup, "host_hook_trust": "NOT_PROBED"}


def attach(repo, state, worker, receipt, chat, project):
    if chat and not THREAD_ID.fullmatch(chat):
        raise Refused("Use the UUID of the destination Codex chat")
    if any((within(worker, repo), within(repo, worker), within(worker, state), within(state, worker))):
        raise Refused("Use a separate Git worktree to resume managed execution. Verify can inspect Local.")
    order_id = order_file_id(receipt["filename"])
    binding = state_path(state, "work", order_id, "revisions", receipt["order_sha256"], "HANDOFF.json")
    binding.parent.mkdir(parents=True, exist_ok=True)
    with lock(binding.with_suffix(".lock")):
        result = verify(repo, state, worker, receipt, project)
        if result["outcome"] != "MATCH":
            return result
        snapshot = state_path(state, *receipt["snapshot"].split("/")).read_text(encoding="utf-8-sig")
        location = {"order_sha256": receipt["order_sha256"], "worktree": str(worker),
                    "git_common_dir": str(common_dir(repo)), "base": receipt["base"], "chat": chat,
                    "handoff": receipt["id"], "source_work_dir": field(snapshot, "WORK_DIR")}
        spec = active_order(state, receipt["filename"], location=location)
        if spec["base"] != receipt["base"] or git(worker, "branch", "--show-current") not in ("", spec["branch"]):
            raise Refused("Worktree does not match the active order and branch")
        brief_path = approved_brief(state, spec)
        if (brief_path.relative_to(state).as_posix() if brief_path else None) != receipt["brief"]:
            raise Refused("Handoff manifest does not match the active approved brief")
        spec_review(state, spec)
        sync_worker(repo, worker, project)
        bind_desktop_chat(state, spec, chat, handoff=receipt["id"])
        atomic_write(binding, json_bytes(location))
    if result["hook_setup"] == "SYNC_REQUIRED":
        result["hook_setup"] = "CURRENT"
    return dict(result, outcome="ATTACHED", worker_sync="SYNCED",
                previously_missing_managed_skills=result.pop("missing_or_changed_managed_skills"), chat=chat)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    sender = commands.add_parser("export")
    sender.add_argument("order")
    sender.add_argument("--out", type=Path, required=True)
    for mode in ("verify", "attach"):
        receiver = commands.add_parser(mode)
        receiver.add_argument("manifest", type=Path)
        receiver.add_argument("--worktree", required=True)
        if mode == "verify":
            receiver.add_argument("--state", type=Path, help="existing staged copy of the sender state to compare")
        else:
            receiver.add_argument("--chat")
    args = parser.parse_args(argv)
    try:
        project = None
        if args.command == "verify" and args.state:
            repo, state = primary_checkout(checkout(args.repo)), args.state.resolve(strict=True)
        else:
            _, state, project = load_project(args.repo)
            repo = Path(project["repo"])
        if args.command == "export":
            result = export(repo, state, active_order(state, args.order))
            with args.out.open("xb") as target:
                target.write(json_bytes(result))
            print(json.dumps({"outcome": "EXPORTED", "manifest": str(args.out), "handoff": result["id"]}))
            return 0
        worker = checkout(args.worktree)
        receipt = read_json(args.manifest)
        result = (attach(repo, state, worker, receipt, args.chat, project) if args.command == "attach" else
                  verify(repo, state, worker, receipt, project))
        print(json.dumps(result, ensure_ascii=False))
        return 2 if result["outcome"] == "MISMATCH" else 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
