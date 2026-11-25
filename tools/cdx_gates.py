"""Evidence controls selected in a dispatched cdxdw work order."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import gate_check
import pre_tr
from cdx_common import ROOT, Refused, check_environment, git, json_bytes, state_path


FILE = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")
DIGEST = re.compile(r"[0-9a-f]{64}")


def relative_file(name):
    if (not isinstance(name, str) or not FILE.fullmatch(name) or
            any(part.casefold() in (".", "..", ".git") for part in name.split("/"))):
        raise Refused("Evidence paths must be repo-relative without traversal")
    return name


def policy(text):
    fields = re.findall(r"^[ \t]*CDX_GATES[ \t]*=[ \t]*(.+)$", text, re.M)
    if not fields:
        return {}
    if len(fields) != 1:
        raise Refused("Work order needs at most one CDX_GATES field")
    data = json.loads(fields[0])
    if not isinstance(data, dict) or data.keys() - {"feasibility", "pre_tr", "ruler", "pack", "po_reply", "audit",
                                                   "artifact_path"}:
        raise Refused("CDX_GATES has an unknown field")
    for key in ("feasibility", "po_reply", "audit"):
        if key in data and type(data[key]) is not bool:
            raise Refused(f"{key} must be a boolean")
    for key in ("pre_tr", "pack", "artifact_path"):
        if key in data:
            relative_file(data[key])
    if "ruler" in data:
        ruler_args(data["ruler"])
    if "artifact_path" in data and not re.search(r"^[ \t]*E2E_COMMAND[ \t]*=", text, re.M):
        raise Refused("artifact_path requires a pinned E2E_COMMAND")
    return data


def feasibility(state, spec):
    if not spec.get("gates", {}).get("feasibility"):
        return None
    path = state_path(state, "work", spec["order_id"], "GATE_FEASIBILITY.md")
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    def field(name):
        values = re.findall(rf"^{name}:[ \t]*(\S[^\r\n]*)", text, re.M)
        return values[0].strip() if len(values) == 1 else ""
    if (field("ORDER") != f"{spec['file']} REVISION {spec['revision']}" or
            field("BASELINE") != spec["base"] or field("FEASIBILITY") != "FEASIBLE" or not field("CHECKED_BY")):
        raise Refused("Feasibility must attest to this exact order revision and baseline")
    criteria = gate_check.ac_table(spec["text"])
    rows = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = gate_check.split_cells(line)
        if cells and re.fullmatch(r"AC-\d+", cells[0]):
            if cells[0] in rows:
                raise Refused(f"Duplicate feasibility row: {cells[0]}")
            rows[cells[0]] = cells
    if not criteria or set(rows) != set(criteria):
        raise Refused("Feasibility needs one baseline probe for every AC")
    for ac, row in rows.items():
        if (len(row) != 6 or row[-1] != "FEASIBLE" or not all(cell.strip("<> ") for cell in row[1:-1]) or
                not re.search(r"\bexit=-?\d+\s+at=\d\d:\d\d", row[2])):
            raise Refused(f"{ac}: missing measurable baseline evidence")
    rule = field("LOOSENED_RULE")
    if rule not in ("無", "NONE"):
        actor = field("CHECKED_BY_OTHER")
        if (not rule or not field("KNOWN_DEFECT") or not actor or actor.casefold() == field("CHECKED_BY").casefold() or
                not re.match(r"yes\b.*\bexit=-?\d+\s+at=\d\d:\d\d", field("RESULT"), re.I)):
            raise Refused("A loosened ruler needs an independent known-defect control")
    return hashlib.sha256(raw).hexdigest()


def committed_control(repo, spec, candidate, name):
    baseline = git(repo, "show", f"{spec['base']}:{name}", raw=True)
    if git(repo, "show", f"{candidate}:{name}", raw=True) != baseline:
        raise Refused(f"Candidate changed approved control {name}")
    return baseline


def prepare_inputs(repo, spec, candidate, root, input_root):
    name = spec.get("gates", {}).get("pre_tr")
    if not name:
        return None
    data = committed_control(repo, spec, candidate, name)
    config = state_path(root, *name.split("/"))
    if config.read_bytes() != data:
        raise Refused("Materialized pre-TR config differs from the approved Git object")
    parsed = json.loads(data.decode("utf-8-sig"))
    if not isinstance(parsed, dict) or not isinstance(parsed.get("inputs", []), list):
        raise Refused("pre-TR inputs must be an array")
    inputs = []
    seen = set()
    for item in parsed.get("inputs", []):
        if not isinstance(item, dict):
            raise Refused("Malformed pre-TR input")
        rel = relative_file(item.get("path"))
        want = item.get("sha256")
        if (not DIGEST.fullmatch(want or "") or not str(item.get("source") or "").strip() or rel.casefold() in seen):
            raise Refused(f"pre-TR input needs a unique path, source and SHA-256: {rel}")
        seen.add(rel.casefold())
        target = state_path(root, *rel.split("/"))
        if target.exists():
            raise Refused(f"pre-TR input would replace a committed file: {rel}")
        if input_root is None:
            raise Refused(f"MISSING_INPUT {rel}: provide the approved input root")
        source = state_path(input_root, *rel.split("/"))
        if not source.is_file():
            raise Refused(f"MISSING_INPUT {rel}")
        payload = source.read_bytes()
        if hashlib.sha256(payload).hexdigest() != want:
            raise Refused(f"INPUT_CHANGED {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        inputs.append({"path": rel, "sha256": want})
    classes = pre_tr.load(config)
    for group in classes.values():
        for check in group.get("checks", []):
            if check.get("cwd"):
                cwd = state_path(config.parent, *relative_file(check["cwd"]).split("/"))
                if not cwd.is_dir():
                    raise Refused("pre-TR check cwd must exist in the materialized workspace")
    return config, inputs


def cpu_checks(repo, spec, candidate, root, input_root, record):
    prepared = prepare_inputs(repo, spec, candidate, root, input_root)
    if prepared is None:
        return True
    config, inputs = prepared
    config_digest = file_hash(config)
    changed = git(repo, "diff", "--name-only", "--no-renames", "-z", spec["base"], candidate).split("\0")
    files = [name for name in changed if name]
    args = ["--config", str(config), "--repo", str(root), "--strict", "--changed", *files] if files else None
    result = invoke("pre_tr.py", args) if args else None
    code = result.returncode if result else 0
    if file_hash(config) != config_digest or any(
            file_hash(state_path(root, *item["path"].split("/"))) != item["sha256"] for item in inputs):
        raise Refused("CPU checks changed the approved pre-TR configuration or inputs")
    record["pre_tr"] = {"config_sha256": config_digest, "inputs": inputs,
                        "exit_code": code, "observation": tail(result) if result else "No changed files"}
    return code == 0


def ruler_args(data):
    if (not isinstance(data, dict) or data.keys() - {"pattern", "real_line", "expect_min", "cap_key",
                                                    "required", "required_min"}):
        raise Refused("ruler must be an object with recognized ruler settings")
    if not all(isinstance(data.get(key), str) and data[key].strip() for key in ("pattern", "real_line")):
        raise Refused("ruler needs a pattern and a real output line")
    args = []
    for key, value in data.items():
        if key in ("expect_min", "required_min"):
            valid = type(value) is int and value > 0
        else:
            valid = isinstance(value, str) and value.strip()
        if not valid:
            raise Refused(f"Invalid ruler setting: {key}")
        args.append(f"--{key.replace('_', '-')}={value}")
    return args


def ruler_check(data, stdout, record):
    if not data:
        return True
    with tempfile.TemporaryDirectory(prefix="cdxdw-ruler-") as folder:
        output = Path(folder) / "entry.log"
        output.write_bytes(stdout)
        result = invoke("ruler_check.py", ["lines", "--input", str(output), *ruler_args(data)])
    record["ruler"] = {"exit_code": result.returncode, "observation": tail(result)}
    return result.returncode == 0


def pack_digest(state, spec):
    name = spec["gates"]["pack"]
    pack = state_path(state, "work", spec["order_id"], "evidence", *name.split("/"))
    manifest = []
    if not pack.is_dir():
        raise Refused("The work order evidence pack does not exist")
    data = json.loads(state_path(pack, "manifest.json").read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("images"), list) or not data["images"]:
        raise Refused("The review pack needs actual images")
    names = set()
    for image in data["images"]:
        name = relative_file(image.get("file") if isinstance(image, dict) else None)
        if name.casefold() in names or not state_path(pack, *name.split("/")).is_file():
            raise Refused(f"Missing or duplicate manifest file: {name}")
        names.add(name.casefold())
    for path in sorted(pack.rglob("*")):
        relative = path.relative_to(pack)
        checked = state_path(pack, *relative.parts)
        if checked.is_file():
            manifest.append((relative.as_posix(), file_hash(checked)))
    if not manifest:
        raise Refused("The evidence pack is empty")
    return pack, hashlib.sha256(json_bytes(manifest)).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def invoke(tool, args):
    return subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str(ROOT / "tools" / tool), *args],
                          capture_output=True, env=check_environment(), timeout=180)


def tail(result):
    return (result.stdout + result.stderr)[-4096:].decode("utf-8", errors="replace")
