---
name: cdx-dispatch
description: Write, validate, and dispatch a cdxdw DIRECTOR-WORK order to a Codex worktree. Use after a cdxdw project has been initialized.
---

# Dispatch a cdxdw work order

Resolve the Git common directory with `git rev-parse --path-format=absolute --git-common-dir` and read its `director-work-cdx.json`. Use that state pointer to find `PROJECT.json` and its installed kit. Read `docs/02_work_orders_gates.md`, `docs/11_codex_operations.md`, and `templates/WORK_ORDER.md` from the kit.

Pin the base commit, scope, forbidden paths, order revision and acceptance commands. Perform the governance level's spec review before dispatch. Register an existing Desktop worktree with `cdxdw work adopt` or create a named worktree with `cdxdw work prepare`. Use `cdxdw work dispatch` to publish the approved snapshot for the worker. Review `PLAN.md` before `cdxdw work approve-plan` and implementation. Start model turns within the user's dispatch authorization. Keep the worker's report and evidence in its order work directory and use `work seal` to retain the committed candidate.
