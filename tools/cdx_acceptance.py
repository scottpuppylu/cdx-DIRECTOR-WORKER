"""Persist candidate verification attempts and structured product judgments."""

from contextlib import contextmanager
import hashlib
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import evidence_record
from cdx_gates import cpu_checks, feasibility, ruler_check
from cdx_common import (ROOT, SHA, Refused, atomic_write, check_environment, executor, git_environment, json_bytes,
                        lock, read_json, stamp, state_path)

# Keep the upstream tree materializer on the same Git environment as cdxdw.
repo_environment = git_environment()
evidence_record.GIT_ENV = {key: value for key, value in evidence_record.GIT_ENV.items()
                           if key == "GIT_NO_REPLACE_OBJECTS" or key in repo_environment}


def journal_path(state, spec, candidate):
    if not SHA.fullmatch(candidate):
        raise Refused("Use the full candidate commit SHA")
    return state_path(state, "acceptance", spec["order_id"], spec["sha"], f"{candidate}.json")


def journal(state, spec, candidate):
    path = journal_path(state, spec, candidate)
    identity = {"order": spec["order_id"], "order_sha256": spec["sha"], "candidate": candidate}
    data = read_json(path) if path.is_file() else dict(identity, schema=1, attempts=[])
    if data.get("schema") != 1 or any(data.get(key) != value for key, value in identity.items()):
        raise Refused("Acceptance journal does not match this order and candidate")
    return path, data


@contextmanager
def acceptance_lock(state, spec, candidate):
    path = journal_path(state, spec, candidate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock(path.with_suffix(".lock")):
        yield


@contextmanager
def attempt(state, spec, candidate, kind, **metadata):
    """Called with the candidate lock held. A crash leaves a visible RUNNING attempt."""
    path, data = journal(state, spec, candidate)
    record = dict(metadata, id=str(uuid.uuid4()), kind=kind, started=stamp(), outcome="RUNNING")
    data["attempts"].append(record)
    atomic_write(path, json_bytes(data))
    try:
        yield record
        if record["outcome"] not in ("PASS", "FAIL", "INVALID", "CHANGES_REQUESTED", "UNKNOWN"):
            raise Refused("Attempt has no explicit outcome")
    except KeyboardInterrupt:
        record["outcome"] = "UNKNOWN"
        raise
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError):
        record["outcome"] = "UNKNOWN"
        raise
    finally:
        record["finished"] = stamp()
        atomic_write(path, json_bytes(data))


def latest_attempts(state, spec, candidate, artifact=None):
    _, data = journal(state, spec, candidate)
    latest = {}
    for row in data["attempts"]:
        kind = row["kind"]
        # .4 wrote operator observations and actual executions under the same kind.
        if kind == "e2e" and row.get("source") == "operator-recorded":
            kind = "manual_e2e"
        if kind in ("auto", "e2e", "preflight") or row.get("artifact") == artifact:
            latest[kind] = row
    return latest


def run_plan(repo, candidate, plan, record, stdout=None):
    with tempfile.TemporaryDirectory(prefix="cdxdw-run-plan-") as directory:
        root = Path(directory)
        config = root / "plan.json"
        config.write_bytes(plan["data"])
        args = ["--plan", str(config), "--repo", str(repo), "--commit", candidate]
        if stdout is not None:
            output = root / "entry.log"
            output.write_bytes(stdout)
            args.extend(("--log", f"{plan['run']}={output}"))
        result = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8",
                                 str(ROOT / "tools" / "run_plan_check.py"), *args],
                                capture_output=True, env=check_environment(), timeout=180)
    phase = "before" if stdout is None else "after"
    record.setdefault("run_plan", {"file": plan["file"], "run": plan["run"],
                                    "sha256": hashlib.sha256(plan["data"]).hexdigest()})
    record["run_plan"][phase] = {"exit_code": result.returncode,
                                 "observation": (result.stdout + result.stderr)[-4096:].decode("utf-8", errors="replace")}
    return result.returncode == 0


def run_entry(repo, candidate, command, timeout, record, artifact_path=None, *, plan=None, gates=None,
              input_root=None, preflight_only=False):
    if not preflight_only and (not command or not all(isinstance(arg, str) and arg.strip() and "\0" not in arg
                                                    for arg in command)):
        raise Refused("The entry point must be an argv array")
    record["executor"] = executor()
    record["command"] = command
    if plan and not run_plan(repo, candidate, plan, record):
        record["outcome"] = "INVALID"
        return
    with tempfile.TemporaryDirectory(prefix="cdxdw-e2e-") as directory:
        root = Path(directory)
        try:
            evidence_record.materialize(repo, candidate, root)
        except evidence_record.Refused as error:
            raise Refused(str(error)) from error
        if gates:
            state, spec = gates
            try:
                record["feasibility_sha256"] = feasibility(state, spec)
                if not cpu_checks(repo, spec, candidate, root.resolve(), input_root, record):
                    record["outcome"] = "FAIL"
                    return
            except (Refused, OSError, ValueError) as error:
                record.update(outcome="INVALID", preflight_error=str(error))
                return
        if preflight_only:
            record["outcome"] = "PASS"
            return
        result = subprocess.run(command, cwd=root, env=check_environment(), timeout=timeout, capture_output=True)
        if result.returncode == 0 and artifact_path:
            if Path(artifact_path).is_absolute():
                raise Refused("Artifact path must be relative to the candidate")
            path = state_path(root.resolve(), artifact_path)
            record["artifact"] = evidence_record.hash_file(path)
            record["artifact_path"] = artifact_path
    for stream in ("stdout", "stderr"):
        raw = getattr(result, stream)
        record[stream] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                          "tail": raw[-4096:].decode("utf-8", errors="replace")}
    record["exit_code"] = result.returncode
    record["outcome"] = "PASS" if result.returncode == 0 else "FAIL"
    if plan and not run_plan(repo, candidate, plan, record, result.stdout):
        record["outcome"] = "INVALID"
    if gates and not ruler_check(gates[1]["gates"].get("ruler"), result.stdout, record):
        record["outcome"] = "INVALID"
