---
name: cdx-review-gate
description: Review cdx work-order evidence and independently verify a candidate before issuing a Director verdict. Use for cdx worker handoffs.
---

# Review a candidate

Locate the project's cdx state from `director-work-cdx.json` in the Git common directory. Read the exact dispatched order, worker report, and the kit's `docs/07_quality_gates.md`. Verify the candidate in its assigned checkout with `cdx work review <order> --candidate <full-sha> --rerun` when the approved commands are in scope.

For independent review, give a fresh reviewer the specification and candidate diff. Verify the reviewer's environment before asserting physical read-only access. Record your own checks, outstanding manual acceptance, and PO-only criteria in `templates/GATE_VERDICT.md`. A successful turn alone provides no test evidence.
