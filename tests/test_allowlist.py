"""Allowlist enforcement tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from matt_box.allowlist import Allowlist, AllowlistError, check_command, check_path


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    (tmp_path / "allowed").mkdir()
    (tmp_path / "denied").mkdir()
    (tmp_path / "allowed" / "file.txt").write_text("hi")
    return tmp_path


@pytest.fixture
def allowlist(tmp_root: Path) -> Allowlist:
    return Allowlist.from_dict(
        {
            "paths": {
                "read_allow": [f"{tmp_root.as_posix()}/allowed/**"],
                "write_allow": [f"{tmp_root.as_posix()}/allowed/**"],
                "deny": [f"{tmp_root.as_posix()}/allowed/**/.git/**", "**/credentials*"],
            },
            "shell": {
                "prefix_allow": ["kubectl", "git", "echo"],
                "deny_regex": [r"rm\s+-rf\s+/", r"\bsudo\b"],
            },
        }
    )


def test_allowed_path_passes(allowlist: Allowlist, tmp_root: Path) -> None:
    p = check_path(allowlist, tmp_root / "allowed" / "file.txt", write=False)
    assert p.exists()


def test_denied_directory_blocked(allowlist: Allowlist, tmp_root: Path) -> None:
    with pytest.raises(AllowlistError):
        check_path(allowlist, tmp_root / "denied" / "file.txt", write=False)


def test_dotdot_cannot_escape(allowlist: Allowlist, tmp_root: Path) -> None:
    sneaky = tmp_root / "allowed" / ".." / "denied" / "file.txt"
    with pytest.raises(AllowlistError):
        check_path(allowlist, sneaky, write=False)


def test_deny_wins_over_allow(allowlist: Allowlist, tmp_root: Path) -> None:
    git_dir = tmp_root / "allowed" / "repo" / ".git"
    git_dir.mkdir(parents=True)
    config = git_dir / "config"
    config.write_text("[core]")
    with pytest.raises(AllowlistError, match="denied"):
        check_path(allowlist, config, write=False)


def test_credentials_pattern_denied(allowlist: Allowlist, tmp_root: Path) -> None:
    creds = tmp_root / "allowed" / "credentials.json"
    creds.write_text("{}")
    with pytest.raises(AllowlistError, match="denied"):
        check_path(allowlist, creds, write=False)


def test_write_to_read_only_blocked() -> None:
    al = Allowlist.from_dict(
        {
            "paths": {
                "read_allow": ["/tmp/**"],
                "write_allow": [],  # nothing writable
                "deny": [],
            },
            "shell": {"prefix_allow": [], "deny_regex": []},
        }
    )
    with pytest.raises(AllowlistError, match="write allowlist"):
        check_path(al, "/tmp/foo", write=True)


def test_shell_allowed_prefix(allowlist: Allowlist) -> None:
    assert check_command(allowlist, "kubectl get pods -n tardai") == "kubectl get pods -n tardai"
    assert check_command(allowlist, "git status").startswith("git")


def test_shell_unknown_prefix_blocked(allowlist: Allowlist) -> None:
    with pytest.raises(AllowlistError, match="prefix"):
        check_command(allowlist, "cat /etc/passwd")


def test_shell_deny_regex_wins(allowlist: Allowlist) -> None:
    # "git" is allowed prefix — but deny regex catches sudo even inside a wrapper
    al = Allowlist.from_dict(
        {
            "paths": {"read_allow": [], "write_allow": [], "deny": []},
            "shell": {
                "prefix_allow": ["echo"],
                "deny_regex": [r"\bsudo\b"],
            },
        }
    )
    with pytest.raises(AllowlistError, match="deny regex"):
        check_command(al, "echo hi && sudo rm")


def test_empty_command_rejected(allowlist: Allowlist) -> None:
    with pytest.raises(AllowlistError):
        check_command(allowlist, "")
    with pytest.raises(AllowlistError):
        check_command(allowlist, "   ")


def test_prefix_must_match_word_boundary(allowlist: Allowlist) -> None:
    # 'gitsomething' should NOT match 'git' prefix
    with pytest.raises(AllowlistError):
        check_command(allowlist, "gitsomething --foo")
