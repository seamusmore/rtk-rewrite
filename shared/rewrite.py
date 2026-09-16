"""Call RTK without executing the command being rewritten."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class RewriteResult:
    status: str
    command: str | None = None
    returncode: int | None = None
    stderr_present: bool = False


def rewrite(command: str, *, timeout_ms: int = 2000, cwd: str | None = None,
            encoding: str | None = None) -> RewriteResult:
    """Classify results; adapters decide how to handle RTK policy exit codes.

    Hermes accepts both 0 and 3 as candidates. Keep returncode so another
    host can decline code 3. Command contents and stderr are never logged.
    """
    kwargs = {} if cwd is None else {"cwd": cwd}
    if encoding is not None:
        kwargs.update(encoding=encoding, errors="replace")
    try:
        result = subprocess.run(
            ["rtk", "rewrite", command],
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        return RewriteResult("timeout")
    except OSError:
        return RewriteResult("error")

    rewritten = result.stdout.strip()
    code = result.returncode
    if code in {0, 3} and rewritten and rewritten != command:
        status = "rewritten"
    elif code == 1:
        status = "no_equivalent"
    elif code == 2:
        status = "denied"
    elif code in {0, 3} and rewritten == command:
        status = "same_command"
    elif code not in {0, 1, 2, 3}:
        status = "unexpected_exit_code"
    else:
        status = "empty"
    # The Hermes adapter historically inspects stderr only for unknown codes.
    # Keep that lazy behavior (Windows text decoding can leave stderr None).
    stderr_present = bool(result.stderr.strip()) if status == "unexpected_exit_code" else False
    return RewriteResult(status, rewritten if status == "rewritten" else None,
                         code, stderr_present)
