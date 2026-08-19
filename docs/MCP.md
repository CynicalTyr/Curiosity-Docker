# MCP adapter

The Docker container is **not** an MCP server. It is an HTTP worker. Agents talk
to it through **MCP** so the model sees tools, not curl.

```
MCP host (Claude Desktop, Cursor, custom runtime)
    │  stdio JSON-RPC
    ▼
examples/mcp_server.py     ← this repo, runs next to the agent
    │  HTTP + X-API-Key
    ▼
curiosity-username-discovery container
    │
    ▼
social-analyzer (fast, inside the image)
```

Keeping MCP on the agent host means:

- The AGPL analyzer never loads in the agent process.
- Tool schemas stay stable if you swap shim internals.
- Stdout of the MCP process stays a clean JSON-RPC pipe (logs on stderr).

## Tools

| Tool | Maps to | Returns |
| ---- | ------- | ------- |
| `username_discovery_health` | `GET /health` | `{status, mode}` or `{error,…}` |
| `username_discovery_scan` | `POST /scan` | `{username, hits}` or `{error,…}` |

`username_discovery_scan` arguments: `username` (string), `top` (int, 1–25, default 25).

The server instructions tell the model that **503 busy is occupancy**, hits are
**unverified public URLs**, and health should be checked first.

## Install (agent host)

```bash
python3 -m pip install -r examples/requirements-mcp.txt
```

The Docker image does **not** include the MCP SDK.

## Configure a host

Copy `examples/mcp.example.json` into your host’s MCP config. Use an
**absolute** path to `examples/mcp_server.py`. Set `USERNAME_DISCOVERY_API_KEY`
in that block (host secret store / local env — not this git tree).

Environment for the adapter:

| Name | Default | Purpose |
| ---- | ------- | ------- |
| `USERNAME_DISCOVERY_URL` | `http://127.0.0.1:8095` | Sidecar base URL |
| `USERNAME_DISCOVERY_API_KEY` | (required) | Same key as the container `.env` |
| `USERNAME_DISCOVERY_TIMEOUT` | `120` | Client wait; keep above container scan timeout |

Restart the MCP host after editing config. Only the MCP SDK may write to stdout.

## How agents should use the tools

1. **Health** at the start of a batch. If it fails, skip username discovery for
   this cycle.
2. **Scan** one handle. On `error: busy` or timeout, **end the batch** and wait.
3. Persist only hits you independently accept (URL matches the handle, platform
   allowlist, human review). Do not treat a URL as a verified identity.
4. Cap scans per cycle. This sidecar will not queue work for you.

This matches a curiosity / OSINT loop: scheduled, budgeted, fail-closed — not a
chat-time spray of every handle the model can invent.
