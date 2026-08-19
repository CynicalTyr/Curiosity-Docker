# HTTP API

Authenticated JSON on the sidecar. MCP tools in `examples/mcp_server.py` are a thin
client of this same API.

Both routes require header `X-API-Key` matching `USERNAME_DISCOVERY_API_KEY`.
Unless `USERNAME_DISCOVERY_ALLOWED_IPS=*` (bridge/Desktop mode), the TCP client
IP must be in the allowlist.

## `GET /health`

```json
{"status":"ok","mode":"fast"}
```

## `POST /scan`

Request:

```json
{"username":"handle","mode":"fast","top":25,"websites":"all"}
```

`mode` must be `fast`. `top` is clamped to 1–25.

Success:

```json
{
  "username": "handle",
  "hits": [
    {
      "platform": "instagram",
      "url": "https://example.invalid/handle",
      "site": "instagram",
      "confidence": "good"
    }
  ]
}
```

`hits` may be an empty list — that is a completed scan, not a transport failure.

| Status | Body | Meaning |
| ------ | ---- | ------- |
| 200 | `username` + `hits` | Scan finished |
| 400 | `unsupported_mode` / `missing_username` / `invalid_json` | Bad request |
| 403 | `forbidden` | Bad key or IP |
| 503 | `{"error":"busy"}` | Another scan holds the lock — wait for the next agent cycle |
| 500 | `scan_failed` | Analyzer exception |

## Client timeout vs scan timeout

The container caps each analyzer run with `USERNAME_DISCOVERY_SCAN_TIMEOUT`
(default **60s**). Agent HTTP/MCP clients should wait longer (default **120s**)
so a slow-but-finishing scan is not classified as a client timeout.

## Occupancy

One scan at a time. A second `/scan` waits up to **2s** for the lock, then
returns 503. Agents must **stop** the current handle batch and retry on a later
cycle — do not tight-loop.

## Suggested client result kinds

If you wrap this API (HTTP or MCP), map outcomes so a curiosity/OSINT loop can
gate retries:

| kind | When |
| ---- | ---- |
| `hits` | HTTP 200 with one or more usable profile URLs |
| `empty` | HTTP 200 and `hits` is `[]` |
| `busy` | HTTP 503 |
| `timeout` | Client gave up before the body arrived |
| `transport` | Connection error |
| `http` | Other non-200 |
| `config` | URL or API key missing on the client |
| `unsupported_mode` / `invalid_json` | 400 / parse error |

Treat `empty` as success for cooldown. Treat `busy` / `timeout` / `transport` as
“try later,” not as “no profiles exist.”
