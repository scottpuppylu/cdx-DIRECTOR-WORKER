# codex-DIRECTOR-WORKER

DIRECTOR-WORK 的 Codex 移植研究原型。用 Codex App Server 管理工作線與取得執行事件，沿用上游工單、範圍檢查及獨立驗收重跑的格式。

- [平台研究與首版設計](research/CODEX-PLATFORM.md)
- [本機 App Server 探針](research/probe_app_server.py)
- [上游快照](upstream/) 來自 DIRECTOR-WORK `v2.6.0`（`787f67bb7483cf07ac45f450a3f9e57262383359`），其中 19 份選用的工具、範本與授權文件經 Git blob 逐份核對。

## 重現平台觀察

需要 PATH 上的 Codex CLI、Git、Python 3.9 以上。從本目錄執行：

```powershell
python -I -X utf8 research/probe_app_server.py
```

探針在臨時目錄建立 Git fixture、worktree 和獨立 Codex 資料目錄。它以 `127.0.0.1` 的仿製 Responses 串流測試原生 App Server 事件，並開啟第二個伺服器程序驗證復工。請依研究報告的結果表解讀輸出，其中包含刻意測試的拒絕與未配置狀態。
