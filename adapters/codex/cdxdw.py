"""Codex entry point for the DW 3.0 adapter."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import check_assets
from cdx_usage import usage_report
from cdx_review import review_server, review_turn
from cdx_rpc import AppServer
from cdx_setup import EVENTS, enable_hooks, hook_ready, install, path_at
from desktop import attach
from runtime import HERE, ROOT, SHA, Refused, base_common, checkout, git, primary, require, specification, tool


def host_binary(value):
    result = value or shutil.which("codex")
    if not result:
        raise Refused("找不到 Codex CLI")
    return result


def live_hooks(work, executable):
    with AppServer(host_binary(executable), work) as server:
        rows = server.call("hooks/list", {"cwds": [str(work)]}).get("data")
        if not isinstance(rows, list):
            raise Refused("宿主沒有回覆 Hook 清單")
        hooks = [hook for row in rows for hook in row.get("hooks", [])]
        for event in EVENTS:
            selected = [hook for hook in hooks if hook.get("statusMessage") == f"cdxdw {event}"]
            if len(selected) != 1 or selected[0].get("trustStatus") != "trusted":
                raise Refused(f"Codex 尚未確認 cdxdw {event} 已信任")


def prepare(repo, director, args):
    specification(director)
    argv = ["open", repo, "--order", args.order, "--base", args.base, "--brief", director / "BRIEF.md"]
    for flag, value in (("--branch", args.branch), ("--root", args.root)):
        if value is not None:
            argv.extend((flag, value))
    parent = args.root.resolve() if args.root else repo.parent / "wt"
    output = require(tool("worktree", *argv), "開工作樹")
    if "WORKER_WORKTREE: " not in output or "隔離 worktree" not in output:
        raise Refused("基板未確認工作樹已建立")
    enable_hooks(checkout(parent / args.order), director)
    print(output)


def dispatch(repo, director, name):
    if name.name != str(name) or name.suffix.lower() != ".md":
        raise Refused("指定 DIRECTOR/orders 裡的工單檔名")
    order = path_at(director, "orders", name.name)
    specification(director)
    status = require(tool("gate_check", "--order", order, "--repo", repo, "--config", director / "director_work.json"),
                     "工單關卡")
    if not any(line.split(maxsplit=2)[:2] == ["OK", "order"] for line in status.splitlines()):
        raise Refused("工單關卡沒有通過結論")
    output = require(tool("gate_check", "--hash", order), "派工指紋")
    if not any(line.lstrip().startswith("DISPATCH ") for line in output.splitlines()):
        raise Refused("派工指紋沒有回傳 DISPATCH 行")
    print(output)


def review_sandbox(server, work):
    if os.name == "nt" and server.call("windowsSandbox/readiness", {}).get("status") != "ready":
        raise Refused("Windows 沙箱尚未就緒")
    probe = work / ".cdxdw-review-probe"
    code = "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('probe')"
    command = [sys.executable, "-I", "-c", code, str(probe)]
    control = server.call("command/exec", {"cwd": str(work), "command": command, "timeoutMs": 10000,
                          "sandboxPolicy": {"type": "workspaceWrite", "writableRoots": [str(work)],
                                            "networkAccess": False}})
    if type(control.get("exitCode")) is not int or control["exitCode"] != 0 or not probe.is_file():
        raise Refused("唯讀探針的正對照未成功")
    probe.unlink()
    result = server.call("command/exec", {"cwd": str(work), "command": command, "timeoutMs": 10000,
                         "sandboxPolicy": {"type": "readOnly", "networkAccess": False}})
    if type(result.get("exitCode")) is not int or result["exitCode"] == 0 or probe.exists():
        raise Refused("未證實唯讀沙箱會擋實際寫入")


def review(repo, director, args):
    specification(director)
    if not (SHA.fullmatch(args.base) and SHA.fullmatch(args.candidate) and args.base != args.candidate):
        raise Refused("使用互不相同的完整 base 與候選 SHA")
    if git(repo, "merge-base", args.base, args.candidate) != args.base:
        raise Refused("候選不在指定 base 之後")
    record = {"base": args.base, "candidate": args.candidate, "state": "PREVIEW"}
    if not args.run:
        print(json.dumps(record))
        return
    executable = host_binary(args.codex)
    receipt = path_at(director, "codex-reviews", f"{uuid.uuid4()}.json")
    with tempfile.TemporaryDirectory(prefix="dw-codex-review-") as directory:
        root = Path(directory).resolve()
        work = root / "candidate"
        work.mkdir()
        git(work, "init", "--template=")
        git(work, "config", "core.hooksPath", str(root / "no-hooks"))
        git(work, "fetch", "--no-tags", "--", repo, args.candidate)
        git(work, "checkout", "--detach", args.candidate)
        events = []
        record["state"] = "RUNNING"
        save = lambda: base_common().write_json_atomic(receipt, record)
        save()
        try:
            with review_server(executable, work, events.append) as server:
                review_sandbox(server, work)
                review_turn(server, work, args.base, args.timeout, record, save, events, args.model)
            if git(work, "status", "--porcelain", "--untracked-files=all") or git(work, "rev-parse", "HEAD") != args.candidate:
                raise Refused("審查後工作樹與原候選不符")
            if record.get("native_status") != "completed" or not record.get("review"):
                raise Refused("原生審查沒有完成結果")
            record["state"] = "RECORDED"
        finally:
            if record["state"] == "RUNNING":
                record["state"] = "UNKNOWN"
            save()
    print(json.dumps(dict(record, receipt=str(receipt)), ensure_ascii=False))


def release_check(repo, director, args):
    frozen = json.loads((HERE / "BASE_SYNC.json").read_text(encoding="utf-8"))["base_commit"]
    base = args.base.resolve()
    if git(base, "rev-parse", "HEAD") != frozen or git(base, "status", "--porcelain"):
        raise Refused("使用乾淨且符合 BASE_SYNC.json 的凍結基板")
    require(tool("base_sync_check", "--base", base, "--variant", repo, "--registry", HERE / "BASE_SYNC.json"),
            "基板同步", "BASE_SYNC: PASS")
    if not SHA.fullmatch(args.candidate) or git(repo, "rev-parse", "HEAD") != args.candidate:
        raise Refused("準備公告的 SHA 要等於目前 HEAD")
    if git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise Refused("發版工作樹必須乾淨")
    require(tool("readme_check", "--repo", repo, "--rev", args.candidate),
            "README 檢查", "README_CHECK: PASS")
    if (director / "BRIEF.md").is_file():
        specification(director)
        require(tool("delivery", "check", "--repo", repo, "--director", director, "--delivered", args.candidate),
                "交付證據", "DELIVERY_CHECK: PASS")
    require(tool("privacy_scan", "--repo", repo, "--rev", args.candidate), "隱私掃描", "PRIVACY_SCAN: CLEAN")
    print(f"CDX_RELEASE_CHECK: PASS candidate={args.candidate}")


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    actions = parser.add_subparsers(dest="action", required=True)
    setup = actions.add_parser("install")
    setup.add_argument("--mode", choices=("general", "beginner"), default="general")
    setup.add_argument("--execute", action="store_true")
    doctor = actions.add_parser("doctor")
    doctor.add_argument("--live", action="store_true")
    doctor.add_argument("--codex")
    actions.add_parser("spec-check")
    worker = actions.add_parser("prepare")
    worker.add_argument("--order", required=True)
    worker.add_argument("--base", default="HEAD")
    worker.add_argument("--branch")
    worker.add_argument("--root", type=Path)
    actions.add_parser("dispatch").add_argument("order", type=Path)
    handoff = actions.add_parser("attach")
    handoff.add_argument("--worktree", required=True, type=Path)
    handoff.add_argument("--candidate", required=True)
    handoff.add_argument("--chat")
    handoff.add_argument("--codex")
    native = actions.add_parser("native-review")
    native.add_argument("--base", required=True)
    native.add_argument("--candidate", required=True)
    native.add_argument("--codex")
    native.add_argument("--model")
    native.add_argument("--timeout", type=int, default=900)
    native.add_argument("--run", action="store_true")
    usage = actions.add_parser("usage")
    usage.add_argument("events", type=Path)
    usage.add_argument("--format", choices=("exec", "app-server"), default="exec")
    assets = actions.add_parser("asset-check")
    assets.add_argument("--candidate", required=True)
    assets.add_argument("--root", required=True, type=Path)
    assets.add_argument("--asset", nargs=2, metavar=("DELIVERY_PATH", "ASSET_NAME"), action="append", required=True)
    release = actions.add_parser("release-check")
    release.add_argument("--base", required=True, type=Path)
    release.add_argument("--candidate", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "usage":
            print(json.dumps(usage_report(args.events, args.format), ensure_ascii=False))
            return 0
        work = checkout(args.repo)
        if args.action == "release-check" and work != ROOT:
            raise Refused("請從 Codex 規則包的正確 checkout 執行發版檢查")
        repo = work if args.action == "release-check" and work == ROOT else primary(work)
        director = path_at(repo, "DIRECTOR")
        if args.action == "install":
            if work != repo:
                raise Refused("在主要工作目錄安裝，再到隔離工作樹交接")
            install(repo, director, args.mode, args.execute)
        elif args.action == "doctor":
            hook_ready(work, director)
            if args.live:
                live_hooks(work, args.codex)
            print("CDX_DOCTOR: " + ("PASS (host trust confirmed)" if args.live else "CONFIGURED (host trust untested)"))
        elif args.action == "spec-check":
            print(specification(director))
        elif args.action == "prepare":
            prepare(repo, director, args)
        elif args.action == "dispatch":
            dispatch(repo, director, args.order)
        elif args.action == "attach":
            print(json.dumps(attach(repo, director, args.worktree, args.candidate, args.chat, args.codex),
                             ensure_ascii=False))
        elif args.action == "asset-check":
            specification(director)
            if not SHA.fullmatch(args.candidate) or git(work, "rev-parse", "HEAD") != args.candidate:
                raise Refused("資產候選要等於交付工作樹的完整 HEAD")
            found = check_assets(work, director, args.candidate, args.root, args.asset)
            print(f"CDX_ASSET_CHECK: PASS candidate={args.candidate} assets={len(found)}")
        elif args.action == "native-review":
            review(repo, director, args)
        else:
            release_check(repo, director, args)
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"CDX: FAIL {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
