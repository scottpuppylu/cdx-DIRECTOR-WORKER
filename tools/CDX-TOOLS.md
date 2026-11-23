# cdxdw 工具

從安裝包根目錄，用 `python -I -B -X utf8 tools/cdxdw.py <command>`。安裝後也可直接使用狀態中的版本化 runtime。Python 3.9 以上與 Git 是必要依賴，原生對話與探針還要 Codex CLI。

`tools/cdx.py` 是相容入口，使用同一套指令。`cdx_*.py` 是 Codex 的平台工具檔名。

| 指令 | 作用 |
|---|---|
| `setup --repo PROJECT [--state PATH] [--apply] [--agents] [--hooks]` | dry run、安裝／升級、Skill 衝突檢查、Hook 合併、狀態歸屬 |
| `doctor --repo PROJECT [--live] [--probe-sandbox]` | 查看 setup 結果、專案 Skill、Hook 信任和原生沙箱探針 |
| `work --repo PROJECT prepare ORDER` | 驗證工單，從完整 BASE_REF 建具名乾淨 worktree |
| `work … lock-tests --base SHA FILE…` | 依 Git base 顯示測試檔內容指紋 |
| `work … approve-spec ORDER --reviewer ID --author ID` | 綁定獨立規格審查檔與當前工單 |
| `work … dispatch ORDER` | 在 DIRECTOR_LOG 記錄工單版次、雜湊及時間 |
| `work … approve-plan ORDER` | 綁定工單與 PLAN 的 SHA-256 |
| `work … review ORDER --candidate SHA [--rerun]` | 核對實際候選、範圍、報告、證據；選用獨立重跑與 receipt |
| `session … new ORDER [--role reviewer --candidate SHA]` | 登記角色與工單；inactive 歷史可顯式 `--replace` |
| `session … run ORDER --phase plan/implement/review` | 原生 App Server 回合，沙箱前置實測及雜湊稽核 |
| `session … status ORDER [--live]` 與 `session … reconcile ORDER` | 查本地或宿主對帳，確認未知項目後續接 |
| `audit verify LOG` 或 `audit build EVENTS --out LOG` | 驗證上游雜湊鏈，或從結構化 App Server JSONL 建立摘要 |
| `usage LOG [--format exec]` | App Server 累計記錄或 Codex exec JSONL 的用量 |
| `cdx_hook.py` | 由 Codex 透過 stdin JSON 觸發 SessionStart、PreToolUse、PostToolUse |
| `selftest_cdx.py` | 一張本機工單的完整重跑，加上安裝、拒絕、稽核等回歸 |

## 上游共用工具

`gate_check.py`、`scope_check.py`、`evidence_record.py`、`audit_log.py`、`report_vs_audit.py`、`trace_report.py`、`ran_line.py`、`release.py`、`pack_check.py`、`ruler_check.py`、`run_plan_check.py`、`pre_tr.py`、`waiver.py` 等以原有命令執行。詳見 [上游工具手冊](README.md)。

上游套件也帶有舊的 Claude 設定與紀錄工具，用於相容原版流程及上游回歸。Codex 專案安裝、用量、Hook 協議和復工走 cdxdw 入口。
