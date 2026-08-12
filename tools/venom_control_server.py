"""Local, audited control plane for the SecurAgentX Venom dashboard.

This server intentionally exposes registered actions rather than a shell.  It
binds to loopback, requires an ephemeral bearer token, validates a target
against an operator supplied allow-list, and records every action result.
"""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
MAX_BODY_BYTES = 4096
MAX_RESPONSE_BYTES = 65536
REQUEST_TIMEOUT_SECONDS = 8


@dataclass(frozen=True)
class ActionSpec:
    """A permitted Venom action and its operator-facing description."""

    name: str
    category: str
    description: str
    requires_target: bool = False


ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec("status", "dashboard", "Return controller status and recent execution count."),
    ActionSpec("tool_catalog", "dashboard", "List registered Venom actions and dashboard tool names."),
    ActionSpec("audit_log", "dashboard", "Return the bounded, most-recent execution audit entries."),
    ActionSpec("scope_validate", "scope", "Validate a target against the session allow-list.", True),
    ActionSpec("http_headers", "recon", "Fetch only response headers from an allowed HTTP(S) target.", True),
    ActionSpec("page_metadata", "recon", "Read bounded public HTML metadata from an allowed HTTP(S) target.", True),
    ActionSpec("project_venom_tests", "project", "Run the fixed Venom dashboard regression test selection."),
)
ACTION_BY_NAME = {action.name: action for action in ACTIONS}


@dataclass
class AuditEntry:
    """A bounded, serialisable record of a completed control-plane action."""

    action: str
    target: str | None
    ok: bool
    started_at: float
    duration_ms: int
    summary: str


class ScopeBoundRedirectHandler(HTTPRedirectHandler):
    """Reject redirects so a trusted target cannot bounce requests out of scope."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def _open_scope_bound(request: Request):
    """Open one approved request without following redirects to another host."""
    return build_opener(ScopeBoundRedirectHandler()).open(request, timeout=REQUEST_TIMEOUT_SECONDS)


class MetadataParser(HTMLParser):
    """Extract only non-sensitive structural metadata from a bounded page."""

    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self._title_parts: list[str] = []
        self.forms = 0
        self.scripts = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        elif tag == "form":
            self.forms += 1
        elif tag == "script":
            self.scripts += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join("".join(self._title_parts).split())[:160]


class VenomController:
    """Policy-enforcing dispatcher for the dashboard's registered actions."""

    def __init__(self, allowed_hosts: set[str]) -> None:
        cleaned = {host.strip().lower().rstrip(".") for host in allowed_hosts if host.strip()}
        if not cleaned:
            raise ValueError("at least one --allow-target host is required")
        self.allowed_hosts = cleaned
        self.audit: list[AuditEntry] = []
        self._lock = threading.Lock()
        self._handlers: dict[str, Callable[[str | None], dict[str, Any]]] = {
            "status": self._status,
            "tool_catalog": self._tool_catalog,
            "audit_log": self._audit_log,
            "scope_validate": self._scope_validate,
            "http_headers": self._http_headers,
            "page_metadata": self._page_metadata,
            "project_venom_tests": self._project_venom_tests,
        }

    def normalize_target(self, target: str) -> str:
        """Return a verified canonical target or raise a safe validation error."""
        if not isinstance(target, str) or len(target) > 2048:
            raise ValueError("target must be a non-empty HTTP(S) URL")
        parts = urlsplit(target.strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("target must be an absolute HTTP(S) URL")
        if parts.username or parts.password or parts.hostname.lower().rstrip(".") not in self.allowed_hosts:
            raise ValueError("target host is outside the approved scope")
        if parts.port not in {None, 80, 443}:
            raise ValueError("target port is outside the approved scope")
        return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))

    def execute(self, action: str, target: str | None = None) -> dict[str, Any]:
        if action not in ACTION_BY_NAME:
            raise ValueError("action is not registered")
        spec = ACTION_BY_NAME[action]
        normalized_target = self.normalize_target(target or "") if spec.requires_target else None
        started = time.monotonic()
        try:
            result = self._handlers[action](normalized_target)
            ok = True
            summary = str(result.get("summary", "completed"))[:240]
        except Exception as exc:  # Defensive boundary: return a safe, bounded error.
            result = {"summary": "action failed", "error": str(exc)[:240]}
            ok = False
            summary = result["summary"]
        entry = AuditEntry(
            action=action,
            target=normalized_target,
            ok=ok,
            started_at=time.time(),
            duration_ms=int((time.monotonic() - started) * 1000),
            summary=summary,
        )
        with self._lock:
            self.audit.append(entry)
            self.audit[:] = self.audit[-100:]
        return {"ok": ok, "action": action, "target": normalized_target, "result": result, "audit": asdict(entry)}

    def _status(self, _: str | None) -> dict[str, Any]:
        with self._lock:
            executions = len(self.audit)
        return {"summary": "Venom control plane ready", "allowed_hosts": sorted(self.allowed_hosts), "executions": executions}

    def _tool_catalog(self, _: str | None) -> dict[str, Any]:
        return {"summary": f"{len(ACTIONS)} registered Venom actions", "actions": [asdict(action) for action in ACTIONS]}

    def _audit_log(self, _: str | None) -> dict[str, Any]:
        with self._lock:
            recent = [asdict(entry) for entry in self.audit[-20:]]
        return {"summary": f"{len(recent)} recent audited actions", "entries": recent}

    def _scope_validate(self, target: str | None) -> dict[str, Any]:
        return {"summary": "target is approved for this session", "target": target}

    def _http_headers(self, target: str | None) -> dict[str, Any]:
        request = Request(target or "", method="HEAD", headers={"User-Agent": "SecurAgentX-Venom-Control/1.0"})
        with _open_scope_bound(request) as response:
            headers = {key.lower(): value[:512] for key, value in response.headers.items()}
            return {"summary": f"received HTTP {response.status} headers", "status": response.status, "headers": headers}

    def _page_metadata(self, target: str | None) -> dict[str, Any]:
        request = Request(target or "", method="GET", headers={"User-Agent": "SecurAgentX-Venom-Control/1.0", "Range": f"bytes=0-{MAX_RESPONSE_BYTES - 1}"})
        with _open_scope_bound(request) as response:
            raw = response.read(MAX_RESPONSE_BYTES)
            encoding = response.headers.get_content_charset() or "utf-8"
            text = raw.decode(encoding, errors="replace")
            parser = MetadataParser()
            parser.feed(text)
            return {
                "summary": f"read bounded public metadata from HTTP {response.status}",
                "status": response.status,
                "content_type": response.headers.get_content_type(),
                "title": parser.title,
                "forms": parser.forms,
                "scripts": parser.scripts,
                "bytes_read": len(raw),
            }

    def _project_venom_tests(self, _: str | None) -> dict[str, Any]:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_venom_dashboard_security.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        output = (completed.stdout + completed.stderr)[-6000:]
        return {"summary": f"Venom regression tests exited {completed.returncode}", "returncode": completed.returncode, "output": output}


class VenomControlHandler(BaseHTTPRequestHandler):
    """Loopback-only token-authenticated API and static dashboard server."""

    server: "VenomControlServer"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/venom/catalog":
            self._require_auth_then(lambda: self._json(HTTPStatus.OK, {"actions": [asdict(action) for action in ACTIONS]}))
            return
        if path == "/api/venom/audit":
            self._require_auth_then(lambda: self._json(HTTPStatus.OK, {"audit": [asdict(item) for item in self.server.controller.audit]}))
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/venom/execute":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self._require_auth_then(self._execute_action)

    def _execute_action(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_BYTES:
                raise ValueError("invalid request body length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be an object")
            action = payload.get("action")
            target = payload.get("target")
            if not isinstance(action, str) or (target is not None and not isinstance(target, str)):
                raise ValueError("invalid action request")
            result = self.server.controller.execute(action, target)
            self._json(HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_REQUEST, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)[:240]})

    def _require_auth_then(self, callback: Callable[[], None]) -> None:
        if not secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {self.server.token}"):
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "authorization required"})
            return
        callback()

    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/", "/index.html"} else path.lstrip("/")
        candidate = (DASHBOARD_ROOT / relative).resolve()
        if DASHBOARD_ROOT not in candidate.parents and candidate != DASHBOARD_ROOT:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = candidate.read_bytes()
        content_type = "text/plain; charset=utf-8"
        if candidate.suffix == ".html":
            content_type = "text/html; charset=utf-8"
            injection = f"<script>window.VENOM_CONTROL_TOKEN={json.dumps(self.server.token)};</script>"
            data = data.replace(b"</head>", injection.encode("utf-8") + b"</head>", 1)
        elif candidate.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif candidate.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif candidate.suffix == ".glb":
            content_type = "model/gltf-binary"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class VenomControlServer(ThreadingHTTPServer):
    """HTTP server carrying the controller and session authentication token."""

    def __init__(self, host: str, port: int, controller: VenomController, token: str) -> None:
        self.controller = controller
        self.token = token
        super().__init__((host, port), VenomControlHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Venom control plane.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-target", action="append", default=[], metavar="HOST")
    args = parser.parse_args()
    controller = VenomController(set(args.allow_target))
    token = secrets.token_urlsafe(32)
    server = VenomControlServer(args.host, args.port, controller, token)
    print(f"Venom control dashboard: http://{args.host}:{args.port}/")
    print("Use the printed bearer token only in the local dashboard session.")
    print(f"Bearer token: {token}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
