"""The plugin manifests, the APM manifest, and the MCP server."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
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
    def call(self, method, params=None, mid=1):
        return mcp.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})

    def test_initialize_and_list(self):
        r = self.call("initialize", {"protocolVersion": "2025-03-26"})["result"]
        self.assertEqual((r["protocolVersion"], r["serverInfo"]["name"]), ("2025-03-26", "agent-council"))
        names = [t["name"] for t in self.call("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["review", "review_status", "review_item", "review_decide"])
        self.assertIsNone(mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(self.call("nope")["error"]["code"], -32601)

    def test_tool_errors_come_back_as_results(self):
        r = self.call("tools/call", {"name": "review", "arguments": {"file": "relative.md"}})["result"]
        self.assertTrue(r["isError"])
        r = self.call("tools/call", {"name": "review_status", "arguments": {"job": "../x"}})["result"]
        self.assertTrue(r["isError"])

    def test_review_runs_the_cli_in_the_background_with_its_options(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "memo.md"
            f.write_text("# Memo\n")
            seen = {}
            fake = lambda cmd, **kw: seen.update(cmd=cmd, cwd=kw["cwd"]) or mock.Mock(poll=lambda: None)
            with mock.patch.object(mcp, "JOBS", Path(d) / "jobs"), mock.patch.object(mcp.subprocess, "Popen", fake):
                r = self.call("tools/call", {"name": "review", "arguments": {
                    "file": str(f), "panel": "gpt,argon", "focus": "methods", "verify": True}})["result"]
                job = r["content"][0]["text"].split("Job: ")[1].split(".")[0]
                s = self.call("tools/call", {"name": "review_status", "arguments": {"job": job}})["result"]
            self.assertEqual(seen["cmd"][1:], [str(mcp.CLI), "-p", "gpt,argon", "-n", "methods", "--verify", str(f)])
            self.assertEqual(seen["cwd"], f.parent)
            self.assertTrue(s["content"][0]["text"].startswith("Running"))

    def test_decide_passes_the_flag_and_note(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "memo.md"
            f.write_text("x")
            with mock.patch.object(mcp, "run_cli", lambda args, cwd: (" ".join(args), False)):
                r = self.call("tools/call", {"name": "review_decide", "arguments": {
                    "file": str(f), "decision": "ignore", "items": "5,7", "note": "out of scope"}})["result"]
        self.assertEqual(r["content"][0]["text"], "--ignore 5,7 --note out of scope")


if __name__ == "__main__":
    unittest.main()
