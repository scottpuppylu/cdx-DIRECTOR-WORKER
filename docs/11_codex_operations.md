# 11 Codex 操作手冊

## 三個工作入口

| 入口 | 可用能力 | 一般用法 |
|---|---|---|
| Codex Desktop | 本機聊天、Worktree、Hand off、變更檢閱、內建瀏覽器依環境開放 | 總監與 PO 對談，由獨立 checkout 開 worker。保留工作分支上的候選 commit。 |
| Codex CLI | `-C`、`--sandbox`、`--worktree`、`exec --json`、`review` | 在指定 checkout 工作或重跑驗收。CLI review 的單一 commit 和 base range 要選對。 |
| cdxdw App Server | 具名工作線的 thread / turn / item API、狀態對帳、用量與稽核 | `cdxdw session` 透過本機 stdio 建立及接續 thread。安裝與派工本身可不送模型回合。 |

[App Server](https://learn.chatgpt.com/docs/app-server) · [Codex worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees) · [CLI](https://learn.chatgpt.com/docs/developer-commands)

## 原生 App Server 流程

1. 用 `work prepare` 準備完整 base SHA 上的乾淨分支。工單的 WORKTREE 是施工路徑，WORK_DIR 是該工單交件資料夾。
2. 完成規格審查後用 `work dispatch`。其時間、工單 ID、版次和雜湊進 DIRECTOR_LOG。
3. 用 `session new` 登記工作線。第一次 `session run` 才建原生 thread 並送回合，避免把空 thread 當作可以恢復的歷史。
4. 用 `--phase plan` 執行唯讀規劃。總監將計畫落檔後跑 `work approve-plan`。用 `--phase implement` 開施工。cwd 和專案外唯一的額外可寫根是該工單 work 目錄。
5. 施工修改完成後，若 Codex 沙箱不允許 Git 索引寫入，總監在候選 checkout 檢查範圍並按專案規則提交；交件紀錄以最後的候選 SHA 為準。
6. 用 `session status … --live` 核對伺服器歷史。若意外中斷，先 `session reconcile …`，對帳找不到新回合後才用 `--reset-empty`。手動開了另一個 turn 時，對帳會要求處理歸屬。
7. 驗收前可用 `session new … --role reviewer --candidate <sha>` 和 `session run … --role reviewer --phase review`。Reviewer 使用另一個 root thread 和唯讀寫入探針。共用的父工作線子代理只做相符權限的工作。

App Server 會拒絕它收到的命令或檔案核准請求。遇到需要外部資源、其他專案或使用者抉擇的情況，將待決項寫入 PO 帳並把對話交回總監。做完單一回合不自動開下一回合。

## Desktop 工作線與手動交接

用 `work prepare` 產生預期分支路徑。在 Desktop 選擇該 checkout 作為工作區，貼工單絕對路徑、範圍、允許寫入的目錄和角色。人工交接從 `RESUME_STATE.md`、最新報告和完整候選 SHA 接手。未啟用 App Server 的 Desktop 工作線也可使用相同工單、驗收和裁決工具。

Desktop 管理的 worktree 可能是 detached HEAD、帶有本機未提交改動或由宿主清理。用具名分支保留候選，驗收前重新核對 Git common dir、base、HEAD 和工作樹。如果要用 `cdxdw work` 的自動入口，使用其指定 worktree 和分支。

## Hook、沙箱與 Plug-in

- `setup --hooks` 在信任的專案配置 SessionStart、PreToolUse、PostToolUse。已有 JSON 的其他 Hook 保留。安裝配置與信任是兩個狀態。
- `work prepare` 把機器本地 Hook 設定放進適用的 worker worktree，由 Git 的本機排除清單保留乾淨工作樹。worktree 若已有版控中的 Hook 設定，以該版設定為準。用 `cdxdw session register-director THREAD_ID` 登記總監，讓它在接續時收到斷點定位。
- 信任入口是 Desktop 的 Hook 審查與 CLI 的 `/hooks`。查看目前的可信來源、命令和路徑；版本升級後重新核對。
- `doctor --live --probe-sandbox` 分別查看配置、Hook 及寫入探測。App Server 啟動模型回合前會做邊界正反控制。Windows readiness 不是 ready 時停止自動回合。
- Hook 辨識 `apply_patch` 路徑及上游規則支援的命令／MCP。OS 沙箱與工單驗收仍各自檢查。部分宿主工具不走此 Hook 路徑。
- 本 repo 附 `.agents/plugins/marketplace.json` 和 `plugin/cdx`。在 Codex Desktop 開這個 checkout，可以從 repo marketplace 選用；project setup 也能直接布署同樣的五份 Skill。見 [Plugin 封裝](https://developers.openai.com/plugins/build/plugins)。

## PO 答覆與展示

總監在聊天詢問，`PO_PENDING.md` 記決定 ID、工單版次、原文與候選。能使用宿主選項元件時，它只是輸入介面，帳本仍保存回覆。展示圖片附可打開的本機成品路徑或宿主展示方式。上傳、公開及切換帳號依專案授權處理。
