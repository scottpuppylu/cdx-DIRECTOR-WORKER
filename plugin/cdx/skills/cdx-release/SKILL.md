---
name: cdx-release
description: Prepare and verify a release for a cdxdw-managed project with release authorization and CI evidence.
---

# Release after verification

Read the project's release policy and the guarded release section in `tools/CDX-TOOLS.md`. A sealed single order or an ordered combination can produce the required integration receipt. Use `cdxdw release --repo PROJECT --integration ID --head FULL_DELIVERY_SHA --ci-run RUN_ID` for the dry run.

Before landing, use `--push-only` with candidate-branch CI or use the repository's merge workflow. Once the delivery SHA is on the target branch, use that branch's current CI for publication. Verify the archive and its accepted member digests when the release includes a built artifact. Use `--execute` within the release authorization already given. Record the commit, CI receipt, version, and recovery path.
