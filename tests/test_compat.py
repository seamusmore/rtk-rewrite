"""Behavioral regression tests against the pre-extraction Hermes revision."""

import importlib.util
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "07be79f4944b19b33a4941ea3f9ca49bed133be9"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hermes = load("rtk_hermes_test", ROOT / "__init__.py")
codex = load("rtk_codex_test", ROOT / "hooks/codex_rewrite.py")


class HermesRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = subprocess.check_output(
            ["git", "show", f"{BASELINE}:__init__.py"], cwd=ROOT
        ).decode("utf-8")
        cls.old = types.ModuleType("rtk_hermes_baseline")
        sys.modules[cls.old.__name__] = cls.old
        exec(compile(source, "baseline/__init__.py", "exec"), cls.old.__dict__)

    def run_case(self, module, mode, backend, command, outcome, marker="true"):
        module._reset_metrics()
        module._rtk_available = None
        args = {"command": command, "backend": backend, "unrelated": 42}
        env = {"RTK_HERMES_MODE": mode, "RTK_HERMES_PREVIEW_MARKER": marker}
        kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
        with patch.dict(os.environ, env, clear=True), patch("subprocess.run", **kwargs) as run, patch("time.perf_counter", side_effect=[1, 1.125]):
            module._pre_tool_call(tool_name="terminal", args=args)
        return args, module._metrics_snapshot(), run.call_args_list

    def test_original_behavior_matrix(self):
        outcomes = [subprocess.CompletedProcess([], code, stdout, "private stderr")
                    for code, stdout in itertools.product([0, 1, 2, 3, 7], ["rtk git status\n", "git status", ""])]
        outcomes += [FileNotFoundError(), OSError(), subprocess.TimeoutExpired("rtk", 2)]
        outcomes += [subprocess.CompletedProcess([], 3, "rtk git status", None)]
        for mode, backend, command, outcome, marker in itertools.product(
            ["rewrite", "suggest", "off"], ["local", "ssh"],
            ["git status", "rtk git status", ": RTK && rtk git status", "", None],
            outcomes, ["true", "false"],
        ):
            with self.subTest(mode=mode, backend=backend, command=command, outcome=outcome, marker=marker):
                self.assertEqual(self.run_case(self.old, mode, backend, command, outcome, marker),
                                 self.run_case(hermes, mode, backend, command, outcome, marker))

    def test_configuration_and_slash_commands(self):
        for env in [{}, {"RTK_HERMES_TIMEOUT_MS": "bad", "RTK_HERMES_MODE": "bad"},
                    {"RTK_HERMES_BACKENDS": "ssh, docker", "RTK_HERMES_TIMEOUT_MS": "-1"},
                    {"RTK_HERMES_BACKENDS": "all", "RTK_HERMES_PREVIEW_MARKER": "false"}]:
            for command in ["", "status", "show", "stats", "metrics", "config", "env", "reset-stats", "reset-metrics", "unknown"]:
                values = []
                for module in [self.old, hermes]:
                    module._reset_metrics()
                    module._rtk_available = None
                    with patch.dict(os.environ, env, clear=True), patch("shutil.which", return_value="rtk"):
                        values.append(module._handle_command(command))
                self.assertEqual(*values)

    def test_registration_contract(self):
        for mode, available in itertools.product(["rewrite", "off", "suggest"], [True, False]):
            snapshots = []
            for module in [self.old, hermes]:
                module._rtk_available = None
                ctx = Mock()
                with patch.dict(os.environ, {"RTK_HERMES_MODE": mode}, clear=True), patch("shutil.which", return_value="rtk" if available else None):
                    module.register(ctx)
                snapshots.append([(call[0], call[1][0]) for call in ctx.mock_calls])
                if ctx.register_hook.called:
                    self.assertIs(ctx.register_hook.call_args.args[1], module._pre_tool_call)
            self.assertEqual(*snapshots)


class CodexContract(unittest.TestCase):
    def expected_command(self, root=ROOT):
        if os.name == "nt":
            script = str(root / "hooks/rtk_windows.ps1").replace("'", "''")
            return f"& '{script}' 'rtk git status'"
        return "rtk git status"

    def event(self, command="git status"):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "cwd": str(ROOT), "tool_input": {"command": command, "timeout_ms": 5000}}

    def test_rewrite_preserves_other_arguments(self):
        from shared.rewrite import RewriteResult
        event = self.event()
        with patch.object(codex, "rewrite", return_value=RewriteResult("rewritten", "rtk git status", 0)):
            output = codex.handle(event)["hookSpecificOutput"]
        self.assertEqual(output["updatedInput"], {"command": self.expected_command(), "timeout_ms": 5000})
        self.assertEqual(event["tool_input"]["command"], "git status")
        self.assertEqual(output["permissionDecision"], "allow")

    def test_skips_scripts_other_tools_and_repeat_rewrites(self):
        for command in ["rtk git status", "RTK.exe git status", "git status; git diff", "git status && git diff",
                        'git diff "$env:HOME"', "git status | Out-String", "git status\ngit diff", "", None]:
            with patch.object(codex, "rewrite") as rewrite:
                self.assertEqual(codex.handle(self.event(command)), {})
                rewrite.assert_not_called()
        for event in [None, [], {}, {"hook_event_name": "PostToolUse"},
                      {**self.event(), "tool_name": "mcp__shell"}, {**self.event(), "tool_input": []}]:
            self.assertEqual(codex.handle(event), {})

    def test_policy_codes_and_failure_outcomes(self):
        from shared.rewrite import RewriteResult
        for code in [2]:
            with patch.object(codex, "rewrite", return_value=RewriteResult("denied", returncode=code)):
                self.assertEqual(codex.handle(self.event())["hookSpecificOutput"]["permissionDecision"], "deny")
        with patch.object(codex, "rewrite", return_value=RewriteResult("rewritten", "rtk git status", 3)):
            self.assertEqual(codex.handle(self.event())["hookSpecificOutput"]["updatedInput"]["command"], self.expected_command())
        for status in ["no_equivalent", "same_command", "empty", "timeout", "error", "unexpected_exit_code"]:
            with patch.object(codex, "rewrite", return_value=RewriteResult(status)):
                self.assertEqual(codex.handle(self.event()), {})

    def test_off_and_timeout_bounds(self):
        from shared.rewrite import RewriteResult
        with patch.dict(os.environ, {"RTK_CODEX_MODE": "off"}), patch.object(codex, "rewrite") as rewrite:
            self.assertEqual(codex.handle(self.event()), {})
            rewrite.assert_not_called()
        for raw, expected in [("bad", 2000), ("0", 2000), ("3000", 3000), ("99999", 8000)]:
            with patch.dict(os.environ, {"RTK_CODEX_TIMEOUT_MS": raw}), patch.object(codex, "rewrite", return_value=RewriteResult("empty")) as rewrite:
                codex.handle(self.event())
                self.assertEqual(rewrite.call_args.kwargs["timeout_ms"], expected)

    def test_json_stdio_and_missing_rtk(self):
        env = {**os.environ, "PATH": "", "RTK_CODEX_MODE": "rewrite"}
        for raw in [b"not json", b"[]", json.dumps(self.event()).encode()]:
            result = subprocess.run([sys.executable, str(ROOT / "hooks/codex_rewrite.py")],
                                    input=raw, capture_output=True, env=env, cwd=ROOT.parent)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {})
            self.assertEqual(result.stderr, b"")

    @unittest.skipUnless(shutil.which("rtk"), "RTK binary required")
    def test_real_rtk_from_a_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="rtk plugin ") as folder:
            copied = Path(folder) / "rtk-rewrite"
            shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            env = {**os.environ, "PLUGIN_ROOT": str(copied), "RTK_CODEX_MODE": "rewrite"}
            hooks = json.loads((copied / "hooks/hooks.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]
            if os.name == "nt":
                # Match Codex's raw_arg quoting, not list2cmdline's escaped quotes.
                comspec = os.environ.get("COMSPEC", "cmd.exe")
                invocation = f'"{comspec}" /d /s /c "{hooks["commandWindows"]}"'
            else:
                invocation = ["/bin/sh", "-c", hooks["command"]]
            result = subprocess.run(invocation, input=json.dumps(self.event()), text=True,
                                    capture_output=True, env=env, cwd=ROOT.parent)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)["hookSpecificOutput"]
            self.assertEqual(output["updatedInput"]["command"], self.expected_command(copied))

    @unittest.skipUnless(os.name == "nt", "Windows adapter required")
    def test_windows_other_shell_is_unchanged(self):
        event = self.event()
        event["tool_input"]["shell"] = "C:/Program Files/Git/bin/bash.exe"
        with patch.object(codex, "rewrite") as rewrite:
            self.assertEqual(codex.handle(event), {})
            rewrite.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows runner required")
    def test_windows_runner_preserves_arguments_exit_and_environment(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        with tempfile.TemporaryDirectory(prefix="rtk user's plugin ") as folder:
            script = Path(folder) / "rtk_windows.ps1"
            shutil.copyfile(ROOT / "hooks/rtk_windows.ps1", script)
            quoted = str(script).replace("'", "''")
            rtk_command = "rtk git diff -- 'folder with spaces/file.txt' 'user''s.txt'"
            driver = (
                "function rtk { ConvertTo-Json -Compress -InputObject "
                "@{arguments=@($args); directory=$env:CLAUDE_CONFIG_DIR}; $global:LASTEXITCODE=7 }; "
                f"& '{quoted}' '{rtk_command.replace(chr(39), chr(39)*2)}'; "
                "$result=$LASTEXITCODE; ConvertTo-Json -Compress -InputObject "
                "@{restored=$env:CLAUDE_CONFIG_DIR}; exit $result"
            )
            for override in [None, str(Path(folder) / "custom-config")]:
                env = dict(os.environ)
                env.pop("CLAUDE_CONFIG_DIR", None)
                if override:
                    env["CLAUDE_CONFIG_DIR"] = override
                result = subprocess.run([shell, "-NoProfile", "-Command", driver],
                                        capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 7, result.stderr)
                invoked, restored = map(json.loads, result.stdout.splitlines())
                self.assertEqual(invoked["arguments"],
                                 ["git", "diff", "folder with spaces/file.txt", "user's.txt"])
                self.assertEqual(invoked["directory"], override or str(Path(env["USERPROFILE"]) / ".claude"))
                self.assertEqual(restored["restored"] or None, override)

    @unittest.skipUnless(os.name == "nt", "Windows launcher required")
    def test_windows_launcher_from_powershell(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell is None:
            self.skipTest("PowerShell required")
        with tempfile.TemporaryDirectory(prefix="rtk plugin ") as folder:
            copied = Path(folder) / "rtk-rewrite"
            shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            hook = json.loads((copied / "hooks/hooks.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]
            # Off mode isolates launcher portability from RTK installation.
            env = {**os.environ, "PLUGIN_ROOT": str(copied), "RTK_CODEX_MODE": "off"}
            result = subprocess.run([shell, "-NoProfile", "-Command", hook["commandWindows"]],
                                    input=json.dumps(self.event()), text=True,
                                    capture_output=True, env=env, cwd=ROOT.parent)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})


if __name__ == "__main__":
    unittest.main()
