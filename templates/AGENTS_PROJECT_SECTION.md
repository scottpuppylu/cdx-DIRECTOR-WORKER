<!-- cdx:begin -->
## cdxdw DIRECTOR-WORK

在受工單派工或接續 cdxdw 時，從 `git rev-parse --path-format=absolute --git-common-dir` 的目錄讀 `director-work-cdx.json`，用它找到此專案的狀態與 `PROJECT.json` 的 kit。總監每輪先讀 `PO_PENDING.md` 和自己的 `RESUME_STATE.md`。Worker 依工單範圍在指定工作樹施工，以個別 `RESUME_STATE.md` 續航。交件必須記 commit 與可重跑證據。詳情按需使用 `cdx-bootstrap`、`cdx-dispatch`、`cdx-review-gate`、`cdx-resume` 與 `cdx-release`。
<!-- cdx:end -->
