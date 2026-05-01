"""Audit log. Local jsonl + push to artefact surface.

Audit-first ordering: audit record is written BEFORE the operation runs.
If the audit write fails, the operation is refused.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx


@dataclass
class AuditRecord:
    audit_id: str
    timestamp: str
    action: str
    args: dict[str, Any]
    caller: str
    outcome: str = "pending"  # pending|ok|blocked|error|paused
    error: str | None = None
    duration_ms: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Audit:
    def __init__(
        self,
        log_dir: str | os.PathLike,
        artefact_surface_url: str | None = None,
        artefact_surface_bearer: str | None = None,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.artefact_surface_url = artefact_surface_url
        self.artefact_surface_bearer = artefact_surface_bearer
        self._lock = threading.Lock()

    def _today_path(self) -> Path:
        date = dt.datetime.utcnow().strftime("%Y-%m-%d")
        return self.log_dir / f"{date}.jsonl"

    def begin(self, action: str, args: dict[str, Any], caller: str) -> AuditRecord:
        rec = AuditRecord(
            audit_id=secrets.token_hex(8),
            timestamp=dt.datetime.utcnow().isoformat() + "Z",
            action=action,
            args=_sanitise_args(args),
            caller=caller,
        )
        # AUDIT-FIRST: write before the operation runs
        self._write(rec)
        return rec

    def finalise(
        self,
        rec: AuditRecord,
        *,
        outcome: str,
        error: str | None = None,
        duration_ms: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        rec.outcome = outcome
        rec.error = error
        rec.duration_ms = duration_ms
        if extra:
            rec.extra.update(extra)
        self._write(rec, suffix=".final")
        self._push(rec)

    def _write(self, rec: AuditRecord, suffix: str = "") -> None:
        line = json.dumps(asdict(rec), sort_keys=True) + "\n"
        path = self._today_path()
        if suffix:
            path = path.with_name(path.name + suffix)
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())

    def _push(self, rec: AuditRecord) -> None:
        if not self.artefact_surface_url:
            return
        try:
            headers = {}
            if self.artefact_surface_bearer:
                headers["Authorization"] = f"Bearer {self.artefact_surface_bearer}"
            httpx.post(
                self.artefact_surface_url,
                json=asdict(rec),
                headers=headers,
                timeout=5.0,
            )
        except Exception:
            # never let artefact-surface push failures block local audit
            pass

    def fetch(self, audit_id: str) -> AuditRecord | None:
        # naive scan of today's log; sufficient for v1
        for path in sorted(self.log_dir.glob("*.jsonl*"), reverse=True):
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("audit_id") == audit_id:
                        return AuditRecord(**{k: data.get(k) for k in AuditRecord.__annotations__})
            except OSError:
                continue
        return None


_SENSITIVE_KEYS = {"bearer", "token", "password", "secret", "authorization", "api_key"}


def _sanitise_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in args.items():
        if k.lower() in _SENSITIVE_KEYS:
            out[k] = "<redacted>"
        elif isinstance(v, dict):
            out[k] = _sanitise_args(v)
        else:
            out[k] = v
    return out
