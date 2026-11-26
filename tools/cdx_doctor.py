"""Distinguish project configuration, Hook trust, and observed sandbox behavior."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdx_common import ROOT, STATE_SCHEMA, Refused, executing_version, load_project, report_error, state_path
from cdx_gates import file_hash
from cdx_manifest import NAME
from cdx_rpc import AppServer


def exec_write(server, cwd, target, policy):
    script = "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text('cdx probe')"
    try:
        result = server.call("command/exec", {"cwd": str(cwd), "timeoutMs": 10000, "sandboxPolicy": policy,
                             "command": [sys.executable, "-I", "-c", script, str(target)]})
    except RuntimeError:
        return {"exit": None, "wrote": target.is_file()}
    return {"exit": result.get("exitCode"), "wrote": target.is_file()}


def sandbox_probe(server, state):
    audit = state_path(state, "audit")
    with tempfile.TemporaryDirectory(prefix="cdx-sandbox-", dir=audit) as temp:
        root = Path(temp).resolve()
        if root.parent != audit or not root.name.startswith("cdx-sandbox-"):
            raise Refused("Unexpected sandbox probe location")
        work = root / "writable"
        work.mkdir()
        read_only = {"type": "readOnly", "networkAccess": False}
        workspace = {"type": "workspaceWrite", "writableRoots": [str(work)], "networkAccess": False,
                     "excludeTmpdirEnvVar": True, "excludeSlashTmp": True}
        return {"read_only": exec_write(server, work, work / "read-only", read_only),
                "inside": exec_write(server, work, work / "inside", workspace),
                "outside": exec_write(server, work, root / "outside", workspace)}


def certified(result, phase):
    # Positive control prevents a missing Python executable from counting as a denial.
    inside = result["inside"]
    target = result["outside"] if phase == "implement" else result["read_only"]
    return (inside["exit"] == 0 and inside["wrote"] and type(target["exit"]) is int
            and target["exit"] != 0 and not target["wrote"])


def discover(server, repo):
    skills = server.call("skills/list", {"cwds": [str(repo)], "forceReload": True})
    hooks = server.call("hooks/list", {"cwds": [str(repo)]})
    return {
        "skills": [s.get("name") for row in skills["data"] for s in row["skills"]
                   if s.get("enabled") and s.get("name", "").startswith("cdx-")],
        "hooks": [{"event": hook.get("eventName"), "trust": hook.get("trustStatus"),
                   "source": hook.get("source"), "path": hook.get("sourcePath") or hook.get("path")}
                  for row in hooks["data"] for hook in row["hooks"]
                  if (hook.get("statusMessage") or "").startswith("cdx DIRECTOR-WORK ")]
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--codex", help="Codex CLI executable, default PATH")
    parser.add_argument("--live", action="store_true", help="query native skill discovery, Hook trust and Windows readiness")
    parser.add_argument("--probe-sandbox", action="store_true", help="test safe writes in an isolated disposable fixture")
    args = parser.parse_args(argv)
    try:
        repo, state, project = load_project(args.repo, diagnostic=True)
        files = ("PO_PENDING.md", "RESUME_STATE.md", "DIRECTOR_LOG.md", "DECISION_REGISTER.md", "director_work.json")
        missing = [name for name in files if not state_path(state, name).is_file()]
        kit = Path(project["kit"])
        if not any((kit / "tools" / name).is_file() for name in ("cdxdw.py", "cdx.py")):
            missing.append("installed runtime")
        codex = args.codex or shutil.which("codex")
        summary = {"project": str(repo), "state": str(state), "kit": str(kit), "version": project["version"],
                   "executing_version": executing_version(), "active_version": project["version"],
                   "minimum_write_version": project["version"] if project["schema"] == STATE_SCHEMA else None,
                   "schema": project["schema"], "launcher": str(state / "cdxdw.py"),
                   "missing": missing, "hooks_configured": project["hooks"], "codex": None, "sandbox": "NOT_PROBED",
                   "provenance": project.get("provenance"), "expected_release_tag": f"v{project['version']}",
                   "manifest_sha256": file_hash(kit / NAME) if (kit / NAME).is_file() else None,
                   "tool_paths": {name: shutil.which(name) for name in ("git", "gh", "ps")}}
        if codex:
            summary["codex"] = subprocess.check_output([codex, "--version"], encoding="utf-8", timeout=15).strip()
        if args.live or args.probe_sandbox:
            if not codex:
                raise Refused("Codex CLI was not found on PATH")
            with AppServer(codex, repo) as server:
                summary.update(discover(server, repo))
                if os.name == "nt":
                    summary["windows_sandbox"] = server.call("windowsSandbox/readiness", {}).get("status")
                if args.probe_sandbox:
                    proof = sandbox_probe(server, state)
                    summary["sandbox"] = dict(proof, read_only_observed=certified(proof, "plan"),
                                              workspace_boundary_observed=certified(proof, "implement"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if missing else 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
