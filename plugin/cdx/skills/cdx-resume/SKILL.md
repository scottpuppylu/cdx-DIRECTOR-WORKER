---
name: cdx-resume
description: Recover an existing cdx DIRECTOR-WORK project or work order after interruption, compaction, or a new Codex session.
---

# Resume a cdx work line

Find `director-work-cdx.json` in the Git common directory. For a Director role, read that state's `PO_PENDING.md`, `RESUME_STATE.md`, and relevant log lines. For a Worker role, read the assigned order and `work/<ID>/RESUME_STATE.md`. The installed kit contains `docs/06b_on_demand_procedures.md`.

Compare the order hash, branch, full HEAD, and saved thread ID. Inspect `cdx session status … --live` for a possibly in-flight turn and `cdx session reconcile …` for an ambiguous launch before retrying. Resume from the last independently verified checkpoint. Preserve evidence and pending user answers.
