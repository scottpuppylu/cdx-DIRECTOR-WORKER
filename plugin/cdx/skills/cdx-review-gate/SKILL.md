---
name: cdx-review-gate
description: Review cdxdw work-order evidence and independently verify a candidate before issuing a Director verdict. Use for cdxdw worker handoffs.
---

# Review a candidate

Locate the project's cdxdw state from `director-work-cdx.json` in the Git common directory. Read the exact dispatched order, worker report, and the kit's `docs/07_quality_gates.md`. Verify the candidate in its assigned checkout with `cdxdw work review <order> --candidate <full-sha> --rerun` when the approved commands are in scope.

For a native code review, seal the candidate and run `session native-review <order> --candidate <full-sha>` to preview the range. Add `--run` to launch the Codex reviewer. Use its findings alongside a fresh review of the specification and product criteria. Run a pinned `E2E_COMMAND` with `work e2e`. Use `work record` for manual observations and REVIEW or PO decisions, then use `work final` for the single candidate. For a release that combines work orders, use `work integrate` and verify the delivery SHA with `work integration-status <id> --expect-head <full-sha>`.
