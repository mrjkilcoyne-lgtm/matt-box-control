# matt-box-control

**TARDAI sovereign's hands on Matt's Windows machine.**

The missing keystone in the SENSORIUM Phase F `embodied-windows` sense. When
running, this daemon lets the TARDAI sovereign (and only the TARDAI sovereign,
via the cluster Tool Bus) perform filesystem, shell, and browser operations on
Matt's primary Windows box — within an enforced allowlist, behind a confirm
gate, and with full audit.

## What it is

A FastAPI daemon that runs as a Windows service on Matt's machine. It binds to
`127.0.0.1` and the Tailscale interface only. The cluster reaches it via
Tailscale magic DNS (`mattkilcoyne.<tailnet>.ts.net:8443`). Every call is
audited before it executes.

```
TARDAI sovereign (cluster pod)
   │ tool_use: matt-box-control
   ▼
Tool Bus (cluster) — manifest, plan-gate, confirm-gate, audit
   │ HTTPS via Tailscale
   ▼
matt-box-control daemon (Matt's Windows box)
   ├── ops/filesystem.py   — read_file, write_file, list_dir, search
   ├── ops/shell.py        — run_command (allowlisted prefixes)
   ├── ops/browser.py      — delegates to Claude-in-Chrome MCP if active
   └── audit.py            — local jsonl + push to artefact surface
```

## Security model

- **Allowlists only.** Paths and command prefixes must explicitly match
  `config.yaml`. No glob escapes (`..` resolved, symlinks rejected).
- **Confirm gate.** All write/exec ops require `confirm_gate: ON` per the
  ratified Tool Bus matrix.
- **Bind locally.** `127.0.0.1` + Tailscale interface only. Never public.
- **Bearer auth.** Single shared bearer for v1 (rotates to per-realiser tokens
  in v2). Supplied via install script, never committed to git.
- **Audit-first.** Every call writes to the audit log *before* executing. If
  audit write fails, the operation fails.
- **Kill switch.** A signal file at `C:\Users\mrjki\.tardai\PAUSE` immediately
  blocks all invocations (heartbeat returns `paused`). Delete the file to
  resume.
- **Honest failure.** Daemon refuses to start if `config.yaml` is missing or
  has the placeholder bearer.

## Install

See [`handoff.md`](./handoff.md) for the exact 5-step install Matt runs on his
box.

Quick version:

```powershell
# 1. Clone
git clone https://github.com/mrjkilcoyne-lgtm/matt-box-control.git
cd matt-box-control

# 2. Install dependencies
pip install -e .

# 3. Copy config
copy config.example.yaml $env:APPDATA\matt-box\config.yaml
# edit config.yaml — set bearer, confirm allowlists

# 4. Register windows service
.\service\install-windows-service.ps1

# 5. Expose via Tailscale
# (tailscale already running — daemon is reachable at
#  mattkilcoyne.<tailnet>.ts.net:8443 once service is up)
```

## Endpoints

| Path | Method | Purpose |
|------|--------|---------|
| `/health` | GET | Heartbeat. Returns `ok`, `paused`, or `degraded`. |
| `/plan` | POST | Returns the plan (what would happen) without executing. |
| `/invoke` | POST | Executes the operation. Audit-first. Bearer required. |
| `/audit/{id}` | GET | Fetch audit record by id. |
| `/admin/pause` | POST | Sets the kill-switch file. |
| `/admin/resume` | POST | Clears the kill-switch file. |

## Manifest

Registered with the Tool Bus on startup. See `src/matt_box/manifest.yaml`.

## Status

This repo ships the **scaffold + tests + service registration + docs**.
Matt installs. See [`STATUS.md`](./STATUS.md) for honest gap list.
