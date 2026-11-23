# DW 系列比較與 cdxdw 2.6.0-cdx.3

2026-11-24 依 Git tag 和提交固定調查基線。範圍包含同一維護者可查到的四個公開 DW 專案。

| 專案 | 調查基線 | 可移植的做法 |
|---|---|---|
| [DIRECTOR-WORK](https://github.com/scottpuppylu/DIRECTOR-WORK/tree/v2.6.0) | `v2.6.0` · `787f67bb7483cf07ac45f450a3f9e57262383359` | 初衷條目指紋、派工版本、核准前測試、驗收與 PO 回覆分別留證。 |
| [dshdw](https://github.com/scottpuppylu/dsh-DIRECTOR-WORKER/tree/v2.6.0-ds.6) | `v2.6.0-ds.6` · `df53e7938fa53d7a97554e92aee0e6afe3d19d59` | 預先鎖定測試，獨立核准規格與計畫，將 worker 報告和平台事後稽核互相比對。 |
| [agydw](https://github.com/scottpuppylu/agy-DIRECTOR-WORKER/tree/v2.6.0-agy.5) | `v2.6.0-agy.5` · `7d75362c0834b696ea1974ecb768a55184ec1e74` | 安裝鎖涵蓋讀取、合併和寫入，升級保留 Hook 開關，依 worktree 隔離稽核，E2E 綁候選。 |
| [cdxdw](https://github.com/scottpuppylu/cdx-DIRECTOR-WORKER/tree/v2.6.0-cdx.2) | `v2.6.0-cdx.2` · `64472c6a32091f3230588cac2b50d3c3c3d9a244` | Codex App Server 的具名 worktree、thread/turn ID、結構化工具與用量事件，以及候選 commit 的獨立重跑。 |

採用端的交接也呈現了規則檢查、鎖定輸入、交付包及公開入口實驗的用途。cdxdw 保留這些上游工具，將本版修改集中於 Codex 專屬入口與證據連接。

## 實作對照

| 問題 | cdxdw 做法 | 可重現的檢查 |
|---|---|---|
| 不同 Git repo 同時指定相同狀態目錄 | 用主 checkout 的 Git 共用目錄與 canonical state 確認歸屬，依外部目的地加鎖。 | 併發安裝到同一目錄，只有一個 repo 完成登記。 |
| Hook 更新覆蓋使用者設定 | 以已知版本的 managed command 判斷歸屬，保留 matcher、timeout、enabled 與其他 handler。 | 自訂 Hook 配置重裝後逐項比對，停用時留下其他 handler。 |
| 草稿替換、工單或需求實質變動 | 核准初衷和派工分別保存快照，按條目指紋檢查已核准需求。 | 草稿可繼續編輯。鎖定變更後，舊候選的最終驗收拒絕。 |
| 回合啟動已接受但回應遺失 | 唯讀取 thread 歷史，以 turn ID 或唯一啟動標記尋找；逾時對已知回合發送停止請求。 | 回復測試先收到不相關回合，翻頁才對上原始回合。 |
| 模型回合完成掩蓋工具失敗 | 按 thread、turn、item 匹配事件，命令成功須有結構化退出碼；保存匯入來源指紋。 | 合成命令 exit 7、回合 completed；破損來源不發布半份稽核。 |
| E2E 或重跑收據沿用其他候選 | 認定當前乾淨 HEAD、派工 SHA、報告雜湊和對應候選的公開入口紀錄。 | 錯候選與舊派工證據拒絕，正確 fixture 能走完整流程。 |

App Server 的唯讀查詢與停止依 [Codex App Server](https://learn.chatgpt.com/docs/app-server)。Hook 信任與沙箱各自取證，實際可用性依使用者所用的 Codex 版本與環境。 [Hooks](https://learn.chatgpt.com/docs/hooks) · [Approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security)

## 驗證範圍

- `tools/selftest_cdx.py` 在臨時 Git 專案跑共用狀態競爭、Hook 變更保留、派工、對帳、候選和稽核測試。
- `research/probe_app_server.py` 透過實際 Codex CLI 和正式 JSON-RPC 客戶端，接本機 Responses fixture，觀察原生事件及重啟後的唯讀對帳。
- 原生 fixture 的模型回覆固定。Windows 自動施工、桌面實際交接和正式模型的獨立 reviewer 有各自的驗收條件。 [Codex 移植和驗證矩陣](../CODEX-PORT.md)
