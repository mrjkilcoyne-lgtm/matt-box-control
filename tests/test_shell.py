"""Shell op tests."""

from __future__ import annotations

import sys

import pytest

from matt_box.allowlist import Allowlist, AllowlistError
from matt_box.ops.shell import shell_run


@pytest.fixture
def allowlist() -> Allowlist:
    # `python` is reasonable to assume present in CI
    return Allowlist.from_dict(
        {
            "paths": {"read_allow": [], "write_allow": [], "deny": []},
            "shell": {
                "prefix_allow": ["python", sys.executable.split("\\")[-1].split("/")[-1]],
                "deny_regex": [r"\bsudo\b", r"rm\s+-rf\s+/"],
            },
        }
    )


def test_allowed_command_runs(allowlist: Allowlist) -> None:
    out = shell_run(allowlist, f'python -c "print(2+2)"', timeout=10)
    assert out["ok"] is True
    assert "4" in out["stdout"]


def test_disallowed_command_raises(allowlist: Allowlist) -> None:
    with pytest.raises(AllowlistError):
        shell_run(allowlist, "cat /etc/passwd")


def test_deny_regex_blocks(allowlist: Allowlist) -> None:
    with pytest.raises(AllowlistError):
        shell_run(allowlist, "python -c sudo")


def test_timeout_returns_error(allowlist: Allowlist) -> None:
    out = shell_run(allowlist, 'python -c "import time; time.sleep(5)"', timeout=1)
    assert out["ok"] is False
    assert "timeout" in out["error"].lower()
