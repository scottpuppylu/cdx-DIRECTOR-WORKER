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
| `work … approve-spec ORDER --reviewer ID --author ID [--active]` | 保存規格審查快照，預設綁草稿，`--active` 綁已派工版 |
| `work … dispatch ORDER` | 在 DIRECTOR_LOG 記錄工單版次、雜湊及時間 |
| `work … approve-plan ORDER` | 綁定工單與 PLAN 的 SHA-256 |
| `work … seal ORDER` 與 `work … status ORDER [--candidate SHA] [--artifact HASH]` | 封存已提交的候選，查派工快照、工作線、候選與工件驗收 |
| `work … sync-worker ORDER` | 同步已派工工作樹內由 cdxdw 管理的 Skill／Hook |
| `work … review ORDER --candidate SHA [--rerun]` | 核對實際候選、範圍、報告、證據；選用獨立重跑與 receipt |
| `work … e2e ORDER --candidate SHA [--artifact-path PATH]` | 執行派工鎖定的公開入口，記退出碼、輸出及選用工件 SHA-256 |
| `work … record ORDER --candidate SHA` | 保存人工或瀏覽器 E2E、獨立 REVIEW 或 PO 原始判定 |
| `work … final ORDER --candidate SHA [--artifact HASH]` | 核對最近的驗收和人工判定，回報單張工單是否通過 |
| `work … integrate` 與 `work … integration-status UUID [--expect-head SHA]` | 驗收實際整合提交，核對收據失效與待發版 SHA |
| `session … new ORDER [--role reviewer --candidate SHA]` | 登記角色與工單；inactive 歷史可顯式 `--replace` |
| `session … run ORDER --phase plan/implement/review` | 原生 App Server 回合，沙箱前置實測及雜湊稽核 |
| `session … status ORDER [--live]` 與 `session … reconcile ORDER` | 查本地或宿主對帳，確認未知項目後續接 |
| `session … native-review ORDER --candidate SHA [--run]` | 預覽封存的 base、候選及 diff 指紋，顯式執行 Codex 原生審查 |
| `audit verify LOG`、`audit status LOG`、`audit build EVENTS --out LOG` | 驗證雜湊鏈、對帳工具開始與終態，或由 App Server JSONL 建立摘要 |
| `usage LOG [--format exec]` | App Server 累計記錄或 Codex exec JSONL 的用量 |
| `cdx_hook.py` | 由 Codex 透過 stdin JSON 觸發 SessionStart、PreToolUse、PostToolUse |
| `selftest_cdx.py` | 一張本機工單的完整重跑，加上安裝、拒絕、稽核等回歸 |

## 初衷與最終驗收

以 `gate_check.py --brief STATE/BRIEF.md` 列出 `BRIEF_REVISION` 和條目指紋。填入工單追溯的條目。新專案預設 `cdx_require_brief_pins: true`，既有專案可在狀態目錄的 `director_work.json` 加入這項設定。PO 草稿可繼續編輯，驗收以最後一次鎖定快照為準。

完成 `review --rerun` 後，使用 `work e2e` 執行派工內的 JSON 陣列 `E2E_COMMAND`。命令在候選 commit 的暫存副本執行，並記錄退出碼、輸出指紋和執行來源。AUTO 及命令 E2E 會篩選傳給測試的環境變數。這條執行路徑使用本機宿主的檔案權限，陌生來源或需要隔離的檢查須使用有權限邊界的環境。

選用 `E2E_RUN_PLAN = {"file": "tests/run-plan.json", "run": "smoke"}` 時，`file` 必須與工單 base 內檔案相同，格式為上游 `run-plan-v1`。工具先驗候選內的程式參照，執行後對照 stdout 所報的啟動行。參照失效、缺少啟動行或必要參數時，該次為 `INVALID`。

人工判定用 `work record`，指定 `--kind e2e|review|po`、`--outcome PASS|FAIL|CHANGES_REQUESTED`，以及 `--actor`、`--environment`、`--entry`、`--expected`、`--observed`。以 `--artifact HASH` 綁定實際查看的建置產物。同一個 SHA-256 傳給 `work status` 和 `work final`。有 `E2E_COMMAND` 的工單需要該入口的最新執行結果；未指定入口命令的工單需要人工 E2E。同一工件上已記錄的人工失敗也阻擋放行。工單要求的 REVIEW 與 PO 各有獨立判定。

要驗組合，在核准後把 `--target refs/heads/main`、`--base FULL_TARGET_SHA`、兩個或更多 `--member ORDER.md=FULL_CANDIDATE_SHA`、以及批准的 `--argv` JSON 命令交給 `work integrate`。採用順序跟參數順序相同。單項驗收有工件時，為該項追加 `--member-artifact ORDER.md=ARTIFACT_SHA256`。目標、工單、候選、封存 ref、單項證據或最近整合嘗試改變時，舊通過收據會失效。發版前用 `work integration-status UUID --expect-head FULL_DELIVERY_SHA` 核對實際提交。遠端產生另一個 merge/rebase SHA 時，要在實際交付提交重跑 CI。

## 中斷後對帳

`session status --live` 讀取 thread 與最新回合。`session reconcile` 透過原始 turn ID 或啟動標記找回紀錄，遇到未知回合時保留原狀。工單改版後，仍可用原工單檔名查詢、對帳既有回合。要啟動新版回合，先完成新版派工，再用 `session new --replace` 登記已結束的工作線。只有啟動未獲確認且宿主沒有記錄該次回合時，才用 `reconcile --reset-empty`。

## 量測裝置與外部證據

在派工前，於工單的 `CDX_GATES` 指定需要的檢查，例如下列組合。

```text
CDX_GATES = {"feasibility": true, "pre_tr": "ci/pre_tr.json", "ruler": {"pattern": "^reading=", "real_line": "reading=42", "expect_min": 10, "cap_key": "skippedOverCap"}, "pack": "render-pack", "audit": true, "po_reply": true}
```

- `feasibility` 使用 [GATE_FEASIBILITY](../templates/GATE_FEASIBILITY.md)。填實際工單檔名、`REVISION`、完整 base、每個 AC 的基準試跑及結論。量法放寬時，要由另一位審查者測試已知缺陷。核准計畫與驗收會綁定檔案內容。
- `pre_tr` 指向 base 內已提交的 `pre-tr-v1`。外部輸入需相對路徑、來源及 SHA-256。把實際輸入放在 `--input-root PATH` 下，執行 `work preflight ORDER --candidate SHA`。工具驗內容後放進暫存副本，缺檔或改動會在 CPU 檢查及公開入口前停止。`work e2e` 也會執行這些前置檢查。
- `ruler` 核對命令 E2E 的 stdout。人工或裝置入口用 `work verify-evidence ORDER --candidate SHA --ruler-log LOG`。零筆、未達門檻或截斷會依上游 ruler 判為 `INVALID`。真實樣本請從實際輸出擷取。
- `pack` 是 `work/<WO>/evidence/` 下的相對資料夾。`work verify-evidence` 用 `pack_check.py check` 驗檔案和覆蓋，並將內容指紋綁到候選。包內容更新後重驗。
- `audit` 用已登記的 worker session 或 Desktop chat，以及 `audit/<WO>-worker.jsonl` 核對報告。先用 `audit_log.py head --log LOG` 取得 `AUDIT_HEAD`，由總監保存在獨立位置，再提供 `work verify-evidence --anchor FILE`。也可用 `audit report --report FILE --log LOG --session UUID --anchor FILE` 單獨對帳。核對範圍只涵蓋可觀察且有終態的命令宣稱。
- `po_reply` 要求 `work record --kind po` 提供 `--reply-file` 和原始訊息定位 `--reply-ref`。保存原始 bytes 與雜湊，後續改判會增加一筆記錄。操作者依專案規則確認帳號及回覆身分。

## 受控發版

在目標專案的 `director_work.json` 設定 `cdx_release_ci.workflow`、`workflow_sha256` 和 `jobs`。使用由發版者確認的 Git workflow blob 計算 SHA-256，填入 CI job 顯示名稱。需交付 CI 建置包可加 `artifact_name`，再以 `--artifact HASH` 比對 GitHub 的 archive SHA-256。重跑 workflow 時，工件名稱須附 `-attempt-N`。

```text
cdxdw release --repo PROJECT --integration INTEGRATION_UUID --head FULL_DELIVERY_SHA --ci-run RUN_ID
```

需安裝並登入 GitHub CLI。工具核對 fetch、push 及 GitHub repo 一致，並查同一個 SHA 的最新 workflow run、attempt 和必要工作。遠端合併或 rebase 產生新 SHA 時，交付 tree 要和驗過的整合結果相同、base 可追且自身 CI 通過。預設為 dry run，取得發布授權後可加 `--execute`。推送使用驗證過的完整 SHA。

## Desktop 交接核對

```text
cdxdw handoff --repo PROJECT export ORDER.md --out HANDOFF.json
cdxdw handoff --repo PROJECT verify HANDOFF.json --worktree DESTINATION
cdxdw handoff --repo PROJECT attach HANDOFF.json --worktree ISOLATED_DESTINATION --chat THREAD_UUID
```

停止原工作線的寫入後匯出清單，在目的地核對候選 refs、暫存／未暫存變更、未追蹤檔及工作線狀態。跨主機時用既有交接方式搬移 Git 資料和狀態備份，以 `verify --state PATH` 核對副本。準備正式接手時，在目的地初始化專屬的 cdxdw 狀態，將確認過的工作紀錄複製到新狀態，使用目的地安裝產生的 `PROJECT.json` 和 `runtime/`。再在同專案的隔離工作樹執行 `attach`。工具保留已派工文件的原 bytes，另記目的地的工作樹與狀態位置。Desktop Local checkout 也可做唯讀核對。原 App Server thread 仍以原路徑及回合對帳。

## 升級

先結束舊版正在執行的命令，以同一 runtime 操作同一份工單。.3 的鎖目錄可保留作為紀錄，.4 起使用由作業系統釋放的 `.guard` 鎖。.3 舊版收據和文字 E2E 可回查，缺少結構化嘗試時顯示 `LEGACY_NEEDS_VERIFICATION`，重跑或補登後用新版 `final` 核對。

用 .5 套件先預覽 `setup`，再加 `--apply`。已有工作中的 worktree 用 `work sync-worker ORDER` 同步，之後在宿主確認 Skill 載入和 Hook 信任。工具更新能對上保留 runtime 的檔案，遇到不認得的本機 Skill 則拒絕覆蓋。舊 spec 收據依原驗法讀取，準備下一版之前可用原報告與 `approve-spec --active` 保存生效版。舊候選 journal 原樣保留，判讀依來源區分人工與實際執行。舊整合 PASS 在新版顯示 `LEGACY_NEEDS_VERIFICATION`，可按原組合重跑。

## 上游共用工具

`gate_check.py`、`scope_check.py`、`evidence_record.py`、`audit_log.py`、`report_vs_audit.py`、`trace_report.py`、`ran_line.py`、`release.py`、`pack_check.py`、`ruler_check.py`、`run_plan_check.py`、`pre_tr.py`、`waiver.py` 等以原有命令執行。詳見 [上游工具手冊](README.md)。

上游套件也帶有舊的 Claude 設定與紀錄工具，用於相容原版流程及上游回歸。Codex 專案安裝、用量、Hook 協議和復工走 cdxdw 入口。
