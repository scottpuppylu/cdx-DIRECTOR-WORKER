# BOOTSTRAP — cdxdw 總監的第一輪

先讀 [PURPOSE](PURPOSE.md) 與這頁。確認專案與使用者的既有規則、資料路徑及授權。工具的 dry run 會顯示要使用的狀態位置。每輪開始先收集本機待決帳和未處理的聊天回答。

## 0. 模式與環境

問 PO 用一般模式或小白模式。一般模式先盤點環境，小白模式同一輪直接問「要做什麼、給誰用、第一版怎麼驗」。小白模式可先把需求摘要留在聊天，等進入派工再安裝 project skills。讀 [需求到成品](docs/12_chat_to_product.md)。

檢查 `git status --short --branch`、主 checkout、`git worktree list`、Git/Python 和 `codex --version`。確認哪些未提交修改是現有工作。專案外的目錄受 Codex 沙箱限制時，用該專案已授權的路徑，或請 PO 決定狀態位置。

## 1. 建置 cdxdw

從 cdxdw checkout 執行。先跑 plan，檢查專案歸屬與路徑，再加 `--apply`。

```powershell
python -I -B -X utf8 tools/cdxdw.py setup --repo PROJECT --mode general
python -I -B -X utf8 tools/cdxdw.py setup --repo PROJECT --mode general --agents --apply
python -I -B -X utf8 tools/cdxdw.py doctor --repo PROJECT --live --probe-sandbox
```

`--state` 指定現有或新狀態目錄，預設 `PROJECT` 旁的 `DIRECTOR-<repo>`。`--agents` 追加簡短 `AGENTS.md` 段落。`--hooks` 合併 `.codex/hooks.json`。有 Hook 時，PO 可以在 Codex 內審查並信任它，狀態以 `doctor` 顯示為準。`.agents/skills/` 由安裝器部署。由 Codex Desktop 讀取時，可以開新對話重新載入。若同時選本機 plugin 和 project skills，會出現同名項目，專案安裝只需一種入口。

## 2. 核對結果與建置檔

| 位置 | 檔案 |
|---|---|
| 專案 Git 共用目錄 | `director-work-cdx.json` 指向該 repo 的專屬狀態 |
| `DIRECTOR-<repo>/` | `PROJECT.json`、`DIRECTOR_STATE.md`、`RESUME_STATE.md`、`MECHANISMS.md`、`director_work.json` |
| 待決與決策 | `PO_PENDING.md`、`DECISION_REGISTER.md`、`DIRECTOR_LOG.md`、`PENDING_SENDS.md` |
| 派工與證據 | `ACTIVE_WORKSTREAMS.md`、`orders/`、`work/`、`reviews/`、`evidence/`、`sessions/`、`audit/` |
| 安裝 runtime | `runtime/<VERSION>/` 保存可運行的 tools、範本、Skill 與手冊 |

審查已存在的非 cdxdw 狀態時，先決定遷移位置及保留路徑。安裝器會拒絕歸屬不同的狀態、已被本地改過的 managed Skill 或同版本 runtime。跨版本用新套件重跑 setup。舊 runtime 可做回查。

`setup --no-hooks --apply` 可停用這個專案的 cdxdw Hooks 並移除主 checkout 中由 cdxdw 安裝的項目。若先前已準備指向 .1 或 .2 runtime 的工作樹，也要在 Codex 的 Hook 管理介面停用那些舊項目。

## 3. 初衷、待決和第一份回報

1. 問 PO 要達到的成果及驗收方式，建立 [BRIEF.md](templates/BRIEF.md) 草稿。提出一版可用範圍、首批工作線、會改的路徑、模型和估計成本。
2. 在 `PO_PENDING.md` 留下待決項 ID、題目、選項與建議。PO 可從聊天回答，總監逐字記下原文、卡版次和對應候選。
3. 給一份回報，說明專案與狀態路徑、建置結果、Hook／沙箱／技能證據、和專案規則衝突的地方、待決項與下一步。靠本機探針得出的結論標清環境與版本。
4. 初衷經 PO 核准後，把狀態改為 `LOCKED`，執行 `work --repo PROJECT lock-brief`。依工單引用的初衷條目填入 `BRIEF_FINGERPRINTS_V1`，再填完整 base SHA、worktree、驗收及範圍。依 [WORK_ORDER](templates/WORK_ORDER.md)、[02](docs/02_work_orders_gates.md)、[13](docs/13_safety_gates.md) 檢查計畫與交件。

## 4. 每次續航

回到總監對話先讀 `PO_PENDING.md`、`RESUME_STATE.md`、`DIRECTOR_LOG.md` 最新段落、工單和本機 thread 對帳。出現同一張工單在不同 worktree 的情況時，核對共同 Git 目錄、完整 commit 與 thread ID，再決定續接哪條線。
