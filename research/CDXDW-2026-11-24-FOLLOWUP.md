# cdxdw .6 對照獨立研究的補強

本輪依 [獨立研究的剩餘優先順序](CDXDW-2026-11-24-INDEPENDENT-REVIEW.md#剩餘優先順序) 接回原版控管與 Codex 特化入口。

| 缺口 | 採用方式 | 證據邊界 |
|---|---|---|
| 整合收據未接實際發版 | `cdxdw release` 接在發版乾跑與遠端操作之間。重新驗該整合、交付 commit 與 tree、目前目標、可信 workflow 的 SHA-256、最新執行及各必要 job。可要求指定 CI 工件摘要。推送使用已驗證的完整 SHA。 | 用錯 SHA、更新後失敗的 CI 及有效 run 測試。GitHub Actions 的結果由 API 讀取。 |
| Desktop 移交遺失未提交內容或外部狀態 | `handoff export/verify/attach` 對照同一份 Git 物件、暫存與未暫存的 diff、未追蹤的檔案內容、封存 refs 及工單紀錄。可選擇在目的地比對外部狀態副本。 | 可由兩個 Git checkout 和獨立 clone 重現。跨主機實際搬運依既有 Git 和狀態備份流程。 |
| compact 回復缺少事件證據 | 已配置 Hook 收到有角色的 startup／resume／compact 後留下 SessionStart 雜湊鏈事件。 | Hook payload 回歸可核對指示和紀錄。受信任的 Desktop 實際 compact 尚待操作環境驗證。 |
| 可行性、pre-TR 輸入和 CPU 檢查 | `CDX_GATES` 在工單快照選用。可行性綁工單、AC、base 及原始紀錄。pre-TR 設定綁 base，外部輸入有來源和 SHA-256，缺失或不符先停止。 | 測試涵蓋漏基準試跑、缺檔、輸入改動、成功物化，以及原工作樹保留。 |
| 量測 coverage 與成品包 | CLI 入口和裝置輸出可跑上游 ruler。審查包用 pack_check 確認格式、覆蓋、檔案及內容指紋。 | 已測 exit 0 且零匹配時回 INVALID、成功樣本、pack 有列檔缺漏時失敗。 |
| 報告宣稱與可靠稽核 | 已登記 session、報告與最新外部 AUDIT_HEAD 可交給 `audit report` 和工單證據閘門。缺終態、無法核對的宣稱或被截短的稽核不能充當通過證據。 | 測試涵蓋實際可核對、錯命令、舊 anchor。來源完整度依宿主事件。 |
| PO 回覆和改判 | 選用保存原文與訊息引用。原始 bytes 依 SHA-256 留檔，候選、工件及改判留在 acceptance journal。 | 已驗證逐位元保存與缺引用時拒絕。操作者身分依專案的登入和授權程序。 |
| App Server／原生 Review 與調度 | 審查程序停用 MCP、Apps、Plugins、Hooks 和 web search。啟動前查有效設定及 MCP 清單。可從既有 receipts 量測重跑、復工及用量，再決定調度方式。 | 真實模型、實體沙箱、Desktop Local→Worktree→Local 與跨主機操作需要合格環境。 |

工具與配置見 [工具手冊](../tools/CDX-TOOLS.md)。
