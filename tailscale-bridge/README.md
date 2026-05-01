# Tailscale bridge

The daemon binds `127.0.0.1:8443`. Tailscale exposes it to the rest of the
tailnet (which includes the `tardai-sovereign` cluster node).

## Recommended path: `tailscale serve`

This is the cleanest option. Tailscale terminates TLS for you with a real
LetsEncrypt cert via the `*.ts.net` MagicDNS name, no self-signed mess.

```powershell
# On Matt's box (mattkilcoyne):
tailscale serve https / http://127.0.0.1:8443

# Verify:
tailscale serve status
# → https://mattkilcoyne.<tailnet>.ts.net  →  http://127.0.0.1:8443
```

The cluster pod can then call:

```
https://mattkilcoyne.<tailnet>.ts.net/invoke
```

## Alternative: tailnet IP only

If `tailscale serve` is unavailable, expose the daemon to the tailnet by
binding to the Tailscale interface IP directly. Edit `config.yaml`:

```yaml
bind_host: 0.0.0.0      # binds all interfaces — Tailscale ACLs gate access
bind_port: 8443
```

**This requires Tailscale ACLs to be tight.** Ensure only the
`tag:tardai-sovereign` (or your equivalent) can reach mattkilcoyne on 8443.
Example ACL fragment:

```
"acls": [
  { "action": "accept",
    "src":    ["tag:tardai-sovereign"],
    "dst":    ["mattkilcoyne:8443"] }
]
```

## Cluster-side: Tool Bus reaches the daemon

The Tool Bus deployment needs the Tailscale sidecar so it shares the tailnet.
The manifest already lists the endpoint as
`https://mattkilcoyne.<tailnet>.ts.net:8443/invoke` — replace
`<tailnet>` with Matt's actual tailnet name when registering.

## Health check

From the cluster:

```bash
kubectl run -n tardai --rm -it curl --image=curlimages/curl --restart=Never -- \
  curl -k -H "Authorization: Bearer $BEARER" https://mattkilcoyne.<tailnet>.ts.net:8443/health
```

Expected: `{"status":"ok","version":"0.1.0"}` (or `paused` if PAUSE file present).
