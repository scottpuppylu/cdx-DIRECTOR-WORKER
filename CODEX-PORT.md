# DIRECTOR-WORK → cdx-DIRECTOR-WORKER

`cdx-DIRECTOR-WORKER` 的產品簡稱是 `cdxdw`，本版 `2.6.0-cdx.2`。上游 `v2.6.0` commit `787f67bb7483cf07ac45f450a3f9e57262383359`。安裝、工單、審查和恢復由這個 repo 提供。

## 對照同系列移植

| Repo | 產品簡稱 | 發行版本 | 平台工具前綴 | 主要治理途徑 |
|---|---|---|---|---|
| `dsh-DIRECTOR-WORKER` | `dshdw` | `2.6.0-ds.6` | `dsh_` | DSH 缺少原生 Hook，以本機 session 紀錄事後稽核、獨立工作樹和安全閘門補足。 |
| `agy-DIRECTOR-WORKER` | `agydw` | `2.6.0-agy.4` | `agy_` | Antigravity 的事前 Hook、角色權限、分支工作區、復工與 transcript 稽核。移植報告另有真實 worker 和獨立 reviewer 的 E2E。 |
| `cdx-DIRECTOR-WORKER` | `cdxdw` | `2.6.0-cdx.2` | `cdx_` | Codex App Server 的 thread、turn 和 item 事件，配合具名 Git worktree、可選 Hook 與候選 commit 的獨立重跑。現有原生流程驗證採本機仿製模型回覆。 |

cdxdw 採 `<上游版號>-cdx.<移植版次>`。本次是 Codex 移植本身的修正，因此由 `.1` 進到 `.2`。公開入口為 `tools/cdxdw.py`。用既有 `tools/cdx.py` 呼叫也會進入同一套工具；外掛 ID、Skill ID 與儲存指標使用平台前綴。 [dshdw 移植報告](https://github.com/scottpuppylu/dsh-DIRECTOR-WORKER/blob/v2.6.0-ds.6/DEEPSEEK-PORT.md) · [agydw 移植報告](https://github.com/scottpuppylu/agy-DIRECTOR-WORKER/blob/v2.6.0-agy.4/ANTIGRAVITY-PORT.md)

## 分層與同步

1. 上游的 PURPOSE、MIT 授權與版本歷史留在獨立檔案。此版有 77 份上游檔案與 `v2.6.0` 的 Git blob 逐位元一致。共用 Python 工具與治理格式維持上游介面，例如 gate、scope、trace、evidence、audit、release、pre_tr、ruler、run_plan、waiver 和 pack。
2. `tools/cdx_*.py` 是平台層，負責安裝、診斷、Git 工作線、App Server、Hook、用量和稽核。手冊第 11、13 章和 PO 工作流為 Codex 撰寫。
3. `plugin/cdx` 提供五個可按需叫用的工作流 Skill。以 [官方 plugin 格式](https://developers.openai.com/plugins/build/plugins) 打包，可用 repo marketplace 或 project setup 的安裝入口。
4. 舊版 Claude 專屬的設定、transcript、Artifact 頁與容器工具隨共用套件保留供上游相容與回歸。cdxdw 的 active 入口走新平台層。

上游更新時，先固定 tag 和 commit，核對原樣核心 Git blobs，再查看 doc 和 schema 的差異。先驗 install、work order、independent rerun、thread resume、Hook trust、用量與章節連結，再將 cdxdw 版次對齊。新版 runtime 裝在不同版本目錄。

## 能力對照

| 治理能力 | cdxdw 實作 | 範圍與限制 |
|---|---|---|
| 開 worker／恢復 | App Server JSON-RPC 加本機 session 登記；Git 具名 worktree | Desktop 手動工作同用工單格式；桌面 Hand off 走宿主介面 |
| 權限 | 每個模型回合驗證寫入邊界，監看 Windows readiness；獨立 reviewer 使用唯讀 root | 寫入探針是對直接 executor 的量測；MCP、遠端工具和外部服務另外依宿主權限 |
| Hook | PreToolUse 沿用上游規則的可辨識路徑，加 `apply_patch` 和 cdxdw 目錄判斷；PostToolUse 寫摘要；SessionStart 指向斷點 | 專案配置與信任分開，工具覆蓋按宿主與版本驗證 |
| 記錄 | 派工 SHA、計畫、範圍、候選、事件雜湊鏈、typed exit code | 回合 completed 只證實回合結束。缺命令終態維持待確認 |
| 用量 | App Server tokenUsage、Codex CLI JSONL | 不推算帳單、額度重置或未揭露的 context 資料 |
| PO 待決 | 本機帳本 + 聊天，保留回覆原文、版次與候選 | 宿主選項是回覆介面。原有 Claude Artifact 的頁面與監聽協定留供相容 |
| 包裝 | 通用 plugin manifest 和本機 repo marketplace | 安裝至使用者層需由使用者選擇 |
| 成品審查 | 工單是驗收來源，總監重跑核准指令與檢查公開入口 | 圖像、外部瀏覽器、產品與 PO 驗收依各工單實際驗證 |

## 驗證矩陣

- `python -I -B -X utf8 tools/selftest_cdx.py --verbose` 在臨時 Git repo 驗證安裝及重入、兩個候選的驗收、稽核、Hook payload 和重啟對帳契約。
- `python -I -B -X utf8 tools/selftest.py` 驗證上游工具與共用範本。
- `python -I -B -X utf8 research/probe_app_server.py` 用實際 Codex CLI 和 loopback provider 驗證工作樹 Skill、Hook 信任狀態、結構化用量、持久化回合。另一個本機探測觀察到空 thread 在重啟後沒有 rollout，所以 cdxdw 把 native thread 建立延到第一次回合。
- 在隔離的 Codex CLI `0.160.1` 資料目錄，實測 `cdxdw doctor --live` 發現五份 project skills 與三個尚未信任的 Hook；CLI 的 marketplace 能發現 cdxdw plugin。
- 從 `v2.6.0-cdx.1` 發行內容安裝到隔離 Git 專案，再用 `.2` 升級。待決帳原文與舊 runtime 都保留；`.2` 的兩個入口回報同一版本。
- 已知環境限制：本機 Windows 探針的沙箱狀態為 `notConfigured`。這臺機器不能用該配置驗證自動施工及物理唯讀；正式專案可走手動工作樹與工具閘門。沒有用真實模型、桌面 Hand off 或真實 compaction Hook 做這份發版測試。實測細節見 [平台研究](research/CODEX-PLATFORM.md)。

## 操作入口

[README](README.md) · [建置](BOOTSTRAP.md) · [Codex 操作](docs/11_codex_operations.md) · [工具手冊](tools/CDX-TOOLS.md)
