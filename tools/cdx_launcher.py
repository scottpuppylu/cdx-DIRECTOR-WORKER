"""Run the active cdxdw installation from a stable path in the project state."""

import json
from pathlib import Path
import re
import subprocess
import sys


def main():
    state = Path(__file__).resolve().parent
    if sys.argv[1:] in (["--help"], ["-h"]) and not (state / "PROJECT.json").is_file():
        print("Usage: python <project-state>/cdxdw.py [COMMAND] [ARGS]")
        print("Run setup first to install this launcher in the project state.")
        return 0
    try:
        project = json.loads((state / "PROJECT.json").read_bytes().decode("utf-8-sig"))
        version = project["version"]
        if project["schema"] != 2 or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-cdx\.[0-9]+", version):
            raise ValueError("Invalid active cdxdw project")
        kit = state / "runtime" / version
        script = kit / "tools" / "cdxdw.py"
        if kit != Path(project["kit"]) or script != script.resolve(strict=True):
            raise ValueError("Active cdxdw runtime is outside the project state")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"cdxdw: {error}", file=sys.stderr)
        return 2
    return subprocess.call([sys.executable, "-I", "-B", "-X", "utf8", str(script), *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
