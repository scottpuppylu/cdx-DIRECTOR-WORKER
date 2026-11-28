# Codex 轉接工具

## 安裝

1. 從規則包執行 `python -I -B -X utf8 adapters/codex/cdxdw.py --repo PROJECT install` 預覽，小白模式加 `--mode beginner`。確認後加 `--execute`，看到 `CDX_INSTALL: APPLIED` 表示已寫入專案設定。
2. 在專案對話用 `/hooks` 核對來源並信任，再以同支工具執行 `doctor --live`。看到 `CDX_DOCTOR: PASS` 才算完成。小白模式在第一個需求問題前做完這兩步，其餘建置依 BOOTSTRAP 後續步驟。
3. 把 PO 確認原話記入初衷卡，再用共用 `spec_gate.py approve` 存快照。工單對回初衷卡，交付附成品、SHA 和證據。

`VARIANT.json` 集中登記預設強度 `standard` 和規則來源 `AGENTS.md`。既有專案明寫的強度沿用。安裝時由基板跳過標成 Claude 選用的工具。既有工具由基板安裝器備份後再換版。

## 新增

| 功能 | 操作 | 判定 |
|---|---|---|
| 專案安裝 | 在規則包執行 `cdxdw.py --repo PROJECT install`，選談需求優先時加 `--mode beginner`，確認後加 `--execute` | 共用工具安裝到 `DIRECTOR/tools/`，專案規則追加到 `AGENTS.md`，同步 `cdx-resume`，`DIRECTOR/` 加入 `.gitignore`，Hook 設定只存在本機 |
| Hook 與檢查 | 在同一個專案對話以 `/hooks` 信任專案設定，再跑 `cdxdw.py --repo PROJECT doctor --live` | 哪個事件未受信任就停下，工作樹也要各自確認 |
| 派工 | PO 確認後執行 `DIRECTOR/tools/spec_gate.py approve --brief DIRECTOR/BRIEF.md`，再用 `cdxdw.py --repo PROJECT prepare --order WO-001 --base HEAD` 及 `dispatch WO-001.md` | 開工作樹和印派工紀錄前都要查到核准快照，採工單已有的基板規則 |
| Desktop 接手 | 在 Desktop 先選隔離工作樹，原總監用共用 `handoff.py export`，接手用 `attach --worktree PATH --candidate FULL_SHA`，加 `--chat UUID` 可由宿主核對對話位置與閒置狀態 | 只登記同專案的乾淨工作樹，先驗交接清單與 SHA，再在 Desktop 開相同工作樹、信任 Hook 並貼 README 的接手句 |
| 原生盲審 | `native-review --base BASE_SHA --candidate FULL_SHA` 預覽，加 `--run` 才啟動，可用 `--model NAME` 選帳號支援的模型 | 在只含待審程式的獨立 Git 目錄，驗證連線隔離和 sandbox 讀寫，再交 Codex 原生 Review，收據給總監查閱 |
| 用量 | `usage EVENTS.jsonl --format exec`（可改 `app-server`） | 讀 Codex 的原生用量欄位，值不合法時用基板標記 partial |
| 產品資產 | `asset-check --candidate FULL_SHA --root ASSETS --asset FILE_IN_DELIVERY ASSET_NAME` | 用基板核對交付紀錄，再對照要上傳的成品大小與 SHA-256 |
| 發版檢查 | 在規則包 checkout 執行 `cdxdw.py release-check --base FROZEN_CHECKOUT --candidate FULL_SHA` | 核對基板同步、交付 SHA 及隱私掃描。系列 README 由基板檢查。發版由 PO 核准，流程使用基板鎖定的交付 SHA |

各例使用 `python -I -B -X utf8` 執行。安裝後除安裝與規則包發版檢查，其餘動作可由 `DIRECTOR/adapters/codex/cdxdw.py` 執行。交接前如有兩套工作目錄，請核對 Git 共用目錄及當前 SHA。跨獨立 clone 依基板的 `handoff.py verify` 搬移證據與 refs，再開同名工單續作。

R6 核准前可讀與研究，可經明確路徑在 `DIRECTOR/` 寫需求與進度。核准前，Hook 會對收到的產品寫入、開工作樹與派工呼叫查規格。核准後，命令攔截依指定規則，受保護路徑的檢查仍有效。其他 Git 操作由 `AGENTS.md` 與操作者把關。放行與拒絕結果用合成事件驗過。僅透過安裝完成並信任的專案會話操作。Codex 宿主可能在 Hook 無法啟動或逾時時放行，見 [Codex Hooks](https://learn.chatgpt.com/docs/hooks)。遇到宿主診斷失敗就停下。受管派工、工作樹及發版檢查的工具本身取得失敗或缺失的結果時一律拒絕。

## 沿用上游

`spec_gate`、`worktree`、`gate_check`、`handoff`、`delivery`、`install`、`privacy_scan`、強度、用量數字與結束碼判定沿用共用工具。交付紀錄用 run 的實際候選 SHA、證據指紋，以及逐驗收條件、逐環境的判定。原生 Review 輸出請納入基板裁決流程。

`tools/base_sync_check.py --base PATH` 比對基板原文、覆寫的原始指紋以及新增檔的清單。更新基板時先合併，再逐項審閱覆寫，最後更新 `BASE_SYNC.json` 的提交與檔案指紋。原本 adapter 下的入口轉呼叫這支共用工具。

## 拿掉（NOT_PORTED）

| 做法 | 理由與替代 |
|---|---|
| Claude 的私有頁面、模型設定、Hook 安裝 | 在 Codex 用 `PO_PENDING.md`、聊天、Codex 專案 Hook 與原生 Review |
| cdx.10 的 C1／C2／C3／C4／C7 副本 | 核准、交付、匯出／驗證和工具安裝已由基板提供 |
| cdx.10 的 GitHub CI 綁定收據和多工單整合狀態機 | 基板將 C5／C6 延後。總監可先合併進隔離工作樹，照實際交付組合跑驗收 |
| cdx.10 的 GUI 自動搬移、私有 thread 續接和舊狀態遷移 | Desktop 選擇工作樹後按清單接手。現有資料先備份，手動挑選可核對的紀錄帶入 |
| cdx.10 專用 Compact、用量和發版入口 | 交接狀態用 RESUME_STATE；原生日誌用 `usage` 讀取與換算；發版走共用審查及隱私流程 |

Credits：DIRECTOR-WORK 系列、Claude 轉接層的覆寫清單，以及 Codex CLI 的 Hook、App Server 和 Review。
