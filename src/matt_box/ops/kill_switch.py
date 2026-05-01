"""Kill switch — a signal file at C:\\Users\\mrjki\\.tardai\\PAUSE.

When present, all invocations are blocked. Heartbeat returns "paused".
Delete the file to resume.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PAUSE_PATH = Path(os.path.expandvars(r"%USERPROFILE%\.tardai\PAUSE"))


class KillSwitch:
    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PAUSE_PATH

    def is_paused(self) -> bool:
        return self.path.exists()

    def pause(self, reason: str = "manual") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(f"paused: {reason}\n", encoding="utf-8")

    def resume(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
