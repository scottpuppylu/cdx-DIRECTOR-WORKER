"""Generate or verify the file manifest for an installable cdxdw bundle."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile, ZipInfo

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
    entries = [{"path": name, "sha256": digest} for name, digest in files.items()]
    return {"schema": 1, "version": (root / "VERSION").read_text(encoding="utf-8").strip(), "files": entries}


def checked_files(root):
    manifest = state_path(root, NAME)
    manifest_bytes = manifest.read_bytes()
    release = json.loads(manifest_bytes.decode("utf-8-sig"))
    version = state_path(root, "VERSION").read_text(encoding="utf-8").strip()
    entries = release.get("files")
    if release.get("schema") != 1 or release.get("version") != version or not isinstance(entries, list):
        raise Refused("Runtime manifest is missing required files or has a different version")
    result = [(manifest, manifest_bytes)]
    files = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise Refused("Invalid runtime manifest entry")
        name, expected = entry.get("path"), entry.get("sha256")
        if (not isinstance(name, str) or not is_runtime_file(name) or name in files or
                not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)):
            raise Refused("Invalid runtime manifest entry")
        files.add(name)
        path = state_path(root, *name.split("/"))
        if not path.is_file():
            raise Refused(f"Runtime source is missing {name}")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise Refused(f"Runtime source does not match the manifest: {name}")
        result.append((path, raw))
    if not STOCK <= files:
        raise Refused("Runtime manifest is missing required files")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--check", action="store_true", help="compare the manifest with the tracked source files")
    flags.add_argument("--package", type=Path, help="build a deterministic installable ZIP from the verified files")
    options = parser.parse_args()
    try:
        if options.package:
            entries = checked_files(ROOT)
            options.package.parent.mkdir(parents=True, exist_ok=True)
            with ZipFile(options.package, "x") as archive:
                for path, contents in sorted(entries, key=lambda row: row[0].relative_to(ROOT).as_posix()):
                    entry = ZipInfo(path.relative_to(ROOT).as_posix())
                    entry.create_system = 3
                    entry.external_attr = 0o100644 << 16
                    archive.writestr(entry, contents)
            print(f"CDX_MANIFEST PACKAGE {options.package}")
            return 0
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
