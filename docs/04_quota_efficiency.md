# 04 額度與效率

## 看得到的數字

`cdxdw usage <audit.jsonl>` 讀 App Server 的 tokenUsage，依 thread 保留最新累計、最近一次輸入峰值、可用時的上下文視窗。輸入 token 已包含快取的輸入部分。按會話累計取最新紀錄，避免把每個累計通知重複相加。缺少欄位時保留未知。

`codex exec --json` 可輸出單次執行的 JSONL。用 `cdxdw usage <file> --format exec` 累計完成回合。這些數據用於任務診斷。方案配額、帳單和部分失敗請求的用量以官方介面為準。 [非互動模式](https://learn.chatgpt.com/docs/non-interactive-mode)

## 決定上下文與工作線大小

1. 把穩定的 repo 指示放在簡短的 AGENTS.md。流程和個別專案證據用 Skill 與專案狀態按需讀取。
2. 工單交代完整需求、範圍和嚴格驗收，避免多輪來回補齊；大型輸出分檔保留，只回可核對的結論。
3. 依需求與偏好挑模型與 effort。首次先量一張代表性工單的實際成本，再決定增加工作線。
4. Context 成長時先整理 RESUME_STATE、保留 checkpoint，再評估同 thread 壓縮或新會話接手。沒有已驗證的上下文視窗時用狀態和實際速度，不猜百分比。
5. 要用並行作業時為各自的讀寫區和驗收分工，總監集中整合。等執行事件或結果，避免反覆問進度。

原上游的 Claude 實測數字保存在上游紀錄。Codex 本地探針使用仿製 token 數值測資料契約，使用者實際用量由自己的 Codex 環境回報。
