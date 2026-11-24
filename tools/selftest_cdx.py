"""Exercise the cdx setup, work-order, evidence, and recovery contract offline."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cdx_audit
import cdx_hook
import cdx_session
import gate_check
from cdx_acceptance import attempt
from cdx_common import ROOT, Refused, atomic_write, git, json_bytes, load_project, lock, read_json
from cdx_usage import summarize_app
from cdx_work import order_spec


def text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class CDX(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.gettempdir()).resolve()
        self.temp = tempfile.TemporaryDirectory(prefix="cdx-suite-", dir=base)
        self.root = Path(self.temp.name).resolve()
        self.assertEqual(self.root.parent, base)
        self.assertTrue(self.root.name.startswith("cdx-suite-"))
        self.addCleanup(self.temp.cleanup)

    def run_script(self, tool, *args, code=0):
        result = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str(ROOT / "tools" / tool), *map(str, args)],
                                cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def git_project(self, name):
        repo = self.root / name
        repo.mkdir()
        git(repo, "init", "-b", "main", "--template=")
        git(repo, "config", "user.name", "cdx fixture")
        git(repo, "config", "user.email", "cdx@example.invalid")
        git(repo, "config", "commit.gpgSign", "false")
        git(repo, "config", "core.autocrlf", "false")
        git(repo, "config", "core.hooksPath", ".git/cdx-fixture-no-hooks")
        return repo

    def work(self, repo, *args, code=0):
        return self.run_script("cdxdw.py", "work", "--repo", repo, *args, code=code)

    def test_install_is_idempotent_and_preserves_existing_files(self):
        repo = self.git_project("主 project")
        agents = repo / "AGENTS.md"
        text(agents, "# existing\nKeep this text.\n")
        custom_hook = {"matcher": "startup", "hooks": [{"type": "command", "command": "echo fixture"}]}
        hook_path = repo / ".codex" / "hooks.json"
        text(hook_path, json.dumps({"hooks": {"SessionStart": [custom_hook]}}))
        state = self.root / "DIRECTOR 外部"
        args = ("setup", "--repo", repo, "--state", state, "--agents", "--hooks")
        self.assertIn("CDX_SETUP PLAN", self.run_script("cdxdw.py", *args))
        self.assertFalse(state.exists())
        self.assertIn("CDX_SETUP COMPLETE", self.run_script("cdxdw.py", *args, "--apply"))
        self.assertTrue(agents.read_bytes().startswith(b"# existing\nKeep this text.\n"))
        self.assertEqual(read_json(hook_path)["hooks"]["SessionStart"][0], custom_hook)
        _, loaded, info = load_project(repo)
        self.assertEqual(loaded, state)
        self.assertEqual(len(info["managed_skills"]), 5)
        kit = Path(info["kit"])
        self.assertTrue((kit / "tools" / "gate_check.py").is_file())
        (state / "PO_PENDING.md").write_bytes(b"PO draft in progress\n")
        self.assertIn("changed=0", self.run_script("cdxdw.py", *args, "--apply"))
        self.assertEqual((state / "PO_PENDING.md").read_bytes(), b"PO draft in progress\n")
        hooks = read_json(hook_path)
        managed_group = hooks["hooks"]["PreToolUse"][0]
        managed_group["matcher"] = "Bash"
        managed_group["hooks"][0].update(timeout=15, enabled=False)
        atomic_write(hook_path, json_bytes(hooks))
        self.assertIn("changed=0", self.run_script("cdxdw.py", *args, "--apply"))
        self.assertEqual(read_json(hook_path), hooks)
        self.run_script("cdxdw.py", "setup", "--repo", repo, "--no-hooks", "--apply")
        self.assertEqual(read_json(hook_path)["hooks"]["SessionStart"], [custom_hook])
        self.assertFalse(load_project(repo)[2]["hooks"])
        self.run_script("cdxdw.py", *args, "--apply")
        conflict = self.git_project("other")
        self.assertIn("belongs", self.run_script("cdxdw.py", "setup", "--repo", conflict, "--state", state, code=2))
        managed = repo / ".agents" / "skills" / "cdx-resume" / "SKILL.md"
        managed.write_bytes(b"local customization\n")
        self.assertIn("contains local edits", self.run_script("cdxdw.py", *args, "--apply", code=2))
        self.assertEqual(managed.read_bytes(), b"local customization\n")

    def test_shared_state_is_reserved_by_one_project(self):
        first, second = self.git_project("first"), self.git_project("second")
        shared = self.root / "shared"

        def install(repo):
            return subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str(ROOT / "tools" / "cdxdw.py"),
                                   "setup", "--repo", str(repo), "--state", str(shared), "--apply"],
                                  capture_output=True, encoding="utf-8", errors="replace", timeout=60).returncode

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(install, [first, second]))
        self.assertCountEqual(results, [0, 2])
        winner, loser = (first, second) if results[0] == 0 else (second, first)
        self.assertEqual(load_project(winner)[1], shared)
        self.assertFalse((loser / ".git" / "director-work-cdx.json").exists())
        self.assertEqual(install(loser), 2)

    def test_work_order_full_flow_and_wrong_candidate(self):
        repo = self.git_project("repo")
        text(repo / "calc.txt", "broken\n")
        force_failure = self.root / "fail check"
        text(repo / "verify.py", "from pathlib import Path\nimport os\n"
             "assert not os.getenv('CDXDW_TEST_SECRET')\n"
             "assert Path('calc.txt').read_text().startswith('42\\n')\n"
             f"assert not Path({str(force_failure)!r}).exists()\n")
        git(repo, "add", "--", "calc.txt", "verify.py")
        git(repo, "commit", "-m", "baseline")
        base = git(repo, "rev-parse", "HEAD")
        self.run_script("cdxdw.py", "setup", "--repo", repo, "--apply", "--hooks")
        _, state, _ = load_project(repo)
        worker = self.root / "worker line"
        work = state / "work" / "WO-001"
        name = "WO-001-calc.md"
        order = state / "orders" / name
        verify = [sys.executable, "-B", "verify.py"]
        locked = self.work(repo, "lock-tests", "--base", base, "verify.py")
        brief = state / "BRIEF.md"
        brief_text = ("# BRIEF\n版次：1\n狀態：LOCKED\n"
                      "| 編號 | 類別 | 內容 | 怎麼算做到 |\n| --- | --- | --- | --- |\n"
                      "| B-1 | 驗收 | Fixture computes 42 | verify.py exits 0 |\n")
        text(brief, brief_text)
        self.work(repo, "lock-brief")
        self.work(repo, "lock-brief")
        pins = json.dumps({"B-1": gate_check.brief_fingerprint(gate_check.brief_table(brief_text)[0]["B-1"])})
        text(brief, brief_text.replace("版次：1", "版次：2").replace("LOCKED", "DRAFT").replace("42", "99"))
        self.work(repo, "lock-brief", code=2)
        text(order, f"""# WO-001 — test the candidate
ISSUED_BY = director 2026-01-02 10:00
REVISION = 1
TRACES_TO = B-1
BRIEF_REVISION = 1
BRIEF_FINGERPRINTS_V1 = {pins}
PRIMARY_WORKER = cdx fixture
MODEL / EFFORT = configured / standard
FALLBACK = recover from state
GOVERNANCE = Standard
BASE_REF = main @ {base}
NEW_BRANCH = codex/wo001
WORKTREE = {worker}
WORK_DIR = {work}
E2E_COMMAND = {json.dumps(verify)}

SCOPE:
- calc.txt
FORBIDDEN:
- verify.py

| ID | type | req | how | expected |
| --- | --- | --- | --- | --- |
| AC-1 | AUTO | Fixture computes 42 | Run approved check | Exit 0 |
| AC-2 | REVIEW | Independently review the output | Read output | Output is clear |

CHECKS:
- AC-1: {json.dumps(verify)}

{locked}
- DELIVERABLES: candidate and evidence
- STOP_RULES: stop after 2 rounds without progress
""")
        git(repo, "worktree", "add", "--detach", str(worker), base)
        self.work(repo, "adopt", name)
        self.assertEqual(git(worker, "rev-parse", "HEAD"), base)
        self.assertTrue((worker / ".codex" / "hooks.json").is_file())
        self.assertEqual(len(list((worker / ".agents" / "skills").glob("cdx-*/SKILL.md"))), 5)
        self.assertEqual(git(worker, "status", "--porcelain"), "")
        self.work(repo, "dispatch", name, code=2)
        text(state / "reviews" / "WO-001-SPEC_REVIEW.md", "AC-1 explicitly verifies 42.\n")
        self.work(repo, "approve-spec", name, "--reviewer", "reviewer-1", "--author", "director-1")
        self.work(repo, "dispatch", name)
        self.assertEqual(len(list((state / "brief-history").glob("*.md"))), 1)
        self.assertEqual(len(list((state / "order-history").glob("*.md"))), 1)
        text(work / "PLAN.md", "AC-1: update calc.txt, then run the approved check.\n")
        self.work(repo, "approve-plan", name)
        self.run_script("cdxdw.py", "session", "--repo", repo, "new", name)
        self.assertIn('"thread": null', self.run_script("cdxdw.py", "session", "--repo", repo, "status", name))
        dispatched = order.read_bytes()
        order.write_bytes(dispatched + b"\nDraft for the next revision.\n")
        self.assertIn('"state": "ready"', self.run_script("cdxdw.py", "session", "--repo", repo, "status", name))
        self.assertEqual(json.loads(self.work(repo, "status", name))["draft"], "EDITED")
        order.write_bytes(dispatched)
        stamp = order_spec(state, name)["sha"]

        def candidate(value):
            text(worker / "calc.txt", value)
            git(worker, "add", "--", "calc.txt")
            git(worker, "commit", "-m", "WO-001 update fixture result")
            return git(worker, "rev-parse", "HEAD")

        def evidence(folder):
            self.run_script("evidence_record.py", "run", "--cwd", worker, "--out-dir", folder, "--order", order,
                            "--label", "AC-1", "--", *verify)
            return next(folder.glob("*.json"))

        candidate("42\nfirst\n")
        stale = evidence(work / "stale-evidence")
        head = candidate("42\nsecond\n")
        shutil.copyfile(stale, work / "evidence" / "stale.json")
        good = evidence(work / "fresh-evidence")
        shutil.copyfile(good, work / "evidence" / "fresh.json")

        def report(filename):
            text(work / "TASK_REPORT.md", f"""# TASK REPORT
TASK_ID: WO-001
HEAD: {head}
ORDER: {name} REVISION 1
ORDER_SHA256: {stamp}
RESULT: PASS
ENGINEERING: ready
PRODUCT: fixture emits 42
DONE: committed and checked
TESTS: verify.py exit 0
SCOPE_CHECK: PASS
EVIDENCE: {filename}
UNVERIFIED: PO
KNOWN_ISSUES: NONE
NEXT: independent review
ACCEPTANCE:
| ID | actual | evidence | status |
| --- | --- | --- | --- |
| AC-1 | exit 0 | {filename} | PASS |
| AC-2 | Output available | CLI output | READY_FOR_REVIEW |
""")

        report("stale.json")
        self.work(repo, "review", name, "--candidate", head, "--rerun", code=2)
        report("fresh.json")
        legacy_receipt = b'{"old_receipt": true}\r\n'
        receipt_path = state / "reviews" / f"WO-001-{head}.json"
        receipt_path.write_bytes(legacy_receipt)
        with patch.dict(os.environ, {"CDXDW_TEST_SECRET": "fixture-credential"}):
            success = self.work(repo, "review", name, "--candidate", head, "--rerun")
        copied = (receipt_path.parent / "receipt-history" / "WO-001" /
                  f"{head}-{hashlib.sha256(legacy_receipt).hexdigest()}.json")
        self.assertEqual(copied.read_bytes(), legacy_receipt)
        self.assertIn("CDX_REVIEW AUTO_RERUNS=1", success)
        receipt = read_json(state / "reviews" / f"WO-001-{head}.json")
        self.assertEqual(receipt["candidate"], head)
        self.assertEqual(receipt["po"], "PENDING_PO")
        self.assertIn(f"EVIDENCE_RERUN WO-001 AC-1 candidate={head}",
                      (state / "DIRECTOR_LOG.md").read_text(encoding="utf-8"))
        self.assertIn("checked out", self.work(repo, "review", name, "--candidate", base, code=2))
        final = state / "evidence" / "E2E" / "WO-001" / f"{head}.md"
        text(final, f"CANDIDATE_HEAD: {head}\nORDER_SHA256: {stamp}\nENTRY_POINT: verify.py\nOBSERVED: Failed\n")
        self.assertIn("e2e=NOT_RUN", self.work(repo, "final", name, "--candidate", head, code=2))
        self.work(repo, "e2e", name, "--candidate", head)
        self.assertIn("Waiting for REVIEW", self.work(repo, "final", name, "--candidate", head, code=2))
        judgment = ("--actor", "independent", "--environment", "fixture", "--entry", "verify.py",
                    "--expected", "42", "--observed", "42")
        self.work(repo, "record", name, "--candidate", head, "--kind", "review", "--outcome", "PASS", *judgment)
        order.write_bytes(dispatched + b"\nAnother draft for the next revision.\n")
        self.assertIn("CDX_FINAL", self.work(repo, "final", name, "--candidate", head))
        text(force_failure, "force a failure in this environment")
        failure = self.work(repo, "e2e", name, "--candidate", head, code=2)
        self.assertEqual(json.loads(failure)["exit_code"], 1)
        self.assertIn("e2e=FAIL", self.work(repo, "final", name, "--candidate", head, code=2))
        with self.subTest("manual success cannot erase a failed executable entry"):
            self.work(repo, "record", name, "--candidate", head, "--kind", "e2e", "--outcome", "PASS", *judgment)
            self.assertIn("e2e=FAIL", self.work(repo, "final", name, "--candidate", head, code=2))
        self.work(repo, "review", name, "--candidate", head, "--rerun", code=2)
        self.assertEqual(read_json(state / "reviews" / f"WO-001-{head}.json"), receipt)
        self.assertIn("auto=FAIL", self.work(repo, "final", name, "--candidate", head, code=2))
        force_failure.unlink()
        self.work(repo, "seal", name)
        git(repo, "worktree", "remove", "--force", str(worker))
        self.work(repo, "review", name, "--candidate", head, "--rerun")
        self.work(repo, "e2e", name, "--candidate", head)
        self.assertIn("CDX_FINAL", self.work(repo, "final", name, "--candidate", head))
        with self.subTest("approving a draft spec preserves the active review"):
            sr = state / "reviews" / "WO-001-SPEC_REVIEW.md"
            original_spec_review = sr.read_bytes()
            order.write_bytes(dispatched.replace(b"REVISION = 1", b"REVISION = 2", 1))
            text(sr, "Review of the next order revision.\n")
            self.work(repo, "approve-spec", name, "--reviewer", "reviewer-2", "--author", "director-1")
            try:
                self.work(repo, "review", name, "--candidate", head, "--rerun")
            finally:
                sr.write_bytes(original_spec_review)
                order.write_bytes(dispatched)
        built = json.loads(self.work(repo, "e2e", name, "--candidate", head, "--artifact-path", "calc.txt"))
        artifact = built["artifact"]
        self.assertEqual(artifact, hashlib.sha256(b"42\nsecond\n").hexdigest())
        self.assertIn("different build artifact", self.work(repo, "final", name, "--candidate", head, code=2))
        self.assertIn("Waiting for REVIEW", self.work(repo, "final", name, "--candidate", head,
                                                     "--artifact", artifact, code=2))
        self.work(repo, "record", name, "--candidate", head, "--kind", "review", "--outcome", "PASS",
                  "--artifact", artifact, *judgment)
        self.assertIn("CDX_FINAL", self.work(repo, "final", name, "--candidate", head, "--artifact", artifact))
        self.work(repo, "e2e", name, "--candidate", head)
        self.work(repo, "record", name, "--candidate", head, "--kind", "po", "--outcome", "CHANGES_REQUESTED",
                  *judgment)
        self.assertIn("po=CHANGES_REQUESTED", self.work(repo, "final", name, "--candidate", head, code=2))
        text(brief, brief_text.replace("版次：1", "版次：2").replace("42", "99"))
        self.work(repo, "lock-brief")
        self.assertIn("BRIEF_STALE", self.work(repo, "final", name, "--candidate", head, code=2))

    def test_lock_releases_after_forced_process_exit(self):
        target = self.root / "session.lock"
        target.mkdir()  # Old interrupted run marker is kept for inspection.
        code = ("import pathlib, sys, time\nsys.path.insert(0, sys.argv[1])\n"
                "from cdx_common import lock\nwith lock(pathlib.Path(sys.argv[2])):\n"
                " print('LOCKED', flush=True)\n time.sleep(30)")
        holder = subprocess.Popen([sys.executable, "-I", "-B", "-c", code, str(ROOT / "tools"), str(target)],
                                  stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "LOCKED")
            with self.assertRaisesRegex(Refused, "locked by another process"):
                with lock(target):
                    self.fail("Acquired an already-held lock")
        finally:
            holder.kill()
            holder.wait(timeout=5)
            holder.stdout.close()
        with lock(target):
            self.assertTrue(target.is_dir())

    def test_integration_checks_the_actual_combination(self):
        repo = self.git_project("integration-project")
        for filename in ("left.txt", "right.txt"):
            text(repo / filename, "1\n")
        text(repo / "entry.py", "import pathlib, sys\n"
             "total = sum(int(pathlib.Path(name).read_text()) for name in ('left.txt', 'right.txt'))\n"
             "print(total)\nraise SystemExit(total > int(sys.argv[1]))\n")
        git(repo, "add", "--", ".")
        git(repo, "commit", "-m", "Baseline")
        base = git(repo, "rev-parse", "HEAD")
        self.run_script("cdxdw.py", "setup", "--repo", repo, "--apply")
        _, state, _ = load_project(repo)
        member_args = []
        entry = [sys.executable, "-B", "entry.py", "3"]
        for index, filename in enumerate(("left.txt", "right.txt"), 1):
            order_id = f"WO-{index:03d}"
            worker = self.root / order_id
            name = f"{order_id}-capacity.md"
            work = state / "work" / order_id
            text(state / "orders" / name, f"""# {order_id} — check capacity
ISSUED_BY = director 2026-01-02 10:00
REVISION = 1
TRACES_TO = NONE
PRIMARY_WORKER = fixture
MODEL / EFFORT = configured / standard
FALLBACK = manual
GOVERNANCE = Direct
BASE_REF = main @ {base}
NEW_BRANCH = codex/{order_id}
WORKTREE = {worker}
WORK_DIR = {work}
E2E_COMMAND = {json.dumps(entry)}

SCOPE:
- {filename}
FORBIDDEN:
- entry.py

| ID | type | req | how | expected |
| --- | --- | --- | --- | --- |
| AC-1 | AUTO | Capacity | Run entry | exit 0 |

CHECKS:
- AC-1: {json.dumps(entry)}

- DELIVERABLES: candidate and evidence
- STOP_RULES: stop after 2 rounds without progress
""")
            self.work(repo, "prepare", name)
            self.work(repo, "dispatch", name)
            text(worker / filename, "2\n")
            git(worker, "add", "--", filename)
            git(worker, "commit", "-m", f"Raise {filename}")
            head = git(worker, "rev-parse", "HEAD")
            self.work(repo, "seal", name)
            self.work(repo, "e2e", name, "--candidate", head)
            # Seed the already verified AUTO receipt. The full review flow has its own entry-point test.
            spec = order_spec(state, name)
            report = "RESULT: PASS\n"
            text(work / "TASK_REPORT.md", report)
            with attempt(state, spec, head, "auto") as record:
                record["outcome"] = "PASS"
            atomic_write(state / "reviews" / f"{order_id}-{head}.json",
                         json_bytes({"candidate": head, "order_sha256": spec["sha"], "attempt": record["id"],
                                     "report_sha256": gate_check.order_hash(report.encode())}))
            member_args.extend(("--member", f"{name}={head}"))
        common = ("integrate", "--target", "refs/heads/main", "--base", base, *member_args, "--argv")
        failure = json.loads(self.work(repo, *common, json.dumps(entry), code=2))
        self.assertEqual(failure["outcome"], "FAIL")
        self.assertEqual(failure["stdout"]["tail"].strip(), "4")
        self.assertEqual(git(repo, "rev-parse", "HEAD"), base)
        success = json.loads(self.work(repo, *common, json.dumps([*entry[:-1], "4"])))
        self.assertEqual(success["outcome"], "PASS")
        with self.subTest("a superseded integrated result cannot still pass"):
            self.work(repo, *common, json.dumps(entry), code=2)
            self.assertEqual(json.loads(self.work(repo, "integration-status", success["id"], code=2))["outcome"], "STALE")
        if "proofs" in success["members"][0]:
            success = json.loads(self.work(repo, *common, json.dumps([*entry[:-1], "4"])))
            status = ("integration-status", success["id"], "--expect-head")
            self.assertEqual(json.loads(self.work(repo, *status, success["head"]))["outcome"], "PASS")
            self.assertEqual(json.loads(self.work(repo, *status, base, code=2))["outcome"], "WRONG_DELIVERY_HEAD")
            first = success["members"][0]
            built = json.loads(self.work(repo, "e2e", first["filename"], "--candidate", first["candidate"],
                                         "--artifact-path", "left.txt"))
            self.assertEqual(json.loads(self.work(repo, *status, success["head"], code=2))["outcome"], "STALE")
            with_artifact = json.loads(self.work(repo, *common, json.dumps([*entry[:-1], "4"]),
                                                 "--member-artifact", f"{first['filename']}={built['artifact']}"))
            self.assertEqual(with_artifact["members"][0]["artifact"], built["artifact"])
            success = with_artifact
        git(repo, "commit", "--allow-empty", "-m", "Advance target")
        self.assertEqual(json.loads(self.work(repo, "integration-status", success["id"], code=2))["outcome"], "STALE")

    def test_native_review_preview_and_worker_refresh(self):
        repo = self.git_project("handoff-project")
        text(repo / "sample.txt", "start\n")
        text(repo / "entry.py", "from pathlib import Path\n"
             "print('argv: --mode ' + ('off' if 'second' in Path('sample.txt').read_text() else 'on'))\n")
        text(repo / "plans.json", json.dumps({"schema": "run-plan-v1",
             "runs": {"launch": {"args": ["--mode on"], "code": {"--mode": "entry.py:2"}}}}))
        git(repo, "add", "--", "sample.txt", "entry.py", "plans.json")
        git(repo, "commit", "-m", "Baseline")
        base = git(repo, "rev-parse", "HEAD")
        self.run_script("cdxdw.py", "setup", "--repo", repo, "--hooks", "--apply")
        _, state, project = load_project(repo)
        worker = self.root / "worker"
        name = "WO-001-review.md"
        text(state / "orders" / name, f"""# WO-001 — native review
ISSUED_BY = director 2026-01-02 10:00
REVISION = 1
TRACES_TO = NONE
PRIMARY_WORKER = fixture
MODEL / EFFORT = configured / standard
FALLBACK = manual
GOVERNANCE = Direct
BASE_REF = main @ {base}
NEW_BRANCH = codex/wo001
WORKTREE = {worker}
WORK_DIR = {state / 'work' / 'WO-001'}
E2E_COMMAND = {json.dumps([sys.executable, "-B", "entry.py"])}
E2E_RUN_PLAN = {json.dumps({"file": "plans.json", "run": "launch"})}

SCOPE:
- sample.txt
FORBIDDEN:
- .gitignore

| ID | type | req | how | expected |
| --- | --- | --- | --- | --- |
| AC-1 | REVIEW | Reading | Read file | Three lines |

- DELIVERABLES: candidate and evidence
- STOP_RULES: stop after 2 rounds without progress
""")
        self.work(repo, "prepare", name)
        self.work(repo, "dispatch", name)
        rel = Path("plugin/cdx/skills/cdx-review-gate/SKILL.md")
        target = worker / ".agents" / "skills" / rel.parent.name / rel.name
        old = state / "runtime" / "2.6.0-cdx.1" / rel
        text(old, "# previous version\n")
        target.write_bytes(old.read_bytes())
        text(worker / "sample.txt", "start\nfirst\n")
        self.work(repo, "sync-worker", name)
        self.assertEqual(target.read_bytes(), (Path(project["kit"]) / rel).read_bytes())
        self.assertEqual((worker / "sample.txt").read_bytes(), b"start\nfirst\n")
        original = target.read_bytes()
        text(target, "# worker local edit\n")
        self.assertIn("has local content", self.work(repo, "sync-worker", name, code=2))
        self.assertEqual(target.read_bytes(), b"# worker local edit\n")
        target.write_bytes(original)
        for version in ("start\nfirst\n", "start\nfirst\nsecond\n"):
            text(worker / "sample.txt", version)
            git(worker, "add", "--", "sample.txt")
            git(worker, "commit", "-m", "Update sample")
            outcome = "INVALID" if "second" in version else "PASS"
            result = json.loads(self.work(repo, "e2e", name, "--candidate", git(worker, "rev-parse", "HEAD"),
                                          code=2 if outcome == "INVALID" else 0))
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["outcome"], outcome)
        head = git(worker, "rev-parse", "HEAD")
        self.work(repo, "seal", name)
        git(repo, "worktree", "remove", "--force", str(worker))
        review = ("session", "--repo", repo, "native-review", name, "--candidate")
        self.run_script("cdxdw.py", *review, base, code=2)
        target = json.loads(self.run_script("cdxdw.py", *review, head))
        diff = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--binary", base, head, "--", raw=True)
        self.assertIn(b"+first", diff)
        self.assertIn(b"+second", diff)
        self.assertEqual(target["diff_sha256"], hashlib.sha256(diff).hexdigest())
        self.assertEqual(target["candidate"], head)
        self.assertEqual(target["base"], base)
        self.assertFalse((state / "reviews" / "native").exists())

    def test_audit_distinguishes_command_and_turn_status(self):
        log = self.root / "audit.jsonl"
        thread = str(uuid.uuid4())
        base = {"threadId": thread, "turnId": "turn"}
        cdx_audit.append_app(log, {"method": "item/started", "params": dict(base, item={
            "type": "commandExecution", "id": "cmd", "command": "python fixture.py", "status": "inProgress"})})
        cdx_audit.append_app(log, {"method": "item/completed", "params": dict(base, item={
            "type": "commandExecution", "id": "cmd", "command": "python fixture.py", "status": "failed", "exitCode": 7})})
        cdx_audit.append_app(log, {"method": "turn/completed", "params": dict(base, turn={"id": "turn", "status": "completed"})})
        items = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(items[0]["result"]["status"], "running")
        self.assertEqual(items[1]["result"], {"status": "error", "exit_code": 7})
        self.assertEqual(items[2]["status"], "completed")
        self.assertEqual(cdx_audit.audit_status(log), {"observed_calls": 1, "without_terminal": 0,
                         "terminal_without_start": 0, "ok": 0, "error": 1, "unverified": 0})
        for count in (80, 160):
            totals = {"inputTokens": count, "cachedInputTokens": 60, "outputTokens": 5, "totalTokens": count + 5}
            cdx_audit.append_app(log, {"method": "thread/tokenUsage/updated", "params": dict(base, tokenUsage={
                "total": totals, "last": totals, "modelContextWindow": 1000})})
        self.assertEqual(summarize_app(log)["threads"][thread]["total"]["inputTokens"], 160)
        self.assertIn("CDX_AUDIT OK", self.run_script("cdxdw.py", "audit", "verify", log))
        log.write_text(log.read_text(encoding="utf-8").replace('"exit_code":7', '"exit_code":0'), encoding="utf-8")
        self.assertIn("hash does not match", self.run_script("cdxdw.py", "audit", "verify", log, code=2))

    def test_audit_build_is_exclusive_and_atomic(self):
        source, output = self.root / "app.jsonl", self.root / "audit.jsonl"
        event = {"method": "item/started", "params": {"threadId": "thread", "turnId": "turn",
                 "item": {"type": "commandExecution", "id": "cmd", "command": "fixture"}}}
        payload = json.dumps(event) + "\n"
        text(source, payload + "{ invalid JSON\n")
        self.run_script("cdxdw.py", "audit", "build", source, "--out", output, code=2)
        self.assertFalse(output.exists())
        text(source, payload)
        self.run_script("cdxdw.py", "audit", "build", source, "--out", output)
        content = output.read_bytes()
        end = list(cdx_audit.verified_entries(output))[-1]
        self.assertEqual(end["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(end["bytes"], len(source.read_bytes()))
        self.assertEqual(cdx_audit.audit_status(output)["without_terminal"], 1)
        self.run_script("cdxdw.py", "audit", "build", source, "--out", output, code=2)
        self.assertEqual(output.read_bytes(), content)

    def test_hook_role_and_restore(self):
        repo = self.git_project("hook project")
        self.run_script("cdxdw.py", "setup", "--repo", repo, "--apply", "--hooks")
        _, state, _ = load_project(repo)
        session = str(uuid.uuid4())
        director = str(uuid.uuid4())
        self.run_script("cdxdw.py", "session", "--repo", repo, "register-director", director)
        self.assertEqual(read_json(state / "sessions" / (director + ".json"))["role"], "director")
        role = {"role": "worker", "worktree": str(repo), "order": "WO-001"}
        atomic_write(state / "sessions" / (session + ".json"), json_bytes(role))
        base = {"session_id": session, "cwd": str(repo)}
        reply = cdx_hook.handle(dict(base, hook_event_name="SessionStart", source="compact"))
        self.assertIn("RESUME_STATE.md", reply["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("PROGRESS:", reply["hookSpecificOutput"]["additionalContext"])
        patch = f"*** Begin Patch\n*** Update File: {state / 'DIRECTOR_LOG.md'}\n*** End Patch"
        denied = cdx_hook.handle(dict(base, hook_event_name="PreToolUse", tool_name="apply_patch", tool_input={"command": patch}))
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        okay = "*** Begin Patch\n*** Add File: calc.txt\n+42\n*** End Patch"
        self.assertEqual(cdx_hook.handle(dict(base, hook_event_name="PreToolUse", tool_name="apply_patch",
                                              tool_input={"command": okay})), {})
        role["worktree"] = str(self.root / "unrelated checkout")
        atomic_write(state / "sessions" / (session + ".json"), json_bytes(role))
        mismatch = cdx_hook.handle(dict(base, hook_event_name="PreToolUse", tool_name="apply_patch",
                                        tool_input={"command": okay}))
        self.assertIn("different checkout", mismatch["hookSpecificOutput"]["permissionDecisionReason"])

    def test_reconcile_ambiguous_acceptance(self):
        attempt = str(uuid.uuid4())
        file = self.root / "binding.json"
        record = {"thread": str(uuid.uuid4()), "state": "starting", "attempt": attempt, "prior_turn": "previous"}

        class RecordedServer:
            def call(self, method, params):
                if not params.get("cursor"):
                    return {"data": [{"id": "unrelated", "status": "completed", "items": []}],
                            "nextCursor": "second-page"}
                return {"data": [{"id": "accepted", "status": "completed", "items": [{"type": "userMessage",
                    "content": [{"type": "text", "text": f"CDX_ATTEMPT: {attempt}\nfixture"}]}]}]}

        cdx_session.reconcile(RecordedServer(), record, file, reset_empty=False)
        self.assertEqual(read_json(file)["turn"], "accepted")
        self.assertEqual(read_json(file)["state"], "completed")

        record.update(state="starting", turn=None)
        active = {"id": "accepted", "status": "inProgress", "items": [{"type": "userMessage",
                  "content": [{"type": "text", "text": f"CDX_ATTEMPT: {attempt}\nfixture"}]}]}
        with patch.object(RecordedServer, "call", return_value={"data": [active]}):
            cdx_session.reconcile(RecordedServer(), record, file, reset_empty=False)
        self.assertEqual(read_json(file)["state"], "running")
        self.assertEqual(read_json(file)["turn"], "accepted")
        self.assertEqual(read_json(file.parent / "attempts" / f"{attempt}.json")["evidence_coverage"],
                         "recovered-history-partial")

        record.update(state="starting", turn=None)
        with patch.object(RecordedServer, "call", return_value={"data": [{"id": "previous", "status": "completed"}]}):
            cdx_session.reconcile(RecordedServer(), record, file, reset_empty=True)
        self.assertEqual(read_json(file)["turn"], "previous")
        self.assertEqual(read_json(file)["state"], "ready")

    def test_timeout_interrupts_only_the_recorded_turn(self):
        file = self.root / "binding.json"
        thread = str(uuid.uuid4())
        record = {"thread": thread, "state": "ready", "role": "worker"}
        spec = {"path": self.root / "order.md", "sha": "f" * 64, "checkout": self.root, "work": self.root}
        observed = {"completed": {"unrelated": "completed"}, "text": {}}

        class RecordedServer:
            def call(self, method, params, timeout=35):
                if method == "thread/resume":
                    return {"thread": {"id": thread, "cwd": str(spec["checkout"])}}
                if method == "thread/turns/list":
                    return {"data": []}
                if method == "turn/start":
                    return {"turn": {"id": "owned"}}
                if method == "turn/interrupt":
                    self.interruption = params
                    observed["completed"]["owned"] = "interrupted"
                    return {}
                raise AssertionError(method)

            def receive(self, *_):
                raise cdx_session.RPCTimeout("fixture timeout")

        record["worktree"] = str(self.root)
        server = RecordedServer()
        with patch.multiple(cdx_session, windows_preflight=lambda _: None, sandbox_probe=lambda *_: {},
                            certified=lambda *_: True, dispatch_check=lambda *_: None,
                            approved_brief=lambda *_: None, dispatched_copy=lambda *_: spec["path"]):
            cdx_session.run_turn(server, self.root, spec, record, file, "plan", 1, observed)
        self.assertEqual(server.interruption, {"threadId": thread, "turnId": "owned"})
        self.assertEqual(read_json(file)["state"], "interrupted")

    def test_published_bundle_is_self_contained(self):
        for name in ("VERSION", "CHANGELOG.md", "CODEX-PORT.md", "BOOTSTRAP.md", "PURPOSE.md", "LICENSE"):
            self.assertTrue((ROOT / name).is_file(), name)
        manifest = read_json(ROOT / ".agents" / "plugins" / "marketplace.json")
        target = ROOT / manifest["plugins"][0]["source"]["path"]
        plugin = read_json(target / "plugin.json")
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(plugin["version"], version)
        self.assertTrue(plugin["extensions"]["com.openai"]["interface"]["displayName"].startswith("cdxdw "))
        self.assertEqual(self.run_script("cdxdw.py", "--version").strip(), version)
        self.assertEqual(self.run_script("cdx.py", "--version").strip(), version)
        self.assertEqual(self.run_script("cdx.py", "work", "--help"), self.run_script("cdxdw.py", "work", "--help"))
        for path in ("README.md", "BOOTSTRAP.md", "CODEX-PORT.md", "tools/CDX-TOOLS.md"):
            self.assertTrue((ROOT / path).read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    unittest.main(argv=[sys.argv[0]], verbosity=2 if args.verbose else 1)
