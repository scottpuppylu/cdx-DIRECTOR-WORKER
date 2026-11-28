"""Exercise the Codex boundary in synthetic checkouts; no account or network required."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cdxdw
import cdx_hook
import desktop
from cdx_review import review_connections
from cdx_setup import EVENTS, INSTALLED_SKILL
from runtime import HERE, ROOT, Refused, git, run, tool

spec = importlib.util.spec_from_file_location("dw_test_fixtures", ROOT / "tools" / "selftest.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class AdapterTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dw-codex-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "project space"
        self.repo.mkdir()
        git(self.repo, "init", "--template=", "-b", "main")
        self.director = self.repo / "DIRECTOR"
        self.app = self.repo / "product.txt"
        self.app.write_text("initial\n", encoding="utf-8")
        git(self.repo, "add", "product.txt")
        git(self.repo, "-c", "user.name=DW Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
        self.initial = git(self.repo, "rev-parse", "HEAD")

    def cli(self, *args, expected=0, repo=None):
        process = run(sys.executable, "-I", "-B", "-X", "utf8", HERE / "cdxdw.py", "--repo", repo or self.repo, *args)
        self.assertEqual(process.returncode, expected, process.stdout + process.stderr)
        self.assertNotIn("Traceback", process.stderr)
        return process.stdout + process.stderr

    def install(self, mode="general"):
        self.assertIn("CDX_INSTALL: APPLIED", self.cli("install", "--mode", mode, "--execute"))

    def brief(self, change=lambda text: text):
        (self.director / "BRIEF.md").write_text(change(base.HANDOFF_BRIEF_300), encoding="utf-8")

    def approve(self):
        self.brief()
        process = tool("spec_gate", "approve", "--brief", self.director / "BRIEF.md")
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def event(self, name, arg, kind="PreToolUse"):
        return {"hook_event_name": kind, "cwd": str(self.repo), "tool_name": name, "tool_input": arg}

    def hook(self, name, arg, kind="PreToolUse"):
        entry = self.director / "adapters" / "codex" / "cdx_hook.py"
        p = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str(entry), "--director", str(self.director)],
                           input=json.dumps(self.event(name, arg, kind)), capture_output=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def assertDenied(self, reply):
        self.assertEqual(reply.get("hookSpecificOutput", {}).get("permissionDecision"), "deny", reply)

    def test_preview_writes_nothing(self):
        self.assertIn("CDX_INSTALL: PLAN", self.cli("install", "--mode", "beginner"))
        self.assertFalse(self.director.exists())
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_beginner_install_and_idempotent_hook(self):
        agents = self.repo / "AGENTS.md"
        agents.write_bytes(b"# Existing rules\n")
        settings = self.repo / ".codex" / "hooks.json"
        settings.parent.mkdir()
        user_hook = {"type": "command", "command": "echo existing"}
        settings.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [user_hook]}]}}), encoding="utf-8")
        self.install("beginner")
        initial = agents.read_bytes(), settings.read_bytes()
        self.install("beginner")
        self.assertEqual(initial, (agents.read_bytes(), settings.read_bytes()))
        self.assertTrue(initial[0].startswith(b"# Existing rules\n"))
        self.assertIn(user_hook, json.loads(initial[1])["hooks"]["SessionStart"][0]["hooks"])
        config = json.loads((self.director / "director_work.json").read_bytes())
        self.assertEqual(config["mode"], "beginner")
        self.assertNotIn("strength", config)
        self.assertEqual(json.loads((self.director / "adapters/codex/VARIANT.json").read_bytes()),
                         {"default_strength": "standard", "rules_section": "AGENTS.md"})
        self.assertFalse((self.director / "tools/hook_guard.py").exists())
        self.assertTrue((self.director / "tools/setup_project_settings.py").is_file())
        strength = run(sys.executable, "-I", "-B", "-X", "utf8", self.director / "tools/safety_gate.py", "--show")
        self.assertEqual(strength.returncode, 0, strength.stdout + strength.stderr)
        self.assertIn("default strength standard from adapters/codex/VARIANT.json", strength.stdout)
        self.assertEqual(git(self.repo, "check-ignore", "DIRECTOR/INDEX.md"), "DIRECTOR/INDEX.md")
        self.assertEqual(git(self.repo, "check-ignore", INSTALLED_SKILL), INSTALLED_SKILL)
        self.assertIn("DIRECTOR/INDEX.md", (self.repo / INSTALLED_SKILL).read_text(encoding="utf-8"))
        self.assertIn("CONFIGURED", self.cli("doctor"))
        (self.director / "adapters/codex/cdx_hook.py").unlink()
        self.assertIn("本機轉接檔缺失", self.cli("doctor", expected=2))

    def test_missing_and_incomplete_spec_all_profiles(self):
        self.install()
        for strength in ("light", "standard", "strict"):
            cfg = self.director / "director_work.json"
            data = json.loads(cfg.read_bytes())
            data["strength"] = strength
            cfg.write_text(json.dumps(data), encoding="utf-8")
            for change in (
                lambda _: "",
                lambda text: text.replace("櫃台人員一打開就看到今天要來的人", ""),
                lambda text: text.replace("- 無", "- 尚未決定"),
                lambda text: text.split("## 現成方案調查")[0],
                lambda text: text.replace("「對，就是這樣，開始做」", ""),
                lambda text: text,
            ):
                with self.subTest(strength=strength, variant=change):
                    self.brief(change)
                    self.cli("spec-check", expected=2)
        (self.director / "BRIEF.md").unlink()
        self.cli("spec-check", expected=2)

    def test_hook_allows_research_and_director_notes_before_approval(self):
        self.install()
        self.assertEqual(self.hook("Bash", {"command": "git status --short"}), {})
        apply = {"command": "*** Begin Patch\n*** Add File: DIRECTOR/research.md\n+notes\n*** End Patch"}
        self.assertEqual(self.hook("apply_patch", apply), {})
        self.assertIn("INDEX.md", json.dumps(self.hook(None, {}, kind="SessionStart")))
        self.assertIn("INDEX.md", self.hook(None, {}, kind="PostCompact")["systemMessage"])

    def test_hook_blocks_product_worktree_dispatch_until_approval_and_reblocks_changed_brief(self):
        self.install("beginner")
        calls = [("apply_patch", {"command": "*** Add File: product.md\n+fixture"}),
                 ("Bash", {"command": "git worktree add ../worker"}),
                 ("Bash", {"command": "git branch topic"}),
                 ("spawn_agent", {"message": "draft a worker report"})]
        for name, arg in calls:
            self.assertDenied(self.hook(name, arg))
        self.approve()
        for name, arg in calls:
            self.assertEqual(self.hook(name, arg), {})
        self.brief(lambda text: text.replace("不花錢", "不用連線"))
        self.assertDenied(self.hook(*calls[0]))

    def test_approval_does_not_grant_operator_actions(self):
        self.install()
        self.approve()
        for command in ("git push origin topic", "gh release create version",
                        "git reset --hard HEAD", "git clean -fd", "git stash",
                        "python tools/spec_gate.py approve", "git status ; Write-Output second"):
            with self.subTest(command=command):
                self.assertDenied(self.hook("Bash", {"command": command}))
        self.assertDenied(self.hook("apply_patch", {"command": "*** Update File: DIRECTOR/brief-history/current.md"}))

    def test_prepare_and_attach_use_real_base_and_exact_head(self):
        self.install()
        self.cli("prepare", "--order", "WO-001", "--root", self.root / "workers", expected=2)
        self.assertFalse((self.root / "workers").exists())
        self.approve()
        self.assertIn("WORKER_WORKTREE:", self.cli("prepare", "--order", "WO-001", "--root", self.root / "workers"))
        worker = self.root / "workers" / "WO-001"
        self.assertTrue((worker / ".codex" / "hooks.json").is_file())
        self.assertTrue((worker / INSTALLED_SKILL).is_file())
        process = tool("handoff", "export", "--director", self.director, "--repo", self.repo)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.cli("attach", "--worktree", worker, "--candidate", "0" * 40, expected=2)
        result = json.loads(self.cli("attach", "--worktree", worker, "--candidate", self.initial))
        self.assertEqual(result["candidate"], self.initial)
        self.assertTrue((self.director / "codex-desktop").is_dir())
        (self.director / "PO_PENDING.md").write_text("changed after export", encoding="utf-8")
        self.assertIn("HANDOFF_VERIFY: FAIL", self.cli("attach", "--worktree", worker, "--candidate", self.initial, expected=2))
        self.cli("attach", "--worktree", self.repo, "--candidate", self.initial, expected=2)

    def test_dispatch_runs_shared_gate_and_returns_a_fingerprint(self):
        self.install()
        order = self.director / "orders" / "WO-001.md"
        order.write_text(base.ORDER.format(base=self.initial), encoding="utf-8")
        self.cli("dispatch", order.name, expected=2)
        self.approve()
        self.assertIn("DISPATCH WO-001 rev=", self.cli("dispatch", order.name))
        self.assertNotIn("DISPATCH WO-001 rev=", (self.director / "DIRECTOR_LOG.md").read_text(encoding="utf-8"))

    def test_desktop_chat_must_be_idle_and_at_the_destination(self):
        thread = "01010101-0101-0101-0101-010101010101"
        chat = {"id": thread, "cwd": str(self.repo), "status": {"type": "idle"}}
        with patch.object(desktop, "AppServer") as client:
            client.return_value.__enter__.return_value.call.return_value = {"thread": chat}
            desktop.verify_chat(self.repo, thread, "fixture-codex")
            chat["status"]["type"] = "active"
            with self.assertRaises(Refused):
                desktop.verify_chat(self.repo, thread, "fixture-codex")
            chat["status"]["type"] = "idle"
            chat["cwd"] = str(self.root)
            with self.assertRaises(Refused):
                desktop.verify_chat(self.repo, thread, "fixture-codex")

    def test_dispatch_never_accepts_result_without_exit_code(self):
        with patch.object(cdxdw, "specification"), patch.object(cdxdw, "tool") as tool_result:
            for response in [SimpleNamespace(stdout="OK  order example"), SimpleNamespace(returncode=0, stdout="")]:
                tool_result.return_value = response
                with self.assertRaises(Refused):
                    cdxdw.dispatch(self.repo, self.director, Path("WO-001.md"))
            tool_result.side_effect = [SimpleNamespace(returncode=0, stdout="OK  order example"),
                                        SimpleNamespace(stdout="DISPATCH WO-001 rev=1 sha=no")]
            with self.assertRaises(Refused):
                cdxdw.dispatch(self.repo, self.director, Path("WO-001.md"))

    def test_asset_hashes_must_match_delivery_and_current_candidate(self):
        self.install()
        self.approve()
        order = self.director / "orders" / "WO-008.md"
        order.write_text("# WO-008\nGOVERNANCE = Direct\n", encoding="utf-8")
        record = tool("delivery", "record", "--repo", self.repo, "--director", self.director,
                      "--candidate", self.initial, "--file", self.app.name, "--order", "WO-008")
        self.assertEqual(record.returncode, 0, record.stdout + record.stderr)
        directory = self.root / "publish"
        directory.mkdir()
        asset = directory / "delivery.txt"
        asset.write_bytes(b"initial\n")
        args = ("asset-check", "--candidate", self.initial, "--root", directory, "--asset", self.app.name, asset.name)
        self.assertIn("CDX_ASSET_CHECK: PASS", self.cli(*args))
        with patch("artifacts.tool", return_value=SimpleNamespace(stdout="DELIVERY_CHECK: PASS")):
            with self.assertRaises(Refused):
                cdxdw.check_assets(self.repo, self.director, self.initial, directory, [(self.app.name, asset.name)])
        self.cli(*args, "--asset", self.app.name, asset.name.upper(), expected=2)
        asset.write_bytes(b"changed\n")
        self.assertIn("資產和驗過的交付檔不同", self.cli(*args, expected=2))

    def test_usage_reports_invalid_counts_and_unobserved_fields(self):
        events = self.root / "events.jsonl"
        rows = [{"type": "turn.completed", "usage": {"input_tokens": 2, "output_tokens": "4"}},
                {"type": "turn.completed", "usage": {"input_tokens": True, "output_tokens": 5}}]
        events.write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
        output = json.loads(self.cli("usage", events))
        self.assertEqual(output["status"], "partial")
        self.assertEqual(output["invalid_fields"], ["usage.input_tokens", "usage.output_tokens"])
        self.assertEqual(output["total"], {"input_tokens": 2, "cached_input_tokens": None,
                                          "output_tokens": 5, "reasoning_output_tokens": None})
        rows = [{"method": "thread/tokenUsage/updated", "params": {
            "threadId": "a", "tokenUsage": {"total": {"inputTokens": 2}, "last": {"inputTokens": 2}}}}]
        events.write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
        output = json.loads(self.cli("usage", events, "--format", "app-server"))
        self.assertEqual(output["threads"]["a"]["total"]["inputTokens"], 2)
        self.assertEqual(output["status"], "observed")

    def test_gate_markers_require_integer_exit_code_and_terminal_proof(self):
        for marker in ("SPEC_GATE: PASS", "HANDOFF_VERIFY: PASS", "BASE_SYNC: PASS",
                       "PRIVACY_SCAN: CLEAN", "DELIVERY_CHECK: PASS", "README_CHECK: PASS", "INSTALL_CHECK: PASS",
                       "BOOTSTRAP_REPO: DONE"):
            for result in (SimpleNamespace(stdout=marker), SimpleNamespace(returncode=False, stdout=marker),
                           SimpleNamespace(returncode=0, stdout=marker + "\nERROR")):
                with self.subTest(marker=marker, result=result):
                    with self.assertRaises(Refused):
                        cdxdw.require(result, "gate", marker)
            self.assertEqual(cdxdw.require(SimpleNamespace(returncode=0, stdout=marker), "gate", marker), marker)

    def test_worktree_gate_and_hook_reject_timeout_or_missing_exit(self):
        args = SimpleNamespace(order="WO-001", base="HEAD", branch=None, root=self.root / "workers")
        with patch.object(cdxdw, "specification"), patch.object(cdxdw, "tool") as tool_result:
            tool_result.return_value = SimpleNamespace(stdout="WORKER_WORKTREE: x\nWORKTREE: 隔離 worktree x")
            with self.assertRaises(Refused):
                cdxdw.prepare(self.repo, self.director, args)
        self.assertFalse((self.root / "workers").exists())
        self.install()
        self.approve()
        with patch.object(cdx_hook, "specification", side_effect=subprocess.TimeoutExpired("spec_gate", 1)):
            with self.assertRaises(subprocess.TimeoutExpired):
                cdx_hook.respond(self.event("Bash", {"command": "git branch topic"}), self.director)

    def test_hook_bad_input_returns_denial(self):
        self.install()
        self.assertDenied(self.hook("Bash", {"command": None}))
        self.assertDenied(self.hook("apply_patch", {"command": "*** Update File: ../outside.txt"}))

    def test_review_requires_runtime_isolation_and_completed_probes(self):
        good = {"config": {"features": {"apps": False, "plugins": False, "hooks": False},
                           "mcp_servers": {}, "web_search": "disabled"}}
        host = SimpleNamespace(call=lambda method, _: good if method == "config/read" else {"data": []})
        review_connections(host, self.repo)
        for response in ({"data": [], "nextCursor": "next"}, {}, {"data": [{"name": "other"}]}):
            host.call = lambda method, _: good if method == "config/read" else response
            with self.assertRaises(Refused):
                review_connections(host, self.repo)

        def sandbox_calls(method, params):
            if method == "windowsSandbox/readiness":
                return {"status": "ready"}
            if params["sandboxPolicy"]["type"] == "workspaceWrite":
                (self.repo / ".cdxdw-review-probe").write_text("probe", encoding="utf-8")
                return {"exitCode": 0}
            return {}

        host.call = sandbox_calls
        with self.assertRaisesRegex(Refused, "未證實唯讀沙箱"):
            cdxdw.review_sandbox(host, self.repo)

    def test_live_doctor_requires_trusted_event_inventory(self):
        rows = [{"statusMessage": f"cdxdw {event}", "trustStatus": "trusted"} for event in EVENTS]
        with patch.object(cdxdw, "AppServer") as rpc:
            rpc.return_value.__enter__.return_value.call.return_value = {"data": [{"hooks": rows}]}
            cdxdw.live_hooks(self.repo, "fixture-codex")
            rows[0]["trustStatus"] = "untrusted"
            with self.assertRaises(Refused):
                cdxdw.live_hooks(self.repo, "fixture-codex")


if __name__ == "__main__":
    unittest.main(verbosity=2)
