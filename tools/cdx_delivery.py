"""Approved integration entry point, final outputs, and product decision."""

import hashlib
import os
from pathlib import PureWindowsPath
import re
import tempfile
import unicodedata

from cdx_common import SHA, Refused, atomic_write, git, json_bytes, lock, read_json, stamp, state_path
from cdx_gates import file_hash


DIGEST = re.compile(r"[0-9a-f]{64}")
ASSET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def output_name(key, value):
    if not isinstance(value, str):
        raise Refused(f"Delivery {key} must be a string")
    if key == "asset":
        if not ASSET.fullmatch(value) or value.endswith(".") or PureWindowsPath(value).is_reserved():
            raise Refused("Delivery asset needs a flat ASCII filename using letters, numbers, dots, underscores or hyphens")
    elif (any(char in '\\:<>|?*"' or unicodedata.category(char) in ("Cc", "Cs") for char in value) or
          any(not part or part.casefold() in (".", "..", ".git") or part != part.strip() or
              part.endswith(".") or PureWindowsPath(part).is_reserved() for part in value.split("/"))):
        raise Refused(f"Delivery {key} needs a portable relative path without traversal")
    return value


def delivery_spec(data):
    if not isinstance(data, dict) or data.keys() - {"mode", "outputs", "require_po", "artifact_source", "build_context"}:
        raise Refused("Delivery approval needs a source or artifacts specification")
    mode, outputs = data.get("mode"), data.get("outputs", [])
    require_po = data.get("require_po", False)
    if (mode not in ("source", "artifacts") or type(require_po) is not bool or
            not isinstance(outputs, list) or (mode == "artifacts") != bool(outputs)):
        raise Refused("Artifacts delivery needs one or more outputs; source delivery uses none")
    seen = {key: set() for key in ("path", "ci_path", "asset")}
    for output in outputs:
        if not isinstance(output, dict) or set(output) != seen.keys():
            raise Refused("Each output needs path, ci_path, and asset")
        for key in seen:
            value = unicodedata.normalize("NFC", output_name(key, output[key])).casefold()
            if value in seen[key]:
                raise Refused(f"Delivery {key} values must be unique")
            seen[key].add(value)
    source = data.get("artifact_source", "ci")
    build = data.get("build_context", "snapshot")
    if source not in ("ci", "retained") or (source == "retained" and mode != "artifacts"):
        raise Refused("artifact_source must be ci, or retained for artifacts delivery")
    if build not in ("snapshot", "git"):
        raise Refused("build_context must be snapshot or git")
    result = {"mode": mode, "outputs": outputs, "require_po": require_po}
    if source != "ci":
        result["artifact_source"] = source
    if build != "snapshot":
        result["build_context"] = build
    return result


def retained_path(state, integration, asset):
    return state_path(state, "integrations", "artifacts", integration, output_name("asset", asset))


def retain_output(state, integration, asset, source, *, expected=None):
    target = retained_path(state, integration, asset)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with lock(target.parent / ".outputs.lock"):
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as dst:
            temporary = target.parent / dst.name
            try:
                with source.open("rb") as src:
                    for chunk in iter(lambda: src.read(1024 * 1024), b""):
                        dst.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                dst.flush()
                os.fsync(dst.fileno())
                value = digest.hexdigest()
                if expected and value != expected:
                    raise Refused(f"File does not match the accepted SHA-256 for {asset}")
                dst.close()
                if target.exists():
                    if not target.is_file() or file_hash(target) != value:
                        raise Refused(f"Existing retained output differs for {asset}")
                else:
                    os.replace(temporary, target)
                return {"sha256": value, "bytes": size, "retained": target.relative_to(state).as_posix()}
            finally:
                dst.close()
                if temporary.exists():
                    temporary.unlink()


def checked_retained(state, integration, asset, output):
    path = retained_path(state, integration, asset)
    if (not path.is_file() or file_hash(path) != output.get("sha256") or
            ("bytes" in output and path.stat().st_size != output["bytes"])):
        raise Refused(f"Retained output is missing or differs for {asset}")
    return path


def approve_integration(state, target, base, command, spec, actor):
    if not actor.strip():
        raise Refused("Record the approver of the integration entry and outputs")
    record = {"schema": 1, "target": target, "base": base, "command": command,
              "delivery": delivery_spec(spec), "approver": actor, "recorded": stamp()}
    raw = json_bytes(record)
    identifier = hashlib.sha256(raw).hexdigest()
    atomic_write(state_path(state, "integrations", "approvals", f"{identifier}.json"), raw)
    return dict(record, approval=identifier)


def integration_approval(state, identifier, target, base, command):
    if not isinstance(identifier, str) or not DIGEST.fullmatch(identifier):
        raise Refused("Use the approved integration fingerprint")
    path = state_path(state, "integrations", "approvals", f"{identifier}.json")
    if file_hash(path) != identifier:
        raise Refused("Integration approval changed")
    record = read_json(path)
    if (record.get("schema") != 1 or (record["target"], record["base"], record["command"]) !=
            (target, base, command)):
        raise Refused("Integration command or target differs from the approved contract")
    return delivery_spec(record["delivery"])


def target_position(repo, result, current):
    if current == result.get("head"):
        return "LANDED"
    if current == result["base"]:
        return "LANDING_PENDING"
    if not SHA.fullmatch(current or "") or not result.get("head"):
        return "TARGET_CHANGED"
    delivery = result.get("delivery", {})
    if delivery.get("build_context") == "git" or delivery.get("artifact_source") == "retained":
        return "TARGET_CHANGED"
    if git(repo, "rev-parse", f"{current}^{{tree}}") != git(repo, "rev-parse", f"{result['head']}^{{tree}}"):
        return "TARGET_CHANGED"
    try:
        git(repo, "merge-base", "--is-ancestor", result["base"], current)
    except Refused:
        return "TARGET_CHANGED"
    return "LANDED_EQUIVALENT_TREE"


def delivery_identity(result):
    return {key: result.get(key) for key in ("id", "head", "tree", "approval", "outputs")}


def save_po_delivery(state, result, args):
    raw = args.reply_file.read_bytes()
    if not raw.decode("utf-8-sig").strip() or not args.actor.strip() or not args.reply_ref.strip():
        raise Refused("Record the integration decision with the original reply, actor and source")
    digest = hashlib.sha256(raw).hexdigest()
    original = state_path(state, "po-replies", f"{digest}.txt")
    if original.is_file() and file_hash(original) != digest:
        raise Refused("Original PO reply changed")
    if not original.is_file():
        atomic_write(original, raw)
    record = dict(delivery_identity(result), outcome=args.outcome, actor=args.actor, reply_ref=args.reply_ref,
                  reply_sha256=digest, recorded=stamp())
    payload = json_bytes(record)
    version = hashlib.sha256(payload).hexdigest()
    atomic_write(state_path(state, "integrations", "po", result["id"], "history", f"{version}.json"), payload)
    atomic_write(state_path(state, "integrations", "po", result["id"], "current.json"), payload)
    return record


def delivery_po_status(state, result):
    path = state_path(state, "integrations", "po", result["id"], "current.json")
    if not path.is_file():
        return "NOT_RUN" if result.get("delivery", {}).get("require_po") else "NOT_REQUIRED"
    record = read_json(path)
    digest = record.get("reply_sha256", "")
    if (any(record.get(key) != value for key, value in delivery_identity(result).items()) or
            not isinstance(digest, str) or not DIGEST.fullmatch(digest) or not record.get("reply_ref")):
        return "STALE"
    reply = state_path(state, "po-replies", f"{digest}.txt")
    return record["outcome"] if reply.is_file() and file_hash(reply) == digest else "STALE"
