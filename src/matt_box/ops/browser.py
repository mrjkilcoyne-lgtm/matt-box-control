"""Browser bridge.

Two modes:
1. If Claude-in-Chrome MCP is reachable on Matt's box, delegate browser.open
   and browser.query through it.
2. Otherwise, browser.open uses `start ""` to open the URL in the default
   browser (no DOM access). browser.query returns "not-installed".
"""

from __future__ import annotations

import os
import socket
import subprocess
from typing import Any
from urllib.parse import urlparse

# Claude-in-Chrome MCP default local port (overridable by env)
CIC_HOST = os.environ.get("CLAUDE_IN_CHROME_HOST", "127.0.0.1")
CIC_PORT = int(os.environ.get("CLAUDE_IN_CHROME_PORT", "12434"))


def _claude_in_chrome_active(timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((CIC_HOST, CIC_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def _safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False
    return True


def browser_open(url: str) -> dict[str, Any]:
    if not _safe_url(url):
        return {"ok": False, "error": "url must be http(s) with a host"}
    if _claude_in_chrome_active():
        return {
            "ok": True,
            "delegate": "claude-in-chrome",
            "note": "delegate transport not wired in v1; use Claude-in-Chrome MCP directly for DOM ops",
            "url": url,
        }
    # native fallback — opens in default browser, no DOM access
    try:
        # Windows: `start "" "<url>"` via cmd.exe
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", url],
            shell=False,
            close_fds=True,
        )
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "delegate": "native",
        "note": "URL opened in default browser, no DOM access",
        "url": url,
    }


def browser_query(url: str, selector: str | None = None) -> dict[str, Any]:
    if _claude_in_chrome_active():
        return {
            "ok": False,
            "delegate": "claude-in-chrome",
            "error": "delegate transport not wired in v1 — call Claude-in-Chrome MCP directly",
            "url": url,
            "selector": selector,
        }
    return {
        "ok": False,
        "delegate": "native",
        "error": "not-installed",
        "note": "Claude-in-Chrome MCP not reachable; native mode cannot query DOM",
    }
