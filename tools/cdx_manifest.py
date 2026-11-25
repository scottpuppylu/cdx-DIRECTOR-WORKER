"""Generate or verify the file manifest for an installable cdxdw bundle."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdx_common import ROOT, Refused, atomic_write, git, json_bytes, report_error, state_path


NAME = "RUNTIME-MANIFEST.json"
STOCK = {"README.md", "PURPOSE.md", "BOOTSTRAP.md", "VERSION", "LICENSE", "director_work.example.json",
         "CODEX-PORT.md", "CHANGELOG.md", "CHANGELOG-upstream.md", ".agents/plugins/marketplace.json"}
FOLDERS = {"docs", "tools", "templates", "plugin", "research"}


def is_runtime_file(name):
    parts = name.split("/")
    return (name in STOCK or (len(parts) > 1 and parts[0] in FOLDERS and
            not any(part in ("", ".", "..", ".git", "__pycache__") for part in parts) and
            not name.endswith(".pyc") and "\\" not in name))


def manifest_from_checkout(root):
    tracked = git(root, "ls-files", "-z", raw=True).decode("utf-8").split("\0")
    files = {}
    for name in sorted(set(tracked)):
        if is_runtime_file(name):
            path = state_path(root, *name.split("/"))
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not STOCK <= files.keys():
        raise Refused("Runtime manifest must cover all required bundle files")
    return {"schema": 1, "version": (root / "VERSION").read_text(encoding="utf-8").strip(), "files": files}


def checked_files(root):
    manifest = state_path(root, NAME)
    manifest_bytes = manifest.read_bytes()
    release = json.loads(manifest_bytes.decode("utf-8-sig"))
    version = state_path(root, "VERSION").read_text(encoding="utf-8").strip()
    files = release.get("files")
    if (release.get("schema") != 1 or release.get("version") != version or not isinstance(files, dict) or
            not STOCK <= files.keys()):
        raise Refused("Runtime manifest is missing required files or has a different version")
    result = [(manifest, manifest_bytes)]
    for name, expected in sorted(files.items()):
        if not is_runtime_file(name) or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise Refused("Invalid runtime manifest entry")
        path = state_path(root, *name.split("/"))
        if not path.is_file():
            raise Refused(f"Runtime source is missing {name}")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise Refused(f"Runtime source does not match the manifest: {name}")
        result.append((path, raw))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare the manifest with the tracked source files")
    options = parser.parse_args()
    try:
        manifest = ROOT / NAME
        raw = json_bytes(manifest_from_checkout(ROOT))
        if options.check:
            if manifest.read_bytes() != raw:
                raise Refused("Runtime manifest is stale. Regenerate it after staging the intended files.")
        else:
            atomic_write(manifest, raw)
        print(f"CDX_MANIFEST {'VERIFIED' if options.check else 'GENERATED'}")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
