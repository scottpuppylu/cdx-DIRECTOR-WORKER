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
| `work … approve-plan ORDER [--approver ID]` | 綁定工單、施工基準與 PLAN 的 SHA-256，動工前可修訂並保存舊核准 |
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
| `audit verify LOG`、`audit status LOG`、`audit build EVENTS --out LOG [--session UUID]` | 驗證雜湊鏈、對帳工具開始與終態，或由 App Server JSONL 建立指定對話的稽核 |
| `usage LOG [--format exec]` | App Server 累計記錄或 Codex exec JSONL 的用量 |
| `cdx_hook.py` | 由 Codex 透過 stdin JSON 觸發 SessionStart、PreToolUse、PostToolUse |
| `selftest_cdx.py` | 一張本機工單的完整重跑，加上安裝、拒絕、稽核等回歸 |

## 初衷與最終驗收

以 `gate_check.py --brief STATE/BRIEF.md` 列出 `BRIEF_REVISION` 和條目指紋。填入工單追溯的條目。新專案預設 `cdx_require_brief_pins: true`，既有專案可在狀態目錄的 `director_work.json` 加入這項設定。PO 草稿可繼續編輯，驗收以最後一次鎖定快照為準。

完成 `review --rerun` 後，使用 `work e2e` 執行派工內的 JSON 陣列 `E2E_COMMAND`。命令在候選 commit 的暫存副本執行，並記錄退出碼、輸出指紋和執行來源。AUTO 及命令 E2E 會篩選傳給測試的環境變數。這條執行路徑使用本機宿主的檔案權限，陌生來源或需要隔離的檢查須使用有權限邊界的環境。

選用 `E2E_RUN_PLAN = {"file": "tests/run-plan.json", "run": "smoke"}` 時，`file` 必須與工單 base 內檔案相同，格式為上游 `run-plan-v1`。工具先驗候選內的程式參照，執行後對照 stdout 所報的啟動行。參照失效、缺少啟動行或必要參數時，該次為 `INVALID`。

人工判定用 `work record`，指定 `--kind e2e|review|po`、`--outcome PASS|FAIL|CHANGES_REQUESTED`，以及 `--actor`、`--environment`、`--entry`、`--expected`、`--observed`。以 `--artifact HASH` 綁定實際查看的建置產物。同一個 SHA-256 傳給 `work status` 和 `work final`。有 `E2E_COMMAND` 的工單需要該入口的最新執行結果；未指定入口命令的工單需要人工 E2E。同一工件上已記錄的人工失敗也阻擋放行。工單要求的 REVIEW 與 PO 各有獨立判定。

工單可用 `CDX_GATES` 的 `artifact_path` 鎖定 E2E 會產出的相對檔案路徑。舊工單在首次使用工件驗收後，同一候選也會維持工件綁定。此後省略工件的重跑和最終放行會被拒絕。用相同指紋登記改判，或給真正的新工件走一次新的驗收。 `status` 的 `final` 欄顯示目前證據是否可放行。

REVIEW 或 PO 有多個 AC 時，每次 `work record` 用一個或多個 `--ac AC-N` 明列覆蓋範圍。單一 AC 的既有收據可沿用。多 AC 的舊總判定需按原文重新登記範圍，`status` 的 `criteria` 會逐項列出判定與來源。封存候選的獨立重審讀核准 PLAN 快照，現場工作稿可保留。

工單可宣告 `CDX_GATES = {"environments":{"AC-2":["windows","wsl"]}}`。裁決用 `--environment-id` 選定一個環境，`--environment` 保存實際版本等描述。`criteria` 用 `AC-2@windows` 等鍵顯示每格判定。舊資料可在環境文字和聲明 ID 完全對應時沿用。其餘格子提示補驗，未宣告的 AC 沿用原有規則。`engineering`、`product` 和 `final` 分別供查工程證據、產品判定及整體放行。

用 `work integrate` 驗證一張或多張工單，指定 `--target refs/heads/main`、`--base FULL_TARGET_SHA`、`--member ORDER.md=FULL_CANDIDATE_SHA` 和已核准的 `--argv` JSON 命令。單張可快轉時保留原候選 SHA。其他情況依提供順序合併並驗證實際結果。單項有工件時，追加 `--member-artifact ORDER.md=ARTIFACT_SHA256`。目標、工單、候選、封存 ref、單項證據或最新整合嘗試改變時，舊收據會失效。發版前用 `work integration-status UUID --expect-head FULL_DELIVERY_SHA` 核對實際提交。

新版受控發版要先執行 `work approve-integration --target REF --base SHA --argv JSON --approved-by ID`，將傳回的 `approval` 交給 `work integrate --approval`。預設規格交付原始碼。交付建置產物時用 `--delivery FILE.json` 核准，例如下列內容。

```json
{
  "mode": "artifacts",
  "require_po": true,
  "outputs": [
    {"path": "dist/product.zip", "ci_path": "product.zip", "asset": "product.zip"}
  ]
}
```

`approve-integration` 及 `integrate` 均接受 `--argv-file FILE.json`，適合 Windows PowerShell 5.1。指定 `"build_context": "git"` 可在獨立 Git checkout 建置，含本機可見的 tag。建置環境也提供 `CDX_DELIVERY_COMMIT`、`CDX_DELIVERY_TREE`，及來源有 `VERSION` 時的 `CDX_DELIVERY_VERSION`。

整合完成後用 `work delivery-file UUID --asset FILE` 取得保留原件與 SHA-256，再請 PO 試用。舊收據可用 `work import-delivery UUID --asset NAME --file ORIGINAL` 匯入與已驗摘要一致的原件。需要記錄 PO 決定時，用 `work record-delivery UUID --outcome PASS --actor PO --reply-file FILE --reply-ref MESSAGE`。可重現建置預設使用 CI ZIP。若選 `"artifact_source": "retained"`，可發行已驗的同一份原件，交付 SHA 須與整合相同。已指定 CI 工件的專案仍核對 ZIP。發版會在草稿核對已上傳資產的摘要，再公開，重試會核對已存在的資產。 [GitHub Release assets](https://docs.github.com/en/rest/releases/assets)

## 中斷後對帳

`session status --live` 讀取 thread 與最新回合。`session reconcile` 透過原始 turn ID 或啟動標記找回紀錄，遇到未知回合時保留原狀。工單改版後，仍可用原工單檔名查詢、對帳既有回合。要啟動新版回合，先完成新版派工，再用 `session new --replace` 登記已結束的工作線。只有啟動未獲確認且宿主沒有記錄該次回合時，才用 `reconcile --reset-empty`。

`session native-review --run` 和 App Server 的 `--phase review` 使用停用 MCP、Apps、Plugins、Hooks 及 web search 的審查程序。啟動模型前核對有效設定與 MCP 清單，並檢查實體唯讀。作業系統的讀取可見範圍仍依有效沙箱而定。

Desktop 以 `work adopt ORDER --chat UUID` 登記工作位置，派工時綁定當前工單快照。既有工作樹可用 `work sync-worker ORDER` 更新註冊。受信任的 `PostCompact` 會保存事件並提示斷點位置，下一次送出提示時由 `UserPromptSubmit` 帶入同一位置。已執行但缺終態的命令維持無法驗證。若有獨立匯出的 App Server 事件，用 `audit build EVENTS --out STATE/audit/WO-001-worker.jsonl --session UUID` 匯入已登記對話，再獨立保存 `AUDIT_HEAD`。

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

在目標專案的 `director_work.json` 設定該產品自己的 `release.selftest`，以及 `cdx_release_ci.workflow`、`workflow_sha256` 和 `jobs`。以下設定示例用於一個有 `tests/smoke.py` 的產品，請用確定經審查的 workflow blob 指紋替換佔位值。

```json
{
  "release": {
    "remote": "origin",
    "branch": "main",
    "selftest": "python -B tests/smoke.py"
  },
  "cdx_release_ci": {
    "workflow": ".github/workflows/ci.yml",
    "workflow_sha256": "REPLACE_WITH_THE_REVIEWED_WORKFLOW_SHA256",
    "jobs": ["windows smoke", "linux smoke"],
    "candidate_branch": "codex/delivery"
  }
}
```

用 `--push-only` 核對候選分支上此 SHA 的最新 CI，取得授權後加 `--execute` 快轉推送。也可由 GitHub 分支規則或合併流程完成落地。交付 SHA 出現在目標分支後，用該分支最新完成的 CI run ID 重跑發布。兩種操作預設都是預覽。

```text
cdxdw release --repo PROJECT --integration INTEGRATION_UUID --head FULL_DELIVERY_SHA --ci-run CANDIDATE_RUN_ID --push-only
cdxdw release --repo PROJECT --integration INTEGRATION_UUID --head FULL_DELIVERY_SHA --ci-run TARGET_BRANCH_RUN_ID
```

需有可讀取 repo 的 GitHub CLI。遠端合併或 rebase 產生新 SHA 時，交付 tree 要符合驗過的整合結果，base 可追溯，該 SHA 自身的 CI 也要通過。GitHub Actions 工件可由 `artifact_name` 固定，重跑建議設成 `build-attempt-{attempt}`，由工具換成實際 attempt。若工單核准的是 CI ZIP 的內檔，將工單 ID 對應 ZIP 相對路徑填入 `cdx_release_ci.artifact_members`，再同時提供 `--artifact ZIP_SHA256` 與 `--archive DOWNLOADED_ZIP`。工具核對 GitHub 的封存指紋、下載的封存 bytes 和實際內檔 SHA，發行內容仍由專案的交付流程管理。 [GitHub workflow runs](https://docs.github.com/en/rest/actions/workflow-runs) · [GitHub Actions artifacts](https://docs.github.com/en/rest/actions/artifacts)

必要 jobs 必須全數出現在同一有效 attempt。部分重跑缺少必要 job 時，使用 GitHub 的完整 workflow 重跑。每次驗證另寫 `delivery/<sha>/checks/`，`latest/` 以整合 UUID、CI run 及預覽／推送／發布階段索引。公開前再確認 run／attempt 仍有效。

## Desktop 交接核對

```text
cdxdw handoff --repo PROJECT export ORDER.md --out HANDOFF.json
cdxdw handoff --repo PROJECT verify HANDOFF.json --worktree DESTINATION --chat THREAD_UUID
cdxdw handoff --repo PROJECT attach HANDOFF.json --worktree ISOLATED_DESTINATION --chat THREAD_UUID
```

停止原工作線的寫入後匯出清單，在目的地核對候選 refs、暫存／未暫存變更、未追蹤檔及工作線狀態。跨主機時用既有交接方式搬移 Git 資料和狀態備份，以 `verify --state PATH` 核對副本。準備正式接手時，在目的地初始化專屬的 cdxdw 狀態，將確認過的工作紀錄複製到新狀態，使用目的地安裝產生的 `PROJECT.json` 和 `runtime/`。再在同專案的隔離工作樹執行 `attach`。工具保留已派工文件的原 bytes，另記目的地的工作樹與狀態位置。Desktop Local checkout 也可做唯讀核對。原 App Server thread 仍以原路徑及回合對帳。

新版清單納入派工歷史、未派草稿、已核准的現行初衷與計畫、驗收引用的 PO 原文和相關回合資料。schema 3 可續接當時現行版。需要完整歷史時從來源重匯。以 `verify --chat` 預檢既有 UUID 及工作線。相同工單版次、相符來源聊天與工作樹才可移轉既有綁定，舊綁定另保存。

預檢也會列出政策與最低 runtime 差異，以及目的地需同步的 Skill。對齊後執行 `attach --chat UUID`，工具會同步接收工作樹。用 `session status ORDER --live` 查實際宿主看到的 Skill、Hook 來源與信任。工單換 worktree 時先增加版次，在新 base 準備工作樹並登記新 chat，再核准及派工。舊版用 `work status ORDER --revision N` 回查。

`attach` 接受工單指定的分支或 detached HEAD。Desktop 若在目的地建立另一個分支，先用 `verify` 確認交接資料，再以目前提交進入 detached HEAD（`git switch --detach HEAD`）並重新執行 `verify` 與 `attach`。若要用 Desktop 繼續搬運該分支，可先完成搬運，再決定在哪個隔離工作樹登記接手。Desktop 若要求清空輸入狀態，請開啟目前的測試或工作對話，確認草稿及待送訊息均已處理後重試。

## 升級

先結束舊版正在執行的命令，以同一 runtime 操作同一份工單。.3 的鎖目錄可保留作為紀錄，.4 起使用由作業系統釋放的 `.guard` 鎖。.3 舊版收據和文字 E2E 可回查，缺少結構化嘗試時顯示 `LEGACY_NEEDS_VERIFICATION`，重跑或補登後用新版 `final` 核對。

用新版套件先預覽 `setup`，再加 `--apply`。已有工作中的 worktree 用 `work sync-worker ORDER` 同步，之後在宿主確認 Skill 載入和 Hook 信任。舊候選 journal 原樣保留，舊 manifest 需重新匯出。遇到舊規格收據可用原報告與 `approve-spec --active` 保存生效版。舊整合若顯示 `LEGACY_NEEDS_VERIFICATION`，可按原組合重跑。

升級至 `.9` 前結束舊命令，避免已載入舊狀態的長工作仍在寫入。安裝先在狀態內的 `migrations/schema-1/` 保存升級前資料、Git 指標、refs 及既存配置副本，再切換 schema。之後使用狀態根目錄的固定入口 `cdxdw.py`，以 `doctor` 查執行及作用中版本。需要回退時，在隔離專案恢復配對的舊 runtime、升級前狀態及 Git 指標，核對 refs 和未提交修改後再採用。

維護者改過套件檔案時，先用 Git stage 選定要發行的檔案，再執行 `python -I -B -X utf8 tools/cdx_manifest.py` 產生 `RUNTIME-MANIFEST.json`。CI 的 `--check` 核對預定安裝的檔案、版本及內容。GitHub 發行封包與 Git checkout 都以該清單安裝。

## 上游共用工具

`gate_check.py`、`scope_check.py`、`evidence_record.py`、`audit_log.py`、`report_vs_audit.py`、`trace_report.py`、`ran_line.py`、`release.py`、`pack_check.py`、`ruler_check.py`、`run_plan_check.py`、`pre_tr.py`、`waiver.py` 等以原有命令執行。詳見 [上游工具手冊](README.md)。

上游套件也帶有舊的 Claude 設定與紀錄工具，用於相容原版流程及上游回歸。Codex 專案安裝、用量、Hook 協議和復工走 cdxdw 入口。
