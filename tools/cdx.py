"""cdx local command entry point."""

import argparse
from pathlib import Path
import subprocess
import sys


COMMANDS = ("setup", "doctor", "work", "session", "audit", "usage")


def main():
    parser = argparse.ArgumentParser(description="cdx — DIRECTOR-WORK for local Codex")
    parser.add_argument("--version", action="version", version=(Path(__file__).resolve().parents[1] / "VERSION")
                        .read_text(encoding="utf-8").strip())
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    script = Path(__file__).resolve().with_name(f"cdx_{args.command}.py")
    return subprocess.call([sys.executable, "-I", "-B", "-X", "utf8", str(script), *args.args])


if __name__ == "__main__":
    raise SystemExit(main())
