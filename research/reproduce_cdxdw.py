"""Run the candidate-evidence regressions on this tree or an archived Git revision."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


CASES = (
    "CDX.test_work_order_full_flow_and_wrong_candidate",
    "CDX.test_integration_checks_the_actual_combination",
)


def archive(repository, revision, folder):
    folder.mkdir(parents=True, exist_ok=True)
    archive_file = folder / "kit.zip"
    commit = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "--verify", "--end-of-options",
                                      revision + "^{commit}"], encoding="ascii").strip()
    subprocess.run(["git", "-C", str(repository), "archive", "--format=zip", f"--output={archive_file}",
                    commit, "--"], check=True)
    kit = folder / "kit"
    with zipfile.ZipFile(archive_file) as bundle:
        bundle.extractall(kit)
    return kit


def run_cases(kit):
    return subprocess.call([sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v",
                            *(f"selftest_cdx.{case}" for case in CASES)], cwd=kit / "tools")


def run_upgrade(here, folder):
    released = archive(here, "v2.6.0-cdx.3", folder / "published")
    candidate = archive(here, "a9c8d1e19c48f2220093bd88cac52c7fb0b853ca", folder / "candidate")
    latest = folder / "latest"
    shutil.copytree(here, latest, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
    repo, state, worker = (folder / name for name in ("project", "state", "worker"))
    repo.mkdir()

    def git(*args, directory=repo):
        return subprocess.check_output(["git", "-C", str(directory), *args], encoding="utf-8").strip()

    def cdx(kit, mode, *args, expected=0):
        result = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str(kit / "tools" / "cdxdw.py"),
                                 mode, "--repo", str(repo), *map(str, args)], capture_output=True, encoding="utf-8")
        if result.returncode != expected:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout

    git("init", "-b", "main", "--template=")
    git("config", "core.hooksPath", ".git/disabled")
    git("config", "user.name", "upgrade fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "commit.gpgSign", "false")
    git("config", "core.autocrlf", "false")
    (repo / "sample.txt").write_bytes(b"old\n")
    git("add", "sample.txt")
    git("commit", "-m", "Baseline")
    base = git("rev-parse", "HEAD")
    cdx(released, "setup", "--state", state, "--hooks", "--apply")
    (state / "PO_PENDING.md").write_bytes("PO 待辦保留\r\n".encode("utf-8"))
    cdx(candidate, "setup", "--apply")
    name = "WO-001-upgrade.md"
    order = state / "orders" / name
    order.write_text(f"""# WO-001 — Upgrade fixture
ISSUED_BY = director 2026-01-02 10:00
REVISION = 1
TRACES_TO = NONE
PRIMARY_WORKER = fixture
MODEL / EFFORT = configured / standard
FALLBACK = manual
GOVERNANCE = Direct
BASE_REF = main @ {base}
NEW_BRANCH = codex/worker
WORKTREE = {worker}
WORK_DIR = {state / 'work' / 'WO-001'}
E2E_COMMAND = {json.dumps([sys.executable, "-c", "raise SystemExit(7)"])}

SCOPE:
- sample.txt
FORBIDDEN:
- .gitignore

| ID | type | req | how | expected |
| --- | --- | --- | --- | --- |
| AC-1 | REVIEW | Content | Read sample | Updated |

- DELIVERABLES: candidate and evidence
- STOP_RULES: stop after 2 rounds without progress
""", encoding="utf-8")
    cdx(candidate, "work", "prepare", name)
    cdx(candidate, "work", "dispatch", name)
    (worker / "sample.txt").write_bytes(b"candidate\n")
    git("add", "sample.txt", directory=worker)
    git("commit", "-m", "Prepare candidate", directory=worker)
    selected = json.loads(cdx(candidate, "work", "seal", name).splitlines()[-1])
    head = selected["candidate"]
    cdx(candidate, "work", "e2e", name, "--candidate", head, expected=2)
    cdx(candidate, "work", "record", name, "--candidate", head, "--kind", "e2e", "--outcome", "PASS",
        "--actor", "fixture", "--environment", "local", "--entry", "manual", "--expected", "42", "--observed", "42")
    assert json.loads(cdx(candidate, "work", "status", name))["acceptance"]["e2e"] == "PASS"
    (worker / "sample.txt").write_bytes(b"pending worker draft\n")
    preserved = [state / "PO_PENDING.md", state / "DIRECTOR_LOG.md", order,
                 state / "work" / "WO-001" / "CANDIDATE.json", worker / "sample.txt",
                 *sorted((state / "acceptance").rglob("*.json"))]
    before = {path: path.read_bytes() for path in preserved}
    rollback_paths = [state / "PROJECT.json", repo / ".codex" / "hooks.json", worker / ".codex" / "hooks.json",
                      *repo.glob(".agents/skills/cdx-*/SKILL.md"), *worker.glob(".agents/skills/cdx-*/SKILL.md")]
    rollback = {path: path.read_bytes() for path in rollback_paths}
    cdx(latest, "setup")
    cdx(latest, "setup", "--apply")
    cdx(latest, "work", "sync-worker", name)
    status = json.loads(cdx(latest, "work", "status", name))
    assert status["candidate"] == head and status["acceptance"]["e2e"] == "FAIL"
    assert status["acceptance"]["manual_e2e"] == "PASS"
    assert "changed=0" in cdx(latest, "setup", "--apply")
    assert git("rev-parse", selected["ref"]) == head
    assert all(path.read_bytes() == data for path, data in before.items())
    assert all((state / "runtime" / f"2.6.0-cdx.{version}" / "tools" / "cdxdw.py").is_file()
               for version in (3, 4, 5))
    assert "2.6.0-cdx.5" in (worker / ".codex" / "hooks.json").read_text(encoding="utf-8")
    print("UPGRADE .3 -> .4 -> .5: evidence, drafts, PO, ref and old runtimes preserved")
    # Only the disposable fixture is rolled back. Keep both runtimes and all evidence.
    for path, payload in rollback.items():
        path.write_bytes(payload)
    restored = state / "runtime" / "2.6.0-cdx.4"
    assert json.loads(cdx(restored, "work", "status", name))["candidate"] == head
    assert "changed=0" in cdx(restored, "setup", "--apply")
    assert all(path.read_bytes() == data for path, data in before.items())
    print("ROLLBACK .5 -> .4: recovered via the saved owner, Skills and Hook files in the fixture")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--against", help="Git commit or tag to run in a disposable archived copy")
    mode.add_argument("--upgrade", action="store_true", help="exercise the real .3 and .4 upgrades in a new Git repo")
    args = parser.parse_args()
    here = Path(__file__).resolve().parents[1]
    if not args.against and not args.upgrade:
        return run_cases(here)
    with tempfile.TemporaryDirectory(prefix="cdxdw-reproduction-") as temporary:
        if args.upgrade:
            return run_upgrade(here, Path(temporary))
        kit = archive(here, args.against, Path(temporary))
        shutil.copyfile(here / "tools" / "selftest_cdx.py", kit / "tools" / "selftest_cdx.py")
        return run_cases(kit)


if __name__ == "__main__":
    raise SystemExit(main())
