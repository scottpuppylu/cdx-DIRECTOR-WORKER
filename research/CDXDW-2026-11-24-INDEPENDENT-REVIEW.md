# cdxdw 獨立研究與實作

下一版應先讓總監能回答「眼前要交付的這個提交和工件，最後一次實際驗了什麼」。手動觀察、命令重跑、個別候選、整合候選及 PO 判定各有來源，舊成功隨新失敗失效。第二步把上游的 run-plan 接進候選公開入口，避免程式跑完卻用了錯的開關。第一個 Codex 特化入口選原生 Review，從封存的完整候選範圍建立獨立審查，留下可查的原生結果。這些修改已在本機 `2.6.0-cdx.5` 候選實作。接著應做一次包含 Desktop Handoff、真實 reviewer、可寫入隔離及實際交付 SHA 的小型驗收。

產品應保留兩條容易上手的路。以 Desktop 操作的人用原生聊天、工作樹和 Handoff，cdxdw 負責核准、候選和驗收證據。需要程式化操作的人再選 App Server。兩條都用相同的 Git 和工單契約。優先投資身份綁定及可攜證據，可以用單一工具入口驗收，日後也能用現有 state 重建進度。

## 版本與調查範圍

2026-11-24 台北時間用 GitHub releases API、`git ls-remote`、本機分支及 `^{commit}` 核對。標籤表列解參照後的提交。比較按 ref 固定，原本打開的 checkout 僅用來核對工作狀態。

| 專案 | 正式版、主分支、候選 | 調查使用 |
|---|---|---|
| cdxdw | `.3`、`origin/main` 及 reliability 都是 `37730ffbec419f071a250e865d6a9bf62a4eaa8c`。候選 evidence 分支 `a9c8d1e19c48f2220093bd88cac52c7fb0b853ca`，程式版本 `.4`。 | 正式版和候選都讀取，候選以 Git archive 做故障重現。舊 `.1` `6a6758f`、`.2` `64472c6` 用來辨識遷移歷史。[正式發版](https://github.com/scottpuppylu/cdx-DIRECTOR-WORKER/releases/tag/v2.6.0-cdx.3) · [候選 CI](https://github.com/scottpuppylu/cdx-DIRECTOR-WORKER/actions/runs/45301529749) |
| DIRECTOR-WORK | `v2.6.0`、遠端 main 和本機 `claude/dw-v260` 都是 `787f67bb7483cf07ac45f450a3f9e57262383359`。原目錄在 `docs/readme-beginner-20261104` `dde49d8`。 | 用 tag 和 `v2.5.0` `decab48` 追 2.6 N1–N6，以及 2.4–2.5 的測試與審查慣例。對照既有 Handoff `req-only-trial/CLAUDE_RUN.md` 的人工派工方式。[正式發版](https://github.com/scottpuppylu/DIRECTOR-WORK/releases/tag/v2.6.0) |
| dshdw | GitHub `v2.6.0-ds.7` 和 main 是 `ea3107caff43f44576f5af18230f6aa3db0ea2bc`。既有本機 main 在 `v2.5.0-ds.6` `00cd1f6`。遠端另有歷史工作線 `claude/ds-224` `cb336ee`。 | 另建 clone，從 `v2.6.0-ds.6` `df53e79` 追 `.7`，尤其 run-plan、會話稽核、Windows 路徑及 CI 狀態。[正式發版](https://github.com/scottpuppylu/dsh-DIRECTOR-WORKER/releases/tag/v2.6.0-ds.7) |
| agydw | `v2.6.0-agy.6` 和 main 是 `2df34836c8afa35b07c4a898900312bef1063b99`。遠端未見另外的候選分支。 | 比對 `.3` 到 `.6` 的工作樹、證據、升級與測試。 `.5` 基線 `7d75362`。[正式發版](https://github.com/scottpuppylu/agy-DIRECTOR-WORKER/releases/tag/v2.6.0-agy.6) · [CI](https://github.com/scottpuppylu/agy-DIRECTOR-WORKER/actions/runs/45324462338) |

本輪起點 cdxdw 原 checkout 無未提交版控修改或其他連結工作樹。只見 Git 排除的 Python cache。保留原有 checkout、狀態及候選 refs，在 `D:\cdx-DIRECTOR-WORKER-review` 建立 `codex/cdxdw-independent-review` 從 `a9c8d1e` 施工。遠端 dshdw 比對另放 `D:\dsh-DIRECTOR-WORKER-research`。版本化 fixture 的工單、refs、報告、Hook 和執行環境都建在暫存 Git 專案。

`git ls-files` 建立 129 檔的候選清單，對比正式版 127 檔，兩版本合計 143 個不重複的 Git blob，候選約 38,185 行。逐檔讀取、解碼、定位入口與查證問題。Codex 平台與重要流程做語意追蹤。大型歷史、相容工具及測試做全文掃描和針對流程的抽查，這部分未完成每行的人工語意審讀。追蹤的檔案全為文字，依賴和生成檔來源另列。每檔指紋在 [閱讀清單](CDXDW-2026-11-24-FILE-REVIEW.md)。

同名路徑的 Git blob 比對也釐清「原樣移植」的口徑。候選與原版 2.6 共用 97 條路徑，其中 76 個 blob 一致。與 ds.7 共用 77 條、24 個 blob 一致，與 agy.6 共用 79 條、39 個 blob 一致。這是全庫同名路徑計數，與支線自己的「核心檔」子集可能不同，也不能用來推論功能覆蓋率。

## 從入口到實作與證據

| 正常入口與使用者步驟 | cdxdw 的實際路徑 | 原版／支線差異與影響 |
|---|---|---|
| 安裝／升級 | `BOOTSTRAP` → `setup` 計算寫入計畫 → 版本化 runtime 和 Git common dir 指標 → `doctor --live`。子目錄指令共用原專案狀態。 | agy.4–.6 對既有 settings 保留、工具版本切換及 worktree 探測做得完整。cdxdw 原先主 checkout 升級後，既有 worker 的 Skill 或 Hook 仍可指向舊版。新增顯式同步，保留 worker 原始碼工作。 |
| PO 需求及規格核准 | `BRIEF.md`、`PO_PENDING.md` → `lock-brief` → 工單條目指紋 → `approve-spec`。歷史 BRIEF 保持可追。 | 原版有選項頁、卡版本和對帳文書，Codex 以聊天及待決帳運作。角色和 PO 是可信操作方輸入。單靠命令列提供兩個不同 ID 不能證實獨立工作。 |
| 派工、計畫、權限 | `prepare/adopt` → `gate_check --order` → `dispatch` 紀錄文件摘要 → `approve-plan` → `session run`。 | 成功重派後依最後工單快照，這是 .4 已完成。上游 `GATE_FEASIBILITY` 正反控制、`pre_tr.inputs`、額度與硬體調度已有工具或範本。cdxdw 的 `approve-plan` 主要綁文件摘要，可執行 preflight 仍未全部接上。 |
| 施工、接手 | App Server thread/turn 綁角色與 cwd，加本機 attempts / audit。Desktop 可登記 detached worktree，`seal` 留 ref，`status` 查活躍工單。 | 原版與 agydw 有較完整的 Stop、resume 壓縮和長期封存程序。Codex 可依原生回合 ID 重新查歷史。Desktop 跨主機 Handoff 會搬聊天及 Git 狀態，外部 cdxdw state 仍需在目的地核對。實際 UI 尚待驗收。 |
| 獨立審查 | `work review --rerun` 用 `scope_check`、`gate_check` 和 `evidence_record verify`；獨立模型規格審查仍可用 `session … --role reviewer`。本輪加入原生 Review。 | 原版強調三層盲審。cdxdw 舊角色路徑依賴仍在的乾淨 worker checkout，原生路徑現在從 seal 重建，獨立 thread 無 worker 報告上下文。規格 AC、真實操作與 PO 仍由對應角色落證。 |
| 單一候選／成品 | `e2e` 物化 Git commit，執行已派工 argv → `record` → `final`。本輪支援選用 run-plan 和工件狀態查詢。 | .3 起重跑有 commit 約束，.4 已新增最新嘗試及選用工件，這輪修正來源混用。原版的 ruler、真圖、browser_check、測量截斷與 pack 等技術仍需按產品調用。退出碼只回答已設定的入口與執行條件。 |
| 整合／發版 | `integrate` 在目標 SHA 合併選定封存候選並執行公開入口。 `integration-status --expect-head` 核對最近收據及待發 SHA。 | 原版 `release.py` 的 dry run 檢查分支、版本、專案 selftest、公開前掃描及推送計畫。遠端 CI 和 cdxdw 收據由 CDX release Skill 交給總監依專案政策核對。GitHub merge queue 會生成自己的 SHA，需用實際部署源提交驗證。 |
| 稽核／復原 | `audit build/verify/status` 從 App Server 事件抽取 thread、turn、item、結構化退出碼與覆蓋。 `session reconcile` 按 ID／啟動標記查回合。 | dshdw 用宿主原始 session 做事後對帳，較完整地處理投影與來源。agy.6 明確區分非終態與結果。CDX 已有同類事件原則，這輪沿用於原生審查和執行來源。上游 `report_vs_audit.py` 與外部 hash anchor 仍需接入專案程序。 |

遠端測試結果也影響採用取捨。dshdw ds.7 的 Ubuntu 3.12 綠燈，Windows 3.11 的 `verify_dsh_run_unit` 因同一暫存路徑的長名與 8.3 短名比較失敗，Ubuntu 3.9 無法在 Ubuntu 26.04 runner 安裝。cdxdw 此前已把 Ubuntu 3.9 job 放在 22.04。本輪借鑑 dsh 對來源與終態的區別、agy 的版本化安裝和既有設定保留。沒有宣稱各支線所有發布版皆通過 CI。[dshdw CI 矩陣和日誌](https://github.com/scottpuppylu/dsh-DIRECTOR-WORKER/actions/runs/45310974505)

## 重現、修法與驗收契約

### P0 · 人工成功把已跑失敗覆蓋成放行

候選 `.4` 把 `work e2e` 和 `work record --kind e2e` 存成同一 kind，`latest_attempts` 取最後一筆。重現先對同一派工和候選完成 AUTO，將公開入口改為會受外部環境變化影響而退出 1，再加入人工成功。 `work final` 回 exit 0 和 `CDX_FINAL`。受影響的是總監由瀏覽器回報切回最終放行的那一步。

本輪分開讀取兩種來源。配置 `E2E_COMMAND` 的工單須有執行通過。同工件人工失敗也阻擋。沒有配置可執行命令時接受人工入口，保留無法用 CLI 驗收的實體裝置、Desktop 或人工工作流。舊 journal 以 `source=operator-recorded` 判讀，不改原檔。驗收負例為「命令 FAIL 其後人工 PASS，final 仍 exit 2」，正例為「鎖定入口成功，所需的獨立審查與 PO 也各自符合」。人工資料仍由操作方錄入。

### P0 · 草稿審批失去生效版的審查證據

`.4` 運用派工指紋選原工單，`approve-spec` 卻仍共用同一份 WO 級的報告和 JSON。實測批准 r2 草稿後，r1 的獨立重跑被拒，進一步的 final 顯示 AUTO UNKNOWN。被阻的是兩輪工作交錯時本來有效的舊候選。

`.5` 保存報告內容快照與以工單 digest 為鍵的收據。舊 r1 驗收直接讀 r1 收據。舊版檔案留在原處，`--active` 可用原報告與獨立審查身分把已有派工的審查補入新快照。驗收是保持 r2 報告可編輯、r1 仍重跑成功，並能查兩次審查的精確內容。相同 r1 的新版審查仍可覆核，內容快照保留。

### P0 · 整合已失敗仍可引用舊成功

兩個工作線各自把一個欄位從 1 改到 2，單獨執行上限 3 都成功。實際合併後 2＋2 超限。對同一組合跑上限 4 成功、再跑上限 3 失敗，`.4` 仍用舊 UUID 回 PASS。若最後由 GitHub 生成不同 merge SHA，舊命令也沒有待發 SHA 可以核對。影響整合驗收和發版前的判定。

`.5` 依目標、base、工單摘要、候選、工件和順序記錄當前嘗試。保存 RUNNING 後才做合併與驗收。新嘗試即接管目前狀態，終態失敗不回退到早成功。收據重查封存 refs、當前候選、單項驗收 ID 及計畫發布 SHA，支援以工件摘要驗組合。改動有意讓 `.4` 的舊整合 PASS 顯示 `LEGACY_NEEDS_VERIFICATION`，歷史檔原樣可查。驗收是同組合新失敗阻擋舊 UUID，待發 SHA 不同回 `WRONG_DELIVERY_HEAD`，目標前移或收據改變回 `STALE`，正常組合及一致的交付提交仍回 0。

本機整合的 `--argv` 仍由操作方帶入已核准命令。跨使用者／跨執行器正式發版宜用獨立 CI receipt 與專案分支保護，把政策及檢查與發布同一個提交綁在一起。一個本機 ref 的新 attempt 可驗指定整合，覆蓋 GitHub 上實際 merge commit 要另外取證。

### P1 · 既有 worker 更新與回復

`.4` 的已準備 worktree 由 `worker_skills` 寫入忽略檔。runtime 或 Skill 內容變更後，`prepare` 以 pristine base 作前提，而且將舊安裝 bytes 視為本地衝突。使用者正在施工時，要手動認出哪些檔案由 kit 管理。

`work sync-worker` 讀生效工單，核對 Git common dir 和 worktree，更新與保留 runtime 一致的管理檔。現有追蹤內容、工作修改和自訂 Skill 都保留；遇到無法辨識的 Skill 以失敗顯示。Hook 的現有 matcher 等由既有合併函式保留。工作目錄的內容、PO 原文、journal、派工和封存 ref 不隨 runtime 移動。升級重現使用實際 `.3` 和 `.4` 打包內容，並在 fixture 以保存的 owner、Skill、Hook 恢復到舊版。原生 Hook 信任是否須重核、跑到一半時怎麼協調宿主，仍須產品環境驗收。

### P1 · 把上游 run-plan 接回公開入口

原版 2.6 新增 `run_plan_check.py`，dshdw 原樣承接。cdxdw `.4` 也保留檔案，`work e2e` 的判定卻只看候選的實際退出碼。使用者若要做一批裝置測試，可能用錯起始開關但得到成功。

`E2E_RUN_PLAN` 選用已在工單 base 存檔的 `run-plan-v1`。新版先確認候選中的程式位置，執行後拿 stdout 提供的啟動行核對必要參數。fixture 的錯誤候選輸出 `--mode off`、exit 0，新增路徑回 `INVALID`。正例的 `--mode on` 通過。此處直接重用上游 checker，程式位置驗證存在性，啟動行驗證必要參數。測試仍應針對參數實際效果、輸出完整度和互斥開關另做正反控制。未設定 opt-in 的舊工單沿用原流程。

## Codex 原生能力的取捨

| 能力 | 版本、證據與選擇 |
|---|---|
| 原生 Review | Codex CLI `0.160.1` 實測 schema 有 `review/start`、`baseBranch`、`reviewThreadId` 及 `exitedReviewMode`，detached delivery 已標為 deprecated。用新 thread＋inline，base 傳完整 SHA，候選在乾淨 detached checkout。測到兩個 commit 的 base 進入 loopback 模型請求。 `--commit` 的語義是「單一提交所引入」，可能漏前一筆差異。桌面 stale merge-base 有公開 issue 記錄，僅用來辨識風險。 [App Server](https://learn.chatgpt.com/docs/app-server#review-delivery) · [resolver 原始碼](https://github.com/openai/codex/blob/rust-v0.160.1/codex-rs/prompts/src/review_request.rs) · [桌面 issue](https://github.com/openai/codex/issues/35667) |
| Desktop Worktrees／Handoff | Desktop 原生管理 checkout 與聊天，Linked worktree 共用 Git metadata。跨 host Handoff 需匹配的已儲存 repo，活動回合會中斷。優先利用已有 `adopt`、`status` 和 `seal`；路徑改變和外部 state 移轉須真的演練。 [Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees) · [遠端 Handoff](https://learn.chatgpt.com/docs/remote-connections) · [Git worktree](https://git-scm.com/docs/git-worktree) |
| Hooks、Skills、Plugins | 套件提供可發現的工作流程。實測原生 `skills/list` 可發現位於 fixture checkout 的 Skill，`hooks/list` 回 untrusted。可見、可信及在指定工具確實執行是三個檢查。保留小型入口與選用 Hook，權限以宿主為準。 [Hooks](https://learn.chatgpt.com/docs/hooks) · [Skills & Plugins](https://learn.chatgpt.com/docs/skills-and-plugins) |
| App Server／事件與權限 | 本機 0.160.1 由 `generate-json-schema` 固定協議，fixture 有 turn terminal、同 ID 重啟查詢與 tokenUsage。Windows readiness 是 `notConfigured`，直接 command probe 在 readOnly 設定仍寫了 marker。這解釋為何工具要求實體正反控制。原生審查收據保存狀態與結果。worktree 和唯讀寫入測試仍須各自驗證遠端、網路、MCP、檔案讀取等權限。 [0.160.1 發版](https://github.com/openai/codex/releases/tag/rust-v0.160.1) · [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox) · [Approvals](https://learn.chatgpt.com/docs/agent-approvals-security) |
| SDK、CLI 和 CI | App Server 適合控制原生對話和接收事件。SDK 或 `exec --json` 更適合無人值守的一次性 CI。確定性工作優先由專案現有測試處理，實際合併已在 CI 事件上預留 `merge_group`。本輪未變更遠端 ruleset、啟用 merge queue 或發動模型出帳。 [SDK](https://learn.chatgpt.com/docs/codex-sdk) · [CLI JSONL](https://learn.chatgpt.com/docs/non-interactive-mode) · [Codex GitHub Action](https://learn.chatgpt.com/docs/github-action) · [GitHub merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) |
| 外部工作流 | Aider 的自動 lint／test 適合施工中的快速回饋。cdxdw 保留 worker 快速自檢，另以已派工的受控入口和當前候選收據作為驗收依據。GitHub merge queue 對組合重新測試的設計，適合借用到發版 SHA。 [Aider 使用手冊](https://aider.chat/docs/usage/lint-test.html) |

預覽原生審查不用模型。 `--run` 之前先核對已封存提交、派工與初衷，建暫存 checkout，再經沙箱探針。收據在 `reviews/native/<WO>/<id>.json` 保留 base、head、diff 指紋與原生 thread／turn。 `RECORDED` 表示確實收到原生結果。模型結論、人工 REVIEW AC 及 PO 批准保留各自入口。此版原生審查 thread 為 ephemeral，結果以收據留存。斷訊或程序中止要以新嘗試重跑，故障不會產生可放行的結果。

## 重跑路徑與完成狀態

以下從研究 worktree 執行，本機需 Git 與 Python。 `--against` 的非零值代表重現中命中反例。

```powershell
python -I -B -X utf8 research/reproduce_cdxdw.py --against a9c8d1e
python -I -B -X utf8 research/reproduce_cdxdw.py
python -I -B -X utf8 research/reproduce_cdxdw.py --upgrade
python -I -B -X utf8 tools/selftest_cdx.py --verbose
python -I -B -X utf8 tools/selftest.py
python -I -B -X utf8 research/probe_app_server.py --native-review
```

獨立反例使用隔離的 Git archive，已觀察 `.4` 在 E2E 覆蓋、草稿審批和整合舊 PASS 的三個失敗。草稿審批的影響也在同工單下一次 final 出現。測試經公開 CLI，整合測試的 AUTO 前置收據由 fixture 建立，單工單的另一個測試實跑 AUTO。run-plan、工作樹同步、PO 變更、工件與錯候選涵蓋正負例。上游工具套件早期在 Windows 回報 3,159/3,159，有一項 symlink fixture 因權限跳過。原生探針回報實際協議及模型請求範圍。模型回覆由 loopback fixture 固定，CLI 的外掛目錄發現另有外部請求，回 401。Windows 實體唯讀沒有成立，因此同機的正式 `--run` 尚無完成證據。

cdxdw 自檢在 Windows Git 2.55.0／Python 3.11.9 和 WSL Ubuntu Git 2.43.0／Python 3.12.3 都是 12/12 通過。隔離專案完成真實打包的 `.3 → .4 → .5` 升級和備份還原 `.5 → .4`，比對 PO 原文、journal、工單、候選 ref 及未提交工作。現場升級仍要在結束執行中的舊指令後部署。保留下來的舊 runtime 可以用於回查，回到舊閘門也會恢復舊判定行為。

發版演練以實作提交 `b9b88a380f1ed0f02f06f188d63aea1695c5f6f2` 從暫存 clone 調用 `tools/release.py`，bare remote 的 main 固定在正式 `.3`。實測分支可快轉、版號與 changelog 對齊、cdxdw selftest 成功、工具內建掃描通過，輸出三個預計遠端步驟。執行前後比較 bare remote 的全部 refs，一致。當地 PATH 沒有 Gitleaks，遠端 CI 發版驗收仍待實際候選環境。

## 剩餘優先順序

1. **P0 · 在實際交付提交和可信執行器驗收。** 以支援沙箱的 Windows／macOS／Linux 跑真模型 Review、實際 shell／MCP 權限及 E2E。為實際 repo 的 CI merge SHA 接受外部執行者和收據，並把 `integration-status --expect-head` 接專案的發布入口。驗收要包含新分支、兩個工作線衝突、快轉/非快轉後 SHA 改變以及失敗不可發布。
2. **P1 · 走完 Desktop Local → Worktree → Local 和跨主機接手。** 用有未提交進度的既有專案，核對 chat、工作樹 path、候選、resume 與外部 state。預期兩步內能定位可續工作線，原案保留可回查的 receipts。只有這條跑過再決定是否做 Desktop 操作整合。應補用已受管理版本驗證 compact 後的工作指示與 Hook 事件覆蓋。
3. **P1 · 補原版實質驗收和審計缺口。** 優先在付費／裝置測試前接 `GATE_FEASIBILITY`、`pre_tr.inputs` 和 ruler 的可判定性。再讓 `report_vs_audit` 核對 worker 宣稱、失敗與部分回復資料，打包 `pack_check` 的證據及適用的外部 anchor。待決帳需要可查的 PO 原始回覆及異動；聲稱角色或會話 ID 的操作方身分可信度依專案需求訂定。
4. **P2 · 量測後才改儲存與調度架構。** 先收集工單完成、接手、錯綁及不必要回合的數據，再比較原生 Goals／子代理、CLI／SDK 或另加服務。落盤紀錄可用 Git 及檔案檢查，這輪無需引入 DB 或常駐程序。

這一輪交付的是本機候選、研究與可執行重現。真實 Desktop 操作、登入帳號、產品 UI 驗收、GitHub 發布與部署需有相應的環境及專案權限。
