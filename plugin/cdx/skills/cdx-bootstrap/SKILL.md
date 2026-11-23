---
name: cdx-bootstrap
description: Install or upgrade cdx DIRECTOR-WORK for a local Git project and prepare the first project brief. Use when the user asks to activate cdx or set up project director mode.
---

# Set up cdx

1. Find the target Git project and the `cdx-DIRECTOR-WORKER` checkout. If the kit is missing, get the user-requested version from `https://github.com/scottpuppylu/cdx-DIRECTOR-WORKER` and read `PURPOSE.md` plus `BOOTSTRAP.md`.
2. Establish general or beginner mode and preserve existing project instructions. In beginner mode, ask what the first usable version needs before opening work lines.
3. Show the setup plan via `python -I -B -X utf8 <kit>/tools/cdx.py setup --repo <project>`. Apply the intended project setup, then run `doctor --live`. Hooks require their own trust review. Report readiness from observed evidence.
4. Register the user's requirements, first scope, and intended acceptance in `BRIEF.md` and `PO_PENDING.md` under the stated cdx state directory.
