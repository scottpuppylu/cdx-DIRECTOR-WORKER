# 06b 需要時才讀的程序

只在做這些事時讀：被打斷後恢復（含總監自身）、建立或修改續航機制、額度中斷後接續、刪檔之前、用 stash / hook / 備份推送、下載或裝開源工具。平常的規則在 `docs/06`、`docs/08`。

## 規則

### 恢復程序（任何 session 被打斷後第一件事）

1. 重讀：工單 → 自己的 RESUME_STATE → 專案 AGENTS.md → 本專案版規則（總監另讀 `DIRECTOR_STATE.md`）。
2. `git status`、`git log -3`，和 RESUME_STATE 的 HEAD 比對；不一致先查原因，不覆寫。
3. IN_FLIGHT：只檢查自己的 PID。程序不在了，就看完成判定檔；不完整就列入重做。**中斷的擷取、量測、打包、匯入一律重做，不沿用。**
4. 被中斷的 GO：通知總管「RESUMED <task>，需要重新排程」，不假設時段還有效。
5. 自己設的計時器、背景等待、監看程序：全部視為可能失效，逐項確認或重建。
6. 更新 RESUME_STATE（時間 + 恢復說明），先處理 COMMS 裡欠別人的，才繼續 NEXT_STEP。
7. 第一則給總監的訊息只有一行：`RESUMED <TASK_ID> at <checkpoint>; next=<step>; waiting=<誰或 NONE>; redo=<第 3 步列入重做的輸出或 NONE>`。沒有需要總監知道的事就不發。總監把收到的這一行（或自己恢復時的同一行）記進 `DIRECTOR_LOG`，`metrics_report.py` 從這裡數中斷後遺失的工作。

PO 手動停止後再讓它繼續，也要先完整跑一次這個程序：停止那一刻的指令可能只跑了一半，背景程序可能變成沒人管的孤兒程序。

### 每輪第一步與總監自身的恢復（2.2.0）

總監每次喚醒、壓縮或恢復後只有一個第一步：**先唯讀檢查並收集輸入，再處理待決頁**。收集完之前不改檔、不派工、不重建。

1. 唯讀收集：跑 `cdx doctor`，讀本機待決帳、未處理的 PO 聊天回答、`DIRECTOR_LOG.md` 最新段落和工作線。對帳不清楚時用 `cdx session status … --live` 和 `reconcile`；保留找不到的來源和原因。
2. 處理待決頁：照收件帳本套用 PO 的回覆和新留言，同輪執行或派工並關閉；未能完成寫續辦紀錄（`docs/03`）。
3. 檢查腳本報缺的才重建；補發被中斷的工單或決定。
4. 巡查時（2.2.2）量一次所有工作線的 RESUME_STATE：`tools/memory_size_check.py --kind resume --workstreams <DIRECTOR>/ACTIVE_WORKSTREAMS.md`（或 `--glob "<根>/**/RESUME_STATE*.md"`），只讀。OVER 的工作線，由總監叫它照下面「RESUME_STATE 瘦身」做；巡查本身不搬檔。

**合併工具呼叫**（題 5）：第 1 步的本機檔案和檢查腳本用同一個本機唯讀呼叫讀完，逐項印出來源和成功 / 失敗，讀不到的那一項照實列出，不當成「沒有新事」。待決帳照 `docs/12` 讀回覆原文和版次；worker 狀態只在恢復或要採取行動時才查。

### 接手演練

隔離 Git fixture 準備兩版簡單成品。一條工單完成第一個 checkpoint 後中斷，保存工作樹、工單與狀態。PO 在待決帳填一項選擇，新總監只收到「繼續這個專案」，用本機檔與 thread 史找回原候選。確認 PO 回覆只記一次，工作線沒有重派；候選若改版，舊證據不得自動延用。

以 `metrics_report.py --run` 記 asked、answer_received、applied、closed 和 preview_ready，記下無法實測的步驟。

### git 細節（2.1.0 從 `docs/08` 移來）

- stash 是所有 worktree 共用的，可能拿到別的 session 的修改。真的要 stash，用 `git stash push -u -m "<唯一標記>"`，記下 SHA，用 `git stash apply <sha>` 還原。
- 選用 `cdx setup --hooks` 提供 Codex 工具護欄。用 `cdx doctor --live` 分別查配置、信任與適用版本。
- 子代理承接父線權限，Hook 覆蓋逐種工具驗證。獨立唯讀 reviewer 使用新 root thread 與寫入探針。
- PO 授權了私人備份推送時，用一支會拒絕大檔與疑似秘密、只做一般 push、事後核對遠端 SHA 的腳本；腳本拒絕就停下回報，不繞過。

### 下載與開源工具（2.1.0 從 `docs/08` 移來）

- 下載的東西放在新的空目錄，用 `python -I` 這類隔離方式處理，從下載目錄外執行。
- 開源工具：只用原作者或官方來源、固定版本或 commit；執行前先讀安裝腳本和主要程式，確認沒有網路回傳或刪檔行為；隔離安裝；登記名稱、來源、版本、授權、用途、路徑、移除方式。

### 機制要能重建（guard check）

- 每個排程和防護機制（壓縮設定、喚醒計時器、排程任務、閒置監看、快照）都不能只活在 session 記憶裡。每一項要有：**檔案紀錄、檢查方法、重建指令**，寫在 `DIRECTOR/GUARDS.md`。
- 寫一支只讀的檢查腳本（原專案叫 `guard_check`），逐項印 `OK / MISSING` 和重建指令，缺任何一項 exit 1。在每輪第一步跑它（上面「每輪第一步」）；重建由總監在自己的 session 背景執行（背景程序要屬於總監，才能叫醒總監）。
- 新增任何機制時，同一步就要加進 GUARDS 表和檢查腳本，否則不算完成。
- 閒置監看把「GO 後逾寬限仍沒有 ACK」列成獨立狀態 `NO_ACK` 並觸發，不套用執行時限的豁免。監看的測試至少三案：GO 逾寬限沒有 ACK 會觸發；GO 還在寬限內不觸發；GO 後有 ACK 不觸發。監看程序有沒有在跑，列進 GUARDS 表，每輪自查和恢復時都檢查。

### 狀態腳本和防護的對象（1.3.0）

- 每條工作線一支 `status.py`：`tools/status_gen.py --config <設定> --out <線的資料夾>/status.py` 產生，一次印出 log 尾段、雜湊、磁碟（GiB）、git 摘要、最新輸出，總長有上限。在每輪第一步跑它，不逐項重查（L-042）。
- 總監版從 `templates/status_director.json` 改起：多印待決頁的計數（PO 已回覆 / 新的）、未結案工單、還沒送出的訊息、每份動作紀錄最近 1 小時的筆數 / 被擋次數 / 讀 log 次數 / session 數，以及該常駐的程序（例如閒置監看）有沒有在跑。讀不到待決頁或程序沒在跑就 exit 1；路徑換成專案自己的。
- cdx 以 Git common directory 綁定狀態。Hook 按已註冊的 session ID 讀角色，App Server 稽核按 thread ID 記。
- 用 `cdx doctor --live` 查工作區的設定與 Hook 信任；用 `cdx session status` 檢查當前工單的分支及 thread。
- 每週用 `tools/poll_hint.py report --log <動作紀錄> --days 7` 看各線手動讀 log 的次數，次數高的線提醒它等完成通知（L-041）。
- 單一工作線的摘要（2.3.0）：`tools/line_brief.py <線名> --config <status 設定>` 一次印那條線的看板行、git 狀態和最後一個 commit、最新結果檔的開頭、log 尾段；設定寫在 status 設定的 `"lines"`（`templates/status_director.json`）。要看某條線時跑它，不逐項查；不是每輪必讀。
- 授權快到期（2.3.0）：`tools/doctor.py --licenses <授權清單>` 列出剩不到 3 天（`--license-days`）的授權和是哪個工具持有的；只檢查授權用 `--licenses-only`。清單是 JSON 或 Markdown 表（tool / license / expires）。

### 用量中斷後復工

保存待決、目前候選 SHA 和回合結果。額度恢復時間以使用者介面為準。重新開啟時先對帳，從 P0 和最接近交付的線處理；cdx 的復工不依賴排程。只有 PO 明確需要定期提醒時才設定宿主排程。

### RESUME_STATE 瘦身（2.2.2）

RESUME_STATE 每次續接都整份讀進 context，太大就是每輪多花額度。上限是整份 20 KiB、單行 4 KiB（`director_work.json` 的 `resume.max_bytes`、`resume.max_line_bytes`）。`gate_check.py --resume` 超過時印 `~ shadow: RESUME_SIZE`，加 `--strict` 才判不過。

- 「壓縮」在這裡只代表**原文搬移**：舊內容一字不改搬到同資料夾的 `RESUME_HISTORY_<YYYYMMDD>.md`，RESUME_STATE 在原處留一行索引（段落開頭、日期、歷史檔名、sha256）。不刪、不摘要、不改寫。
- **永遠不動**：四行表頭（仍是四行）、有 `UPDATED:` 的現況段、標題或開頭含 `resume.protect_headings` 的段落（預設 現況／未結／OPEN／BLOCKED／TODO／待辦／IN_FLIGHT／DO_NOT_REPEAT）、最近 `resume.keep_recent` 筆紀錄（預設 10）。**近期只用筆數算，不用日期算**（PO 2026-11-14）：一般段落用裡面的完整日期排先後，最新 10 筆不動，和第 10 筆同一天的也不動（同一天分不出先後）。沒有完整日期的段落排不出先後，不動並印 `~ shadow: RESUME_ORDER`。
- 表頭的 `Before:` 鏈：`Before:` 本身就是新到舊的順序，每行保留現況文字和最新 10 筆，更舊的原文搬走，行尾留 `[RESUME_ARCHIVED: ...]`，表頭仍是四行。某一筆是空的（筆數不明），或 `(MM-DD HH:MM)` 開頭顯示後面的比前面的新（順序不明），整行不動並印 `~ shadow: RESUME_HEADER`。新寫的 `Before:` 請用 `(MM-DD HH:MM)` 開頭，順序才查得到。
- 做法（工作線自己做）：先 `tools/resume_archive.py <RESUME_STATE.md>`（dry-run，只列可搬 / 保護的段落和搬後 bytes / token），看過再加 `--execute`。`--execute` 先寫 `.bak`，搬完驗證 (a) 歷史檔逐字含搬走的內容 (b) 留下的部分 sha256 不變、表頭仍是四行 (c) 搬走＋留下＝原檔；任何一項不過就從 `.bak` 還原並 exit 1。`.bak` 不刪。
- 全部可搬的都搬完仍超過上限時，工具印 `~ shadow: RESUME_SIZE protected part over limit`，保護段落不動，交總監人工判斷（例如請工作線把已結案的現況文字改寫短，那是工作線自己的編輯，不是工具做的）。
- 舊的 RESUME_STATE 照樣能讀：沒有超過上限的不用改；歷史檔是一般 Markdown，需要時再讀。

### 刪檔之前

- 刪除前逐條比對三份清單：擁有者的保留段、總監的保留清單、受保護清單，各寫「無衝突」或「衝突 → 不刪」。有疑問就不刪。
- 不在版控內的工作資料（例如 worktree 裡的本機資料夾），刪除前先產生盤點清單（路徑、大小、SHA-256）存檔。
- 同一路徑不能同時出現在「保留」和「可回收」，改標記要附系統時間並刪掉舊標記。
- 擁有者同意還不夠：刪 build 或審查匯出前，先 grep 所有工單、PLAN、RESUME_STATE 有沒有提到這個名稱；有提到的等總監確認。可以重建的，也先寫明重建用的 commit（L-026）。
- **刪除五步**（2.5.0，L-072）：① 先列清單（路徑一行一個）② `tools/delete_guard.py --list <清單> --repo <每個 repo> --refs "<各線>/**/RESUME_STATE*.md"`，exit 1 的項目不刪，等總監確認 ③ 搬進隔離區或備份，記 SHA-256 ④ 過一段保留期才真刪 ⑤ 對帳：刪了哪些、留下哪些、清單和實際一致。先隔離、可復原期過了才刪，是雲端儲存「soft delete」的做法（Google Cloud Storage〈Soft delete〉，https://docs.cloud.google.com/storage/docs/soft-delete ，2026-11-16 查）。
- 工作線自己剛產出的中間檔也不刪：不用的 `mv` 到 `_trash_pending/` 交給清理員；要換掉試做的輸出就寫到新資料夾（b1 → b2），試做最好直接寫進暫存資料夾（L-023）。

### 程序衛生（2.5.0）

- **停背景工作要連子程序一起看，只停自己的。** 停掉背景工作後，它開的子程序可能還在跑。先依完整命令列列出程序樹（Windows：`Get-CimInstance Win32_Process | Select ProcessId,ParentProcessId,CommandLine`；Linux：`ps -eo pid,ppid,args`），只停自己啟動的那棵樹的 PID，不依名稱停程序（同名的可能是別人的，或是常駐服務）。（收件匣 L-063）
- **批次前先用程式自己的規則驗名稱。** 由參數組出來的名稱（輸出檔名、資產名、分支名），在批次開始前用目標程式自己的命名規則全部驗一次，不合的先改；監看程式除了看完成檔，也要在「N 分鐘沒有新 log」時停下回報，不無限等。（收件匣 L-062）
- **commit 不用 `;` 接。** 檢查步驟和 commit 用 `&&` 串，檢查失敗 commit 就不會跑；commit 前先 `git diff --cached --check`（會報殘留的衝突標記和空白錯誤）。要自動擋，`templates/.pre-commit-config.yaml` 的 `dw-conflict-markers` hook 在暫存檔有 `<<<<<<<` / `>>>>>>>` 行時停下 commit（選用，要自己裝 pre-commit）。（收件匣 L-065）
- **JSON 用 JSON parser 讀，不用 grep。** 多行或縮排不同的 JSON，grep 一行一行比會永遠對不上；閘門要讀 JSON 欄位就用 `python -c "import json,sys; print(json.load(open(sys.argv[1]))['key'])" 檔名` 或工具本身的 `--json`。（收件匣 L-075）
- **時間取時鐘，不手打。** 紀錄、報告、標頭裡的時間用 `tools/ran_line.py --stamp` 或系統時鐘印，不憑記憶打；手打的時間曾經寫成未來時間。（收件匣 L-070）
- **CRLF 檔不用 `sed -i`。** Git Bash 的 `sed -i` 會把整個 CRLF 檔改成 LF，而且含 `\r` 的比對常常沒套上。改檔前後各看一次 `file <檔>` 或 `git ls-files --eol <檔>`，換行不能變；改檔用會保留原換行的方式（編輯器工具、或讀 bytes 改完原樣寫回的小腳本）。（收件匣 L-069；換行規則見 git〈gitattributes〉）
- **改 RESUME 標頭要安全重寫。** 先把整份讀進來、只換四行表頭、寫到暫存檔，比對「新檔行數 = 舊檔行數」和表頭以外的內容不變，才換掉原檔；不用會先清空檔案的重導向（`> 檔`）邊讀邊寫。（收件匣 L-068）
- **量測跑次要獨佔機器。** 排了量測（效能、時間、GPU）的時段，自己也不在同一台機器跑別的工作；同時有別的工作，這次量測作廢重跑，不拿來比。（收件匣 L-066；Google SRE workbook〈Canarying Releases〉：指標要能歸因於變更本身）
- **非版控輸入要有清單（2.6.0）。** build 需要、卻不在版控裡的檔（未追蹤的原始檔、被忽略的設定、產生的快取），在 `pre_tr.py` 設定的 `inputs` 列出路徑、來源和 SHA-256；缺了就 `MISSING_INPUT` 明確 STOP，新工作樹在第 0 步就知道缺什麼。工具不寫死別的工作樹的路徑：用環境變數加搜尋，找不到就用特定 exit code 結束，不靜默改用別的資料。刪鎖檔前先確認沒有對應的程序在跑，只刪那一個檔並記錄。（收件匣 L-082）

## 為什麼

- 原專案有一次 worker 在清單還沒做完時就結束回合，閒置了 80 分鐘沒人發現。之後才加了閒置監看，並規定「真的要等，就寫明在等誰、等什麼，並用背景等待觸發」。
- 機制要能重建，因為重開機、壓縮和額度重置都會讓背景程序消失，而 session 自己不會記得它曾經設過什麼。
- 原專案發生過兩次：在保留清單送達前，當作證據的 build 被刪掉，刪前也沒有盤點。之後才加了三份清單逐條比對和刪前盤點。
