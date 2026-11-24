# cdxdw 逐檔閱讀清單

用 `git ls-files -z` 建立清單，核對候選 `a9c8d1e19c48f2220093bd88cac52c7fb0b853ca` 與正式 `v2.6.0-cdx.3` 的 Git tree。候選 129 檔、38,185 行，正式 127 檔。兩版 143 個不重複 blob 全量讀取並解碼，逐檔定位用途和需要查證的行為。指紋為原始 Git blob 的 SHA-256 前 16 碼，可用 `git show REF:PATH` 的原始位元組重算。未標示 .3 差異的列與候選同一 blob。

逐檔證據包括用途定位、文字遍歷及格式檢查。逐行人工推演聚焦於 Codex 平台層、派工、候選、整合與安裝；共用大型測試、原版歷史和相容工具採全文掃描後按用途及入口抽查，人工深度不同。候選 Python 全部以 3.9 AST 語法解析，JSON 全部解析。上游 selftest 的測試主要由 harness 計數，不能用函式數代替。

兩版沒有版控二進位、submodule 或生成快取。所有被追蹤檔案都是可解碼文字。原版 CHANGELOG 是匯入的歷史文本。HTML 是與舊互動宿主相容的範本，容器檔是來源及設定。實際安裝會生成外部狀態、版本化 runtime、repo 指標、project Skill 和選用 Hook，均由 `cdx_setup.py` 啟動。Python bytecode cache 由 `.gitignore` 與安裝器排除。

| 依賴或生成來源 | 執行入口 | 這輪證據 |
|---|---|---|
| Git、Python ≥ 3.9 | 所有 CLI、本機 worktree、CI | AST 3.9；Git 與 Python 3.11 Windows、系統 Python 3.12 WSL |
| Codex CLI、App Server、模型 provider | session、doctor、research probe | CLI 0.160.1 生成 schema；Responses fixture 走 loopback |
| GitHub CLI、GitHub Actions | `tools/release.py`、CI | 查詢遠端發布和 run；發布由專案授權 |
| Docker、容器基底、Claude CLI、套件與網路配置 | `tools/container/Dockerfile`、`run_worker.sh` | Dockerfile 固定 `python:3.12-slim-bookworm` manifest digest 與 Claude Code `2.1.317`。Git、iptables、curl 與 CA 由 apt 安裝。保留作上游相容，本輪未啟動。 |
| pre-commit、Gitleaks | `templates/.pre-commit-config.yaml` | 範本使用 repo-local 執行入口，Gitleaks 依本機 PATH 選用。各下游自行啟用。 |
| Desktop／原版 Artifact Host | `work adopt`、`choice_page.html`／`choice_reconcile.py` | Git 採用與 worktree 以 fixture 測；原生 UI 另驗 |

| 路徑 | 候選內容與正式版差異 | 使用流程／入口 | 查證點 |
|---|---|---|---|
| `.agents/plugins/marketplace.json` | 12 行 · `d43749df7770b959` | 安裝 · repo marketplace 指向 plugin/cdx | 宿主可否發現、同名 Skill 是否重複 |
| `.gitattributes` | 5 行 · `aaafcdf4b49b3823` | 版本與 CI · checkout 的 LF 及 container 腳本 | Windows／Linux 的 blob 與工作副本差異 |
| `.github/workflows/ci.yml` | 36 行 · `f91f59d9657bb50e` | 發版 · Windows／Ubuntu Python 矩陣、原版測試 | 合併佇列觸發、實際整合 SHA、測試分層 |
| `.gitignore` | 2 行 · `862263fa1f46c20f` | 開發 · 排除 Python cache | 安裝包是否意外收進生成物 |
| `BOOTSTRAP.md` | 46 行 · `b5c700b2eb6c46dc` | 安裝 · 從 PO 確認專案、setup、doctor 到初衷鎖定 | 恢復既有其他支線、舊 Hook 的停用方式 |
| `CHANGELOG-upstream.md` | 1135 行 · `e5407a9d58c03d19` | 發版 · 保留上游歷史 | N1–N6 與當前原版 blob 的關係 |
| `CHANGELOG.md` | 38 行 · `3fae521b9ec57bec`，.3 29 行 [ce29f6c9301ca537] | 發版 · cdxdw 變更與遷移說明 | 歷史聲明對應 tag、CI 和候選 |
| `CODEX-PORT.md` | 48 行 · `7b96286f1c85c665`，.3 48 行 [a6402033a9553897] | 安裝與治理 · port 邊界、操作與測試矩陣 | 支線版本時效、79/77 類同步口徑 |
| `LICENSE` | 21 行 · `917bc82a207b10b6` | 發版 · MIT 授權 | 安裝包保留原文 |
| `PURPOSE.md` | 69 行 · `1e636c27a634e905` | 需求 · PO、總監、工作線的產品初衷 | 最終結果與拘束力是否落入 CLI |
| `README.md` | 108 行 · `499d089bfd2216f3`，.3 113 行 [3304aafe32dbdb44] | 總入口 · quick start、派工例、復工與驗收 | 列出的命令需從乾淨專案可走 |
| `VERSION` | 1 行 · `8af540abc4182299`，.3 1 行 [1abc5e52e766621f] | 安裝／發版 · runtime 路徑、wrapper、版本號 | 與 plugin manifest 和 changelog 同步 |
| `director_work.example.json` | 50 行 · `82e8dcc208f89a00` | 安裝 · 預設治理模式、scope、brief pins | 各設定哪些在 Codex native 路徑讀取 |
| `docs/01_roles_authority.md` | 33 行 · `a49c60710ef9050a` | 需求 · PO／總監／施工者權限和 Go 條件 | 角色宣告與可驗證的身分差距 |
| `docs/02_work_orders_gates.md` | 120 行 · `b709560ed9be4e79` | 派工 · Direct、Standard、Strict、AC 與變更要求 | 原版計畫審批與候選版強制點的差異 |
| `docs/03_communication.md` | 40 行 · `6c9a6209c908b897` | 接手 · 最小訊息、PO 回覆與禁止代答 | 聊天／待決帳是否一致 |
| `docs/04_quota_efficiency.md` | 17 行 · `74be854759424299` | 用量 · 輪次與有用工作比率 | 平台缺少帳單及重置語義 |
| `docs/05_models_effort.md` | 16 行 · `4fc725df0b1ee88b` | 派工 · 模型階層、effort、備援 | 工單宣告與 App Server 有效設定的差異 |
| `docs/06_resume_lossless.md` | 30 行 · `7649ff7fa2d19865` | 復工 · 最小指示鏈與繼續檔 | compact 及工作樹搬移後跨宿主核對 |
| `docs/06b_on_demand_procedures.md` | 105 行 · `5717f43aeafd8c9a` | 續航／稽核 · 派工、備份、工作線與包 | 哪些上游程序仍需手動入口 |
| `docs/07_quality_gates.md` | 137 行 · `929e59c362c0366c` | 驗收 · rerun、ruler、E2E、可重現環境 | 平台 wrapper 是否實際調用各工具 |
| `docs/08_safety_rules.md` | 46 行 · `36f53b3973f00193` | 派工 · 破壞性操作和授權邊界 | 政策文字、Hook、沙箱各自的證據 |
| `docs/09_memory.md` | 7 行 · `b5c499ce3ba00ad2` | 續航 · 檔案化的決策和工作狀態 | 是否存在跨專案混入 |
| `docs/10_lessons_learned.md` | 178 行 · `1e3b4a7e2f0fdc18` | 研究 · 上游實際紀錄與長期改進 | 上游經驗移植需要宿主對照 |
| `docs/11_codex_operations.md` | 43 行 · `1fc2433b6188366f`，.3 42 行 [730d8ddd68dbd99d] | 平台入口 · Desktop、CLI、App Server、Hook | 桌面 Handoff 對 state 與 commit 的實際影響 |
| `docs/12_chat_to_product.md` | 94 行 · `80d9d79118cf3edf` | 需求 · 小白模式、BRIEF、PO 判定與畫面 | 可執行入口與純作業說明的區別 |
| `docs/13_safety_gates.md` | 28 行 · `8f529c6ddedef545` | 驗收 · safety gate 依治理級別對照 | 可選工具是否誤被描述成硬閘 |
| `plugin/cdx/plugin.json` | 17 行 · `22dfbedf4cb55282`，.3 17 行 [f650440af90a63f2] | 安裝 · 外掛發現與 UI metadata | 版本、安裝與新聊天載入 |
| `plugin/cdx/skills/cdx-bootstrap/SKILL.md` | 11 行 · `855754d4b0718b21` | 安裝 · 啟動專案與初衷討論 | 能否從 plugin 和 project 安裝各自取得 kit |
| `plugin/cdx/skills/cdx-dispatch/SKILL.md` | 10 行 · `c61a4216f2febc3a`，.3 10 行 [7b00d2827fd93396] | 派工 · scope、worktree、核准後派工 | prepare／adopt 在查核決定前後的輸出 |
| `plugin/cdx/skills/cdx-release/SKILL.md` | 8 行 · `9d577b208c13f66a` | 發版 · 專案原生流程、CI、核准與回復 | 沒有專案 release policy 時如何阻止誤放行 |
| `plugin/cdx/skills/cdx-resume/SKILL.md` | 10 行 · `12d3f8c213675dd5` | 復工 · active order、狀態與對帳 | 舊 thread、手動 Handoff、重派發 |
| `plugin/cdx/skills/cdx-review-gate/SKILL.md` | 10 行 · `b5069166101761fa`，.3 10 行 [59df6f4dc5047e11] | 驗收 · 候選範圍、rerun、人工核准 | Native review 與 REVIEW AC 的區別 |
| `research/CDX-NEXT-VERSION.md` | 17 行 · `324aa81a6abdd83d`，.3 無此檔 | 研究 · .3 的故障與 .4 提案 | 已落地的功能從待辦移出 |
| `research/CODEX-PLATFORM.md` | 47 行 · `8676cfe965ff34f3` | 研究 · App Server、本機 fixture 與平台差距 | 用安裝版本、schema 與實際事件再測 |
| `research/DW-FAMILY-REVIEW.md` | 31 行 · `9831561f5477adef` | 研究 · 原版與支線比較 | 主分支及發布 refs 是否有漂移 |
| `research/probe_app_server.py` | 223 行 · `08395e5c041ec678` | 研究入口 · fake Responses、真 CLI、Git fixtures | 本機模型回覆／實際沙箱與 permission 分開 |
| `templates/.gitleaks.toml` | 32 行 · `e4527af3cf9fb469` | 發版相容 · 原版的秘密掃描配置 | 獨立工具和 pre-commit 才會讀 |
| `templates/.pre-commit-config.yaml` | 44 行 · `03ab1609cb5ec43f` | 發版相容 · pre-commit、格式、gitleaks | 依賴、版本與使用者啟用方式 |
| `templates/AGENTS_PROJECT_SECTION.md` | 5 行 · `0376bf334ec59262` | 安裝 · setup --agents 追加工作流程說明 | 既有人工修改和 marker |
| `templates/BRIEF.md` | 40 行 · `db756d2ef4e6ed60` | PO 核准 · gate_check 解析的需求表和版次 | lock-brief、條目 hash、改需求與草稿 |
| `templates/CLAUDE_PROJECT_SECTION.md` | 14 行 · `5843004266ea4b24` | 上游相容 · Claude 設定入口的項目指南 | Codex setup 的入口是 AGENTS |
| `templates/CPU_REPRO.md` | 65 行 · `d81e04e58c23d0ed` | 驗收 · 冷啟動、測試資料與 CPU 重現卡 | 重跑時的 pinned 環境與可拿到的輸入 |
| `templates/DECISION_REGISTER.md` | 19 行 · `2df68b3784292a61` | 需求／發版 · 決策、依據、重新開啟條件 | setup 複製，不自動代替 PO |
| `templates/DIRECTOR_FILES.md` | 77 行 · `35a382719ab9786a` | 復工 · 會話／溝通／證據檔與邊界 | 名稱跟 Codex state 位置的差異 |
| `templates/GATE_FEASIBILITY.md` | 28 行 · `6c389ed66139ff69` | 派工 · 凍結驗收前正反例及可行性 | 是否在 approve-plan 留 structured proof |
| `templates/GATE_VERDICT.md` | 46 行 · `99b18b392a3318f8` | 驗收 · 總監的驗收裁決與證據索引 | Codex final 不生成這份上游記錄 |
| `templates/HANDOFF.md` | 15 行 · `8698a2e7c1528ad2` | 接手 · 輸入、依賴、進度和證據 | 是否跟實際 Desktop Handoff 同步 |
| `templates/PO_PENDING.md` | 24 行 · `f3753ca995053972` | PO 溝通 · 問題、選項及已結原文 | 新安裝 scaffolding 用簡化內容 |
| `templates/RESUME_STATE.md` | 22 行 · `b7c1f5fec3ffda96` | 接手 · 進度、繼續動作與通訊 | 是否在自動回合或 Stop 更新 |
| `templates/SETTINGS_MANIFEST.md` | 32 行 · `e4567323184523ac` | 驗收 · 執行環境與設定差異 | 換執行器與無效結果的判定 |
| `templates/SPEC_REVIEW.md` | 44 行 · `2e9f7878f9fb0048` | 派工 · 獨立規格審查格式 | approve-spec 的 hash 不等於作者身分證明 |
| `templates/TASK_REPORT.md` | 43 行 · `b33edfa83448f925` | 驗收 · worker 候選、AC、測試與證據 | gate_check、report_vs_audit 和 final 的不同輸入 |
| `templates/TEST_REQUEST.md` | 24 行 · `654fef03f01d77d7` | 派工 · TEST_REQUEST、CODE_REFS 和評量 | run_plan_check 的程式參照與執行前鎖輸入 |
| `templates/WORKER_PLAN.md` | 11 行 · `20abfdeb7800dba8` | 派工 · worker 產出的驗收計畫 | Standard／Strict 的批准時點與快照 |
| `templates/WORK_ORDER.md` | 121 行 · `09e8e942a4955d2e`，.3 119 行 [4bd65063188dd455] | 派工 · BRIEF、BASE_REF、scope、AC、E2E | CLI 驗參與最後提交點 |
| `templates/choice_page.html` | 396 行 · `b5f302a6067e4e04` | PO 相容 · 選項 Artifact 介面、回覆與 token | 需要原版宿主協議，Codex 手動帳本仍可用 |
| `templates/guard_sessions.json` | 14 行 · `a6f55eb1b65ac325` | 權限相容 · 原版角色／會話登記範本 | 與外部 state 的 session JSON 不同 |
| `templates/pre_tr.json` | 29 行 · `61308b756771d2a1` | 驗收 · pre_tr 檢查設定與 inputs | 舊版已存在的 inputs 兼容 |
| `templates/run_closing.py` | 147 行 · `efe509889a0980b8` | 發版 · 收尾指令 wrapper | 人為調用、腳本選擇與呼叫順序 |
| `templates/settings.runtime-guard.json` | 61 行 · `5b1a2c23388a38bd` | 安裝相容 · Claude hooks 配置 | 與 .codex/hooks.json 的 matcher 和欄位不同 |
| `templates/status_director.json` | 22 行 · `fdb3df206476553a` | 復工 · status_gen 的輸入範本 | 現有活躍工單資訊是否需人工更新 |
| `templates/weird_inputs.py` | 70 行 · `f4cf5670315d4a14` | 驗收 · 產生邊界測試和非預期資料 | 保留可重現輸入與測試入口 |
| `tools/CDX-TOOLS.md` | 54 行 · `7077f5e39dbe89e4`，.3 41 行 [8acf6a19165200bc] | 入口 · Codex 指令與輸出契約 | 最新人工／機器證據、整合和升級契約 |
| `tools/README.md` | 1026 行 · `c597a800a87a690b` | 相容入口 · 上游 tools 命令索引 | 哪些可直接支援 Codex、哪些需橋接 |
| `tools/audit_log.py` | 565 行 · `465f5d19361f0dee` | 稽核 · hash chain 追加、驗證與錨定 | Codex app log 能使用外部信任錨的範圍 |
| `tools/browser_check.py` | 210 行 · `044dc9c0d05dc5e4` | 成品驗收 · browser report、截圖與入口驗證 | 真實瀏覽器與候選工件連結 |
| `tools/cdx.py` | 10 行 · `6b9b26c6ec2d9eb5` | 入口 · 舊 wrapper 委派 cdxdw.py | 相容參數與版本輸出 |
| `tools/cdx_acceptance.py` | 94 行 · `8a917a1b944d1d7a`，.3 無此檔 | 驗收 · 接受記錄、最新嘗試、物化及 E2E | 人工與執行來源、RUNNING／FAIL、外部檔案邊界 |
| `tools/cdx_audit.py` | 185 行 · `0dcd3de9b0f9231b` | 稽核 · App Server 結構化事件與 hash-chain | 終態、缺項、來源 identity |
| `tools/cdx_common.py` | 172 行 · `532f8d59a217ad02`，.3 133 行 [81436d578c374bdd] | 共用 · Git、路徑、原子寫入、OS lock | Windows 路徑、舊鎖與故障恢復 |
| `tools/cdx_doctor.py` | 94 行 · `212560a822eba005` | 安裝 · live skill／hook／sandbox 探針 | 設定、實際生效、正控制各自測 |
| `tools/cdx_hook.py` | 139 行 · `11322ee99a1e8452` | 宿主生命週期 · SessionStart／pre／post | 信任、工具實際覆蓋、role 綁 worktree |
| `tools/cdx_rpc.py` | 112 行 · `3840813f9326f522` | 模型入口 · stdio JSON-RPC、錯誤及核准 | 版本欄位、逾時、ID／event 交錯 |
| `tools/cdx_session.py` | 334 行 · `8f593b414467d6bd`，.3 318 行 [b2283bb4e7c476f7] | 派工／復工 · thread 綁定、turn journal 與 reconcile | 失去確認、未管理回合、stderr／中斷 |
| `tools/cdx_setup.py` | 240 行 · `a710c04de608875f` | 安裝 · 外部 state、管理 Skill、hooks 和 runtime | 有主 checkout 修改、跨版本、併發或中斷 |
| `tools/cdx_usage.py` | 66 行 · `278a9e23e0010697` | 用量 · App Server 累計與 exec --json | 同 thread 去重、數字缺漏 |
| `tools/cdx_work.py` | 788 行 · `a01e8284c56cb7d4`，.3 438 行 [73188101b8e657ab] | 治理入口 · BRIEF 鎖、派工、封存、E2E、整合 | 舊證據、工件、多工單、草稿互不踩踏 |
| `tools/cdxdw.py` | 25 行 · `b7179955f184f56e` | 產品入口 · argv 子命令和 Python 隔離旗標 | 安裝版與 checkout 的一致性 |
| `tools/choice_reconcile.py` | 870 行 · `812445bcc13f0165` | PO 相容 · Artifact 回覆與紀錄 reconciliation | 外部介面依賴、原文與卡版次 |
| `tools/completion.py` | 319 行 · `8fe785501b21daf7` | 驗收 · 上游工作完整度和收尾摘要 | 對應 Codex 任務和 receipt 需轉接 |
| `tools/container/Dockerfile` | 33 行 · `490dad76881e2d63` | 上游容器 · 建立 worker 映像和依賴 | 本版未建構／啟用 |
| `tools/container/dns_allow.py` | 271 行 · `1e857b7b75b075a6` | 上游容器 · DNS 設定、允許清單管理 | 依賴 Docker 網路、環境與管理權限 |
| `tools/container/dns_allow.txt` | 5 行 · `3edcf4ff63ccd6c7` | 上游容器 · 下載端點及服務域名例表 | 依賴部屬環境，避免照表盲信 |
| `tools/container/entrypoint.sh` | 28 行 · `b2fe88e80a317902` | 上游容器 · 啟動流程和執行環境 | Dockerfile 執行路徑、宿主差異 |
| `tools/container/init_firewall.sh` | 67 行 · `2f8a0cd3bb06b7a6` | 上游容器 · 網路規則初始化 | 部署環境需另外驗證 |
| `tools/container/run_worker.sh` | 238 行 · `2c0240ecd248bf37` | 上游容器 · worker 啟動與輸出 | Claude 及 Docker，未接 Codex wrapper |
| `tools/container/worker_clone.sh` | 143 行 · `215ff699c8db2ab8` | 上游容器 · 獨立 clone 的 worker checkout | 與 Git linked worktree 的共用物件庫不同 |
| `tools/context_probe.py` | 126 行 · `7b6fb7e95c423353` | 復工／用量 · Claude context 環境探針 | App Server 當期 context 與輸出對接 |
| `tools/delete_guard.py` | 139 行 · `14fae0c65a533664` | 收尾 · 保存仍被引用的候選 | 封存 refs／外部 state 是否被 CLI 用於清理 |
| `tools/dispatch_check.py` | 201 行 · `ad145e85dcdf00a3` | 派工 · effort 和重複派工計數 | 哪些檢查原生 dispatch 已有等效 |
| `tools/doctor.py` | 616 行 · `88627e7c7aec8ebe` | 上游安裝 · Python、配置、工具、hook 狀態 | 與 cdx_doctor 不同輸入及宿主 |
| `tools/evidence_record.py` | 738 行 · `f128a79dc2e04efe` | 驗收 · 鎖定 argv、SHA、獨立 git 快照重跑 | 候選樹、路徑連結／外部依賴與 stderr |
| `tools/flag_check.py` | 101 行 · `452c52170239a691` | 復工 · 常駐 flag 是否一致可解讀 | cdxdw runtime stage 不以它裁決 |
| `tools/gate_check.py` | 2463 行 · `41ca446c47fd4a6b` | 治理 · 工單、BRIEF、報告、候選與上游 final | 哪些 CLI flags 被 wrapper 轉發 |
| `tools/guard_rules.json` | 254 行 · `44f1b96bac0349d1` | 權限 · 規則庫供 hook_guard 選擇 | 宿主工具名稱與實際輸入 |
| `tools/hash_check.py` | 158 行 · `b3ba60d57d858ff5` | 稽核 · 指紋與工具鏈保存 | 哪些證據受本機帳本／外部 anchor 確認 |
| `tools/hook_guard.py` | 1320 行 · `39d8a3a27e67df56` | 權限 · 上游命令、路徑與規則比對 | cdx_hook 使用 evaluator 部分，宿主實測另列 |
| `tools/inject_scan.py` | 189 行 · `83f762343445dc70` | 派工／驗收 · 可疑輸入標記 | 何時手動觸發、輸出是否進治理紀錄 |
| `tools/line_brief.py` | 185 行 · `c6fbb7192dc8c46d` | 復工 · 將 workstream 狀態壓縮成摘要 | 可從 cdxdw 記錄生成的欄位 |
| `tools/loop_guard.py` | 552 行 · `978864e287c435de` | 派工相容 · 重試／工具模式計數 | App Server 對活躍 turn 有鎖，無同等輪次預算 |
| `tools/memory_size_check.py` | 260 行 · `def90c6af674f0f6` | 復工 · 量測常駐文件與記憶體字節 | 安裝的 AGENTS 指示預算 |
| `tools/metrics_report.py` | 440 行 · `d8fa42e173dede57` | 稽核 · 週期資料、成果證據、量測摘要 | Codex events／PO 驗收對應的匯入 |
| `tools/pack_check.py` | 253 行 · `ad54c835bde8fb4c` | 發版 · evidence bundle 檔案和 unique 檢查 | 有工具，工作流未自動發布 pack |
| `tools/pause_ctl.py` | 190 行 · `33a6bc3820b9ba28` | 復工 · 原版暫停檔案／續跑 | 原生 turn interrupt 是另一層 |
| `tools/poll_hint.py` | 212 行 · `c74d874e5c2a8d4a` | 復工 · 由進度推算何時查詢 | CLI status 不自動監視或排程 |
| `tools/pre_tr.py` | 188 行 · `bd5d20f30a529829` | 驗收 · 測試請求 preflight、額度及輸入檔 | 批准前對程式參照與檔案均須驗 |
| `tools/ran_line.py` | 182 行 · `3adf87d58efa74fd` | 驗收 · 處理 RAN 輸出與實測資料 | 需與實際 executor/命令證據對照 |
| `tools/release.py` | 551 行 · `8f9bb9f59ce2110b` | 發版 · 原版 Git／CI／GitHub release 流程 | dry-run、上游發布限制與專案候選收據 |
| `tools/report_vs_audit.py` | 1323 行 · `0cbb2450bbe43d1f` | 稽核 · worker 宣稱和工具終態對照 | 缺事件應 UNKNOWN，native JSONL 對應 |
| `tools/resume_archive.py` | 434 行 · `03569fa3d185a8f3` | 復工 · 結束及封存原版 resume 產物 | 與 Codex session 替換的 archive 位置 |
| `tools/resume_inject.py` | 141 行 · `8ad7368b9d972a70` | 復工 · 取短斷點內容 | 與 SessionStart 指路策略的對照 |
| `tools/round_check.py` | 190 行 · `1fcad6d29d57a3d7` | 派工／驗收 · 回合數與連續失敗停下 | 何時要求另一個 reviewer |
| `tools/ruler_check.py` | 124 行 · `931513571973b19c` | 驗收 · 量測前鎖標準／改版／套用標準 | 上游 2.6 新增，cdxdw wrapper 未調用 |
| `tools/run_plan_check.py` | 114 行 · `ffe66f75ae659634` | 派工 · 計畫引用的程式與行數檢查 | 當前工作樹應使用哪個 pinned SHA |
| `tools/scope_check.py` | 362 行 · `f18680a0e5409ab0` | 驗收 · 候選所有檔案變更、scope 和 required | 真候選中心、非 main checkout 外觀 |
| `tools/secret_mask.py` | 124 行 · `5e1ba8b000e73241` | 稽核 · 輸出敏感樣式遮罩 | 真實 E2E 尾端及 stdout 的採用位置 |
| `tools/selftest.py` | 11364 行 · `59304882f13aad1a` | CI · 上游回歸與整合 fixtures | 全文掃描與測試清冊，完整分支行為依測試 |
| `tools/selftest_cdx.py` | 553 行 · `bc887aca02e33a61`，.3 400 行 [6cb9aead70c9e1f3] | CI · cdxdw 公用入口、隔離 Git、故障注入 | 實體 Desktop／模型與 fixture 的區別 |
| `tools/setup_check.py` | 358 行 · `de36119540ef7ed8` | 安裝相容 · 原版規則與路徑測試 | 不能取代 cdx doctor |
| `tools/setup_project_settings.py` | 775 行 · `8e80b64bc0bb2fb8` | 安裝相容 · Claude 設定合併與 hooks | 不上寫 .codex 設定 |
| `tools/sim_check.py` | 173 行 · `c208dd81b80c358e` | 驗收 · 模擬／真實機制的測試標籤 | clock、端點與 input 來源證據 |
| `tools/status_gen.py` | 581 行 · `3154e1c4bb804b44` | 復工 · 上游狀態頁和資料檢查 | 目前由工作流手動使用 |
| `tools/trace_report.py` | 561 行 · `ae46906c676e1e36` | 驗收 · BRIEF 條目與 AC 證據綁定 | 專案整體 coverage 不等於單工單 final |
| `tools/transcript_audit.py` | 301 行 · `d0fe6079875586c2` | 稽核相容 · Claude JSONL 解析 | Codex 使用 cdx_audit 或原生宿主資訊 |
| `tools/usage_mix.py` | 590 行 · `9c36f9a2da5db21a` | 稽核 · 模型用量、讀取重複與成本分布 | Codex event 欄位及輸入來源不可直接照搬 |
| `tools/usage_report.py` | 176 行 · `879b6afbbc29dd0c` | 稽核 · 上游用量報表與聚合 | 遵循資料依賴及配額可見性 |
| `tools/vocabulary.json` | 17 行 · `11049446187f4e90` | 驗收 · completion／report 應用的狀態字彙 | 同字 / 不同語義的格式衝突 |
| `tools/waiver.py` | 224 行 · `41491a765cd52757` | 發版 · 依工單、理由與到期核准豁免 | Codex final 是否應承接，以及核准權限 |

## 本輪新檔

- `tools/cdx_review.py` 在封存、預覽、原生審查、證據保存之間建立 SHA 綁定。
- `research/reproduce_cdxdw.py` 使用目前 kit 或 Git archive 執行回歸和升級重現。
- 本清單及研究報告記錄基線與驗證結果。
