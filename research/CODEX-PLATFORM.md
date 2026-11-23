# Codex 特化研究

2026-11-24｜Windows 11 Pro build 26300｜Codex CLI `0.160.1`｜DIRECTOR-WORK `v2.6.0`

**Codex 版最值得做的地方，是把一張工單變成可監看、可復工、可稽核的工作線。** 總監把工單版次、Git base、worker thread ID、候選 commit 與驗收結果綁在一起，重開之後仍知道哪一個候選有證據、哪一步要補做。agy 版以原生分支工作區、Hook 與宿主紀錄達成同一工程目標，Codex 可以用 App Server 的結構化事件和持久 thread 實作這條路徑。 [agy 移植實證](https://github.com/scottpuppylu/agy-DIRECTOR-WORKER/blob/f4e80e669057c49754f1ace7455e967adffb0a42/ANTIGRAVITY-PORT.md) · [Codex App Server](https://learn.chatgpt.com/docs/app-server)

## 原生能力怎麼用

| 能力 | 對 DIRECTOR-WORK 的價值 | 首版設計 |
|---|---|---|
| App Server threads 與事件 | 可用 thread ID 接回工作線，用 turn ID 與 item ID 檢查一項工作到底有沒有執行完 | 以 App Server 管理獨立 worker。派工帳記錄初始 commit、Git common dir、worktree、thread ID 和工單雜湊。重啟先對帳，再決定續接或重跑。 |
| Git worktree、Desktop Hand off | 可以把施工和主 checkout 分開，之後用桌面版檢視或接手 | 自動派工使用固定 base 的具名 worktree。桌面 Worktree／Hand off 可供人操作，接受前仍查 HEAD、工作樹和 Git 共用目錄。候選 commit 另外保留在具名 Git ref。 |
| `SessionStart`、`PreToolUse`、`PostToolUse` | 支援復工提醒、攔截部分工具操作、發送下一步提示 | `SessionStart` 匹配 `resume` 與 `compact`，只提供可信的工單定位與讀檔提示。工具防護依項目測試 Bash、`apply_patch` 和啟用的 MCP；每個 Hook 區分已配置、已信任和實際命中。 |
| 沙箱與自訂子代理 | 可依任務區分施工與審查的執行權限 | 子代理承接父工作線的權限，適合查資料或平行讀程式。獨立審查另以新 root thread 和經探針驗證的唯讀執行環境啟動，輸入只包含規格、候選 diff 與驗收案例。 |
| 專案 Skill、`AGENTS.md` | 讓總監工作流按需載入，工作線各自取得 repo 規則 | `.agents/skills` 放工單與驗收流程。`AGENTS.md` 放該 repo 的入口、規則與驗證命令。部署檢查以 `skills/list` 和 `instructionSources` 的回傳為準。 |
| 用量事件與 CLI JSONL | 能用結構化事件看最近 token 用量、快取和工具結果 | App Server 接 `thread/tokenUsage/updated`。單次 CLI 任務可接 `codex exec --json`。`inputTokens` 已含快取部分，兩欄保留各自原值；上下文視窗未回傳時顯示未知。 |

[App Server API](https://learn.chatgpt.com/docs/app-server) · [Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees) · [Hooks](https://learn.chatgpt.com/docs/hooks) · [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) · [Build skills](https://learn.chatgpt.com/docs/build-skills) · [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)

### 三個會影響設計的邊界

1. **專案信任和 Hook 信任是兩個狀態。** 本機已信任 fixture 專案時，`hooks/list` 仍把新 Hook 列為 `untrusted`。正式版需顯示目前信任狀態與實際執行證據。`SessionStart` 在壓縮後的注入可依官方事件使用，但仍要在目標版本驗證。桌面由使用者審查 Hook，CLI 可用 `/hooks`。 [Hook 信任與生命週期](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks)
2. **沙箱有效性要實測。** 新的隔離 Codex 設定下，Windows readiness 回 `notConfigured`，`command/exec` 指定 `readOnly` 呼叫仍寫入了測試檔。同一測試中的模型工具 `exec_command` 則被本機政策拒絕。兩個執行路徑要各自測試。首版唯讀審查的合格條件包含 readiness、同路徑的實際寫入拒絕，以及審查 thread 只可存取必要工具和資料。 [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox) · [App Server Windows readiness](https://learn.chatgpt.com/docs/app-server#windows-sandbox-setup-windowssandboxsetupstart)
3. **Git worktree 隔離修改，交付仍需固定 commit。** 桌面管理的 worktree 通常從 detached HEAD 開始，可能帶入本地未提交改動，也有自動清理。派工時應固定 base，獨立重跑時應取得候選 commit 的乾淨工作樹。原生 `review --commit` 看單一 commit，跨多個 commit 的工單以固定 base 到候選的整體 diff 審查。 [Worktree 建立、交接與清理](https://learn.chatgpt.com/docs/environments/git-worktrees) · [Codex review](https://learn.chatgpt.com/docs/developer-commands)

## 本機探針結果

探針使用含空格與中文路徑的兩個臨時 checkout。模型回覆與 token 數值由 loopback fixture 提供。App Server、Git 和工具政策實際執行，探針沒有呼叫 OpenAI 模型。 [重現程式](probe_app_server.py)

| 探針 | `0.160.1` 的觀察 |
|---|---|
| Skill、專案指示載入 | 主 checkout 與施工 worktree 都發現已提交的 project skill。`thread/start` 的 cwd 指向施工 worktree，`instructionSources` 包含施工 worktree 的 `AGENTS.md`。 |
| Hook 發現 | 兩個 checkout 都列出 `SessionStart`，狀態皆為 `untrusted`。目前只驗證發現與信任狀態。 |
| 原生 thread 復工 | 伺服器關閉後，正式 JSON-RPC 客戶端先用 `thread/read` 和 `thread/turns/list` 唯讀查到相同 thread 與完成的回合，再以 `thread/resume` 接回原 worktree。 |
| 用量事件 | 收到 `thread/tokenUsage/updated`。fixture 提供 `input=80, cached=60, output=5, total=85`，App Server 原樣投影。這組數字只測欄位語意，沒有實際模型用量。 |
| 工具失敗與回合完成 | `exec_command` 收到政策拒絕，探針沒有觀測到這次命令的 `commandExecution` 完成項，但 `turn/completed` 的狀態仍是 `completed`。 |
| 沙箱執行 | `windowsSandbox/readiness=notConfigured`。獨立 `command/exec` 指定 `readOnly` 與 `workspaceWrite` 皆以 exit 0 寫入各自的測試檔。結論限於這次新設定和測試路徑。 |

## 首版的工單流程

1. **派工**。總監確認工單、驗收指令與 base。沿用上游工單及雜湊，啟動新工作線時存下 Git common dir、worktree、thread ID、工單 ID、版次和雜湊。worker 只寫施工區及自己的交件區。施工安全區和總監資料區的權限依有效沙箱驗證。
2. **記錄**。訂閱事件，用 `threadId`、`turnId`、`item.id` 去重與對帳。保留必要狀態、exit code、允許的產物路徑與雜湊。指令輸出可包含專案資料，預設留摘要與稽核所需欄位。工具被拒、未觀測到終態或回合被中斷時，驗收條件標為待確認。
3. **接手**。從派工帳找正確的 thread，對照目前 Git base、候選與未終結項目。先查 App Server 歷史，再讀 `RESUME_STATE.md`。重連後遇到已記錄的回合或仍在進行的工作，先找原工作結果，避免重派同一工單。工單狀態由總監更新。
4. **驗收**。候選 commit 必須與工單範圍、交件報告及證據一致。`scope_check --candidate` 檢查範圍，`gate_check --match` 綁定版次與候選，`evidence_record verify --rerun` 由總監按工單允許的指令在乾淨候選上重跑。需要人工審查和 PO 驗收的條件各自記錄。
5. **決策**。`PO_PENDING.md` 保留問題 ID、選項、回覆原文和對應候選。桌面或聊天回覆可接入同一帳本；App Server 結構式提問目前屬實驗能力，待決項目不能把回合中斷、提示消失或逾時當成使用者回覆。 [App Server 提問與核准](https://learn.chatgpt.com/docs/app-server#approvals)

第一個完整驗收案例應含一個兩 commit 的小工單。讓 worker 在第一個 commit 後中斷，重啟 App Server 再續接；交件時刻意放入一份早於候選 commit 的測試紀錄，確認被拒。改為正確的候選證據後，讓總監獨立重跑並對照實際輸出。若唯讀審查的寫入探針無法通過，保留這一關的未驗證狀態。待驗證項目還包括受信任 Hook 實際命中、壓縮後提醒、可寫 worker 的正常交件及桌面 Hand off。
