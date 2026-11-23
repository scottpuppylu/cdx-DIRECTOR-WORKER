# 13 施工安全閘門

用四個可查的狀態保護工程交付。建立前先確認資料可保留的方式，實作後逐項驗證。

| 閘門 | 記錄 | 驗證 |
|---|---|---|
| 規格與派工 | 原需求、工單版次、獨立規格審查、SCOPE／FORBIDDEN、AUTO 指令 | `gate_check --order`、cdxdw 工單雜湊及 DIRECTOR_LOG |
| 規劃 | 核准的 PLAN、工單 SHA、Git base | `cdxdw work approve-plan` 記錄檔案和工單指紋，App Server 施工前核對 |
| 施工 | 具名 worktree、短斷點、隔離沙箱、選用 Hook | `cdxdw doctor`、工單與工作線對帳、`scope_check` |
| 交件 | 完整候選 SHA、worker 報告、可重跑證據、總監裁決 | `cdxdw work review --candidate … --rerun`、`gate_check --verdict` |

## 先鎖驗收條件

驗收設計要基於目前的產品行為與獨立的期望值。既有測試可寫進 FORBIDDEN，或用 `TESTS_LOCKED` 留內容指紋，避免施工時一併改掉測試。需要更動已鎖測試時，由總監確認理由和新預期，更新工單版次、重新派工。Strict 保留完整 spec review 和測試／成品覆核證據。

## 計畫與候選

計畫包含各 AC、入口、要改的檔案、測試與回退條件。總監核准後再改程式。如果 PLAN 或工單變動，重審並重新核准。工單範圍有限時，可以把 `REQUIRED_CHANGES` 和禁止路徑定得具體，避免缺行或牽涉其他專案。

總監從已註冊工作樹讀取 candidate，不信任報告自己宣告的 HEAD。review 核對派工與候選，AUTO 依工單驗收命令重跑。若工單修改、紀錄屬舊候選或重跑失敗，改寫裁決前先查實際問題。詳見 [品質閘門](07_quality_gates.md)。

## 權限、分段與停工

- Worker 使用 single writer，每張工單一條寫入線。Reviewer 的物理唯讀必須由有效沙箱和寫入探針證明。
- Hook 放行表示這次沒有命中該規則；結果仍依宿主限制。PostToolUse 寫的宿主輸出摘要保持待確認，只有帶終態與 exit code 的命令事件可證明執行結果。
- 遇到越界、需不可逆的動作、需授權或連續兩輪根因沒有進展，記入 TASK REPORT 和 RESUME_STATE，把決策交回總監。
- `evidence_record verify --rerun` 會執行候選中的程式碼。只核准有正當目的且環境允許的工單指令，依候選信任程度選擇適當限制。
