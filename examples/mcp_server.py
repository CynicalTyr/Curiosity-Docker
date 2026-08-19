#!/usr/bin/env python3
"""MCP stdio adapter for the Curiosity-Docker HTTP sidecar.

The container is JSON-over-HTTP. This process is the agent-facing MCP server:
hosts such as Claude Desktop, Cursor, or any MCP client launch it as a child
process. Logs go to stderr only — stdout is the MCP JSON-RPC pipe.

Environment (names only):
  USERNAME_DISCOVERY_URL       default http://127.0.0.1:8095
  USERNAME_DISCOVERY_API_KEY   required
  USERNAME_DISCOVERY_TIMEOUT   scan timeout seconds, default 120
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
log = logging.getLogger("curiosity_docker_mcp")

BASE = (os.environ.get("USERNAME_DISCOVERY_URL") or "http://127.0.0.1:8095").rstrip("/")
API_KEY = (os.environ.get("USERNAME_DISCOVERY_API_KEY") or "").strip()
try:
    TIMEOUT_S = float(os.environ.get("USERNAME_DISCOVERY_TIMEOUT") or "120")
except ValueError:
    TIMEOUT_S = 120.0

mcp = FastMCP(
    "curiosity-username-discovery",
    instructions=(
        "Username discovery sidecar: map a public handle to candidate social "
        "profile URLs. Call username_discovery_health before scans. Treat HTTP "
        "503 busy as occupancy — do not retry in a tight loop. Hits are "
        "unverified public URLs, not proof of identity."
    ),
)


def _request(method: str, path: str, body: dict | None = None, timeout: float = 5.0) -> dict:
    if not API_KEY:
        return {"error": "config", "detail": "USERNAME_DISCOVERY_API_KEY is not set"}
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"status": resp.status}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            parsed = {"error": "http", "status": exc.code, "detail": detail[:500]}
        if isinstance(parsed, dict):
            parsed.setdefault("status", exc.code)
            return parsed
        return {"error": "http", "status": exc.code}
    except TimeoutError:
        return {"error": "timeout"}
    except urllib.error.URLError as exc:
        return {"error": "transport", "detail": str(exc.reason)}
    except json.JSONDecodeError:
        return {"error": "invalid_json"}


@mcp.tool()
def username_discovery_health() -> dict:
    """Check that the username-discovery sidecar is up and accepting authenticated requests."""
    return _request("GET", "/health", timeout=5.0)


@mcp.tool()
def username_discovery_scan(username: str, top: int = 25) -> dict:
    """Look up public social profile URL candidates for a username/handle.

    Fast HTTP checks only (no browser). Returns hits as platform/url/site/confidence
    or an error object (busy, timeout, forbidden, …). Do not retry immediately on busy.
    """
    handle = (username or "").strip()
    if not handle:
        return {"error": "missing_username"}
    n = max(1, min(int(top), 25))
    return _request(
        "POST",
        "/scan",
        body={"username": handle, "mode": "fast", "top": n, "websites": "all"},
        timeout=TIMEOUT_S,
    )


def main() -> None:
    if not API_KEY:
        log.error("USERNAME_DISCOVERY_API_KEY is required")
        sys.exit(1)
    mcp.run()


if __name__ == "__main__":
    main()
