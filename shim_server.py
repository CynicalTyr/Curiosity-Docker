#!/usr/bin/env python3
"""Minimal HTTP shim around qeeqbox/social-analyzer (AGPL — separate container only)."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

SOCIAL_ANALYZER_ROOT = os.environ.get("SOCIAL_ANALYZER_ROOT", "/opt/social-analyzer")
if SOCIAL_ANALYZER_ROOT not in sys.path:
    sys.path.insert(0, SOCIAL_ANALYZER_ROOT)

logger = logging.getLogger("username_discovery_shim")
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

API_KEY = (os.environ.get("USERNAME_DISCOVERY_API_KEY") or "").strip()
_ALLOWED_RAW = (os.environ.get("USERNAME_DISCOVERY_ALLOWED_IPS") or "127.0.0.1").strip()
ALLOW_ANY_IP = _ALLOWED_RAW in {"*", "any"}
ALLOWED_IPS = (
    set()
    if ALLOW_ANY_IP
    else {ip.strip() for ip in _ALLOWED_RAW.split(",") if ip.strip()}
)
BIND_HOST = os.environ.get("USERNAME_DISCOVERY_BIND", "0.0.0.0")
BIND_PORT = int(os.environ.get("USERNAME_DISCOVERY_PORT", "8095"))
SCAN_TIMEOUT = int(os.environ.get("USERNAME_DISCOVERY_SCAN_TIMEOUT", "60"))
SCAN_LOCK = threading.Lock()

_DOMAIN_TO_PLATFORM = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "snapchat.com": "snapchat",
    "twitter.com": "x",
    "x.com": "x",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
}


_ANALYZER_MODULE = None


def _load_analyzer():
    """Import social-analyzer app.py once; new SocialAnalyzer() per scan."""
    global _ANALYZER_MODULE
    if _ANALYZER_MODULE is None:
        spec = importlib.util.spec_from_file_location(
            "social_analyzer_app", os.path.join(SOCIAL_ANALYZER_ROOT, "app.py")
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("failed to load social-analyzer app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _ANALYZER_MODULE = module
    return _ANALYZER_MODULE.SocialAnalyzer()


def _map_platform(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    if host in _DOMAIN_TO_PLATFORM:
        return _DOMAIN_TO_PLATFORM[host]
    for suffix, plat in _DOMAIN_TO_PLATFORM.items():
        if host.endswith(suffix):
            return plat
    return ""


def _normalize_results(raw: Any) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    if not isinstance(raw, dict):
        return hits

    detected = raw.get("detected") or raw.get("profiles") or raw.get("data")
    if isinstance(detected, list):
        rows = detected
    elif isinstance(detected, dict):
        rows = list(detected.values())
    else:
        rows = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(
            row.get("link")
            or row.get("url")
            or row.get("profile")
            or row.get("profile_url")
            or ""
        ).strip()
        if not url:
            continue
        site = str(row.get("name") or row.get("site") or row.get("title") or "").strip()
        platform = _map_platform(url)
        confidence = str(row.get("rate") or row.get("status") or row.get("confidence") or "good")
        hits.append(
            {
                "platform": platform,
                "url": url,
                "site": site or platform or "unknown",
                "confidence": confidence,
            }
        )
    return hits


class ShimHandler(BaseHTTPRequestHandler):
    server_version = "UsernameDiscoveryShim/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _client_ip(self) -> str:
        # Do not trust X-Forwarded-For unless an operator explicitly enables it
        # behind a known reverse proxy (otherwise clients can spoof the allowlist).
        if os.environ.get("USERNAME_DISCOVERY_TRUST_FORWARDED", "").strip() in {
            "1",
            "true",
            "yes",
        }:
            forwarded = self.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return self.client_address[0]

    def _authorized(self) -> bool:
        if not ALLOW_ANY_IP and ALLOWED_IPS and self._client_ip() not in ALLOWED_IPS:
            return False
        key = (self.headers.get("X-API-Key") or "").strip()
        return bool(API_KEY) and key == API_KEY

    def _json_response(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") != "/health":
            self._json_response(404, {"error": "not_found"})
            return
        if not self._authorized():
            self._json_response(403, {"error": "forbidden"})
            return
        self._json_response(200, {"status": "ok", "mode": "fast"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/scan":
            self._json_response(404, {"error": "not_found"})
            return
        if not self._authorized():
            self._json_response(403, {"error": "forbidden"})
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json_response(400, {"error": "invalid_json"})
            return

        username = str(body.get("username") or "").strip()
        if not username:
            self._json_response(400, {"error": "missing_username"})
            return

        mode = str(body.get("mode") or "fast").strip().lower()
        if mode != "fast":
            self._json_response(400, {"error": "unsupported_mode"})
            return

        top = int(body.get("top") or 25)
        top = max(1, min(top, 25))
        websites = str(body.get("websites") or "all")

        if not SCAN_LOCK.acquire(timeout=2):
            self._json_response(503, {"error": "busy"})
            return
        try:
            logger.info("scan start %s", username)
            analyzer = _load_analyzer()
            raw_result = analyzer.run_as_object(
                username=username,
                mode="fast",
                output="json",
                filter="good",
                silent=True,
                timeout=SCAN_TIMEOUT,
                top=str(top),
                websites=websites,
                metadata=False,
                extract=False,
            )
            hits = _normalize_results(raw_result)
            self._json_response(200, {"hits": hits, "username": username})
        except Exception as exc:
            logger.exception("scan failed for %s: %s", username, exc)
            self._json_response(500, {"error": "scan_failed"})
        finally:
            SCAN_LOCK.release()


def main() -> None:
    if not API_KEY:
        logger.error("USERNAME_DISCOVERY_API_KEY is required")
        sys.exit(1)
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), ShimHandler)
    logger.info(
        "username-discovery shim listening on %s:%s (allowed IPs: %s)",
        BIND_HOST,
        BIND_PORT,
        "*" if ALLOW_ANY_IP else ",".join(sorted(ALLOWED_IPS)),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
