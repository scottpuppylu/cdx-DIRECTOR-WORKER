---
name: cdx-review-gate
description: Review cdxdw work-order evidence and independently verify a candidate before issuing a Director verdict. Use for cdxdw worker handoffs.
---

# Review a candidate

Locate the project's cdxdw state from `director-work-cdx.json` in the Git common directory. Read the exact dispatched order, worker report, and the kit's `docs/07_quality_gates.md`. Verify the candidate in its assigned checkout with `cdxdw work review <order> --candidate <full-sha> --rerun` when the approved commands are in scope.

For independent review, give a fresh reviewer the specification and candidate diff. Verify the reviewer's environment before asserting physical read-only access. Run the approved product entry with `work e2e` or record a manual result with `work record`. Record REVIEW and PO decisions separately, then use `work final` for the single candidate. For a release that combines work orders, use `work integrate` against the current target and ordered sealed candidates.
