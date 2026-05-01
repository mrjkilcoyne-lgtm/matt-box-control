# STATUS — matt-box-control

Honesty rule: every gap surfaces here. Don't dress scaffold as finished work.

## Built (in this scaffold pass)

- [x] `pyproject.toml` — Python project layout, deps, scripts entry
- [x] `src/matt_box/daemon.py` — FastAPI app, `/health`, `/plan`, `/invoke`, `/audit`, `/admin` endpoints
- [x] `src/matt_box/auth.py` — bearer token validation (constant-time compare)
- [x] `src/matt_box/allowlist.py` — path + command-prefix enforcement; deny rules; symlink rejection; `..` resolution
- [x] `src/matt_box/audit.py` — local jsonl writer; artefact-surface POST; audit-first ordering
- [x] `src/matt_box/ops/filesystem.py` — `fs.read`, `fs.write`, `fs.list`, `fs.search`
- [x] `src/matt_box/ops/shell.py` — `shell.run` with prefix allowlist + regex deny
- [x] `src/matt_box/ops/browser.py` — `browser.open` (start ""), `browser.query` (returns "not-installed" unless Claude-in-Chrome MCP delegate path is wired)
- [x] `src/matt_box/ops/kill_switch.py` — PAUSE file check, set, clear
- [x] `src/matt_box/manifest.yaml` — Tool Bus plugin manifest
- [x] `config.example.yaml` — template with placeholder bearer
- [x] `service/install-windows-service.ps1` — uses NSSM if available, else falls back to `sc.exe`
- [x] `service/uninstall-windows-service.ps1`
- [x] `service/tardai-box-control.xml` — service descriptor (winsw-compatible)
- [x] `tailscale-bridge/README.md` — exposure instructions
- [x] `tests/test_allowlist.py`, `tests/test_filesystem.py`, `tests/test_shell.py` — unit tests
- [x] `.github/workflows/ci.yml` — pytest on push
- [x] `handoff.md` — 5-step install for Matt
- [x] `README.md`

## Not built / known gaps

- [ ] **mTLS.** v1 uses bearer over Tailscale. Tailscale already provides
      transport encryption + identity, so bearer is sufficient for v1. mTLS
      proper is a v2 item.
- [ ] **Per-realiser tokens.** v1 single shared bearer (`tardai-auth/bearer`).
      v2 will issue per-realiser tokens with claims.
- [ ] **Browser query delegation to Claude-in-Chrome MCP.** Scaffold detects
      whether the MCP socket is reachable and returns `not-installed` if not.
      Actual delegate-and-forward to the Chrome MCP transport is not wired —
      that requires the MCP SDK client and is out of v1 scope. `browser.open`
      works (uses `start ""`).
- [ ] **Tool Bus auto-registration.** Daemon will POST manifest to the Bus on
      startup *if* `tool_bus_url` is set in config. No retry/backoff loop yet
      — if Bus is down at startup, daemon logs and continues; manual
      re-registration via `/admin/register-with-bus`.
- [ ] **Rate limiting.** Manifest declares `30/min` but enforcement is
      stubbed (TODO in `daemon.py`). v2.
- [ ] **TLS certificate provisioning.** Service runs HTTP on `127.0.0.1:8443`
      by default. For Tailscale exposure, terminate TLS via the Tailscale
      sidecar's `tailscale serve` (recommended path documented in
      `tailscale-bridge/README.md`). Self-signed cert generation is not in
      this scaffold.
- [ ] **Service installation has not been run on Matt's box.** This is by
      design — Matt installs.
- [ ] **Smoke test against the live cluster.** Cannot run from this agent
      session.

## What Matt has to do (the 5 things)

1. **Install the service** — run `service\install-windows-service.ps1` from
   an elevated PowerShell.
2. **Set the bearer** — paste the value of the `tardai-auth/bearer` secret
   into `%APPDATA%\matt-box\config.yaml` (replacing the placeholder).
3. **Configure the allowlist** — open `%APPDATA%\matt-box\config.yaml`,
   confirm/edit paths and command prefixes for his actual workflow.
4. **Smoke test** — `curl -H "Authorization: Bearer $BEARER" https://127.0.0.1:8443/health`
   then a `fs.list` on his Desktop via `/invoke`.
5. **Expose via Tailscale** — `tailscale serve https / http://127.0.0.1:8443`
   so the cluster pod can reach it at `mattkilcoyne.<tailnet>.ts.net`.

Once those five are done, register the manifest with the Bus
(`POST /api/tools/register`) and TARDAI sovereign has hands.
