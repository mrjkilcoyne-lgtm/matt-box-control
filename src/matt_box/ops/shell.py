"""Shell command execution. Prefix-allowlisted, regex-denied, time-limited."""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Any

from ..allowlist import Allowlist, check_command

DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 600


def shell_run(
    allowlist: Allowlist,
    command: str,
    *,
    cwd: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    env_extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    cmd = check_command(allowlist, command)
    timeout = max(1, min(timeout, MAX_TIMEOUT))

    env = os.environ.copy()
    # never inherit hostile env from request — only allowlisted keys
    if env_extra:
        for k, v in env_extra.items():
            if k.startswith(("PATH", "HOME", "USERPROFILE", "TARDAI_")):
                env[k] = v

    # Use shell=False where we can — split on Windows respects quoting via shlex
    try:
        argv = shlex.split(cmd, posix=False)
    except ValueError as exc:
        return {"ok": False, "error": f"could not parse command: {exc}"}

    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            env=env,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout}s", "command": cmd}
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"command not found: {exc}", "command": cmd}

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.decode("utf-8", errors="replace")[-8192:],
        "stderr": proc.stderr.decode("utf-8", errors="replace")[-8192:],
        "command": cmd,
    }
