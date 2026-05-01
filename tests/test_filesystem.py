"""Filesystem op tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from matt_box.allowlist import Allowlist, AllowlistError
from matt_box.ops.filesystem import fs_list, fs_read, fs_search, fs_write


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Allowlist]:
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "a.txt").write_text("hello world")
    (tmp_path / "ok" / "b.txt").write_text("foo bar baz")
    (tmp_path / "ok" / "sub").mkdir()
    (tmp_path / "ok" / "sub" / "c.txt").write_text("matched needle here")
    (tmp_path / "blocked").mkdir()
    (tmp_path / "blocked" / "secret.txt").write_text("nope")

    al = Allowlist.from_dict(
        {
            "paths": {
                "read_allow": [f"{tmp_path.as_posix()}/ok/**"],
                "write_allow": [f"{tmp_path.as_posix()}/ok/**"],
                "deny": [],
            },
            "shell": {"prefix_allow": [], "deny_regex": []},
        }
    )
    return tmp_path, al


def test_read_in_allow(workspace: tuple[Path, Allowlist]) -> None:
    root, al = workspace
    out = fs_read(al, str(root / "ok" / "a.txt"))
    assert out["ok"] is True
    assert out["text"] == "hello world"


def test_read_outside_allow_raises(workspace: tuple[Path, Allowlist]) -> None:
    root, al = workspace
    with pytest.raises(AllowlistError):
        fs_read(al, str(root / "blocked" / "secret.txt"))


def test_write_creates_file(workspace: tuple[Path, Allowlist]) -> None:
    root, al = workspace
    out = fs_write(al, str(root / "ok" / "new.txt"), "fresh")
    assert out["ok"] is True
    assert (root / "ok" / "new.txt").read_text() == "fresh"


def test_write_outside_allow_raises(workspace: tuple[Path, Allowlist]) -> None:
    root, al = workspace
    with pytest.raises(AllowlistError):
        fs_write(al, str(root / "blocked" / "x.txt"), "no")


def test_list_directory(workspace: tuple[Path, Allowlist]) -> None:
    root, al = workspace
    out = fs_list(al, str(root / "ok"))
    assert out["ok"] is True
    names = {e["name"] for e in out["entries"]}
    assert {"a.txt", "b.txt", "sub"} <= names


def test_search_finds_match(workspace: tuple[Path, Allowlist]) -> None:
    root, al = workspace
    out = fs_search(al, str(root / "ok"), "needle")
    assert out["ok"] is True
    assert any("c.txt" in m["file"] for m in out["matches"])


def test_search_outside_allow_raises(workspace: tuple[Path, Allowlist]) -> None:
    root, al = workspace
    with pytest.raises(AllowlistError):
        fs_search(al, str(root / "blocked"), "anything")
