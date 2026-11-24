---
name: cdx-release
description: Prepare and verify a release for a cdxdw-managed project with release authorization and CI evidence.
---

# Release after verification

Read the project's release policy, `docs/07_quality_gates.md`, and the guarded release section in `tools/CDX-TOOLS.md`. Use `cdxdw release --repo PROJECT --integration ID --head FULL_DELIVERY_SHA --ci-run RUN_ID` for the dry run. It checks the ordered integration, trusted workflow, and required jobs at the exact delivery SHA. Include the named CI artifact digest when the project policy requires it. Record the version, commit, CI receipt, and recovery path. Use `--execute` within the release authorization already given for the project.
