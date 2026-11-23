# cdx 版本紀錄

## 2.6.0-cdx.1 — 2026-11-24

- 以 DIRECTOR-WORK v2.6.0 建立獨立 Codex 版。上游歷史見 [CHANGELOG-upstream.md](CHANGELOG-upstream.md)。
- 新增 `cdx` 入口與可重跑安裝，部署 project skills、選用 Codex Hooks、Git 專案識別及版本化 runtime。
- App Server 支援工單工作線、角色限制、原生 thread/turn、斷點對帳與用量。Git worktree 以固定 base 建立。
- 移植上游工單、報告與裁決工具。新增測試鎖、規格／計畫指紋以及候選 commit 獨立重跑。
- 加上 README、BOOTSTRAP、分章治理手冊、本機 plugin 與整合 CI。

對齊初衷（PURPOSE.md）：維持 PO 的權限，保留可追溯的施工、續航與驗收證據。缺少實測的宿主能力標在 [CODEX-PORT.md](CODEX-PORT.md)。
