"""Allowlist + denylist enforcement for paths and shell commands.

Hard rules:
- paths are resolved (`.resolve()`) before checking, so `..` cannot escape
- symlinks are rejected
- match is glob-style via fnmatch on the normalised, case-folded posix path
- deny patterns ALWAYS win over allow patterns
- shell commands match by *prefix* on the first token (or first two tokens
  for things like `git push`, `kubectl apply`)
- shell deny is regex against the full command line
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PathPolicy:
    read_allow: list[str] = field(default_factory=list)
    write_allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
    require_explicit_confirm: list[str] = field(default_factory=list)


@dataclass
class ShellPolicy:
    prefix_allow: list[str] = field(default_factory=list)
    deny_regex: list[str] = field(default_factory=list)


@dataclass
class Allowlist:
    paths: PathPolicy
    shell: ShellPolicy

    @classmethod
    def from_dict(cls, raw: dict) -> "Allowlist":
        p = raw.get("paths", {}) or {}
        s = raw.get("shell", {}) or {}
        return cls(
            paths=PathPolicy(
                read_allow=list(p.get("read_allow", []) or []),
                write_allow=list(p.get("write_allow", []) or []),
                deny=list(p.get("deny", []) or []),
                require_explicit_confirm=list(p.get("require_explicit_confirm", []) or []),
            ),
            shell=ShellPolicy(
                prefix_allow=list(s.get("prefix_allow", []) or []),
                deny_regex=list(s.get("deny_regex", []) or []),
            ),
        )


def _normalise(p: str | os.PathLike) -> tuple[Path, str]:
    """Return (resolved Path, posix-style case-folded string for matching)."""
    path = Path(os.path.expandvars(os.path.expanduser(str(p))))
    resolved = path.resolve(strict=False)
    return resolved, resolved.as_posix().casefold()


def _matches_any(needle: str, patterns: list[str]) -> bool:
    needle_cf = needle.casefold()
    for pat in patterns:
        pat_norm = os.path.expandvars(pat).replace("\\", "/").casefold()
        if fnmatch.fnmatchcase(needle_cf, pat_norm):
            return True
        # also try matching against trailing-slash normalised form
        if fnmatch.fnmatchcase(needle_cf + "/", pat_norm):
            return True
    return False


class AllowlistError(Exception):
    """Raised when an operation is blocked by allowlist policy."""


def check_path(
    allowlist: Allowlist,
    path: str | os.PathLike,
    *,
    write: bool,
    follow_symlinks: bool = False,
) -> Path:
    """Resolve and validate a path. Returns resolved Path or raises.

    - write=True checks write_allow; write=False checks read_allow
    - symlinks rejected unless follow_symlinks=True (never recommended)
    - deny patterns checked first and always win
    """
    resolved, key = _normalise(path)

    # Symlink rejection — examine the *original* path for any symlink in chain
    original = Path(os.path.expandvars(os.path.expanduser(str(path))))
    if not follow_symlinks:
        cur = original
        while True:
            if cur.is_symlink():
                raise AllowlistError(f"symlink rejected: {cur}")
            parent = cur.parent
            if parent == cur:
                break
            cur = parent

    if _matches_any(key, allowlist.paths.deny):
        raise AllowlistError(f"path denied by policy: {resolved}")

    pool = allowlist.paths.write_allow if write else allowlist.paths.read_allow
    if not _matches_any(key, pool):
        kind = "write" if write else "read"
        raise AllowlistError(f"path not in {kind} allowlist: {resolved}")

    return resolved


def requires_explicit_confirm(allowlist: Allowlist, path: str | os.PathLike) -> bool:
    _, key = _normalise(path)
    return _matches_any(key, allowlist.paths.require_explicit_confirm)


def check_command(allowlist: Allowlist, cmd: str) -> str:
    """Validate a shell command. Returns the command if allowed, else raises."""
    if not cmd or not cmd.strip():
        raise AllowlistError("empty command")

    stripped = cmd.strip()

    for pat in allowlist.shell.deny_regex:
        try:
            if re.search(pat, stripped):
                raise AllowlistError(f"command matches deny regex: {pat!r}")
        except re.error as exc:
            raise AllowlistError(f"invalid deny regex {pat!r}: {exc}") from exc

    for prefix in allowlist.shell.prefix_allow:
        prefix_norm = prefix.strip().rstrip(".").rstrip()
        if not prefix_norm:
            continue
        # prefix must match at start, followed by whitespace or end
        if stripped == prefix_norm or stripped.startswith(prefix_norm + " "):
            return stripped

    raise AllowlistError(f"command does not match any allowed prefix: {stripped.split()[0]!r}")
