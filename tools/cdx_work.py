"""Prepare a work order, lock dispatch, and check the exact candidate."""

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_check
from cdx_common import (ORDER_ID, SHA, ROOT, Refused, atomic_write, checkout, common_dir, git, json_bytes,
                        load_project, lock, read_json, report_error, stamp, state_path, within)
from cdx_setup import config_with_hooks


def field(text, key):
    found = re.findall(rf"^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(.+)$", text, re.M)
    if len(found) != 1:
        raise Refused(f"Order needs exactly one {key} field")
    return found[0].split(" #", 1)[0].strip()


def order_spec(state, filename):
    name = Path(filename).name
    if name != filename or not re.fullmatch(r"WO-[0-9]+(?:-[A-Za-z0-9_.-]+)?\.md", name):
        raise Refused("Use an order filename such as WO-001-export.md")
    path = state_path(state, "orders", name)
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    names, problem = gate_check.order_identity(text, path)
    order_id = gate_check.order_key(names)
    if problem or not order_id or not ORDER_ID.fullmatch(order_id):
        raise Refused(problem or "Order does not have a WO-n ID")
    base = field(text, "BASE_REF").rsplit("@", 1)[-1].strip().lower()
    if not SHA.fullmatch(base):
        raise Refused("BASE_REF must pin a complete 40-character commit SHA")
    rev = field(text, "REVISION")
    if not rev.isdigit() or int(rev) < 1:
        raise Refused("Order revision must be a positive integer")
    work = state_path(state, "work", order_id)
    worker_path = Path(field(text, "WORKTREE"))
    if not worker_path.is_absolute() or Path(field(text, "WORK_DIR")) != work:
        raise Refused(f"WORKTREE must be absolute, and WORK_DIR must be {work}")
    return {"order_id": order_id, "file": name, "path": path, "text": text, "sha": gate_check.order_hash(data),
            "revision": int(rev), "base": base, "branch": field(text, "NEW_BRANCH"), "work": work,
            "checkout": worker_path.resolve(), "governance": field(text, "GOVERNANCE")}


def validate_checkout(repo, state, spec, *, fresh=False):
    worker = spec["checkout"]
    if (within(worker, repo) or within(repo, worker) or within(worker, state) or within(state, worker) or
            checkout(worker) != worker or common_dir(worker) != common_dir(repo)):
        raise Refused("Worker must be an isolated worktree of this Git project")
    branch = git(worker, "branch", "--show-current")
    if branch != spec["branch"]:
        raise Refused(f"Expected worktree branch {spec['branch']}; found {branch or 'detached HEAD'}")
    head = git(worker, "rev-parse", "HEAD")
    if fresh and (head != spec["base"] or git(worker, "status", "--porcelain", "--untracked-files=all")):
        raise Refused("Initial worker checkout must be clean at the pinned base")
    git(worker, "merge-base", "--is-ancestor", spec["base"], head)
    return head


def dispatch_check(state, spec):
    log = state_path(state, "DIRECTOR_LOG.md")
    records = gate_check.dispatch_records(log.read_text(encoding="utf-8-sig"))
    if records.get(spec["order_id"]) != (str(spec["revision"]), spec["sha"]):
        raise Refused("Current order revision and hash are not registered in DIRECTOR_LOG.md")
    return log


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
    log = state_path(state, "DIRECTOR_LOG.md")
    with lock(state / ".dispatch.lock"):
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"\n{stamp()} | {event} | cdx\n")


def spec_review(state, spec, *, reviewer=None, author=None):
    if spec["governance"] == "Direct":
        return
    report = state_path(state, "reviews", f"{spec['order_id']}-SPEC_REVIEW.md")
    raw = report.read_bytes()
    if not raw.strip():
        raise Refused("Write the independent spec review before approval")
    expected = {"order_sha256": spec["sha"], "review_sha256": hashlib.sha256(raw).hexdigest()}
    path = state_path(state, "reviews", f"{spec['order_id']}-spec.json")
    if reviewer is not None:
        valid = r"[A-Za-z0-9_.-]+"
        if not re.fullmatch(valid, reviewer) or not re.fullmatch(valid, author) or reviewer == author:
            raise Refused("Supply distinct reviewer and author session identifiers")
        atomic_write(path, json_bytes(dict(expected, reviewer=reviewer, author=author)))
        log_event(state, f"SPEC_REVIEW {spec['order_id']} session={reviewer} author={author} sha={spec['sha']}")
        return
    actual = read_json(path)
    if any(actual.get(key) != value for key, value in expected.items()):
        raise Refused("The order or independent spec review changed after approval")


def run_tool(name, *args, capture=False):
    command = [sys.executable, "-I", "-B", "-X", "utf8", str(ROOT / "tools" / name), *map(str, args)]
    result = subprocess.run(command, capture_output=capture, encoding="utf-8", errors="replace")
    if capture:
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        raise Refused(f"{name} exited {result.returncode}")
    return result.stdout if capture else ""


def prepare(repo, state, spec, project):
    run_tool("gate_check.py", "--order", spec["path"], "--repo", repo,
             "--config", state_path(state, "director_work.json"))
    worker = spec["checkout"]
    if within(worker, repo) or within(repo, worker) or within(worker, state) or within(state, worker):
        raise Refused("Worker checkout must be outside both project and cdx state")
    git(repo, "check-ref-format", "--branch", spec["branch"])
    if not worker.exists():
        git(repo, "worktree", "add", "-b", spec["branch"], "--", str(worker), spec["base"])
    validate_checkout(repo, state, spec, fresh=True)
    if project.get("hooks") and not git(worker, "ls-files", "--", ".codex/hooks.json"):
        hook_file = state_path(worker, ".codex", "hooks.json")
        # A committed ignore exception can override info/exclude. Do not dirty the worker checkout.
        git(worker, "check-ignore", "--", ".codex/hooks.json")
        config = config_with_hooks(hook_file, Path(project["kit"]))
        if not hook_file.exists() or hook_file.read_bytes() != config:
            atomic_write(hook_file, config)
    (spec["work"] / "evidence").mkdir(parents=True, exist_ok=True)
    resume = spec["work"] / "RESUME_STATE.md"
    if not resume.exists():
        text = (f"PROGRESS: worker checkout ready at {spec['base']}\nDOING: read {spec['file']}\n"
                "NEXT_STEP: confirm the dispatched order and prepare a plan\nCOMMS: NONE\n\n"
                f"# RESUME_STATE — {spec['order_id']}\nUPDATED: {stamp()}\n")
        with resume.open("x", encoding="utf-8") as handle:
            handle.write(text)


def dispatch(repo, state, spec):
    validate_checkout(repo, state, spec)
    run_tool("gate_check.py", "--order", spec["path"], "--repo", repo,
             "--config", state_path(state, "director_work.json"))
    validate_tests(repo, spec, spec["base"])
    spec_review(state, spec)
    log = state_path(state, "DIRECTOR_LOG.md")
    with lock(state / ".dispatch.lock"):
        current = log.read_text(encoding="utf-8-sig")
        old = gate_check.dispatch_records(current).get(spec["order_id"])
        if old == (str(spec["revision"]), spec["sha"]):
            return
        if old and spec["revision"] <= int(old[0]):
            raise Refused("A changed work order must increment REVISION before redispatch")
        if old is None:
            validate_checkout(repo, state, spec, fresh=True)
        line = f"{stamp()} | DISPATCH {spec['order_id']} rev={spec['revision']} sha={spec['sha']} | cdx\n"
        with log.open("a", encoding="utf-8") as handle:
            handle.write(("\n" if current and not current.endswith("\n") else "") + line)


def review(repo, state, spec, candidate, rerun):
    log = dispatch_check(state, spec)
    if not SHA.fullmatch(candidate) or validate_checkout(repo, state, spec) != candidate:
        raise Refused("Review requires the full candidate SHA checked out in the assigned worker worktree")
    if git(spec["checkout"], "status", "--porcelain", "--untracked-files=all"):
        raise Refused("Candidate checkout must be clean")
    validate_tests(repo, spec, candidate)
    spec_review(state, spec)
    if spec["governance"] in ("Standard", "Strict"):
        plan_approval(state, spec)
    folder = state_path(state, "work", spec["order_id"], "evidence")
    report = state_path(state, "work", spec["order_id"], "TASK_REPORT.md")
    report_data = report.read_bytes()
    run_tool("scope_check.py", "--order", spec["path"], "--repo", spec["checkout"], "--candidate", candidate)
    run_tool("gate_check.py", "--report", report, "--match", report, spec["path"], "--evidence-dir", folder,
             "--dispatch-log", log, "--candidate", candidate)
    if not rerun:
        print("CDX_REVIEW candidate/record checks complete; AUTO reruns NOT_RUN")
        return

    expected, rows = gate_check.ac_table(spec["text"]), gate_check.ac_table(report_data.decode("utf-8-sig"))
    logs = []
    for ac, row in expected.items():
        if (row.get("type") or "AUTO") != "AUTO":
            continue
        result = rows.get(ac, {})
        filename = result.get("evidence", "").strip(" `")
        if result.get("status") != "PASS" or not re.fullmatch(r"[\w.-]+\.json", filename):
            raise Refused(f"{ac} needs an individual passing evidence record before rerun")
        record = state_path(folder, filename)
        response = run_tool("evidence_record.py", "verify", record, "--rerun", "--order", spec["path"],
                            "--dispatch-log", log, "--repo", spec["checkout"], "--candidate", candidate,
                            "--timeout", 180, capture=True)
        verified = [line[len("LOG_LINE: "):] for line in response.splitlines()
                    if line.startswith(f"LOG_LINE: EVIDENCE_RERUN {spec['order_id']} {ac} ")]
        if len(verified) != 1 or f"candidate={candidate} result=ok " not in verified[0]:
            raise Refused(f"No matching independent rerun receipt for {ac}")
        logs.extend(verified)
    if (report.read_bytes() != report_data or gate_check.order_hash(spec["path"].read_bytes()) != spec["sha"] or
            validate_checkout(repo, state, spec) != candidate):
        raise Refused("The order, report, or candidate changed during review")
    if logs:
        with lock(state / ".dispatch.lock"):
            dispatch_check(state, spec)
            existing = log.read_text(encoding="utf-8-sig").splitlines()
            additions = [line for line in logs if line not in existing]
            if additions:
                with log.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(additions) + "\n")
    receipt = state_path(state, "reviews", f"{spec['order_id']}-{candidate}.json")
    atomic_write(receipt, json_bytes({"candidate": candidate, "order_sha256": spec["sha"], "auto": logs,
                                      "report_sha256": gate_check.order_hash(report_data), "recorded": stamp(),
                                      "po": "PENDING_PO"}))
    print(f"CDX_REVIEW AUTO_RERUNS={len(logs)} receipt={receipt}; REVIEW and PO still separate")


def plan_approval(state, spec, *, save=False):
    plan_file = state_path(state, "work", spec["order_id"], "PLAN.md")
    payload = plan_file.read_bytes()
    if not payload.strip():
        raise Refused("PLAN.md must contain the reviewed plan")
    path = state_path(state, "reviews", f"{spec['order_id']}-plan.json")
    digest = hashlib.sha256(payload).hexdigest()
    snapshot = state_path(state, "reviews", f"{spec['order_id']}-PLAN-{digest}.md")
    expected = {"order_sha256": spec["sha"], "plan_sha256": digest}
    if save:
        if not snapshot.exists():
            atomic_write(snapshot, payload)
        atomic_write(path, json_bytes(dict(expected, recorded=stamp())))
        log_event(state, f"PLAN_APPROVED {spec['order_id']} sha={digest}")
    else:
        actual = read_json(path)
        if any(actual.get(key) != value for key, value in expected.items()) or snapshot.read_bytes() != payload:
            raise Refused("Plan or order changed after approval")
    return snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "dispatch", "approve-spec", "approve-plan", "review"):
        sub = commands.add_parser(command)
        sub.add_argument("order", help="filename inside DIRECTOR/orders")
        if command == "review":
            sub.add_argument("--candidate", required=True)
            sub.add_argument("--rerun", action="store_true", help="execute only the checks pinned in the order")
        elif command == "approve-spec":
            sub.add_argument("--reviewer", required=True)
            sub.add_argument("--author", required=True)
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
        spec = order_spec(state, args.order)
        if args.command == "review":
            review(repo, state, spec, args.candidate, args.rerun)
        elif args.command == "approve-plan":
            dispatch_check(state, spec)
            if spec["revision"] == 1:
                approval = state_path(state, "reviews", f"{spec['order_id']}-plan.json")
                if not approval.exists():
                    validate_checkout(repo, state, spec, fresh=True)
                else:
                    plan_approval(state, spec)
            plan_approval(state, spec, save=True)
            print(f"CDX_WORK PLAN_APPROVED {spec['order_id']}")
        elif args.command == "approve-spec":
            spec_review(state, spec, reviewer=args.reviewer, author=args.author)
            print(f"CDX_WORK SPEC_REVIEW {spec['order_id']}")
        elif args.command == "prepare":
            prepare(repo, state, spec, project)
            print(f"CDX_WORK PREPARE {spec['order_id']} {spec['checkout']}")
        else:
            dispatch(repo, state, spec)
            print(f"CDX_WORK DISPATCH {spec['order_id']} {spec['checkout']}")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
