"""Public command entry point for cdx-DIRECTOR-WORKER (cdxdw)."""

import argparse
from pathlib import Path
import subprocess
import sys


COMMANDS = ("setup", "doctor", "work", "session", "audit", "usage", "release", "handoff")


def main(argv=None):
    tools = Path(__file__).resolve().parent
    version = (tools.parent / "VERSION").read_text(encoding="utf-8").strip()
    parser = argparse.ArgumentParser(prog="cdxdw", description="DIRECTOR-WORK for local Codex")
    parser.add_argument("--version", action="version", version=version)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    script = tools / f"cdx_{args.command}.py"
    return subprocess.call([sys.executable, "-I", "-B", "-X", "utf8", str(script), *args.args])


if __name__ == "__main__":
    raise SystemExit(main())
