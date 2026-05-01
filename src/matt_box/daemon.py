"""matt-box-control daemon — FastAPI service.

Runs as a Windows service. Binds 127.0.0.1 + Tailscale interface only.
Audit-first ordering. Bearer auth. Kill-switch enforced.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from . import __version__
from .allowlist import Allowlist, AllowlistError
from .audit import Audit
from .auth import PLACEHOLDER, make_bearer_dep
from .ops import browser, filesystem, kill_switch, shell

log = logging.getLogger("matt_box")
logging.basicConfig(level=os.environ.get("MATT_BOX_LOG_LEVEL", "INFO"))


# --- config -----------------------------------------------------------------

DEFAULT_CONFIG_PATH = Path(os.path.expandvars(r"%APPDATA%\matt-box\config.yaml"))


class Config:
    def __init__(self, raw: dict[str, Any], path: Path) -> None:
        self.path = path
        self.raw = raw
        self.bearer: str = raw.get("bearer", "")
        self.bind_host: str = raw.get("bind_host", "127.0.0.1")
        self.bind_port: int = int(raw.get("bind_port", 8443))
        self.audit_dir: Path = Path(
            raw.get("audit_dir", str(Path.home() / ".tardai" / "audit"))
        )
        self.artefact_surface_url: str | None = raw.get("artefact_surface_url")
        self.artefact_surface_bearer: str | None = raw.get("artefact_surface_bearer")
        self.tool_bus_url: str | None = raw.get("tool_bus_url")
        self.kill_switch_path: str | None = raw.get("kill_switch_path")
        self.allowlist = Allowlist.from_dict(raw.get("allowlist", {}) or {})

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> "Config":
        if not path.exists():
            raise SystemExit(
                f"FATAL: config file not found at {path}. "
                f"Copy config.example.yaml and edit it."
            )
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cfg = cls(raw, path)
        if not cfg.bearer or cfg.bearer == PLACEHOLDER:
            raise SystemExit(
                f"FATAL: bearer in {path} is missing or placeholder. "
                f"Set the real bearer before starting."
            )
        return cfg


# --- pydantic schemas -------------------------------------------------------


class InvokeArgs(BaseModel):
    action: str = Field(
        ..., pattern=r"^(fs\.read|fs\.write|fs\.list|fs\.search|shell\.run|browser\.open|browser\.query)$"
    )
    args: dict[str, Any] = Field(default_factory=dict)
    caller: str = Field(default="unknown", description="Identifier of the calling realiser")


class InvokeResult(BaseModel):
    status: str  # ok|blocked|paused|error
    result: dict[str, Any] = Field(default_factory=dict)
    audit_id: str


# --- app factory ------------------------------------------------------------


def create_app(config: Config) -> FastAPI:
    app = FastAPI(
        title="matt-box-control",
        version=__version__,
        description="TARDAI sovereign's hands on Matt's Windows machine.",
    )

    audit = Audit(
        log_dir=config.audit_dir,
        artefact_surface_url=config.artefact_surface_url,
        artefact_surface_bearer=config.artefact_surface_bearer,
    )
    ks = kill_switch.KillSwitch(config.kill_switch_path)

    bearer_dep = make_bearer_dep(lambda: config.bearer)

    # ---- public health -----------------------------------------------------

    @app.get("/health")
    async def health() -> dict[str, Any]:
        if ks.is_paused():
            return {"status": "paused", "version": __version__}
        return {"status": "ok", "version": __version__}

    # ---- plan (no execution) ----------------------------------------------

    @app.post("/plan", dependencies=[Depends(bearer_dep)])
    async def plan(body: InvokeArgs) -> dict[str, Any]:
        try:
            _dry_check(config.allowlist, body)
        except AllowlistError as exc:
            return {"status": "blocked", "reason": str(exc), "action": body.action, "args": body.args}
        return {"status": "would_execute", "action": body.action, "args": body.args}

    # ---- invoke -----------------------------------------------------------

    @app.post("/invoke", response_model=InvokeResult, dependencies=[Depends(bearer_dep)])
    async def invoke(body: InvokeArgs, request: Request) -> InvokeResult:
        # 1. kill-switch
        if ks.is_paused():
            rec = audit.begin(body.action, body.args, body.caller)
            audit.finalise(rec, outcome="paused", error="kill-switch active")
            return InvokeResult(status="paused", result={"reason": "kill-switch active"}, audit_id=rec.audit_id)

        # 2. AUDIT-FIRST — record before running
        rec = audit.begin(body.action, body.args, body.caller)
        start = time.perf_counter()

        try:
            result = _dispatch(config.allowlist, body)
            duration_ms = (time.perf_counter() - start) * 1000
            audit.finalise(rec, outcome="ok", duration_ms=duration_ms)
            return InvokeResult(status="ok", result=result, audit_id=rec.audit_id)
        except AllowlistError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            audit.finalise(rec, outcome="blocked", error=str(exc), duration_ms=duration_ms)
            return InvokeResult(status="blocked", result={"reason": str(exc)}, audit_id=rec.audit_id)
        except Exception as exc:  # noqa: BLE001 — top-level safety net
            duration_ms = (time.perf_counter() - start) * 1000
            log.exception("op failed: %s", body.action)
            audit.finalise(rec, outcome="error", error=str(exc), duration_ms=duration_ms)
            return InvokeResult(status="error", result={"reason": str(exc)}, audit_id=rec.audit_id)

    # ---- audit fetch ------------------------------------------------------

    @app.get("/audit/{audit_id}", dependencies=[Depends(bearer_dep)])
    async def get_audit(audit_id: str) -> dict[str, Any]:
        rec = audit.fetch(audit_id)
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no audit record {audit_id}")
        return {
            "audit_id": rec.audit_id,
            "timestamp": rec.timestamp,
            "action": rec.action,
            "args": rec.args,
            "caller": rec.caller,
            "outcome": rec.outcome,
            "error": rec.error,
            "duration_ms": rec.duration_ms,
        }

    # ---- admin ------------------------------------------------------------

    @app.post("/admin/pause", dependencies=[Depends(bearer_dep)])
    async def admin_pause(reason: str = "admin endpoint") -> dict[str, Any]:
        ks.pause(reason)
        return {"status": "paused", "path": str(ks.path)}

    @app.post("/admin/resume", dependencies=[Depends(bearer_dep)])
    async def admin_resume() -> dict[str, Any]:
        ks.resume()
        return {"status": "ok", "path": str(ks.path)}

    @app.post("/admin/register-with-bus", dependencies=[Depends(bearer_dep)])
    async def admin_register() -> dict[str, Any]:
        return _register_with_bus(config)

    # startup hook — try to register with bus (best effort)
    @app.on_event("startup")
    async def _on_startup() -> None:
        if config.tool_bus_url:
            try:
                _register_with_bus(config)
            except Exception as exc:  # noqa: BLE001
                log.warning("tool bus registration failed at startup: %s", exc)

    return app


# --- dispatch ---------------------------------------------------------------


def _dry_check(allowlist: Allowlist, body: InvokeArgs) -> None:
    """Run the same allowlist checks dispatch would, without executing."""
    a = body.args
    if body.action == "fs.read":
        from .allowlist import check_path

        check_path(allowlist, a["path"], write=False)
    elif body.action == "fs.write":
        from .allowlist import check_path

        check_path(allowlist, a["path"], write=True)
    elif body.action in ("fs.list", "fs.search"):
        from .allowlist import check_path

        check_path(allowlist, a["path"], write=False)
    elif body.action == "shell.run":
        from .allowlist import check_command

        check_command(allowlist, a["command"])
    elif body.action in ("browser.open", "browser.query"):
        # browser ops have their own internal validation
        return
    else:
        raise AllowlistError(f"unknown action: {body.action}")


def _dispatch(allowlist: Allowlist, body: InvokeArgs) -> dict[str, Any]:
    a = body.args
    if body.action == "fs.read":
        return filesystem.fs_read(allowlist, a["path"], max_bytes=a.get("max_bytes", filesystem.MAX_READ_BYTES))
    if body.action == "fs.write":
        return filesystem.fs_write(
            allowlist,
            a["path"],
            a["content"],
            create_dirs=a.get("create_dirs", True),
            encoding=a.get("encoding", "utf-8"),
        )
    if body.action == "fs.list":
        return filesystem.fs_list(allowlist, a["path"], glob=a.get("glob", "*"))
    if body.action == "fs.search":
        return filesystem.fs_search(
            allowlist,
            a["path"],
            a["pattern"],
            file_glob=a.get("file_glob", "*"),
            case_insensitive=a.get("case_insensitive", True),
            max_matches=a.get("max_matches", 200),
        )
    if body.action == "shell.run":
        return shell.shell_run(
            allowlist,
            a["command"],
            cwd=a.get("cwd"),
            timeout=a.get("timeout", shell.DEFAULT_TIMEOUT),
            env_extra=a.get("env_extra"),
        )
    if body.action == "browser.open":
        return browser.browser_open(a["url"])
    if body.action == "browser.query":
        return browser.browser_query(a["url"], a.get("selector"))
    raise AllowlistError(f"unknown action: {body.action}")


# --- tool bus registration --------------------------------------------------


def _register_with_bus(config: Config) -> dict[str, Any]:
    if not config.tool_bus_url:
        return {"ok": False, "error": "tool_bus_url not set in config"}
    manifest_path = Path(__file__).parent / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    try:
        resp = httpx.post(
            config.tool_bus_url.rstrip("/") + "/api/tools/register",
            json=manifest,
            timeout=10.0,
        )
        resp.raise_for_status()
        return {"ok": True, "status_code": resp.status_code, "body": resp.text[:500]}
    except httpx.HTTPError as exc:
        log.warning("tool-bus register failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# --- entrypoint -------------------------------------------------------------


def main() -> None:
    config_path = Path(os.environ.get("MATT_BOX_CONFIG", str(DEFAULT_CONFIG_PATH)))
    config = Config.load(config_path)
    app = create_app(config)
    log.info("matt-box-control v%s starting on %s:%d", __version__, config.bind_host, config.bind_port)
    uvicorn.run(
        app,
        host=config.bind_host,
        port=config.bind_port,
        log_level=os.environ.get("MATT_BOX_LOG_LEVEL", "info").lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
