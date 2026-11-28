"""Install the project-local Codex adapter and find its active hooks."""

import json
import os
from pathlib import Path
import shlex
import sys

from runtime import HERE, ROOT, Refused, base_common, git, require, run, tool


EVENTS = {"PreToolUse": ".*", "SessionStart": "^(startup|resume|clear|compact|fork)$", "PostCompact": "^(manual|auto)$"}
BEGIN = "<!-- cdxdw:begin -->"
END = "<!-- cdxdw:end -->"
SKILL = "skills/cdx-resume/SKILL.md"
INSTALLED_SKILL = ".agents/" + SKILL
ADAPTER_FILES = (SKILL, "artifacts.py", "cdx_usage.py", "runtime.py", "cdxdw.py", "cdx_setup.py", "cdx_hook.py", "cdx_rpc.py", "cdx_review.py",
                 "desktop.py", "BASE_SYNC.json", "VARIANT.json")


def path_at(root, *parts):
    path = root.joinpath(*parts)
    if path != path.resolve():
        raise Refused(f"路徑指向別處：{path}")
    return path


def settings(work, director):
    path = path_at(work, ".codex", "hooks.json")
    if git(work, "ls-files", "--", ".codex/hooks.json"):
        raise Refused("已追蹤的 .codex/hooks.json 需要由操作者設定本機 Hook")
    data = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    if not isinstance(data, dict) or not isinstance(data.setdefault("hooks", {}), dict):
        raise Refused(".codex/hooks.json 需要 hooks 物件")
    hook = director / "adapters" / "codex" / "cdx_hook.py"
    argv = [sys.executable, "-I", "-B", "-X", "utf8", str(hook), "--director", str(director)]
    if os.name == "nt" and any(any(c in arg for c in "\r\n`") for arg in argv):
        raise Refused("Hook 路徑含控制字元")
    # Codex uses PowerShell on Windows and the default POSIX shell on other platforms.
    win = "& " + " ".join("'" + arg.replace("'", "''") + "'" for arg in argv)
    regular = win if os.name == "nt" else shlex.join(argv)
    for event, matcher in EVENTS.items():
        label = f"cdxdw {event}"
        groups = data["hooks"].setdefault(event, [])
        if not isinstance(groups, list) or any(not isinstance(group, dict) or
                                               not isinstance(group.get("hooks"), list) for group in groups):
            raise Refused(f"{event} 的 Hook 格式有誤")
        retained = []
        for group in groups:
            handlers = [item for item in group["hooks"] if not isinstance(item, dict) or item.get("statusMessage") != label]
            if handlers:
                retained.append(dict(group, hooks=handlers))
        retained.append({"matcher": matcher, "hooks": [{"type": "command", "command": regular,
                             "commandWindows": win, "statusMessage": label, "timeout": 12}]})
        data["hooks"][event] = retained
    return path, data


def skill_plan(work):
    destination = path_at(work, INSTALLED_SKILL)
    payload = (HERE / SKILL).read_bytes()
    if git(work, "ls-files", "--", INSTALLED_SKILL):
        raise Refused("續接技能已被 Git 追蹤，請先確認專案的版本")
    if destination.exists() and destination.read_bytes() != payload:
        raise Refused("已有不同版本的續接技能，請先備份及確認")
    return destination, payload


def hook_ready(work, director):
    path, wanted = settings(work, director)
    if not path.is_file() or json.loads(path.read_text(encoding="utf-8-sig")) != wanted:
        raise Refused("專案 Hook 設定尚未安裝或已變更")

    skill, payload = skill_plan(work)
    if not skill.is_file() or skill.read_bytes() != payload:
        raise Refused("Codex 續接技能尚未安裝")
    script = director / "adapters" / "codex"
    for name in ADAPTER_FILES:
        if not path_at(script, name).is_file():
            raise Refused(f"本機轉接檔缺失：{name}")
        if HERE != script and (script / name).read_bytes() != (HERE / name).read_bytes():
            raise Refused(f"本機轉接檔已變更或需要更新：{name}")
    require(tool("install", "check", "--to", director / "tools"), "共用工具驗證", "INSTALL_CHECK: PASS")
    return path


def enable_hooks(work, director, plan=None):
    path, data = plan or settings(work, director)
    skill, payload = skill_plan(work)
    result = tool("bootstrap_repo", "--repo", work, "--add", "/.codex/hooks.json", "--add", "/" + INSTALLED_SKILL)
    require(result, "本機 Hook 忽略規則", "BOOTSTRAP_REPO: DONE")
    require(tool_git_ignore(work, ".codex/hooks.json"), "Hook 必須是本機檔案")
    require(tool_git_ignore(work, INSTALLED_SKILL), "續接技能必須是本機檔案")
    common = base_common()
    common.write_bytes_atomic(skill, payload)
    common.write_json_atomic(path, data)
    return path


def tool_git_ignore(work, path):
    return run("git", "-C", work, "check-ignore", "--", path)


def read_existing(path):
    return path.read_bytes() if path.is_file() else b""


def project_agents(repo):
    path = path_at(repo, "AGENTS.md")
    original = read_existing(path)
    variant = json.loads((HERE / "VARIANT.json").read_text(encoding="utf-8"))
    source = Path(variant["rules_section"])
    if source.is_absolute() or ".." in source.parts:
        raise Refused("VARIANT.json 的 rules_section 必須是規則包內的相對路徑")
    rule = path_at(ROOT, *source.parts).read_text(encoding="utf-8")
    block = f"{BEGIN}\n{rule.rstrip()}\n{END}\n".encode()
    start, finish = BEGIN.encode(), END.encode()
    if original.count(start) != original.count(finish) or original.count(start) > 1:
        raise Refused("AGENTS.md 有不完整的 cdxdw 標記")
    if start in original:
        prefix, _, previous = original.partition(start)
        body, _, suffix = previous.partition(finish)
        if not body or finish in prefix:
            raise Refused("AGENTS.md 的 cdxdw 標記順序有誤")
        return path, prefix + block.rstrip(b"\n") + suffix
    return path, original + (b"\n\n" if original else b"") + block


def install(repo, director, mode, execute):
    director = path_at(repo, "DIRECTOR")
    if git(repo, "ls-files", "--", "DIRECTOR"):
        raise Refused("DIRECTOR 已被 Git 追蹤，請先處理這份紀錄的保存方式")
    hook_plan = settings(repo, director)
    skill_plan(repo)
    agents, rules = project_agents(repo)
    ignore = path_at(repo, ".gitignore")
    raw = read_existing(ignore)
    if b"/DIRECTOR/" not in raw.splitlines():
        raw += (b"\n" if raw and not raw.endswith(b"\n") else b"") + b"/DIRECTOR/\n"
    install_args = ("install", "--rules", ROOT, "--to", director / "tools", "--skip-optional")
    installer = tool("install", *install_args)
    text = require(installer, "共用工具安裝預覽")
    if not text.splitlines() or not text.splitlines()[-1].startswith(("INSTALL: DRY_RUN ", "INSTALL: OK ")):
        raise Refused("共用工具安裝預覽沒有結論")
    if not execute:
        print(text.splitlines()[-1])
        print(f"CDX_INSTALL: PLAN mode={mode} DIRECTOR/ AGENTS.md .gitignore .codex/hooks.json")
        return
    common = base_common()
    common.write_bytes_atomic(ignore, raw)
    require(tool_git_ignore(repo, "DIRECTOR/INDEX.md"), "DIRECTOR 必須被 Git 忽略")
    done = require(tool("install", *install_args, "--execute"),
                   "共用工具安裝")
    if not done.splitlines() or not done.splitlines()[-1].startswith(("INSTALL: DONE ", "INSTALL: OK ")):
        raise Refused("共用工具安裝沒有結論")
    deployed = path_at(director, "adapters", "codex")
    for name in ADAPTER_FILES:
        common.write_bytes_atomic(path_at(deployed, name), (HERE / name).read_bytes())
    state = path_at(director, "director_work.json")
    if not state.exists():
        config = json.loads((ROOT / "director_work.example.json").read_text(encoding="utf-8-sig"))
        config["mode"] = mode
        config.pop("strength", None)
        common.write_json_atomic(state, config)
    templates = ROOT / "templates"
    contents = {name: (templates / name).read_bytes()
                for name in ("BRIEF.md", "PO_PENDING.md", "DECISION_REGISTER.md", "RESUME_STATE.md")}
    contents["DIRECTOR_LOG.md"] = b"# Director log\n"
    contents["INDEX.md"] = (
        f"# {repo.name}\n\n- 初衷與驗收：[BRIEF.md](BRIEF.md)\n"
        "- 決定：[DECISION_REGISTER.md](DECISION_REGISTER.md)\n"
        "- 進度與下一步：[RESUME_STATE.md](RESUME_STATE.md)\n"
        "- 待答：[PO_PENDING.md](PO_PENDING.md)\n"
        "- 派工：[DIRECTOR_LOG.md](DIRECTOR_LOG.md) · [orders](orders/)\n"
        "- 交接：[HANDOFF_MANIFEST.md](HANDOFF_MANIFEST.md)（匯出後產生）\n"
    ).encode()
    for name, payload in contents.items():
        target = path_at(director, name)
        if not target.exists():
            common.write_bytes_atomic(target, payload)
    path_at(director, "orders").mkdir(exist_ok=True)
    common.write_bytes_atomic(agents, rules)
    enable_hooks(repo, director, hook_plan)
    print("CDX_INSTALL: APPLIED (請在 Codex 載入並信任專案 Hook)")
