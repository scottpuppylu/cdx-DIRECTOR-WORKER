"""Approved integration entry point, final outputs, and product decision."""

import hashlib
import re

from cdx_common import SHA, Refused, atomic_write, git, json_bytes, read_json, stamp, state_path
from cdx_gates import file_hash, relative_file


DIGEST = re.compile(r"[0-9a-f]{64}")
ASSET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def delivery_spec(data):
    if not isinstance(data, dict) or data.keys() - {"mode", "outputs", "require_po"}:
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
            value = relative_file(output[key])
            if (key == "asset" and not ASSET.fullmatch(value)) or value.casefold() in seen[key]:
                raise Refused("Delivery output names must be unique and asset names must be flat")
            seen[key].add(value.casefold())
    return {"mode": mode, "outputs": outputs, "require_po": require_po}


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
