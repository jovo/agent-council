"""The plugin manifests, the APM manifest, and the MCP server."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp"))
import agent_council_mcp as mcp  # noqa: E402


class Manifests(unittest.TestCase):
    def load(self, rel):
        return json.loads((ROOT / rel).read_text())

    def test_versions_and_names_agree(self):
        claude, copilot = self.load(".claude-plugin/plugin.json"), self.load(".github/plugin/plugin.json")
        market = self.load(".claude-plugin/marketplace.json")
        apm = dict(re.findall(r"^(\w+): (.+)$", (ROOT / "apm.yml").read_text(), re.M))
        self.assertEqual({claude["version"], copilot["version"], apm["version"]}, {claude["version"]})
        self.assertEqual({claude["name"], copilot["name"], apm["name"], market["plugins"][0]["name"]}, {"agent-council"})
        self.assertEqual(market["plugins"][0]["source"], "./")

    def test_each_mcp_config_uses_its_hosts_root_variable(self):
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/mcp/agent_council_mcp.py",
                      self.load(".mcp.json")["mcpServers"]["agent-council"]["args"])
        copilot = self.load(".github/plugin/plugin.json")
        cfg = self.load(copilot["mcpServers"][2:])
        self.assertIn("${PLUGIN_ROOT}/mcp/agent_council_mcp.py", cfg["mcpServers"]["agent-council"]["args"])
        self.assertTrue((ROOT / copilot["skills"][2:]).is_dir())

    def test_skill_names_match_their_folders(self):
        # Copilot loads a skill only when its name is lowercase, hyphenated, and the folder's name.
        for d in (ROOT / "skills").iterdir():
            if (d / "SKILL.md").exists():
                head = (d / "SKILL.md").read_text().split("---")[1]
                name = re.search(r"^name: (.+)$", head, re.M).group(1).strip()
                desc = re.search(r"^description: (.+)$", head, re.M).group(1).strip()
                self.assertEqual(name, d.name)
                self.assertRegex(name, r"^[a-z0-9-]{1,64}$")
                self.assertLessEqual(len(desc), 1024)

    def test_bin_names_the_commands_skills_call(self):
        for cmd in ("unified-review", "make-pdf", "edit-md", "fix-strikes", "plain-words"):
            p = ROOT / "bin" / cmd
            self.assertTrue(p.exists(), cmd)
            self.assertTrue(p.resolve().stat().st_mode & 0o111, cmd)


class Server(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name).resolve()
        self.f = self.d / "memo.md"
        self.f.write_text("# Memo\n")
        for patch in (mock.patch.object(mcp, "ROOTS", [self.d]), mock.patch.object(mcp, "JOBS", self.d / "jobs")):
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, method, params=None, mid=1):
        return mcp.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})

    def tool(self, name, **args):
        r = self.call("tools/call", {"name": name, "arguments": args})["result"]
        return r["isError"], r["content"][0]["text"]

    def test_initialize_negotiates_a_supported_version(self):
        r = self.call("initialize", {"protocolVersion": "2025-03-26"})["result"]
        self.assertEqual((r["protocolVersion"], r["serverInfo"]["name"]), ("2025-03-26", "agent-council"))
        self.assertEqual(self.call("initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"],
                         mcp.SUPPORTED[0])
        names = [t["name"] for t in self.call("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["review", "review_status", "review_item", "review_decide"])
        self.assertIsNone(mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(self.call("nope")["error"]["code"], -32601)

    def test_malformed_requests_get_errors_not_a_crash(self):
        self.assertEqual(mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": []})["error"]["code"], -32600)
        self.assertEqual(self.call("tools/call", {"name": "review", "arguments": []})["error"]["code"], -32602)
        self.assertEqual(self.call("tools/call", {"name": 5})["error"]["code"], -32602)
        for args in ({"job": 1}, {"job": "../x"}, {"job": "20261128-001543-zzzzzz"}):
            self.assertTrue(self.tool("review_status", **args)[0], args)
        self.assertTrue(self.tool("review", file=str(self.f), panel=["gpt"])[0])
        self.assertTrue(self.tool("review_decide", file=str(self.f), decision="maybe", items="1")[0])

    def test_files_outside_the_roots_or_in_hidden_folders_are_refused(self):
        hidden = self.d / ".secrets" / "key.md"
        hidden.parent.mkdir()
        hidden.write_text("x")
        link = self.d / "link.md"
        link.symlink_to("/etc/hosts")
        for f in ("relative.md", str(hidden), str(link), "/etc/hosts"):
            err, text = self.tool("review", file=f)
            self.assertTrue(err, f)

    def test_review_runs_the_cli_in_the_background_and_status_follows_the_exit_file(self):
        seen = {}
        fake = lambda cmd, **kw: seen.update(cmd=cmd, cwd=kw["cwd"]) or SimpleNamespace(pid=os.getpid())
        with mock.patch.object(mcp.subprocess, "Popen", fake):
            err, text = self.tool("review", file=str(self.f), panel="gpt,argon", focus="methods", verify=True)
        self.assertFalse(err, text)
        job = text.split("Job: ")[1].split(".")[0]
        self.assertEqual(seen["cmd"][4:], [sys.executable, str(mcp.CLI), "-p", "gpt,argon", "-n", "methods", "--verify", str(self.f)])
        self.assertEqual(seen["cwd"], self.f.parent)
        self.assertTrue(self.tool("review_status", job=job)[1].startswith("Running"))
        d = self.d / "jobs" / job
        run = self.d / "run"
        run.mkdir()
        (d / "stdout.txt").write_text(f"Notes: {self.d}/notes/review.md\n{run}/unified.md\n")
        (d / "exit").write_text("0\n")
        text = self.tool("review_status", job=job)[1]
        self.assertIn("Done.", text)
        self.assertIn("Fact-check: still running", text)
        (run / "factcheck.md").write_text("x")
        self.assertIn("Fact-check: done", self.tool("review_status", job=job)[1])
        (d / "exit").write_text("1\n")
        self.assertIn("Failed (exit 1)", self.tool("review_status", job=job)[1])

    def test_a_job_whose_process_died_reports_it(self):
        d = self.d / "jobs" / "20261128-001543-abcdef"
        d.mkdir(parents=True)
        (d / "job.json").write_text(json.dumps({"pid": 2 ** 22 + 12345}))
        (d / "log.txt").write_text("1/4 review\n")
        self.assertIn("Stopped without finishing", self.tool("review_status", job="20261128-001543-abcdef")[1])

    def test_item_and_decide_name_the_files_own_run(self):
        calls = []
        with mock.patch.object(mcp, "run_cli", lambda args, cwd: (calls.append(args), (" ".join(args), False))[1]), \
                mock.patch.object(mcp, "run_of", lambda f: Path("/runs/r1")):
            self.tool("review_item", file=str(self.f), items="3")
            self.tool("review_decide", file=str(self.f), decision="ignore", items="5,7", note="out of scope")
        self.assertEqual(calls, [["--item", "3", "--run", "/runs/r1"],
                                 ["--ignore", "5,7", "--run", "/runs/r1", "--note", "out of scope"]])

    def test_run_of_finds_only_this_files_review(self):
        ur = mcp.cli_module()
        with mock.patch.object(ur, "runs_for", lambda p: [Path("/runs/new")] if p == self.f else []):
            self.assertEqual(mcp.run_of(self.f), Path("/runs/new"))
            with self.assertRaises(ValueError):
                mcp.run_of(self.d / "other.md")


if __name__ == "__main__":
    unittest.main()
