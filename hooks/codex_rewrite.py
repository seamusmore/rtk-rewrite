"""Codex PreToolUse adapter. stdin/stdout contain hook JSON only."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

# Run directly from an installed plugin, independent of the session cwd.
# Do not import the root __init__.py: it is the Hermes entry point.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.rewrite import rewrite


def updated_command(args: dict, command: str) -> dict:
    if os.name == "nt":
        launcher = str(Path(__file__).with_name("rtk_windows.ps1")).replace("'", "''")
        command = f"& '{launcher}' '{command.replace(chr(39), chr(39) * 2)}'"
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": {**args, "command": command},
    }}


def handle(event: object) -> dict:
    if not isinstance(event, dict) or event.get("hook_event_name") != "PreToolUse":
        return {}
    if event.get("tool_name") != "Bash":
        return {}
    args = event.get("tool_input")
    if not isinstance(args, dict):
        return {}
    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        return {}
    if os.name == "nt" and args.get("shell"):
        shell_name = str(args["shell"]).replace("\\", "/").rsplit("/", 1)[-1].lower()
        if shell_name not in {"pwsh", "pwsh.exe", "powershell", "powershell.exe"}:
            return {}
    mode = os.getenv("RTK_CODEX_MODE", "rewrite").strip().lower()
    if mode == "off":
        return {}
    if mode != "rewrite":
        return {"systemMessage": "[rtk] Invalid RTK_CODEX_MODE; keeping the original command."}
    stripped = command.lstrip()
    # RTK's parser assumes POSIX shell syntax. Leave compound commands,
    # substitutions, scripts and shell control syntax to the original shell.
    # This conservative rule also protects PowerShell on Windows.
    if any(char in command for char in "\r\n;&|<>`$(){}"):
        return {}
    explicit_rtk = re.match(r"rtk(?:\.exe)?\s+(.+)$", stripped, re.IGNORECASE)
    if explicit_rtk:
        # Direct diagnostics (including gain) need the same Windows profile
        # resolution and host-specific messages as automatically rewritten calls.
        if os.name == "nt":
            return updated_command(args, "rtk " + explicit_rtk.group(1))
        return {}
    try:
        timeout_ms = int(os.getenv("RTK_CODEX_TIMEOUT_MS", "2000"))
    except ValueError:
        timeout_ms = 2000
    if timeout_ms <= 0:
        timeout_ms = 2000
    # Stay below the outer hook timeout (10 seconds).
    timeout_ms = min(timeout_ms, 8000)
    cwd = args.get("cwd", args.get("workdir", event.get("cwd")))
    if cwd is not None and not isinstance(cwd, str):
        return {}
    result = rewrite(command, timeout_ms=timeout_ms, cwd=cwd, encoding="utf-8")
    if result.returncode == 2:
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "RTK policy denied this command. Review the RTK policy before retrying.",
        }}
    if result.status != "rewritten" or result.returncode not in {0, 3}:
        return {}
    # Only accept RTK-prefixed simple commands, with no shell prelude.
    if not result.command.startswith("rtk ") or any(
        char in result.command for char in "\r\n;&|<>`$(){}"
    ):
        return {}
    # Codex PreToolUse allow + updatedInput replaces arguments, then invokes
    # the regular tool handler (including its sandbox/approval checks).
    # It is distinct from PermissionRequest allow. RTK code 3 delegates to
    # that host approval flow, as it does in the existing Hermes adapter.
    return updated_command(args, result.command)


def main() -> None:
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
        output = handle(event)
    except (ValueError, OSError, UnicodeError):
        # Malformed input, unavailable RTK, or decoding errors leave the
        # original command to Codex. Never print command contents on errors.
        output = {}
    print(json.dumps(output, ensure_ascii=True))


if __name__ == "__main__":
    main()
