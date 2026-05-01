"""Filesystem operations — read, write, list, search. Allowlist-enforced."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from ..allowlist import Allowlist, check_path

MAX_READ_BYTES = 5 * 1024 * 1024  # 5 MiB
MAX_WRITE_BYTES = 5 * 1024 * 1024
MAX_SEARCH_FILES = 5000


def fs_read(allowlist: Allowlist, path: str, max_bytes: int = MAX_READ_BYTES) -> dict[str, Any]:
    resolved = check_path(allowlist, path, write=False)
    if not resolved.is_file():
        return {"ok": False, "error": "not a file", "path": str(resolved)}
    size = resolved.stat().st_size
    if size > max_bytes:
        return {"ok": False, "error": f"file too large ({size} > {max_bytes})", "path": str(resolved)}
    data = resolved.read_bytes()
    try:
        text = data.decode("utf-8")
        return {"ok": True, "path": str(resolved), "size": size, "text": text, "encoding": "utf-8"}
    except UnicodeDecodeError:
        import base64

        return {
            "ok": True,
            "path": str(resolved),
            "size": size,
            "base64": base64.b64encode(data).decode("ascii"),
            "encoding": "base64",
        }


def fs_write(
    allowlist: Allowlist,
    path: str,
    content: str,
    *,
    create_dirs: bool = True,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    if len(content.encode(encoding, errors="ignore")) > MAX_WRITE_BYTES:
        return {"ok": False, "error": "content too large"}
    resolved = check_path(allowlist, path, write=True)
    if create_dirs:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding=encoding)
    return {"ok": True, "path": str(resolved), "bytes_written": len(content.encode(encoding))}


def fs_list(allowlist: Allowlist, path: str, *, glob: str = "*") -> dict[str, Any]:
    resolved = check_path(allowlist, path, write=False)
    if not resolved.is_dir():
        return {"ok": False, "error": "not a directory", "path": str(resolved)}
    entries = []
    for p in sorted(resolved.glob(glob)):
        try:
            stat = p.stat()
            entries.append(
                {
                    "name": p.name,
                    "path": str(p),
                    "is_dir": p.is_dir(),
                    "size": stat.st_size if p.is_file() else None,
                    "mtime": stat.st_mtime,
                }
            )
        except OSError:
            continue
    return {"ok": True, "path": str(resolved), "entries": entries}


def fs_search(
    allowlist: Allowlist,
    path: str,
    pattern: str,
    *,
    file_glob: str = "*",
    case_insensitive: bool = True,
    max_matches: int = 200,
) -> dict[str, Any]:
    """Substring search across allowlisted files. Not regex (yet)."""
    resolved = check_path(allowlist, path, write=False)
    if not resolved.is_dir():
        return {"ok": False, "error": "not a directory"}
    needle = pattern.lower() if case_insensitive else pattern
    matches = []
    files_seen = 0
    for p in resolved.rglob(file_glob):
        if files_seen >= MAX_SEARCH_FILES:
            break
        if not p.is_file():
            continue
        files_seen += 1
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hay = text.lower() if case_insensitive else text
        if needle in hay:
            # find line numbers
            for i, line in enumerate(text.splitlines(), start=1):
                hl = line.lower() if case_insensitive else line
                if needle in hl:
                    matches.append({"file": str(p), "line": i, "text": line[:200]})
                    if len(matches) >= max_matches:
                        return {"ok": True, "truncated": True, "matches": matches}
    return {"ok": True, "truncated": False, "matches": matches, "files_scanned": files_seen}
