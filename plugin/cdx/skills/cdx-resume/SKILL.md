---
name: cdx-resume
description: Recover an existing cdxdw DIRECTOR-WORK project or work order after interruption, compaction, or a new Codex session.
---

# Resume a cdxdw work line

Find `director-work-cdx.json` in the Git common directory. For a Director role, read that state's `PO_PENDING.md`, `RESUME_STATE.md`, and relevant log lines. For a Worker role, read the assigned order and `work/<ID>/RESUME_STATE.md`. The installed kit contains `docs/06b_on_demand_procedures.md`.

Compare the order hash, branch, full HEAD, and saved thread ID. Inspect `cdxdw session status … --live` for a possibly in-flight turn and `cdxdw session reconcile …` for an ambiguous launch before retrying. Resume from the last independently verified checkpoint. Preserve evidence and pending user answers.

For a Desktop handoff, compare the current manifest before attaching the receiving worktree. Follow the saved `RESUME_STATE.md` location after compaction. A Hook event records that the host ran the Hook and gives a resume location. Check that the referenced state was actually read before continuing.
