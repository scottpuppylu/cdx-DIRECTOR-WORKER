---
name: cdx-dispatch
description: Write, validate, and dispatch a cdx DIRECTOR-WORK order to a Codex worktree. Use after a cdx project has been initialized.
---

# Dispatch a cdx work order

Resolve the Git common directory with `git rev-parse --path-format=absolute --git-common-dir` and read its `director-work-cdx.json`. Use that state pointer to find `PROJECT.json` and its installed kit. Read `docs/02_work_orders_gates.md`, `docs/11_codex_operations.md`, and `templates/WORK_ORDER.md` from the kit.

Pin the base commit, scope, forbidden paths, order revision and per-acceptance commands. Perform the governance level's spec review before dispatch. Prepare a separate worktree with `cdx work prepare` and record the order hash with `cdx work dispatch`. Review `PLAN.md` before `cdx work approve-plan` and implementation. Start model turns within the user's dispatch authorization. Keep the worker's report and evidence in its order work directory.
