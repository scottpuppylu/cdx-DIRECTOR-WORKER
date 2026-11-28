# CHANGELOG

## 3.0.0-cdx.11 — 2026-11-28

- 從 2.6.0-cdx.10 接續序號，使用 DIRECTOR-WORK 3.0.0 凍結基板 `0e9ae22`。核准前，Codex 專案 Hook 會對收到的產品寫入、開工作樹及派工呼叫查規格。核准後，命令攔截依指定規則，其他 Git 操作仍由 `AGENTS.md` 與操作者把關。
- `AGENTS.md`、Codex Hook、本機安裝、Desktop 隔離工作樹接手、原生 Review 實際隔離檢查放在 Codex 層。核准快照、工單、CANDIDATE_HEAD、交付證據、交接清單改接共用程式。
- README 按新增、沿用上游、拿掉三段列差異。轉接層回覆不完整、缺結束碼或逾時會擋下。基板有完整獨立上游紀錄 `CHANGELOG-upstream.md`。

對齊初衷：縮短每輪需要讀的內容，讓中斷後能從紙面紀錄接手。規格與交付證據的關卡跟著候選走，最後由 PO 看成品裁定。

### 遷移

先備份舊紀錄，確認採用後再把初衷卡、工單、原始回覆、決策和可核對的證據搬進專案的 `DIRECTOR/`。以新版安裝器補上工具、Hook 與 INDEX，由使用者重新確認新版需要的欄位。以 `handoff.py` 重建交接清單。不同格式的舊收據留作歷史查閱。

### 延後

- 換手測試的真實跨平台路線（DW→cdx、cdx→DW、DW→dsh、DW→agy，R5／C3）：基板只放工具、範本和自動測試（`test_handoff_300` 用假的答案檔驗計分）。真的換平台要在 Codex、DeepSeek、Antigravity 上開對話，屬於各變體的工作，所以在各變體發版前跑，結果記在那一版的 CHANGELOG。同平台換帳號也一樣。
- CI 收據（C5）：留到 3.0.x。理由：cdxdw 的做法要讀 GitHub 的 CI run、attempt 和 workflow 指紋，綁在它自己的整合狀態機上（`cdx_work.py`），抽成平台無關又預設關閉的選項，要先定好收據格式和沒有 CI 的專案怎麼辦；這次硬做只會多一份沒人用的檢查。現在的替代：`delivery.py` 記交付 SHA，`gate_check --final` 核對。
- 整合試跑（C6）：留到 3.0.x。理由：兩張以上工單合起來試跑，要先有合併順序和衝突的規則，cdxdw 的版本同樣綁在它的狀態機上；基板目前只有單張工單的候選 commit 和證據，先不加新的必讀步驟。現在的替代：總監把要合的分支開在一個整合 worktree（`worktree.py open`）照常跑 CHECKS。

### 第二次基板凍結（9b10371）

| 上游項目 | 怎麼處理（沿用／改寫／不做） | 理由 |
|---|---|---|
| B1 候選差異 | 沿用 | 共用範圍檢查讀候選提交 |
| B2 E2E 失敗訊號 | 沿用 | 共用 final 辨識失敗 |
| B3 推送交付 SHA | 沿用 | 基板綁實際交付版本並查遠端是否變動 |
| B4 範圍大小與保護測試 | 沿用 | 工單或專案設定啟用 |
| B5 發版更新描述 | 沿用 | 由基板流程管理 |
| B6 README 與基板同步檢查 | 沿用 | adapter 的舊同步入口改為轉呼叫 |
| B7 系列 README | 改寫 Codex 入口 | 保留五版對照和平台已知限制 |
| B8 工單報告骨架 | 沿用 | 共用 gate_check 產生 |
| B9 共用隱私規則 | 沿用 | 檢查合併成一套 |
| B10 打轉狀態 | 沿用 | 狀態頁讀共用工具 |
| B11 選用安裝與派工表 | 沿用 | Codex 安裝省略標為 Claude 選用的工具 |
| B12 舊 E2E 開關 | 沿用 | 基板預設維持嚴格 |
| B13 根目錄忽略規則 | 沿用 | 使用基板修好的斜線錨定處理 |
| B14 變體序號 | 沿用 | cdx.11 接 cdx.10，回退與跳號由基板擋 |
| B15 預設強度 | 沿用 | Codex VARIANT.json 宣告 standard |
| B16 自檢上游辨識 | 沿用 | 移除自檢覆寫 |
| B17 進展與重試判斷 | 沿用 | 使用基板打轉分析 |
| B18 機械派工 effort | 沿用 | 共用派工表接收 off |
| B19 必讀鏈加入平台規則 | 沿用 | 一般和小白一起量 AGENTS.md 的 DW 段落 |
| 小修：重建來源 | 沿用 | 共用報告顯示實際工具 |
| 小修：待決題號 | 沿用 | 網頁題保留 CH 編號 |
| 小修：非 UTF-8 主控台 help | 沿用 | 由共用工具處理 |
| 小修：變體 README 自檢 | 沿用 | 共用自檢依實際 checkout 判斷 |

### 第一次凍結的上游逐項處理

| 上游項目 | 怎麼處理 | 理由 |
|---|---|---|
| `tools/_common.py`（G1） | 沿用 | 共用規則、工具及自檢 |
| `_common.exit_code_from`／`gate_status`（G2） | 沿用 | 共用規則、工具及自檢 |
| `tools/bootstrap_repo.py`（D6，取自 dshdw） | 沿用 | 共用規則、工具及自檢 |
| `memory_size_check --chain FILE...`（D4，取自 dshdw） | 沿用 | 共用規則、工具及自檢 |
| `_common.usage_number`／`usage_numbers`／`usage_partial`／`partial_line`（D7，取自 dshdw ds.7） | 沿用 | 共用規則、工具及自檢 |
| `usage_report`、`usage_mix`（D7） | 沿用 | 共用規則、工具及自檢 |
| selftest 新增 `test_usage_partial_300`（D7） | 沿用 | 共用規則、工具及自檢 |
| `tools/safety_gate.py`（D1，合併 dshdw ds.7 和 agydw） | 沿用 | 共用規則、工具及自檢 |
| `gate_check --order`／`--match`（D1） | 沿用 | 共用規則、工具及自檢 |
| `setup_check`（D1） | 沿用 | 共用規則、工具及自檢 |
| `templates/WORK_ORDER.md`（D1） | 沿用 | 共用規則、工具及自檢 |
| selftest 新增 `test_safety_gate_300`（D1） | 沿用 | 共用規則、工具及自檢 |
| selftest 新增 `test_gate_fail_closed_300`（G2） | 沿用 | 共用規則、工具及自檢 |
| `tools/spec_gate.py`（R6、R7、C1，硬底線） | 沿用 | 共用規則、工具及自檢 |
| `templates/BRIEF.md` | 沿用 | 共用規則、工具及自檢 |
| selftest 新增 `test_spec_gate_300` | 沿用 | 共用規則、工具及自檢 |
| selftest 新增 `test_director_in_project_300`（R3、G4） | 沿用 | 共用規則、工具及自檢 |
| `tools/handoff.py`（R5、C3，取自 baton 的做法） | 沿用 | 共用規則、工具及自檢 |
| `templates/DIRECTOR_HANDOFF.md`（R5、C10） | 沿用 | 共用規則、工具及自檢 |
| selftest 新增 `test_handoff_300`（R5、C3、C10） | 沿用 | 共用規則、工具及自檢 |
| `tools/delivery.py`（C2 硬底線、C4，取自 cdxdw 的交付合約和驗收紀錄，簡化成平台無關的一個檔） | 沿用 | 共用規則、工具及自檢 |
| selftest 新增 `test_delivery_300`（C2、C4） | 沿用 | 共用規則、工具及自檢 |
| `tools/worktree.py`（D3、G6，取自 dshdw 的 worker worktree 和 cwd 檢查） | 沿用 | 共用規則、工具及自檢 |
| `tools/install.py`（C7） | 沿用 | 共用規則、工具及自檢 |
| `templates/VARIANT_README.md`（D8、G8） | 改寫平台入口 | 共用規則原樣保留，Codex README 量在上限內 |
| selftest 新增 `test_worktree_300`、`test_loop_wait_tools_300`、`test_install_300`、 | 沿用 | 共用規則、工具及自檢 |
| `docs/13_bootstrap_details.md`、`docs/14_user_guide.md`（plan 6.9-2、G5） | 沿用 | 共用規則、工具及自檢 |
| 「隔離要能驗證」（C8，原理）：併進 `docs/07` 盲審稽核那一行，沒有新條目；各平台的檢查程式留在 adapter（cdxdw 已有） | 沿用並提供實測 | 保留 Codex sandbox 與 Review 隔離檢查 |
| `gate_check --final`（C2，硬底線） | 沿用 | 共用規則、工具及自檢 |
| `setup_project_settings` 的 `NOT_IGNORED`（D6） | 使用 Codex 轉接 | 保留上游檔，實際由 Codex Hook 或本機工具接手 |
| agy adapter（G2，agy P0，`build/agy-base` 另一個 repo） | 使用 Codex 轉接 | 保留上游檔，實際由 Codex Hook 或本機工具接手 |
| `gate_check --final`（D2，取自 dshdw，硬底線） | 沿用 | 共用規則、工具及自檢 |
| `gate_check --order`／`--match` 的 Standard／Strict 工單（D1，預設強度 standard） | 沿用 | 共用規則、工具及自檢 |
| `line_brief`（G1） | 沿用 | 共用規則、工具及自檢 |
| `line_brief --log-lines 0`（G1） | 沿用 | 共用規則、工具及自檢 |
| `gate_check --hash`（R6） | 沿用 | 共用規則、工具及自檢 |
| `dispatch_check --log`（R6） | 沿用 | 共用規則、工具及自檢 |
| 總監資料夾的位置（R3、G4）：預設從 repo 外（`<WS>/DIRECTOR/`）改成專案資料夾裡的 `<REPO>/DIRECTOR/`，但不進 git | 沿用 | 共用規則、工具及自檢 |
| `loop_guard`（D5） | 沿用 | 共用規則、工具及自檢 |
| `transcript_audit`（C9） | 沿用 | 共用規則、工具及自檢 |
| 必讀瘦身（plan 6.9-2、G5、R4、D9） | 改寫平台入口 | 共用規則原樣保留，Codex README 量在上限內 |
| `release.py`（plan 6.9-3） | 沿用 | 共用規則、工具及自檢 |
| `gate_check --po-acceptance` | 沿用 | 共用規則、工具及自檢 |
| `round_check`：空檔，或不是 UTF-8 的檔，從 `ROUNDS: PASS` 改成 FAIL（`INVALID empty file`／ | 沿用 | 共用規則、工具及自檢 |
| `memory_size_check` | 沿用 | 共用規則、工具及自檢 |
| `audit_log verify` | 沿用 | 共用規則、工具及自檢 |
| `dispatch_check --log` | 沿用 | 共用規則、工具及自檢 |
| `setup_check`：目標檔不是 UTF-8 時，從 traceback 改成一行 `INVALID not UTF-8 text`（FAIL） | 沿用 | 共用規則、工具及自檢 |
| `delete_guard` | 沿用 | 共用規則、工具及自檢 |
| 幫到誰：總監和 worker | 沿用 | 共用規則、工具及自檢 |
| Desktop：都是本機命令列工具，沒有新的每輪步驟 | 沿用 | 共用規則、工具及自檢 |
| 服務的初衷 | 沿用 | 共用規則、工具及自檢 |
| 核心：每輪必讀沒有變長；只用標準庫；git 只讀 | 沿用 | 共用規則、工具及自檢 |
| 舊檔案和舊指令：照常的檔案照樣通過 | 沿用 | 共用規則、工具及自檢 |
| P1-1、P2-2 `spec_gate approve` | 沿用 | 共用規則、工具及自檢 |
| P1-2 `spec_gate` | 沿用 | 共用規則、工具及自檢 |
| P1-3 `worktree.py open` | 沿用 | 共用規則、工具及自檢 |
| P1-4、P1-5、P1-6、P2-6、P2-7 `delivery.py` | 沿用 | 共用規則、工具及自檢 |
| P1-7、P2-13 `handoff.py` | 沿用 | 共用規則、工具及自檢 |
| P1-8、P2-3 `safety_gate` | 沿用 | 共用規則、工具及自檢 |
| P2-1 `spec_gate` | 沿用 | 共用規則、工具及自檢 |
| P2-8 `gate_check --hash` | 沿用 | 共用規則、工具及自檢 |
| P2-10 `bootstrap_repo.py` | 沿用 | 共用規則、工具及自檢 |
| 5-2（裁定為 P1）小白模式必讀鏈 | 沿用 | 共用規則、工具及自檢 |
| 5-1、5-3、5-4、5-5 文件 | 沿用 | 共用規則、工具及自檢 |
| 隱私（裁定）：新增 `tools/privacy_scan.py` 和 `tools/privacy_allow.txt` | 沿用 | 共用規則、工具及自檢 |
| 最終驗收（C2、C4）：最終裁決前跑  | 沿用 | 共用規則、工具及自檢 |
| 安裝（C7）：`DIRECTOR/tools/` 改用 `install.py install --to <WS>/DIRECTOR/tools --execute` 安裝和升級（BOOTSTRA | 沿用 | 共用規則、工具及自檢 |
| 讀法（G5）：已在跑的總監不用改檔；下次恢復照 README 新的第 1 步讀那條鏈就好 | 沿用 | 共用規則、工具及自檢 |
| 換總監（R5）：在 `DIRECTOR/` 補一個 `INDEX.md`（骨架在 `templates/DIRECTOR_FILES.md`），五個檔名都要寫到 | 沿用 | 共用規則、工具及自檢 |
| 初衷卡（R6）：在 `DIRECTOR/BRIEF.md` 補「使用者確認原話」欄、「## 未決事項」（沒有就寫「- 無」）和「## 現成方案調查」兩節，再跑一次  | 沿用 | 共用規則、工具及自檢 |
| 總監資料夾（R3）：舊專案的 DIRECTOR 放在 repo 外，照樣能用，不必搬 | 沿用 | 共用規則、工具及自檢 |
| 腳本若把 `delete_guard` 沒給 `--repo`／`--refs` 時的 exit 0 當成「可以刪」，現在會拿到 exit 2 | 沿用 | 共用規則、工具及自檢 |
| Standard／Strict 工單（D1） | 沿用 | 共用規則、工具及自檢 |
| 若把空的 audit log、空的 DIRECTOR_LOG、空的 RESUME_STATE 當成通過，現在會失敗 | 沿用 | 共用規則、工具及自檢 |
| 讀 `memory_size_check` 最後一行的腳本，請注意新的 `INVALID` 狀態和 ` invalid=n` 欄位（加在結尾）。 | 沿用 | 共用規則、工具及自檢 |
| `gate_check --final` | 沿用 | 共用規則、工具及自檢 |
| 用 `release.py` 發版的專案 | 沿用 | 共用規則、工具及自檢 |
| 初衷卡（審查 P1-2）：舊卡只有欄位名稱、內容空白的，現在是 `INCOMPLETE_SPEC`：回頭問使用者補上一句話、給誰、一定要有和限制，再跑一次 approve | 沿用 | 共用規則、工具及自檢 |
| 未決事項（審查 P2-1）：處理完的項目改成以「已解決：」或「暫緩：」開頭 | 沿用 | 共用規則、工具及自檢 |
| 換手測試的真實跨平台路線（DW→cdx、cdx→DW、DW→dsh、DW→agy，R5／C3） | Codex 路線驗收 | 基板負責清單及計分，轉接層登記 Desktop 工作樹 |
| `base_sync_check.py`（C7 的後半） | 延後 | 沿用基板排程 |
| CI 收據（C5）：留到 3.0.x | 延後 | 沿用基板排程 |
| 整合試跑（C6）：留到 3.0.x | 延後 | 沿用基板排程 |
| P2-4 safety_gate 只比預設強度、PO 回覆沒有簽核欄 | 延後 | 沿用基板排程 |
| P2-5 safety_gate 用 repo 根目錄的相對路徑讀候選 commit | 延後 | 沿用基板排程 |
| P2-9 worktree.py 預設位置跨專案撞名 | 延後 | 沿用基板排程 |
| P2-11 bootstrap 只寫本機的 info/exclude、`DIRECTOR/` 規則沒有 `/` 前綴 | 延後 | 沿用基板排程 |
| P2-12 handoff 的 repo_state 在 detached HEAD 時找不到候選分支 | 延後 | 沿用基板排程 |
| P2-14 install.py 第一次裝到已有舊檔的資料夾 | 延後 | 沿用基板排程 |
| P2-15 install manifest 只涵蓋 `tools/` | 延後 | 沿用基板排程 |
| P2-16 release.py 整組版號 | 延後 | 沿用基板排程 |
| P2-17 memory_size_check --chain | 延後 | 沿用基板排程 |

## 2.6.0-cdx.10

對齊初衷：用逐環境判定、保留驗過的成品及可查的斷點，讓驗收和續接有依據。

[cdx.10 發行歷史](https://github.com/scottpuppylu/cdx-DIRECTOR-WORKER/releases/tag/v2.6.0-cdx.10)
