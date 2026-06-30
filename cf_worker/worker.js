/**
 * Cloudflare Worker — WebSocket-to-TCP bridge for FF game server
 *
 * WebSocket bridge (authed):
 *   GET /tcp?host=<ip>&port=<port>&token=<CF_TOKEN>
 *   Upgrade: websocket
 *
 * HTTP proxy (existing, unchanged):
 *   GET /?url=https://...
 *
 * Set CF_TOKEN environment variable in Cloudflare Worker settings.
 * Only FF game-server IPs / ports 17000-17001 are allowed through the bridge.
 */

// ── Allowed destinations (whitelist) ────────────────────────────────────────
const ALLOWED_PORTS = new Set([17000, 17001]);
const ALLOWED_HOST_SUFFIXES = [
  ".freefiremobile.com",
  ".stronghold.freefiremobile.com",
];
// Direct IPs for known FF regions (from tp_url)
const ALLOWED_IP_PREFIXES = [
  "34.126.", "34.87.", "35.185.",   // ID/SG (Asia Pacific)
  "13.251.",                         // IND
  "18.228.",                         // BR
  "35.205.",                         // EUROPE
];

function isAllowedHost(host) {
  for (const s of ALLOWED_HOST_SUFFIXES) {
    if (host.endsWith(s)) return true;
  }
  for (const p of ALLOWED_IP_PREFIXES) {
    if (host.startsWith(p)) return true;
  }
  return false;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // ── WebSocket-to-TCP bridge ──────────────────────────────────────────────
    if (url.pathname === "/tcp") {

      // Auth check — requires ?token= matching CF_TOKEN secret
      const token = url.searchParams.get("token") || "";
      if (!env.CF_TOKEN || token !== env.CF_TOKEN) {
        return new Response("Unauthorized", { status: 401 });
      }

      const host = url.searchParams.get("host") || "";
      const port = parseInt(url.searchParams.get("port") || "0", 10);

      if (!host || !port) {
        return new Response("Missing ?host= and ?port=", { status: 400 });
      }
      if (!ALLOWED_PORTS.has(port)) {
        return new Response(`Port ${port} not allowed`, { status: 403 });
      }
      if (!isAllowedHost(host)) {
        return new Response(`Host ${host} not allowed`, { status: 403 });
      }

      // Must be a WebSocket upgrade
      if (request.headers.get("Upgrade") !== "websocket") {
        return new Response("WebSocket upgrade required", { status: 426 });
      }

      const [client, server] = Object.values(new WebSocketPair());
      server.accept();

      // Open TCP to game server
      let tcpConn;
      try {
        const { connect } = await import("cloudflare:sockets");
        tcpConn = connect({ hostname: host, port });
      } catch (e) {
        server.close(1011, `TCP connect failed: ${e.message}`);
        return new Response(null, { status: 101, webSocket: client });
      }

      const writer = tcpConn.writable.getWriter();
      const reader = tcpConn.readable.getReader();

      // WebSocket → TCP
      server.addEventListener("message", async (evt) => {
        try {
          // Forward exact bytes regardless of ArrayBuffer view offset/length
          let data;
          if (evt.data instanceof ArrayBuffer) {
            data = new Uint8Array(evt.data);
          } else if (ArrayBuffer.isView(evt.data)) {
            data = new Uint8Array(evt.data.buffer, evt.data.byteOffset, evt.data.byteLength);
          } else {
            data = new TextEncoder().encode(evt.data);
          }
          await writer.write(data);
        } catch (_) {}
      });

      server.addEventListener("close", () => {
        try { writer.close(); } catch (_) {}
      });

      // TCP → WebSocket (background stream)
      (async () => {
        try {
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            if (server.readyState === 1 /* OPEN */) {
              // Send exact chunk — slice to avoid sending whole backing buffer
              const chunk = value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength);
              server.send(chunk);
            }
          }
        } catch (_) {}
        try { server.close(1000, "TCP closed"); } catch (_) {}
      })();

      return new Response(null, { status: 101, webSocket: client });
    }

    // ── HTTP proxy (existing) ────────────────────────────────────────────────
    const target = url.searchParams.get("url");
    if (!target) {
      return new Response(
        "Silakan tambahkan parameter ?url= di akhir URL. Contoh: ?url=https://google.com",
        { status: 200, headers: { "Content-Type": "text/plain; charset=UTF-8" } }
      );
    }

    try {
      const resp = await fetch(target, {
        method:  request.method,
        headers: request.headers,
        body:    request.method !== "GET" && request.method !== "HEAD"
                   ? request.body
                   : undefined,
      });
      return new Response(resp.body, {
        status:  resp.status,
        headers: resp.headers,
      });
    } catch (e) {
      return new Response(`Proxy error: ${e.message}`, { status: 502 });
    }
  },
};
