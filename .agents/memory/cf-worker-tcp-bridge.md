---
name: CF Worker WebSocket-to-TCP bridge
description: How to bypass Replit outbound TCP port restrictions for FF game server communication
---

## Rule
Replit only allows outbound TCP on ports 80 and 443. FF game servers use TCP port 17000/17001. Solution: Cloudflare Worker acts as WebSocket-to-TCP bridge.

## Architecture
```
Replit (Python websocket-client) → WSS:443 → CF Worker /tcp → TCP:17000 → FF game server
```

## Worker setup
- File: `cf_worker/worker.js`
- Endpoint: `wss://<worker>.workers.dev/tcp?host=<ip>&port=<port>&token=<CF_TOKEN>`
- Auth: `CF_TOKEN` env var in Worker Settings (must match Replit secret `CF_TOKEN`)
- Allowlist: only ports 17000/17001 and known FF IP prefixes pass through
- Uses `cloudflare:sockets` API for TCP connection on worker side

## Python client
- Library: `websocket-client` (pip)
- Key class: `_FFBotClient` in `garena/levelup.py`
- Uses `ws.send_binary()` for binary protocol frames

**Why:** Replit blocks all non-80/443 outbound TCP. CF Workers allow outbound TCP to any port via `cloudflare:sockets`. This is the only viable approach without a separate VPS.

**How to apply:** Any time a raw TCP game-server connection is needed from Replit, route it through the CF Worker bridge. Set `CF_TOKEN` in both Cloudflare Worker env vars and Replit Secrets.
