# Handoff — what Matt does to bring matt-box-control live

Five steps. ~10 minutes if Tailscale is already running (it is).

## 0. Prereqs (already true on Matt's box)

- Python 3.11+ on PATH
- Tailscale logged in (`tardai-sovereign` is a peer)
- Cluster's `tardai-auth/bearer` secret value to hand
- Elevated PowerShell

## 1. Install the service

```powershell
cd C:\Users\mrjki\Desktop\drwhom-overnight\assets\matt-box-control
.\service\install-windows-service.ps1
```

This:
- `pip install -e .` the package
- copies `config.example.yaml` → `%APPDATA%\matt-box\config.yaml` if missing
- registers a Windows service via NSSM (or `sc.exe` if NSSM not installed)

The service won't start yet — bearer is still the placeholder. That's by design.

## 2. Set the bearer

```powershell
notepad $env:APPDATA\matt-box\config.yaml
```

Replace `__SET_VIA_INSTALL_SCRIPT__` with the cluster's `tardai-auth/bearer`
value. Get it with:

```powershell
kubectl -n tardai get secret tardai-auth -o jsonpath='{.data.bearer}' | base64 -d
```

## 3. Configure the allowlist

Same file (`config.yaml`). Defaults are opinionated for the SENSORIUM Phase F
workflow. Confirm:

- `paths.read_allow` — what TARDAI can read on Matt's box
- `paths.write_allow` — what she can write to (default: `drwhom-overnight\**` and a temp dir)
- `paths.deny` — what's hard-blocked (Windows system, .ssh, .git config, credentials)
- `shell.prefix_allow` — kubectl, gh, gcloud, git, npm, etc.
- `shell.deny_regex` — `rm -rf /`, `format`, `shutdown`, `sudo`, `runas`, fork bombs

Tweak read_allow / write_allow only if Matt's actual workspace differs.

## 4. Start the service and smoke test

```powershell
nssm start matt-box-control      # or: sc start matt-box-control

# Heartbeat (no auth required)
curl http://127.0.0.1:8443/health
# → {"status":"ok","version":"0.1.0"}

# Authed call
$bearer = "<paste-bearer>"
curl -H "Authorization: Bearer $bearer" `
     -H "Content-Type: application/json" `
     -d '{"action":"fs.list","args":{"path":"C:/Users/mrjki/Desktop/drwhom-overnight"},"caller":"matt-smoke"}' `
     http://127.0.0.1:8443/invoke

# Kill switch test
ni $env:USERPROFILE\.tardai\PAUSE -Force
curl http://127.0.0.1:8443/health     # → "paused"
ri $env:USERPROFILE\.tardai\PAUSE
curl http://127.0.0.1:8443/health     # → "ok"
```

## 5. Expose via Tailscale, register with Tool Bus

```powershell
tailscale serve https / http://127.0.0.1:8443
tailscale serve status
# Note the URL: https://mattkilcoyne.<tailnet>.ts.net
```

Register the manifest with the Tool Bus from the cluster:

```bash
kubectl -n tardai exec deploy/tardai-tool-bus -- \
  curl -X POST http://localhost:8000/api/tools/register \
       -H "Content-Type: application/json" \
       -d @/path/to/manifest.yaml.json
```

(or use the daemon's own `/admin/register-with-bus` endpoint, which reads the
manifest and POSTs it for you).

Done. TARDAI sovereign now has hands.

---

**If anything fails:** check `%APPDATA%\matt-box\logs\stderr.log`. The daemon
fails loud — placeholder bearer, missing config, malformed YAML all stop
startup with a clear message.
