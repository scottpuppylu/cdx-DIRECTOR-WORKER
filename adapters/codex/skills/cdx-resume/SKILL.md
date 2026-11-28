---
name: cdx-resume
description: Resume a cdxdw Director or worker after Codex compaction, handoff, or a change of Desktop worktree.
---

讀 `DIRECTOR/INDEX.md`，照它接手，不要重問已確認的需求。

隔離工作樹若沒有 DIRECTOR，用 `git worktree list --porcelain` 找同一 Git 專案的主要工作目錄，讀那裡的 INDEX。工單依 INDEX 和派工紀錄找現行版，核對 RESUME_STATE 的下一步、工單指紋和 checkout 的完整 HEAD。若有換手清單，先用共用的 `handoff.py verify` 核對，再繼續。
