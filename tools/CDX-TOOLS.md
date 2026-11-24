# cdxdw 工具

從安裝包根目錄，用 `python -I -B -X utf8 tools/cdxdw.py <command>`。安裝後也可直接使用狀態中的版本化 runtime。Python 3.9 以上與 Git 是必要依賴，原生對話與探針還要 Codex CLI。

`tools/cdx.py` 是相容入口，使用同一套指令。`cdx_*.py` 是 Codex 的平台工具檔名。

| 指令 | 作用 |
|---|---|
| `setup --repo PROJECT [--state PATH] [--apply] [--agents] [--hooks / --no-hooks]` | dry run、安裝／升級、Skill 衝突檢查、Hook 合併、狀態歸屬 |
| `doctor --repo PROJECT [--live] [--probe-sandbox]` | 查看 setup 結果、專案 Skill、Hook 信任和原生沙箱探針 |
| `work … lock-brief` | 將 PO 已核准的 `LOCKED` 初衷保存為可追溯快照 |
| `work --repo PROJECT prepare ORDER` | 驗證工單，從完整 BASE_REF 建具名乾淨 worktree |
| `work … adopt ORDER [--chat UUID]` | 登記已在核准 base 的乾淨 Desktop worktree，支援 detached HEAD |
| `work … lock-tests --base SHA FILE…` | 依 Git base 顯示測試檔內容指紋 |
| `work … approve-spec ORDER --reviewer ID --author ID` | 綁定獨立規格審查檔與當前工單 |
| `work … dispatch ORDER` | 在 DIRECTOR_LOG 記錄工單版次、雜湊及時間 |
| `work … approve-plan ORDER` | 綁定工單與 PLAN 的 SHA-256 |
| `work … seal ORDER` 與 `work … status ORDER [--candidate SHA]` | 封存已提交的候選，查派工快照、工作線、候選與驗收進度 |
| `work … review ORDER --candidate SHA [--rerun]` | 核對實際候選、範圍、報告、證據；選用獨立重跑與 receipt |
| `work … e2e ORDER --candidate SHA [--artifact-path PATH]` | 執行派工鎖定的公開入口，記退出碼、輸出及選用工件 SHA-256 |
| `work … record ORDER --candidate SHA` | 保存人工或瀏覽器 E2E、獨立 REVIEW 或 PO 原始判定 |
| `work … final ORDER --candidate SHA [--artifact HASH]` | 核對最近的驗收和人工判定，回報單張工單是否通過 |
| `work … integrate` 與 `work … integration-status UUID` | 在暫存工作樹合併指定候選，驗收實際整合版本並檢查是否已過期 |
| `session … new ORDER [--role reviewer --candidate SHA]` | 登記角色與工單；inactive 歷史可顯式 `--replace` |
| `session … run ORDER --phase plan/implement/review` | 原生 App Server 回合，沙箱前置實測及雜湊稽核 |
| `session … status ORDER [--live]` 與 `session … reconcile ORDER` | 查本地或宿主對帳，確認未知項目後續接 |
| `audit verify LOG`、`audit status LOG`、`audit build EVENTS --out LOG` | 驗證雜湊鏈、對帳工具開始與終態，或由 App Server JSONL 建立摘要 |
| `usage LOG [--format exec]` | App Server 累計記錄或 Codex exec JSONL 的用量 |
| `cdx_hook.py` | 由 Codex 透過 stdin JSON 觸發 SessionStart、PreToolUse、PostToolUse |
| `selftest_cdx.py` | 一張本機工單的完整重跑，加上安裝、拒絕、稽核等回歸 |

## 初衷與最終驗收

以 `gate_check.py --brief STATE/BRIEF.md` 列出 `BRIEF_REVISION` 和條目指紋。填入工單追溯的條目。新專案預設 `cdx_require_brief_pins: true`，既有專案可在狀態目錄的 `director_work.json` 加入這項設定。PO 草稿可繼續編輯，驗收以最後一次鎖定快照為準。

完成 `review --rerun` 後，使用 `work e2e` 執行派工內的 JSON 陣列 `E2E_COMMAND`。命令在候選 commit 的暫存副本執行，並記錄退出碼、輸出指紋和執行來源。AUTO 及命令 E2E 會篩選傳給測試的環境變數。這條執行路徑使用本機宿主的檔案權限，陌生來源或需要隔離的檢查須使用有權限邊界的環境。

人工判定用 `work record`，指定 `--kind e2e|review|po`、`--outcome PASS|FAIL|CHANGES_REQUESTED`，以及 `--actor`、`--environment`、`--entry`、`--expected`、`--observed`。以 `--artifact HASH` 綁定實際查看的建置產物。需要放行該工件時，同一個 SHA-256 傳給 `work final`。每次舊紀錄都可回查。最新 AUTO 或 E2E 結果需要為 PASS，工單要求的 REVIEW 與 PO 須各自有判定。

要驗組合，在核准後把 `--target refs/heads/main`、`--base FULL_TARGET_SHA`、兩個或更多 `--member ORDER.md=FULL_CANDIDATE_SHA`、以及批准的 `--argv` JSON 命令交給 `work integrate`。採用順序跟參數順序相同。整合版本的退出碼獨立於各工單，目標前移、工單重派或選用候選改變會使通過結果過期。

## 中斷後對帳

`session status --live` 讀取 thread 與最新回合。`session reconcile` 透過原始 turn ID 或啟動標記找回紀錄，遇到未知回合時保留原狀。工單改版後，仍可用原工單檔名查詢、對帳既有回合。要啟動新版回合，先完成新版派工，再用 `session new --replace` 登記已結束的工作線。只有啟動未獲確認且宿主沒有記錄該次回合時，才用 `reconcile --reset-empty`。

## 從 .3 升級

先結束舊版正在執行的命令，改用 .4 套件跑 `setup` 預覽和 `setup --apply`。.4 使用由作業系統釋放的 `.guard` 鎖，舊版的鎖目錄可保留作為紀錄。請以同一 runtime 操作同一份工單。舊版收據和文字 E2E 可回查，`work status` 將缺少結構化嘗試的項目顯示為 `LEGACY_NEEDS_VERIFICATION`，重跑或補登後即可使用新的 `final`。

## 上游共用工具

`gate_check.py`、`scope_check.py`、`evidence_record.py`、`audit_log.py`、`report_vs_audit.py`、`trace_report.py`、`ran_line.py`、`release.py`、`pack_check.py`、`ruler_check.py`、`run_plan_check.py`、`pre_tr.py`、`waiver.py` 等以原有命令執行。詳見 [上游工具手冊](README.md)。

上游套件也帶有舊的 Claude 設定與紀錄工具，用於相容原版流程及上游回歸。Codex 專案安裝、用量、Hook 協議和復工走 cdxdw 入口。
