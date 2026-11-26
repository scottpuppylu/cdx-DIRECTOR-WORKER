"""Prepare a work order, lock dispatch, and check the exact candidate."""

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_check
from cdx_acceptance import (acceptance_lock, artifact_required, attempt, current_judgments, judgment_criteria,
                            latest_attempts, run_entry)
from cdx_audit import check_report
from cdx_delivery import (approve_integration, checked_retained, delivery_po_status, integration_approval,
                          retain_output, save_po_delivery, target_position)
from cdx_gates import feasibility, file_hash, invoke, pack_digest, policy, ruler_check, tail
from cdx_common import (SHA, ROOT, THREAD_ID, VERSION, Refused, atomic_write, check_environment, checkout, common_dir,
                        detached_checkout, executor, git, git_environment, json_bytes,
                        load_project, lock, read_json, report_error, stamp, state_path, within)
from cdx_setup import config_with_hooks


def field(text, key, *, allow_comment=True):
    found = re.findall(rf"^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(.+)$", text, re.M)
    if len(found) != 1:
        raise Refused(f"Order needs exactly one {key} field")
    return (found[0].split(" #", 1)[0] if allow_comment else found[0]).strip()


def order_file_id(filename):
    match = re.fullmatch(r"(WO-[0-9]+)(?:-[A-Za-z0-9_.-]+)?\.md", filename)
    if not match:
        raise Refused("Use an order filename such as WO-001-export.md")
    return match[1]


def order_spec(state, filename, source=None, *, location=None, historical=False):
    file_id = order_file_id(filename)
    path = source or state_path(state, "orders", filename)
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    names, problem = gate_check.order_identity(text, path)
    order_id = gate_check.order_key(names)
    if problem or order_id != file_id:
        raise Refused(problem or "Order does not have a WO-n ID")
    base = field(text, "BASE_REF").rsplit("@", 1)[-1].strip().lower()
    if not SHA.fullmatch(base):
        raise Refused("BASE_REF must pin a complete 40-character commit SHA")
    rev = field(text, "REVISION")
    if not rev.isdigit() or int(rev) < 1:
        raise Refused("Order revision must be a positive integer")
    work = state_path(state, "work", order_id)
    digest = gate_check.order_hash(data)
    original_work = field(text, "WORK_DIR")
    if location:
        if location.get("order_sha256") != digest or location.get("source_work_dir") != original_work:
            raise Refused("Handoff location does not match this frozen work order")
        worker_path = Path(location["worktree"])
        if not worker_path.is_absolute() or worker_path != worker_path.resolve():
            raise Refused("Handoff worktree is not a canonical local path")
    else:
        worker_path = Path(field(text, "WORKTREE"))
    if not historical and (not worker_path.is_absolute() or (not location and Path(original_work) != work)):
        raise Refused(f"WORKTREE must be absolute, and WORK_DIR must be {work}")
    spec = {"order_id": order_id, "file": filename, "path": path, "text": text, "sha": digest,
            "revision": int(rev), "base": base, "branch": field(text, "NEW_BRANCH"), "work": work,
            "checkout": worker_path if historical and not location else worker_path.resolve(),
            "governance": field(text, "GOVERNANCE"), "gates": policy(text)}
    if location:
        spec["handoff"] = location
    return spec


def validate_checkout(repo, state, spec, *, fresh=False):
    worker = spec["checkout"]
    if (within(worker, repo) or within(repo, worker) or within(worker, state) or within(state, worker) or
            checkout(worker) != worker or common_dir(worker) != common_dir(repo)):
        raise Refused("Worker must be an isolated worktree of this Git project")
    branch = git(worker, "branch", "--show-current")
    adopted = spec.get("handoff") or desktop_registration(state, spec)
    if branch != spec["branch"] and (
            branch or any(adopted.get(key) != value for key, value in desktop_identity(repo, spec).items())):
        raise Refused(f"Expected worktree branch {spec['branch']}; found {branch or 'detached HEAD'}")
    head = git(worker, "rev-parse", "HEAD")
    if fresh and (head != spec["base"] or git(worker, "status", "--porcelain", "--untracked-files=all")):
        raise Refused("Initial worker checkout must be clean at the pinned base")
    git(worker, "merge-base", "--is-ancestor", spec["base"], head)
    return head


def desktop_identity(repo, spec):
    return {"worktree": str(spec["checkout"]), "git_common_dir": str(common_dir(repo)), "base": spec["base"]}


def revision_record(state, spec, name):
    return state_path(state, "work", spec["order_id"], "revisions", spec["sha"], name)


def resume_location(state, spec):
    archived = revision_record(state, spec, "RESUME_STATE.md")
    return archived if archived.is_file() else spec["work"] / "RESUME_STATE.md"


def initialize_resume(state, spec, previous=None):
    resume = (revision_record(state, spec, "RESUME_STATE.md") if spec["revision"] > 1 else
              state_path(state, "work", spec["order_id"], "RESUME_STATE.md"))
    if resume.exists():
        return
    if previous and previous.is_file():
        atomic_write(resume, previous.read_bytes())
        return
    text = (f"PROGRESS: worker checkout ready at {spec['base']}\nDOING: read {spec['file']}\n"
            "NEXT_STEP: confirm the dispatched order and prepare a plan\nCOMMS: NONE\n\n"
            f"# RESUME_STATE — {spec['order_id']} r{spec['revision']}\nUPDATED: {stamp()}\n")
    atomic_write(resume, text.encode("utf-8"))


def desktop_registration(state, spec):
    current = revision_record(state, spec, "DESKTOP.json")
    if current.is_file():
        return read_json(current)
    legacy = state_path(state, "work", spec["order_id"], "DESKTOP.json")
    record = read_json(legacy) if legacy.is_file() else {}
    if record.get("worktree") == str(spec["checkout"]) and record.get("base") == spec["base"]:
        return record
    return {}


def desktop_chat(state, spec):
    if "handoff" in spec:
        return spec["handoff"].get("chat")
    return desktop_registration(state, spec).get("chat")


def desktop_binding(prior, record, source_worktree):
    if any(prior.get(key) != record[key] for key in ("role", "source", "thread", "order")):
        raise Refused("This Desktop chat is already bound to another role or checkout")
    if prior.get("worktree") != record["worktree"] and (
            not source_worktree or prior.get("worktree") != source_worktree or
            prior.get("order_sha256") != record["order_sha256"]):
        raise Refused("This Desktop chat is already bound to another role or checkout")


def bind_desktop_chat(state, spec, chat, *, handoff=None, source_worktree=None, prepare=None):
    if chat is None:
        if prepare:
            prepare()
        return
    if not THREAD_ID.fullmatch(chat):
        raise Refused("Supply the UUID of the Desktop chat")
    record = {"role": "worker", "source": "codex-desktop", "thread": chat, "order": spec["order_id"],
              "order_file": spec["file"], "order_sha256": spec["sha"], "worktree": str(spec["checkout"])}
    if handoff:
        record["handoff"] = handoff
    path = state_path(state, "sessions", f"{chat}.json")
    with lock(path.with_suffix(".lock")):
        old = None
        if path.is_file():
            old = path.read_bytes()
            prior = json.loads(old.decode("utf-8-sig"))
            desktop_binding(prior, record, source_worktree)
            if prior != record:
                archive = state_path(state, "sessions", "desktop-history", chat, hashlib.sha256(old).hexdigest() + ".json")
                if not archive.is_file():
                    atomic_write(archive, old)
        if prepare:
            prepare()
        if old is None or prior != record:
            atomic_write(path, json_bytes(record))


def active_order(state, filename, *, location=None):
    order_id = order_file_id(filename)
    log = state_path(state, "DIRECTOR_LOG.md")
    record = gate_check.dispatch_records(log.read_text(encoding="utf-8-sig")).get(order_id)
    if not record:
        raise Refused("Order is not registered in DIRECTOR_LOG.md")
    revision, digest = record
    snapshot = state_path(state, "order-history", f"{order_id}-r{revision}-{digest}.md")
    if location is None:
        location = handoff_location(state, order_id, digest)
    spec = order_spec(state, filename, snapshot if snapshot.is_file() else None, location=location)
    dispatch_check(state, spec)
    return spec


def handoff_location(state, order_id, digest):
    for path in (state_path(state, "work", order_id, "revisions", digest, "HANDOFF.json"),
                 state_path(state, "work", order_id, "HANDOFF.json")):
        if path.is_file():
            record = read_json(path)
            if record.get("order_sha256") == digest:
                return record
    return None


def historical_order(state, filename, revision):
    order_id = order_file_id(filename)
    snapshots = list(state_path(state, "order-history").glob(f"{order_id}-r{revision}-*.md"))
    if len(snapshots) != 1:
        raise Refused("Use a uniquely archived, dispatched order revision")
    snapshot = snapshots[0]
    digest = gate_check.order_hash(snapshot.read_bytes())
    if snapshot.name != f"{order_id}-r{revision}-{digest}.md":
        raise Refused("Historical order snapshot fingerprint does not match")
    log = state_path(state, "DIRECTOR_LOG.md").read_text(encoding="utf-8-sig")
    if not any(gate_check.dispatch_records(line).get(order_id) == (str(revision), digest) for line in log.splitlines()):
        raise Refused("Historical snapshot has no matching dispatch event")
    return order_spec(state, filename, snapshot, location=handoff_location(state, order_id, digest), historical=True)


def dispatch_check(state, spec):
    log = state_path(state, "DIRECTOR_LOG.md")
    records = gate_check.dispatch_records(log.read_text(encoding="utf-8-sig"))
    if (records.get(spec["order_id"]) != (str(spec["revision"]), spec["sha"]) or
            gate_check.order_hash(spec["path"].read_bytes()) != spec["sha"]):
        raise Refused("Current order revision and hash are not registered in DIRECTOR_LOG.md")
    return log


def approved_brief(state, spec):
    text = spec["text"]
    config = read_json(state_path(state, "director_work.json"))
    traces, per_ac = gate_check.order_traces(text)
    ids = [*traces, *(item for values in (per_ac or {}).values() for item in values)]
    if not re.search(r"^[ \t]*BRIEF_(?:REVISION|FINGERPRINTS_V1)[ \t]*=", text, re.M) and not (
            config.get("cdx_require_brief_pins") is True and any(re.fullmatch(r"B-\d+", item) for item in ids)):
        return None
    _, pins = gate_check.order_brief(text)
    if not pins:
        raise Refused("Work order needs valid BRIEF_FINGERPRINTS_V1 for its product requirements")
    log = state_path(state, "DIRECTOR_LOG.md")
    log_text = log.read_text(encoding="utf-8-sig")
    locks = gate_check.brief_locks(log_text)
    if not locks:
        raise Refused("No approved product brief is recorded")
    revision, digest, snapshot = locks[-1]
    if snapshot and not re.fullmatch(r"brief-history/[\w.-]+\.md", snapshot):
        raise Refused("Approved brief snapshot must be inside brief-history")
    path = state_path(state, *snapshot.split("/")) if snapshot else state_path(state, "BRIEF.md")
    raw = path.read_bytes()
    if gate_check.order_hash(raw) != digest or gate_check.brief_revision(raw.decode("utf-8-sig")) != revision:
        raise Refused("Approved product brief does not match its recorded revision and hash")
    brief = gate_check.load_brief(path, log_text, log)
    if not brief["trusted"] or brief["ambiguous"] or brief["problem"]:
        raise Refused("Approved product brief has invalid or ambiguous requirement rows")
    notes = []
    gate_check.brief_notes(text, spec["path"], brief, notes)
    if notes:
        raise Refused("; ".join(notes))
    return path


def lock_brief(state):
    current = state_path(state, "BRIEF.md")
    raw = current.read_bytes()
    text = raw.decode("utf-8-sig")
    revision = gate_check.brief_revision(text)
    rows, ambiguous, problem = gate_check.brief_table(text)
    if not revision or not gate_check.brief_is_locked(text) or not rows or ambiguous or problem:
        raise Refused("A LOCKED product brief needs a revision and unambiguous requirement rows")
    digest = gate_check.order_hash(raw)
    snapshot = state_path(state, "brief-history", f"r{revision}-{digest}.md")
    log = state_path(state, "DIRECTOR_LOG.md")
    with lock(state / ".dispatch.lock"):
        locks = gate_check.brief_locks(log.read_text(encoding="utf-8-sig"))
        if locks and revision <= locks[-1][0]:
            if revision == locks[-1][0] and digest == locks[-1][1]:
                return
            raise Refused("A changed product brief needs a revision newer than the last approved revision")
        save_snapshot(snapshot, raw, digest)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"\n{stamp()} | BRIEF_LOCKED rev={revision} sha={digest} "
                         f"snapshot={snapshot.relative_to(state).as_posix()} | cdx\n")


def save_snapshot(path, raw, digest):
    if path.exists():
        if gate_check.order_hash(path.read_bytes()) != digest:
            raise Refused(f"A saved snapshot has changed: {path.name}")
    else:
        atomic_write(path, raw)


def dispatched_copy(state, spec):
    snapshot = state_path(state, "order-history", f"{spec['order_id']}-r{spec['revision']}-{spec['sha']}.md")
    if not snapshot.exists():
        return spec["path"]  # Orders dispatched by earlier releases may have no archived copy.
    if gate_check.order_hash(snapshot.read_bytes()) != spec["sha"]:
        raise Refused("The dispatched work order snapshot was modified")
    return snapshot


def locked_hash(repo, candidate, name):
    if (not re.fullmatch(r"[^:/\\]+(?:/[^:/\\]+)*", name) or
            any(part in (".", "..", ".git") for part in name.split("/"))):
        raise Refused(f"Expected a repo-relative test path: {name}")
    return hashlib.sha256(git(repo, "show", f"{candidate}:{name}", raw=True)).hexdigest()


def validate_tests(repo, spec, candidate):
    if spec["governance"] == "Direct":
        return
    locked = gate_check.parse_list(spec["text"], "TESTS_LOCKED")
    if not locked:
        raise Refused("Standard and Strict orders require TESTS_LOCKED. Use `- NONE # reason` when justified.")
    if locked == ["NONE"]:
        return
    for line in locked:
        match = re.fullmatch(r"(.+) sha256=([0-9a-f]{64})", line)
        if not match or locked_hash(repo, candidate, match[1]) != match[2]:
            raise Refused(f"Locked acceptance test differs at {candidate[:12]}: {line}")


def log_event(state, event):
    with lock(state / ".dispatch.lock"):
        append_event(state, event)


def append_event(state, event):
    with state_path(state, "DIRECTOR_LOG.md").open("a", encoding="utf-8") as handle:
        handle.write(f"\n{stamp()} | {event} | cdx\n")


def spec_review(state, spec, *, reviewer=None, author=None):
    if spec["governance"] == "Direct":
        return
    report = state_path(state, "reviews", f"{spec['order_id']}-SPEC_REVIEW.md")
    path = state_path(state, "reviews", "spec-history", spec["order_id"], f"{spec['sha']}.json")
    legacy = state_path(state, "reviews", f"{spec['order_id']}-spec.json")
    if reviewer is not None:
        valid = r"[A-Za-z0-9_.-]+"
        if not re.fullmatch(valid, reviewer) or not re.fullmatch(valid, author) or reviewer == author:
            raise Refused("Supply distinct reviewer and author session identifiers")
        raw = report.read_bytes()
        if not raw.strip():
            raise Refused("Write the independent spec review before approval")
        digest = hashlib.sha256(raw).hexdigest()
        snapshot = state_path(path.parent, f"{digest}.md")
        with lock(state / ".dispatch.lock"):
            if snapshot.exists() and snapshot.read_bytes() != raw:
                raise Refused("Archived spec review does not match its digest")
            if not snapshot.exists():
                atomic_write(snapshot, raw)
            atomic_write(path, json_bytes({"order_sha256": spec["sha"], "review_sha256": digest,
                                          "reviewer": reviewer, "author": author}))
            append_event(state, f"SPEC_REVIEW {spec['order_id']} session={reviewer} author={author} sha={spec['sha']}")
        return
    archived = path.exists()
    actual = read_json(path if archived else legacy)
    digest = actual.get("review_sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise Refused("Spec review digest is invalid")
    raw = (state_path(path.parent, f"{digest}.md") if archived else report).read_bytes()
    if actual.get("order_sha256") != spec["sha"] or digest != hashlib.sha256(raw).hexdigest():
        raise Refused("The order or independent spec review changed after approval")


class ToolFailure(Refused):
    def __init__(self, name, result):
        self.output = result.stdout or ""
        super().__init__(f"{name} exited {result.returncode}")


def run_tool(name, *args, capture=False, filtered_env=False):
    command = [sys.executable, "-I", "-B", "-X", "utf8", str(ROOT / "tools" / name), *map(str, args)]
    result = subprocess.run(command, capture_output=capture, encoding="utf-8", errors="replace",
                            env=check_environment() if filtered_env else git_environment())
    if capture:
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        raise ToolFailure(name, result)
    return result.stdout if capture else ""


def prepare(repo, state, spec, project, *, adopt=False, chat=None):
    run_tool("gate_check.py", "--order", spec["path"], "--repo", repo,
             "--config", state_path(state, "director_work.json"))
    worker = spec["checkout"]
    if within(worker, repo) or within(repo, worker) or within(worker, state) or within(state, worker):
        raise Refused("Worker checkout must be outside both project and cdx state")
    git(repo, "check-ref-format", "--branch", spec["branch"])
    if adopt:
        if (checkout(worker) != worker or common_dir(worker) != common_dir(repo) or
                git(worker, "rev-parse", "HEAD") != spec["base"] or
                git(worker, "status", "--porcelain", "--untracked-files=all") or
                git(worker, "branch", "--show-current") not in ("", spec["branch"])):
            raise Refused("Adopt a clean Codex worktree of this repo at the exact approved base")
        registration = revision_record(state, spec, "DESKTOP.json")
        identity = desktop_identity(repo, spec)
        previous = desktop_registration(state, spec)
        if previous and any(previous.get(key) != value for key, value in identity.items()):
            raise Refused("This work order already has a different Desktop worktree")
        if chat and not THREAD_ID.fullmatch(chat):
            raise Refused("Supply the UUID of the Desktop chat")
        atomic_write(registration, json_bytes(dict(identity, order_sha256=spec["sha"], chat=chat or previous.get("chat"))))
    elif not worker.exists():
        git(repo, "worktree", "add", "-b", spec["branch"], "--", str(worker), spec["base"])
    validate_checkout(repo, state, spec, fresh=True)
    sync_worker(repo, worker, project)
    (spec["work"] / "evidence").mkdir(parents=True, exist_ok=True)
    if spec["revision"] == 1:
        initialize_resume(state, spec)


def sync_worker(repo, worker, project):
    with lock(common_dir(repo) / "cdx-setup.lock"):
        exclude = state_path(common_dir(repo), "info", "exclude")
        rules = exclude.read_bytes() if exclude.is_file() else b""
        kit = Path(project["kit"])
        former = [state_path(kit.parent, path.name) for path in kit.parent.iterdir()
                  if VERSION.fullmatch(path.name) and path != kit and path.is_dir() and not path.is_symlink()]
        changes = []
        patterns = []
        for source in sorted((kit / "plugin" / "cdx" / "skills").glob("*/SKILL.md")):
            name = f".agents/skills/{source.parent.name}/SKILL.md"
            if git(worker, "ls-files", "--", name) or git(worker, "ls-tree", "HEAD", "--", name):
                continue
            target = state_path(worker, *name.split("/"))
            payload = source.read_bytes()
            if target.exists():
                current = target.read_bytes()
                if current != payload:
                    old_sources = [state_path(path, *source.relative_to(kit).parts) for path in former]
                    if not any(old.is_file() and old.read_bytes() == current for old in old_sources):
                        raise Refused(f"Existing worktree Skill has local content: {target}")
            patterns.append(f"/{name}".encode("utf-8"))
            changes.append((name, target, payload))
        hook_name = ".codex/hooks.json"
        if not (git(worker, "ls-files", "--", hook_name) or git(worker, "ls-tree", "HEAD", "--", hook_name)):
            hook_file = state_path(worker, ".codex", "hooks.json")
            enabled = bool(project.get("hooks"))
            if hook_file.exists() or enabled:
                config = config_with_hooks(hook_file, kit, enabled=enabled)
                if enabled:
                    patterns.append(b"/.codex/hooks.json")
                if enabled or hook_file.read_bytes() != config:
                    changes.append((hook_name, hook_file, config))
        additions = [pattern for pattern in patterns if pattern not in rules.splitlines()]
        if additions:
            atomic_write(exclude, (rules.rstrip(b"\r\n") + b"\n" if rules else b"") + b"\n".join(additions) + b"\n")
        for name, _, _ in changes:
            git(worker, "check-ignore", "--", name)
        for _, target, payload in changes:
            if not target.exists() or target.read_bytes() != payload:
                atomic_write(target, payload)


def dispatch(repo, state, spec):
    validate_checkout(repo, state, spec)
    run_tool("gate_check.py", "--order", spec["path"], "--repo", repo,
             "--config", state_path(state, "director_work.json"))
    validate_tests(repo, spec, spec["base"])
    spec_review(state, spec)
    log = state_path(state, "DIRECTOR_LOG.md")
    with lock(state / ".dispatch.lock"):
        approved_brief(state, spec)
        raw = spec["path"].read_bytes()
        if gate_check.order_hash(raw) != spec["sha"]:
            raise Refused("Work order changed while it was being checked")
        current = log.read_text(encoding="utf-8-sig")
        old = gate_check.dispatch_records(current).get(spec["order_id"])
        repeated = old == (str(spec["revision"]), spec["sha"])
        if old and not repeated and spec["revision"] <= int(old[0]):
            raise Refused("A changed work order must increment REVISION before redispatch")
        if old is None:
            validate_checkout(repo, state, spec, fresh=True)
        elif not repeated:
            last = historical_order(state, spec["file"], old[0])
            same_workline = spec["checkout"] == last["checkout"] and spec["base"] == last["base"]
            if not same_workline:
                validate_checkout(repo, state, spec, fresh=True)
            resume = resume_location(state, last)
            archive = revision_record(state, last, "RESUME_STATE.md")
            if resume.is_file() and not archive.exists():
                atomic_write(archive, resume.read_bytes())
            initialize_resume(state, spec, previous=resume if same_workline else None)
            legacy_candidate = state_path(state, "work", last["order_id"], "CANDIDATE.json")
            selected = read_json(legacy_candidate) if legacy_candidate.is_file() else {}
            history = revision_record(state, last, "CANDIDATE.json")
            if selected.get("order_sha256") == last["sha"] and not history.is_file():
                atomic_write(history, json_bytes(selected))
        initialize_resume(state, spec)
        snapshot = state_path(state, "order-history", f"{spec['order_id']}-r{spec['revision']}-{spec['sha']}.md")
        save_snapshot(snapshot, raw, spec["sha"])
        bind_desktop_chat(state, spec, desktop_chat(state, spec))
        if repeated:
            return
        line = f"{stamp()} | DISPATCH {spec['order_id']} rev={spec['revision']} sha={spec['sha']} | cdx\n"
        with log.open("a", encoding="utf-8") as handle:
            handle.write(("\n" if current and not current.endswith("\n") else "") + line)


def sealed_ref(spec, candidate):
    if not SHA.fullmatch(candidate):
        raise Refused("Use the full candidate commit SHA")
    return f"refs/cdxdw/candidates/{spec['order_id']}/{candidate}"


def seal(repo, state, spec):
    dispatch_check(state, spec)
    approved_brief(state, spec)
    candidate = validate_checkout(repo, state, spec)
    if git(spec["checkout"], "status", "--porcelain", "--untracked-files=all"):
        raise Refused("Commit the intended candidate before sealing. Existing changes are preserved.")
    run_tool("scope_check.py", "--order", spec["path"], "--repo", spec["checkout"], "--candidate", candidate)
    ref = sealed_ref(spec, candidate)
    selection = state_path(state, "work", spec["order_id"], "CANDIDATE.json")
    selected = {"candidate": candidate, "ref": ref, "order_sha256": spec["sha"]}
    with lock(selection.with_suffix(".lock")):
        plan = approved_plan(state, spec, candidate)
        old = git(repo, "for-each-ref", "--format=%(objectname)", ref)
        if old and old != candidate:
            raise Refused("Candidate ref points to a different commit")
        if not old:
            git(repo, "update-ref", "--create-reflog", ref, candidate, "0" * len(candidate))
        if plan:
            binding = revision_record(state, spec, f"plan-{candidate}.json")
            atomic_write(binding, json_bytes(plan))
        atomic_write(revision_record(state, spec, "CANDIDATE.json"), json_bytes(selected))
        atomic_write(selection, json_bytes(selected))
    print(json.dumps(selected))


def selected_candidate(state, spec):
    path = revision_record(state, spec, "CANDIDATE.json")
    if not path.is_file():
        path = state_path(state, "work", spec["order_id"], "CANDIDATE.json")
    selected = read_json(path) if path.is_file() else {}
    return selected.get("candidate") if selected.get("order_sha256") == spec["sha"] else None


@contextmanager
def candidate_checkout(repo, state, spec, candidate):
    ref = sealed_ref(spec, candidate)
    if git(repo, "for-each-ref", "--format=%(objectname)", ref) == candidate:
        git(repo, "merge-base", "--is-ancestor", spec["base"], candidate)
        with detached_checkout(repo, candidate) as worker:
            yield worker
        return
    if (validate_checkout(repo, state, spec) != candidate or
            git(spec["checkout"], "status", "--porcelain", "--untracked-files=all")):
        raise Refused("Review requires the full candidate SHA checked out in the clean assigned worktree")
    yield spec["checkout"]


def review(repo, state, spec, candidate, rerun):
    with acceptance_lock(state, spec, candidate):
        if not rerun:
            with candidate_checkout(repo, state, spec, candidate) as worker:
                check_review(repo, state, spec, candidate, worker, None)
            return
        with attempt(state, spec, candidate, "auto", executor=executor()) as result:
            with candidate_checkout(repo, state, spec, candidate) as worker:
                check_review(repo, state, spec, candidate, worker, result)
            if result["outcome"] == "RUNNING":
                result["outcome"] = "PASS"
        if result["outcome"] != "PASS":
            raise Refused(f"Latest AUTO attempt is {result['outcome']}")


def check_review(repo, state, spec, candidate, worker, result):
    log = dispatch_check(state, spec)
    brief = approved_brief(state, spec)
    brief_args = ["--brief", brief, "--order-history", state_path(state, "order-history")] if brief else []
    validate_tests(repo, spec, candidate)
    spec_review(state, spec)
    plan = approved_plan(state, spec, candidate)
    folder = state_path(state, "work", spec["order_id"], "evidence")
    report = state_path(state, "work", spec["order_id"], "TASK_REPORT.md")
    report_data = report.read_bytes()
    run_tool("scope_check.py", "--order", spec["path"], "--repo", worker, "--candidate", candidate)
    run_tool("gate_check.py", "--report", report, "--match", report, spec["path"], "--evidence-dir", folder,
             "--dispatch-log", log, "--candidate", candidate, *brief_args)
    if result is None:
        print("CDX_REVIEW candidate/record checks complete; AUTO reruns NOT_RUN")
        return

    expected, rows = gate_check.ac_table(spec["text"]), gate_check.ac_table(report_data.decode("utf-8-sig"))
    checks = {ac: {"outcome": "NOT_RUN"} for ac, row in expected.items() if (row.get("type") or "AUTO") == "AUTO"}
    result["checks"] = checks
    logs = []
    for ac in checks:
        row_result = rows.get(ac, {})
        filename = row_result.get("evidence", "").strip(" `")
        if row_result.get("status") != "PASS" or not re.fullmatch(r"[\w.-]+\.json", filename):
            raise Refused(f"{ac} needs an individual passing evidence record before rerun")
        record = state_path(folder, filename)
        try:
            response = run_tool("evidence_record.py", "verify", record, "--rerun", "--order", spec["path"],
                                "--dispatch-log", log, "--repo", worker, "--candidate", candidate,
                                "--timeout", 180, *brief_args, capture=True, filtered_env=True)
        except ToolFailure as error:
            result.update(failed_check=ac, observation=error.output[-4096:])
            matches = re.findall(r"failed\(rerun exit (-?\d+)\)", error.output)
            result["outcome"] = "FAIL" if matches else "UNKNOWN"
            checks[ac] = {"outcome": result["outcome"], "exit_code": int(matches[-1]) if matches else None}
            return
        verified = [line[len("LOG_LINE: "):] for line in response.splitlines()
                    if line.startswith(f"LOG_LINE: EVIDENCE_RERUN {spec['order_id']} {ac} ")]
        if len(verified) != 1 or f"candidate={candidate} result=ok " not in verified[0]:
            raise Refused(f"No matching independent rerun receipt for {ac}")
        checks[ac] = {"outcome": "PASS", "exit_code": 0, "evidence": filename}
        logs.extend(verified)
    if (report.read_bytes() != report_data or gate_check.order_hash(spec["path"].read_bytes()) != spec["sha"] or
            git(worker, "rev-parse", "HEAD") != candidate):
        raise Refused("The order, report, or candidate changed during review")
    if logs:
        with lock(state / ".dispatch.lock"):
            dispatch_check(state, spec)
            approved_brief(state, spec)
            existing = log.read_text(encoding="utf-8-sig").splitlines()
            additions = [line for line in logs if line not in existing]
            if additions:
                with log.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(additions) + "\n")
    receipt = state_path(state, "reviews", f"{spec['order_id']}-{candidate}.json")
    if receipt.is_file():
        previous = receipt.read_bytes()
        digest = hashlib.sha256(previous).hexdigest()
        history = state_path(state, "reviews", "receipt-history", spec["order_id"], f"{candidate}-{digest}.json")
        if not history.exists():
            atomic_write(history, previous)
        elif history.read_bytes() != previous:
            raise Refused("Archived review receipt does not match its digest")
    result["report_sha256"] = gate_check.order_hash(report_data)
    atomic_write(receipt, json_bytes({"candidate": candidate, "order_sha256": spec["sha"], "auto": logs,
                                      "plan_sha256": plan["plan_sha256"] if plan else None,
                                      "report_sha256": result["report_sha256"], "recorded": stamp(),
                                      "attempt": result["id"],
                                      "po": "PENDING_PO"}))
    print(f"CDX_REVIEW AUTO_RERUNS={len(logs)} receipt={receipt}; REVIEW and PO still separate")


def final_review(repo, state, spec, candidate, artifact=None):
    with acceptance_lock(state, spec, candidate):
        with candidate_checkout(repo, state, spec, candidate):
            check_final(state, spec, candidate, artifact)


def e2e_kind(spec):
    if re.search(r"^[ \t]*E2E_COMMAND[ \t]*=", spec["text"], re.M):
        return "e2e"
    return "manual_e2e"


def check_final(state, spec, candidate, artifact, *, emit=True):
    dispatch_check(state, spec)
    approved_brief(state, spec)
    if artifact is None and artifact_required(state, spec, candidate):
        raise Refused("This candidate requires a build artifact. Supply its SHA-256 with --artifact.")
    latest = latest_attempts(state, spec, candidate, artifact)
    required_e2e = e2e_kind(spec)
    for kind in ("auto", required_e2e):
        result = latest.get(kind, {}).get("outcome", "NOT_RUN")
        if result != "PASS":
            raise Refused(f"{kind}={result}. Record a current successful attempt.")
    gates = spec.get("gates", {})
    if gates.get("feasibility") or gates.get("pre_tr"):
        proof_kind = "e2e" if required_e2e == "e2e" else "preflight"
        proof = latest.get(proof_kind, {})
        if (proof.get("outcome") != "PASS" or proof.get("feasibility_sha256") != feasibility(state, spec) or
                (gates.get("pre_tr") and proof.get("pre_tr", {}).get("exit_code") != 0)):
            raise Refused("The current candidate needs successful preflight evidence")
    manual_ruler = gates.get("ruler") and required_e2e == "manual_e2e"
    if gates.get("ruler"):
        kind = "evidence" if manual_ruler else "e2e"
        if latest.get(kind, {}).get("ruler", {}).get("exit_code") != 0:
            raise Refused("The current candidate needs a valid ruler result")
    report = state_path(state, "work", spec["order_id"], "TASK_REPORT.md")
    report_data = report.read_bytes()
    receipt = read_json(state_path(state, "reviews", f"{spec['order_id']}-{candidate}.json"))
    if (receipt.get("candidate") != candidate or receipt.get("order_sha256") != spec["sha"] or
            receipt.get("report_sha256") != gate_check.order_hash(report_data) or
            receipt.get("attempt") != latest["auto"]["id"]):
        raise Refused("Independent review receipt is for a different order, report or candidate")
    if receipt.get("plan_sha256") or revision_record(state, spec, f"plan-{candidate}.json").is_file():
        plan = approved_plan(state, spec, candidate)
        if not plan or receipt.get("plan_sha256") != plan["plan_sha256"]:
            raise Refused("Independent review receipt does not match the sealed plan")
    results = re.findall(r"^[ \t]*RESULT:[ \t]*(\S+)[ \t]*\r?$", report_data.decode("utf-8-sig"), re.M)
    if results != ["PASS"]:
        raise Refused("Final review needs a passing candidate report")
    if latest[required_e2e].get("artifact") != artifact:
        raise Refused("Latest E2E tested a different build artifact")
    evidence = latest.get("evidence", {})
    if gates.get("pack") or gates.get("audit") or manual_ruler:
        if evidence.get("outcome") != "PASS":
            raise Refused("Current candidate needs work verify-evidence")
        if gates.get("pack") and evidence.get("pack_sha256") != pack_digest(state, spec)[1]:
            raise Refused("Evidence pack changed after verification")
        if gates.get("audit"):
            log = state_path(state, "audit", f"{spec['order_id']}-worker.jsonl")
            audit = evidence.get("audit", {})
            if (audit.get("report_sha256") != hashlib.sha256(report_data).hexdigest() or
                    audit.get("audit_sha256") != file_hash(log)):
                raise Refused("Report or externally anchored audit changed after verification")
    manual = latest.get("manual_e2e")
    if manual and manual["outcome"] != "PASS":
        raise Refused(f"manual_e2e={manual['outcome']}")
    decisions = current_judgments(state, spec, candidate, artifact)
    pending = []
    for ac, record in sorted(decisions.items()):
        kind, outcome = record["kind"], record["outcome"]
        if outcome in ("NOT_RUN", "LEGACY_NEEDS_VERIFICATION"):
            pending.append(f"{kind.upper()} {ac} ({outcome})")
            continue
        if outcome != "PASS":
            raise Refused(f"{kind}={outcome} ({ac})")
        if kind == "po" and gates.get("po_reply"):
            digest = record.get("reply_sha256")
            if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or not record.get("reply_ref") or
                    file_hash(state_path(state, "po-replies", f"{digest}.txt")) != digest):
                raise Refused(f"{ac} needs the PO's original reply and source reference")
    status = {"candidate": candidate, "order_sha256": spec["sha"], "artifact": artifact, "product": "PENDING" if pending else "PASS",
              "pending": pending, "integration": "CHECK_RELEASE_TARGET_SEPARATELY"}
    if emit:
        print(json.dumps(status))
    if pending:
        raise Refused(f"Product check passed. Waiting for {', '.join(pending)}")
    if emit:
        print(f"CDX_FINAL candidate={candidate} scope=single-order")
    proofs = {kind: latest[kind]["id"] for kind in ("auto", "e2e", "manual_e2e", "review", "po", "preflight", "evidence")
              if kind in latest}
    if decisions:
        proofs["criteria"] = {ac: record["id"] for ac, record in sorted(decisions.items())}
    return proofs


def e2e(repo, state, spec, args):
    preflight = args.command == "preflight"
    kind = "preflight" if preflight else "e2e"
    input_root = Path(args.input_root).resolve() if args.input_root else None
    with acceptance_lock(state, spec, args.candidate):
        dispatch_check(state, spec)
        approved_brief(state, spec)
        pinned_path = spec.get("gates", {}).get("artifact_path")
        artifact_path = args.artifact_path
        if not preflight:
            if pinned_path and artifact_path and artifact_path != pinned_path:
                raise Refused("Use the artifact path pinned by the dispatched work order")
            artifact_path = pinned_path or artifact_path
            if not artifact_path and artifact_required(state, spec, args.candidate):
                raise Refused("This candidate requires --artifact-path for each E2E rerun")
            if artifact_path and Path(artifact_path).is_absolute():
                raise Refused("Artifact path must be relative to the candidate")
        with attempt(state, spec, args.candidate, kind, artifact=None, artifact_path=artifact_path) as record:
            command = None if preflight else json.loads(field(spec["text"], "E2E_COMMAND", allow_comment=False))
            if not preflight and not isinstance(command, list):
                raise Refused("E2E_COMMAND must contain an approved JSON argv array")
            with candidate_checkout(repo, state, spec, args.candidate):
                plan = None if preflight else e2e_run_plan(repo, spec, args.candidate)
                run_entry(repo, args.candidate, command, args.timeout, record, artifact_path, plan=plan,
                          gates=(state, spec), input_root=input_root, preflight_only=preflight)
                dispatch_check(state, spec)
        print(json.dumps(record, ensure_ascii=False))
        return 0 if record["outcome"] == "PASS" else 2


def e2e_run_plan(repo, spec, candidate):
    if not re.search(r"^[ \t]*E2E_RUN_PLAN[ \t]*=", spec["text"], re.M):
        return None
    plan = json.loads(field(spec["text"], "E2E_RUN_PLAN", allow_comment=False))
    if (not isinstance(plan, dict) or
            not isinstance(plan.get("file"), str) or not isinstance(plan.get("run"), str) or
            not re.fullmatch(r"[A-Za-z0-9_.-]+", plan["run"])):
        raise Refused("E2E_RUN_PLAN must specify a repo-relative file and a run name")
    if locked_hash(repo, spec["base"], plan["file"]) != locked_hash(repo, candidate, plan["file"]):
        raise Refused("The E2E run plan differs from the plan pinned at the baseline")
    data = git(repo, "show", f"{candidate}:{plan['file']}", raw=True)
    manifest = json.loads(data.decode("utf-8-sig"))
    runs = manifest.get("runs") if isinstance(manifest, dict) else None
    if not isinstance(runs, dict) or not isinstance(runs.get(plan["run"]), dict):
        raise Refused("The pinned E2E run plan does not contain the named run")
    return dict(plan, data=data)


def judgment(repo, state, spec, args):
    with acceptance_lock(state, spec, args.candidate):
        dispatch_check(state, spec)
        approved_brief(state, spec)
        if args.artifact is None and artifact_required(state, spec, args.candidate):
            raise Refused("This candidate requires --artifact for recorded judgments")
        if not all(value.strip() for value in (args.actor, args.environment, args.entry, args.expected, args.observed)):
            raise Refused("Record actor, environment, entry point, expected and observed behavior")
        criteria = judgment_criteria(spec, args.kind) if args.kind in ("review", "po") else set()
        chosen = set(args.ac)
        if chosen - criteria or len(chosen) != len(args.ac):
            raise Refused("Each --ac needs a distinct criterion of the selected judgment kind")
        if len(criteria) > 1 and not chosen:
            raise Refused(f"Select the exact criteria with --ac: {', '.join(sorted(criteria))}")
        matrix = spec.get("gates", {}).get("environments", {})
        scoped = (chosen or criteria) & matrix.keys()
        env_id = args.environment_id
        if scoped:
            env_id = env_id or args.environment.strip().casefold()
            for ac in sorted(scoped):
                if env_id not in matrix[ac]:
                    raise Refused(f"{ac}: use --environment-id from {', '.join(matrix[ac])}")
        elif env_id is not None:
            raise Refused("--environment-id requires a criterion with declared environments")
        reply = {}
        if args.reply_file or args.reply_ref or (args.kind == "po" and spec.get("gates", {}).get("po_reply")):
            if args.kind != "po" or not args.reply_file or not (args.reply_ref or "").strip():
                raise Refused("PO replies need both --reply-file and --reply-ref")
            raw = args.reply_file.read_bytes()
            if not raw.decode("utf-8-sig").strip():
                raise Refused("The original PO reply is empty")
            digest = hashlib.sha256(raw).hexdigest()
            path = state_path(state, "po-replies", f"{digest}.txt")
            if path.is_file() and file_hash(path) != digest:
                raise Refused("Original PO reply was changed")
            if not path.is_file():
                atomic_write(path, raw)
            reply = {"reply_sha256": digest, "reply_ref": args.reply_ref}
        with candidate_checkout(repo, state, spec, args.candidate):
            kind = "manual_e2e" if args.kind == "e2e" else args.kind
            with attempt(state, spec, args.candidate, kind, source="operator-recorded", actor=args.actor,
                         environment=args.environment, entry_point=args.entry, expected=args.expected,
                         observed=args.observed, artifact=args.artifact, criteria=sorted(chosen or criteria),
                         **({"environment_id": env_id} if env_id else {}),
                         **reply) as record:
                record["outcome"] = args.outcome
        print(json.dumps(record, ensure_ascii=False))


def verify_evidence(repo, state, spec, args):
    gates = spec["gates"]
    manual_ruler = gates.get("ruler") if e2e_kind(spec) == "manual_e2e" else None
    if not gates.get("pack") and not gates.get("audit") and not manual_ruler:
        raise Refused("Dispatch the required pack, audit or device ruler proof in CDX_GATES first")
    with acceptance_lock(state, spec, args.candidate):
        dispatch_check(state, spec)
        approved_brief(state, spec)
        if args.artifact is None and artifact_required(state, spec, args.candidate):
            raise Refused("This candidate requires --artifact for verified evidence")
        with candidate_checkout(repo, state, spec, args.candidate):
            with attempt(state, spec, args.candidate, "evidence", artifact=args.artifact) as record:
                record["outcome"] = "PASS"
                if manual_ruler:
                    if not args.ruler_log:
                        raise Refused("Supply actual device output with --ruler-log")
                    raw = args.ruler_log.read_bytes()
                    record["ruler_log_sha256"] = hashlib.sha256(raw).hexdigest()
                    if not ruler_check(manual_ruler, raw, record):
                        record["outcome"] = "INVALID"
                if gates.get("pack"):
                    pack, digest = pack_digest(state, spec)
                    result = invoke("pack_check.py", ["check", str(pack)])
                    record["pack_sha256"] = digest
                    record["pack_check"] = tail(result)
                    if result.returncode or pack_digest(state, spec)[1] != digest:
                        record["outcome"] = "FAIL"
                if gates.get("audit"):
                    if not args.anchor:
                        raise Refused("Supply the independently saved audit head with --anchor")
                    if (within(args.anchor.resolve(), state_path(state, "work")) or
                            within(args.anchor.resolve(), spec["checkout"])):
                        raise Refused("Keep the audit anchor outside worker-controlled directories")
                    bound = state_path(state, "sessions", f"{spec['order_id']}-worker.json")
                    worker = read_json(bound) if bound.is_file() else {}
                    session = desktop_chat(state, spec)
                    if (not session and worker.get("order_sha256") == spec["sha"] and
                            worker.get("worktree") == str(spec["checkout"])):
                        session = worker.get("thread")
                    if not session:
                        raise Refused("Register the worker session or Desktop chat before auditing its claims")
                    report = state_path(state, "work", spec["order_id"], "TASK_REPORT.md")
                    log = state_path(state, "audit", f"{spec['order_id']}-worker.jsonl")
                    record["audit"] = check_report(report, log, session, args.anchor, strict=True)
                    if record["audit"]["outcome"] != "PASS":
                        record["outcome"] = "FAIL"
        print(json.dumps(record, ensure_ascii=False))
        return 0 if record["outcome"] == "PASS" else 2


def integration_request(repo, args):
    if (not SHA.fullmatch(args.base) or not args.target.startswith(("refs/heads/", "refs/remotes/")) or
            git(repo, "rev-parse", "--verify", args.target + "^{commit}") != args.base):
        raise Refused("Pin the current full target ref and commit before integration")
    command = json.loads(args.argv_file.read_bytes() if getattr(args, "argv_file", None) else args.argv)
    if (not isinstance(command, list) or not command or
            not all(isinstance(part, str) and part.strip() and "\0" not in part for part in command)):
        raise Refused("Supply the approved integration entry point as a JSON argv array")
    return command


def integrate(repo, state, args):
    command = integration_request(repo, args)
    artifacts = {}
    for item in args.member_artifact:
        filename, separator, digest = item.partition("=")
        if not separator or filename in artifacts or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise Refused("Each member artifact is a unique ORDER.md=FULL_ARTIFACT_SHA256")
        artifacts[filename] = digest
    members = []
    for item in args.member:
        filename, separator, candidate = item.partition("=")
        if not separator:
            raise Refused("Each member is ORDER.md=FULL_CANDIDATE_SHA")
        spec = active_order(state, filename)
        ref = sealed_ref(spec, candidate)
        if (git(repo, "for-each-ref", "--format=%(objectname)", ref) != candidate or
                selected_candidate(state, spec) != candidate):
            raise Refused(f"Select the sealed candidate for {filename} before integration")
        artifact = artifacts.pop(filename, None)
        with acceptance_lock(state, spec, candidate):
            proofs = check_final(state, spec, candidate, artifact, emit=False)
        members.append({"order": spec["order_id"], "filename": filename, "order_sha256": spec["sha"],
                        "candidate": candidate, "artifact": artifact, "proofs": proofs})
    if artifacts or not members or len({item["order"] for item in members}) != len(members):
        raise Refused("Select one or more distinct work orders and match each artifact to a selected member")
    config = read_json(state_path(state, "director_work.json"))
    if not args.approval and (config.get("cdx_require_integration_approval") or any(row["artifact"] for row in members)):
        raise Refused("Approve the integration entry and delivery contract before integrating")
    delivery = (integration_approval(state, args.approval, args.target, args.base, command) if args.approval
                else {"mode": "source", "outputs": [], "require_po": False})
    series = integration_series(state, args.target, args.base, members)
    series.parent.mkdir(parents=True, exist_ok=True)
    with lock(series.with_suffix(".lock")):
        return run_integration(repo, state, args, members, command, series, delivery=delivery)


def integration_series(state, target, base, members):
    # Retries of an ordered combination supersede one another even if the check command changes.
    identity = [target, base, [[row["order"], row["order_sha256"], row["candidate"], row["artifact"]]
                               for row in members]]
    digest = hashlib.sha256(json_bytes(identity)).hexdigest()
    return state_path(state, "integrations", "latest", f"{digest}.json")


def run_integration(repo, state, args, members, command, series, *, delivery=None):
    integration = str(uuid.uuid4())
    path = state_path(state, "integrations", f"{integration}.json")
    result = {"schema": 3, "id": integration, "target": args.target, "base": args.base,
              "members": members, "outcome": "RUNNING", "started": stamp(), "command": command}
    result["approval"] = getattr(args, "approval", None)
    result["delivery"] = delivery or {"mode": "source", "outputs": [], "require_po": False}
    atomic_write(path, json_bytes(result))
    atomic_write(series, json_bytes({"id": integration}))
    try:
        with detached_checkout(repo, args.base) as worker:
            for member in members:
                merge_mode = "--no-ff"
                if len(members) == 1 and subprocess.run(
                        ["git", "-C", str(repo), "merge-base", "--is-ancestor", args.base, member["candidate"]],
                        env=git_environment(), capture_output=True).returncode == 0:
                    merge_mode = "--ff-only"
                try:
                    git(worker, "-c", f"core.hooksPath={worker.parent / 'no-hooks'}", "-c", "commit.gpgSign=false",
                        "-c", "rerere.enabled=false",
                        "-c", "user.name=cdxdw integration", "-c", "user.email=cdxdw@example.invalid",
                        "merge", merge_mode, "--no-edit", member["candidate"])
                except Refused:
                    result.update(outcome="MERGE_FAILED", failed_member=member["order"])
                    return 2
            head = git(worker, "rev-parse", "HEAD")
            result["head"] = head
            result["tree"] = git(worker, "rev-parse", "HEAD^{tree}")
            git(repo, "update-ref", f"refs/cdxdw/integrations/{integration}", head, "0" * len(head))
            run_entry(repo, head, command, args.timeout, result, delivery_outputs=result["delivery"]["outputs"],
                      delivery_state=state, build_context=result["delivery"].get("build_context", "snapshot"))
        if integration_stale(repo, state, result):
            result["outcome"] = "STALE"
        return 0 if result["outcome"] == "PASS" else 2
    except (KeyboardInterrupt, OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError):
        result["outcome"] = "UNKNOWN"
        raise
    finally:
        result["finished"] = stamp()
        atomic_write(path, json_bytes(result))
        print(json.dumps(result, ensure_ascii=False))


def integration_stale(repo, state, result, landed_head=None):
    try:
        target = landed_head or git(repo, "rev-parse", "--verify", result["target"] + "^{commit}")
        if target_position(repo, result, target) == "TARGET_CHANGED":
            return True
        integration_ref = f"refs/cdxdw/integrations/{result['id']}"
        if git(repo, "for-each-ref", "--format=%(objectname)", integration_ref) != result.get("head"):
            return True
        if result.get("tree") and git(repo, "rev-parse", f"{result['head']}^{{tree}}") != result["tree"]:
            return True
        if result.get("approval"):
            if integration_approval(state, result["approval"], result["target"], result["base"], result["command"]) != result["delivery"]:
                return True
        for member in result["members"]:
            spec = active_order(state, member["filename"])
            candidate = member["candidate"]
            if (spec["sha"] != member["order_sha256"] or selected_candidate(state, spec) != candidate or
                    git(repo, "for-each-ref", "--format=%(objectname)", sealed_ref(spec, candidate)) != candidate):
                return True
            with acceptance_lock(state, spec, candidate):
                actual = check_final(state, spec, candidate, member["artifact"], emit=False)
                if result.get("schema") == 2:
                    actual.pop("criteria", None)
                if actual != member["proofs"]:
                    return True
    except (Refused, OSError):
        return True
    return False


def recorded_integration(state, identifier):
    if str(uuid.UUID(identifier)) != identifier:
        raise Refused("Use the integration UUID")
    result = read_json(state_path(state, "integrations", f"{identifier}.json"))
    if result.get("id") != identifier:
        raise Refused("Integration receipt ID does not match this attempt")
    return result


def integration_receipt(repo, state, identifier, expected_head=None, *, landed_head=None):
    result = recorded_integration(state, identifier)
    if result["outcome"] == "PASS":
        if result.get("schema") not in (2, 3) or (
                result["schema"] == 2 and any(row.get("artifact") for row in result["members"])):
            result["outcome"] = "LEGACY_NEEDS_VERIFICATION"
        else:
            series = integration_series(state, result["target"], result["base"], result["members"])
            with lock(series.with_suffix(".lock")):
                if (not series.is_file() or read_json(series).get("id") != identifier or
                        integration_stale(repo, state, result, landed_head)):
                    result["outcome"] = "STALE"
    if expected_head is not None:
        if not SHA.fullmatch(expected_head):
            raise Refused("Use the full delivery commit SHA")
        result["expected_head"] = expected_head
    if result["outcome"] == "PASS":
        current = landed_head or git(repo, "rev-parse", "--verify", result["target"] + "^{commit}")
        position = target_position(repo, result, current)
        if expected_head is not None and result["head"] != expected_head and not (
                expected_head == current and position == "LANDED_EQUIVALENT_TREE"):
            result["outcome"] = "WRONG_DELIVERY_HEAD"
        else:
            result.update(target_head=current, delivery_state=position, po_delivery=delivery_po_status(state, result))
    product = result.get("po_delivery", "NOT_RUN")
    publication = {"state": "BLOCKED"}
    if result["outcome"] != "PASS":
        publication["reason"] = f"Integration is {result['outcome']}"
    elif result.get("schema") == 3 and not result.get("approval"):
        publication["reason"] = "Approve and rerun integration"
    elif product not in ("PASS", "NOT_REQUIRED"):
        publication["reason"] = f"Integrated product judgment is {product}"
    elif result["delivery_state"] == "LANDING_PENDING":
        publication["reason"] = "Land the verified delivery tree first"
    else:
        publication.update(state="CI_REQUIRED", reason="Verify current target-branch CI before publishing")
    result["publication"] = publication
    return result


def integration_status(repo, state, identifier, expected_head=None):
    result = integration_receipt(repo, state, identifier, expected_head)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["outcome"] == "PASS" else 2


def delivery_file(state, args):
    result = recorded_integration(state, args.id)
    output = result.get("outputs", {}).get(args.asset)
    if not output or result["outcome"] != "PASS":
        raise Refused("Choose an output from a successful integration receipt")
    if args.command == "import-delivery":
        retain_output(state, args.id, args.asset, args.file, expected=output["sha256"])
    path = checked_retained(state, args.id, args.asset, output)
    print(json.dumps({"integration": args.id, "asset": args.asset, "path": str(path),
                      "sha256": output["sha256"], "bytes": path.stat().st_size}, ensure_ascii=False))


def order_status(repo, state, spec, candidate, artifact=None):
    records = gate_check.dispatch_records(state_path(state, "DIRECTOR_LOG.md").read_text(encoding="utf-8-sig"))
    current = records.get(spec["order_id"]) == (str(spec["revision"]), spec["sha"])
    sessions = {}
    for role in ("worker", "reviewer"):
        path = state_path(state, "sessions", f"{spec['order_id']}-{role}.json")
        if path.is_file():
            record = read_json(path)
            sessions[role] = {key: record.get(key) for key in ("state", "thread", "turn", "order_sha256")}
    draft = state_path(state, "orders", spec["file"])
    draft_status = "MISSING"
    if draft.is_file():
        draft_status = "SAME" if gate_check.order_hash(draft.read_bytes()) == spec["sha"] else "EDITED"
    prefix = f"refs/cdxdw/candidates/{spec['order_id']}"
    seals = git(repo, "for-each-ref", "--format=%(objectname)", prefix).splitlines()
    candidate = candidate or selected_candidate(state, spec)
    desktop = spec.get("handoff") or desktop_registration(state, spec)
    latest = latest_attempts(state, spec, candidate, artifact) if candidate else {}
    decisions = current_judgments(state, spec, candidate, artifact) if candidate else {}
    statuses = {kind: latest.get(kind, {}).get("outcome", "NOT_RUN")
                for kind in ("auto", "e2e", "manual_e2e", "review", "po", "preflight", "evidence")}
    if statuses["e2e"] == "PASS" and latest["e2e"].get("artifact") != artifact:
        statuses["e2e"] = "DIFFERENT_ARTIFACT"
    final = None
    if candidate and not current:
        final = {"outcome": "SUPERSEDED", "reason": "Historical acceptance belongs to the archived order revision"}
    elif candidate:
        try:
            check_final(state, spec, candidate, artifact, emit=False)
            final = {"outcome": "PASS"}
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            final = {"outcome": "BLOCKED", "reason": str(error)}
    if candidate:
        legacy = {"auto": state_path(state, "reviews", f"{spec['order_id']}-{candidate}.json"),
                  "e2e": state_path(state, "evidence", "E2E", spec["order_id"], f"{candidate}.md")}
        for kind, path in legacy.items():
            if statuses[kind] == "NOT_RUN" and path.is_file():
                statuses[kind] = "LEGACY_NEEDS_VERIFICATION"
    levels = {row.get("type") for row in gate_check.ac_table(spec["text"]).values()}
    required = {"auto", e2e_kind(spec)}
    gates = spec.get("gates", {})
    if e2e_kind(spec) == "manual_e2e" and (gates.get("feasibility") or gates.get("pre_tr")):
        required.add("preflight")
    if gates.get("audit") or gates.get("pack") or (gates.get("ruler") and e2e_kind(spec) == "manual_e2e"):
        required.add("evidence")
    if gates.get("po_reply"):
        required.add("po")
    recorded = {"manual_e2e", "review", "po"} & latest.keys()
    needed = [kind for kind, status in statuses.items()
              if status != "PASS" and (kind in required or kind in recorded or kind.upper() in levels)]
    open_criteria = sorted(ac for ac, record in decisions.items() if record["outcome"] != "PASS")
    engineering = sorted(kind for kind in required | (recorded - {"review", "po"})
                         if kind not in ("review", "po") and statuses[kind] != "PASS")
    if not current:
        product = "SUPERSEDED"
    elif open_criteria:
        product = "BLOCKED" if any(decisions[ac]["outcome"] not in ("NOT_RUN", "LEGACY_NEEDS_VERIFICATION")
                                   for ac in open_criteria) else "PENDING"
    else:
        product = "PASS" if final and final["outcome"] == "PASS" else "PENDING"
    next_step = "Consult the active order revision for current work" if not current else (
        "Choose or seal a candidate") if not candidate else (
        "Resolve " + ", ".join(needed) if needed else
        "Run final for this candidate" if final["outcome"] == "PASS" else final["reason"])
    plan_binding = revision_record(state, spec, f"plan-{candidate}.json")
    print(json.dumps({"order": spec["order_id"], "revision": spec["revision"], "order_sha256": spec["sha"],
                      "snapshot": str(spec["path"]), "revision_state": "ACTIVE" if current else "SUPERSEDED",
                      "draft": draft_status, "sessions": sessions,
                      "desktop": desktop or None,
                      "resume": str(resume_location(state, spec)),
                      "sealed_plan": read_json(plan_binding) if plan_binding.is_file() else None,
                      "checkout": str(spec["checkout"]), "handoff": spec.get("handoff"),
                      "source_checkout": field(spec["text"], "WORKTREE"), "source_work_dir": field(spec["text"], "WORK_DIR"),
                      "sealed_candidates": seals, "candidate": candidate, "artifact": artifact, "acceptance": statuses,
                      "criteria": {ac: {key: row.get(key) for key in ("kind", "outcome", "id", "reply_ref")}
                                   for ac, row in sorted(decisions.items())},
                      "engineering": {"outcome": "PENDING" if engineering else "PASS", "unresolved": engineering},
                      "product": {"outcome": product, "unresolved": open_criteria},
                      "final": final, "next": next_step}, ensure_ascii=False))


def plan_approval(state, spec, *, save=False, head=None, approver=None):
    plan_file = state_path(state, "work", spec["order_id"], "PLAN.md")
    payload = plan_file.read_bytes()
    if not payload.strip():
        raise Refused("PLAN.md must contain the reviewed plan")
    path = state_path(state, "reviews", f"{spec['order_id']}-plan.json")
    digest = hashlib.sha256(payload).hexdigest()
    snapshot = state_path(state, "reviews", f"{spec['order_id']}-PLAN-{digest}.md")
    expected = {"order_sha256": spec["sha"], "plan_sha256": digest}
    if spec.get("gates", {}).get("feasibility"):
        expected["feasibility_sha256"] = feasibility(state, spec)
    if save:
        if snapshot.exists():
            if snapshot.read_bytes() != payload:
                raise Refused("The archived plan does not match its fingerprint")
        else:
            atomic_write(snapshot, payload)
        previous = read_json(path) if path.is_file() else {}
        if previous and all(previous.get(key) == value for key, value in expected.items()):
            return snapshot
        revision = previous.get("plan_revision", 1) + 1 if previous else 1
        if previous:
            history = state_path(state, "reviews", "plan-history", spec["order_id"],
                                 f"r{revision - 1}-{previous['plan_sha256']}.json")
            raw = json_bytes(previous)
            save_snapshot(history, raw, hashlib.sha256(raw).hexdigest())
        atomic_write(path, json_bytes(dict(expected, recorded=stamp(), plan_revision=revision,
                                          base=spec["base"], worktree_head=head, approver=approver)))
        log_event(state, f"PLAN_APPROVED {spec['order_id']} plan_rev={revision} sha={digest}")
    else:
        actual = read_json(path)
        if (any(actual.get(key) != value for key, value in expected.items()) or
                actual.get("base", spec["base"]) != spec["base"] or snapshot.read_bytes() != payload):
            raise Refused("Plan or order changed after approval")
    return snapshot


def approved_plan(state, spec, candidate):
    if spec["governance"] not in ("Standard", "Strict"):
        return None
    binding = revision_record(state, spec, f"plan-{candidate}.json")
    path = binding if binding.is_file() else state_path(state, "reviews", f"{spec['order_id']}-plan.json")
    record = read_json(path)
    digest = record.get("plan_sha256", "")
    if (record.get("order_sha256") != spec["sha"] or record.get("base", spec["base"]) != spec["base"] or
            not re.fullmatch(r"[0-9a-f]{64}", digest)):
        raise Refused("Approved plan does not match this dispatched order")
    snapshot = state_path(state, "reviews", f"{spec['order_id']}-PLAN-{digest}.md")
    if file_hash(snapshot) != digest:
        raise Refused("Approved plan snapshot does not match its fingerprint")
    return {"order_sha256": spec["sha"], "base": spec["base"], "plan_sha256": digest}


def approve_plan(repo, state, spec, approver):
    worker = state_path(state, "sessions", f"{spec['order_id']}-worker.json")
    with lock(worker.with_suffix(".lock")):
        dispatch_check(state, spec)
        approved_brief(state, spec)
        approval = state_path(state, "reviews", f"{spec['order_id']}-plan.json")
        previous = read_json(approval) if approval.is_file() else {}
        current_head = validate_checkout(repo, state, spec, fresh=not previous and spec["revision"] == 1)
        if previous.get("order_sha256") == spec["sha"]:
            plan_file = state_path(state, "work", spec["order_id"], "PLAN.md")
            if (file_hash(plan_file) != previous["plan_sha256"] or
                    (spec.get("gates", {}).get("feasibility") and
                     feasibility(state, spec) != previous.get("feasibility_sha256"))):
                session = read_json(worker) if worker.is_file() else {}
                if (current_head != (previous.get("worktree_head") or spec["base"]) or
                        git(spec["checkout"], "status", "--porcelain", "--untracked-files=all") or
                        (session.get("order_sha256") == spec["sha"] and
                         (session.get("phase") == "implement" or session.get("state") in ("starting", "running")))):
                    raise Refused("Implementation has begun. Revise and redispatch the work order to approve a new plan.")
        return plan_approval(state, spec, save=True, head=current_head, approver=approver)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("lock-brief", help="snapshot the product brief after the PO has approved it")
    for command in ("prepare", "adopt", "dispatch", "approve-spec", "approve-plan", "sync-worker", "seal", "review", "e2e",
                    "preflight", "verify-evidence", "record", "final", "status"):
        sub = commands.add_parser(command)
        sub.add_argument("order", help="filename inside DIRECTOR/orders")
        if command in ("review", "e2e", "preflight", "verify-evidence", "record", "final", "status"):
            sub.add_argument("--candidate", required=command != "status")
        if command in ("record", "verify-evidence", "final", "status"):
            sub.add_argument("--artifact", help="SHA-256 of the actual build artifact")
        if command == "status":
            sub.add_argument("--revision", type=int, help="read an archived dispatched revision")
        if command in ("e2e", "preflight"):
            sub.add_argument("--timeout", type=int, default=180)
            sub.add_argument("--input-root", help="directory containing approved, hash-pinned pre-TR inputs")
            sub.set_defaults(artifact=None, artifact_path=None)
            if command == "e2e":
                sub.add_argument("--artifact-path", help="hash this built file inside the disposable candidate tree")
        if command == "adopt":
            sub.add_argument("--chat", help="UUID of the Desktop chat for status and handoff")
        if command == "record":
            sub.add_argument("--ac", action="append", default=[], help="exact REVIEW or PO criterion, repeat as needed")
            sub.add_argument("--environment-id", help="stable environment ID declared by this criterion")
            sub.add_argument("--reply-file", type=Path, help="UTF-8 file with the exact original PO reply")
            sub.add_argument("--reply-ref", help="original PO message reference")
            sub.add_argument("--kind", required=True, choices=("e2e", "review", "po"))
            sub.add_argument("--outcome", required=True, choices=("PASS", "FAIL", "CHANGES_REQUESTED"))
            for name in ("actor", "environment", "entry", "expected", "observed"):
                sub.add_argument("--" + name, required=True)
        if command == "verify-evidence":
            sub.add_argument("--anchor", type=Path, help="independently preserved AUDIT_HEAD record")
            sub.add_argument("--ruler-log", type=Path, help="actual device output for a manually run E2E")
        if command == "review":
            sub.add_argument("--rerun", action="store_true", help="execute only the checks pinned in the order")
        elif command == "approve-spec":
            sub.add_argument("--reviewer", required=True)
            sub.add_argument("--author", required=True)
            sub.add_argument("--active", action="store_true", help="approve the dispatched snapshot instead of the draft")
        elif command == "approve-plan":
            sub.add_argument("--approver", help="record the operator-supplied approver identity")
    approval = commands.add_parser("approve-integration", help="pin the integration command and delivery contract")
    approval.add_argument("--target", required=True)
    approval.add_argument("--base", required=True)
    approval_entry = approval.add_mutually_exclusive_group(required=True)
    approval_entry.add_argument("--argv")
    approval_entry.add_argument("--argv-file", type=Path, help="JSON argv file (including for Windows PowerShell)")
    approval.add_argument("--delivery", type=Path, help="source or artifacts delivery JSON")
    approval.add_argument("--approved-by", required=True)
    integration = commands.add_parser("integrate", help="check an ordered combination of sealed candidates")
    integration.add_argument("--target", required=True)
    integration.add_argument("--base", required=True)
    integration.add_argument("--member", action="append", required=True)
    integration.add_argument("--member-artifact", action="append", default=[])
    integration_entry = integration.add_mutually_exclusive_group(required=True)
    integration_entry.add_argument("--argv", help="approved public entry command in JSON argv form")
    integration_entry.add_argument("--argv-file", type=Path, help="JSON argv file")
    integration.add_argument("--approval", help="fingerprint from approve-integration")
    integration.add_argument("--timeout", type=int, default=180)
    integration_check = commands.add_parser("integration-status")
    integration_check.add_argument("id")
    integration_check.add_argument("--expect-head", help="require the exact commit proposed for delivery")
    po_delivery = commands.add_parser("record-delivery", help="record PO judgment for the exact integration outputs")
    po_delivery.add_argument("id")
    po_delivery.add_argument("--outcome", required=True, choices=("PASS", "CHANGES_REQUESTED"))
    po_delivery.add_argument("--actor", required=True)
    po_delivery.add_argument("--reply-file", required=True, type=Path)
    po_delivery.add_argument("--reply-ref", required=True)
    for command in ("delivery-file", "import-delivery"):
        deliver = commands.add_parser(command, help="locate retained output or import an exact previously accepted file")
        deliver.add_argument("id")
        deliver.add_argument("--asset", required=True)
        if command == "import-delivery":
            deliver.add_argument("--file", type=Path, required=True)
    tests = commands.add_parser("lock-tests", help="hash the tests as stored in the baseline commit")
    tests.add_argument("--base", required=True)
    tests.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.command == "lock-tests":
            if not SHA.fullmatch(args.base):
                raise Refused("Use the full base commit SHA")
            print("TESTS_LOCKED:")
            for filename in args.paths:
                print(f"- {filename} sha256={locked_hash(checkout(args.repo), args.base, filename)}")
            return 0
        _, state, project = load_project(args.repo)
        repo = Path(project["repo"])
        if args.command in ("delivery-file", "import-delivery"):
            delivery_file(state, args)
            return 0
        if args.command == "lock-brief":
            lock_brief(state)
            print("CDX_WORK BRIEF_LOCKED")
            return 0
        if args.command == "integrate":
            return integrate(repo, state, args)
        if args.command == "approve-integration":
            command = integration_request(repo, args)
            delivery = read_json(args.delivery) if args.delivery else {"mode": "source"}
            result = approve_integration(state, args.target, args.base, command, delivery, args.approved_by)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command == "record-delivery":
            result = integration_receipt(repo, state, args.id)
            if result["outcome"] != "PASS":
                raise Refused("Only a current passing integration has a delivery to judge")
            print(json.dumps(save_po_delivery(state, result, args), ensure_ascii=False))
            return 0
        if args.command == "integration-status":
            return integration_status(repo, state, args.id, args.expect_head)
        artifact = getattr(args, "artifact", None)
        if artifact is not None and not re.fullmatch(r"[0-9a-f]{64}", artifact):
            raise Refused("Use a full SHA-256 for the build artifact")
        if getattr(args, "timeout", 1) < 1:
            raise Refused("Use a positive timeout")
        if args.command in ("prepare", "adopt", "dispatch") or (args.command == "approve-spec" and not args.active):
            spec = order_spec(state, args.order)
        elif args.command == "status" and args.revision is not None:
            spec = historical_order(state, args.order, args.revision)
        else:
            spec = active_order(state, args.order)
        if args.command == "review":
            review(repo, state, spec, args.candidate, args.rerun)
        elif args.command == "final":
            final_review(repo, state, spec, args.candidate, artifact)
        elif args.command in ("e2e", "preflight"):
            return e2e(repo, state, spec, args)
        elif args.command == "record":
            judgment(repo, state, spec, args)
        elif args.command == "verify-evidence":
            return verify_evidence(repo, state, spec, args)
        elif args.command == "seal":
            seal(repo, state, spec)
        elif args.command == "status":
            order_status(repo, state, spec, args.candidate, artifact)
        elif args.command == "sync-worker":
            validate_checkout(repo, state, spec)
            sync_worker(repo, spec["checkout"], project)
            bind_desktop_chat(state, spec, desktop_chat(state, spec), handoff=spec.get("handoff", {}).get("handoff"))
            print(f"CDX_WORK SYNC_WORKER {spec['order_id']} {spec['checkout']}")
        elif args.command == "approve-plan":
            approve_plan(repo, state, spec, args.approver)
            print(f"CDX_WORK PLAN_APPROVED {spec['order_id']}")
        elif args.command == "approve-spec":
            spec_review(state, spec, reviewer=args.reviewer, author=args.author)
            print(f"CDX_WORK SPEC_REVIEW {spec['order_id']}")
        elif args.command in ("prepare", "adopt"):
            prepare(repo, state, spec, project, adopt=args.command == "adopt", chat=getattr(args, "chat", None))
            print(f"CDX_WORK PREPARE {spec['order_id']} {spec['checkout']}")
        else:
            dispatch(repo, state, spec)
            print(f"CDX_WORK DISPATCH {spec['order_id']} {spec['checkout']}")
            print(f"Worker instructions: approved order {dispatched_copy(state, spec)}. "
                  f"Stay within SCOPE. Resume from {resume_location(state, spec)}. Keep work notes in {spec['work']}.")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
