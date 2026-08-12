"""DEPRECATED: This module is the canonical SecurAgentX FastAPI server.

(The historical ``securagentx.api`` package — a parallel, unused FastAPI
factory — was removed as dead code; see ``securagentx/api/`` removal.
This ``tools/api_server.py`` module remains the live API surface used by
``main.py`` and ``commands/system.py`` via the ``run_server`` shim.)

--- legacy docstring below (for historical context) -----------------------

tools/api_server.py — SecurAgentX Enterprise REST API
====================================================
Professional-grade FastAPI REST API for CI/CD integration, web dashboards,
and enterprise orchestration.

Endpoints:
  - POST   /scan             Start a new scan
  - GET    /scan/{id}        Get scan status
  - POST   /scan/{id}/stop   Stop a running scan
  - GET    /scan/{id}/findings   Get scan findings
  - GET    /findings         Search/filter all findings
  - POST   /findings/{id}/suppress  Suppress a false positive
  - POST   /report           Generate a compliance report
  - GET    /report/{id}      Download a generated report
  - POST   /webhook          Register a CI/CD webhook
  - DELETE /webhook/{id}     Remove a webhook
  - GET    /health           System health + uptime
  - WS     /ws/{scan_id}     Real-time scan progress

Design: World-class API design. RESTful, versioned, documented.
Built for integration with GitHub Actions, GitLab CI, Jenkins.
"""

from __future__ import annotations

import warnings

# Note: the parallel ``securagentx.api.app`` factory was removed as dead
# code (see the securagentx/api/ deletion). This ``tools/api_server.py``
# module is the live FastAPI surface and is invoked lazily by ``main.py``
# and ``commands/system.py`` via the ``run_server`` shim. The warning is
# emitted at the very top of the module (before any heavy imports) so
# downstream callers surface the deprecation in their logs even if an
# optional dependency is missing.
warnings.warn(
    "tools.api_server is the canonical API server; the parallel securagentx.api package has been removed",
    DeprecationWarning,
    stacklevel=2,
)

import asyncio
import json
from contextlib import asynccontextmanager
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from securagentx.paths import get_reports_path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("securagentx.api_server")

# Issue 32 (P8-C): TLS verification is ON by default. Set
# SECURAGENTX_INSECURE=1|true|yes to opt into verify=False for hostile
# targets (self-signed certs, pentest labs). See verify=not INSECURE calls.
# Used by any outbound HTTP clients spawned by API route handlers.
INSECURE = os.environ.get("SECURAGENTX_INSECURE", "").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Safe FastAPI import (optional dependency)
# ---------------------------------------------------------------------------
try:
    from fastapi import (
        BackgroundTasks,
        Depends,
        FastAPI,
        Header,
        HTTPException,
        WebSocket,
        WebSocketDisconnect,
    )
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, HTMLResponse
    from pydantic import BaseModel, Field

    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

# ---------------------------------------------------------------------------
# In-Memory Scan Store (replace with DB in production)
# ---------------------------------------------------------------------------


class ScanRecord:
    """Represents a single scan in the system."""

    def __init__(self, target: str, scan_type: str = "full"):
        self.id: str = f"scan_{uuid.uuid4().hex[:12]}"
        self.target: str = target
        self.scan_type: str = scan_type
        self.status: str = "pending"  # pending -> running -> completed | failed
        self.created_at: datetime = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None
        self.findings: List[Dict[str, Any]] = []
        self.error: Optional[str] = None
        self._task: Optional[asyncio.Task] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "scan_type": self.scan_type,
            "status": self.status,
            "findings_count": len(self.findings),
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


# Global scan store (use Redis/Postgres in production).
#
# Concurrency note: ``_scan_store`` is accessed from async handlers, but in
# asyncio's single-threaded model every dict read/write below is atomic
# (no ``await`` between read and mutate — e.g.
# ``_scan_store[record.id] = record`` is a single bytecode op). The
# ``_scan_lock`` is therefore reserved for future handlers that may need
# to span an ``await`` between read and mutate; current call sites are
# safe without it.
_scan_store: Dict[str, ScanRecord] = {}
_scan_lock = asyncio.Lock()  # reserved for future read-mutate-await spans

# WebSocket connection registry — REAL race condition: ``_notify_ws`` iterates
# the per-scan set while awaiting ``ws.send_text`` between iterations, so
# another coroutine can mutate the set (raise "Set changed size during
# iteration") or replace it. All mutations and iterations of ``_ws_connections``
# MUST be performed while holding ``_ws_lock``.
_ws_connections: Dict[str, Set[WebSocket]] = {}
_ws_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

# ── Module-level app (for uvicorn import) ────────────────────────────
_app_instance = None
app = None

if _HAS_FASTAPI:

    class ScanRequest(BaseModel):
        """Request body for starting a scan."""

        target: str = Field(..., description="Target to scan (URL, IP, domain)")
        scan_type: str = Field(
            "full", description="Scan type: full, quick, deep, stealth, web, api"
        )

    class ScanStatus(BaseModel):
        """Scan status response."""

        id: str
        target: str
        scan_type: str
        status: str
        findings_count: int
        created_at: str
        completed_at: Optional[str] = None
        error: Optional[str] = None

    class FindingFilter(BaseModel):
        """Filters for finding search."""

        severity: Optional[str] = None
        vuln_type: Optional[str] = None
        target: Optional[str] = None
        limit: int = Field(100, ge=1, le=1000)
        offset: int = Field(0, ge=0)

    class SuppressRequest(BaseModel):
        """Request to suppress a false positive finding."""

        reason: str = Field(..., description="Why this finding is a false positive")

    class WebhookRequest(BaseModel):
        """Register a CI/CD webhook."""

        url: str = Field(..., description="Webhook URL")
        secret: Optional[str] = Field(None, description="Shared secret for HMAC signing")
        events: List[str] = Field(
            ["scan.completed", "finding.critical"], description="Events to trigger on"
        )

    class ReportRequest(BaseModel):
        """Generate a compliance report."""

        scan_ids: List[str] = Field(..., description="Scan IDs to include")
        format: str = Field("html", description="Report format: html, pdf, json, sarif")
        standard: str = Field("pci_dss", description="Compliance standard: pci_dss, soc2, iso27001")

    # ── API App & Helpers ────────────────────────────────────────────────

    async def _notify_ws(scan_id: str, event: str, data: Dict[str, Any]) -> None:
        """Send a WebSocket notification to all connected clients for a scan.

        Race-condition safe: we hold ``_ws_lock`` only long enough to snapshot
        the per-scan set, then release it before awaiting ``ws.send_text``
        (so a slow client cannot block other handlers from mutating the
        registry). Stale websockets are pruned under the lock afterwards.
        """
        async with _ws_lock:
            conns = _ws_connections.get(scan_id)
            if not conns:
                return
            # Snapshot so iteration is safe across the awaits below.
            snapshot: Set[WebSocket] = set(conns)
        payload = json.dumps({"event": event, "data": data})
        stale: Set[WebSocket] = set()
        for ws in snapshot:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.add(ws)
        if stale:
            async with _ws_lock:
                conns = _ws_connections.get(scan_id)
                if conns:
                    conns -= stale

    @asynccontextmanager
    async def _api_lifespan(_: FastAPI):
        logger.info("SecurAgentX Enterprise API server started")
        Path("data/webhooks").mkdir(parents=True, exist_ok=True)
        get_reports_path()
        yield

    # Create the FastAPI app
    _app = FastAPI(
        title="SecurAgentX Security API",
        description="World-class AI-powered security scanning API for enterprise CI/CD integration.",
        version="2.0.0",
        lifespan=_api_lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Explicit origins only
        allow_credentials=False,  # Cannot use True with specific origins safely
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _server_start_time: float = time.time()

    # Ensure the global WS bucket exists. Safe to do without ``_ws_lock``
    # because module import runs synchronously (no event loop yet) — no
    # other coroutine can interleave. Runtime mutations of this bucket
    # (in ``global_websocket`` and ``_notify_ws``) DO acquire ``_ws_lock``.
    _ws_connections.setdefault("global", set())

    pass  # app assigned below

    async def _run_scan_task(target: str, scan_type: str, scan_id: str) -> None:
        """Background task that runs the actual scan."""
        record = _scan_store[scan_id]
        record.status = "running"
        await _notify_ws(scan_id, "scan.started", {"scan_id": scan_id, "target": target})

        try:
            from main import normalize_target  # type: ignore[attr-defined]
            from core.orchestrator import Orchestrator

            normalized = normalize_target(target)
            orch = Orchestrator(normalized)

            # Run pipeline based on scan type
            if scan_type == "quick":
                findings = await orch.run_quick_scan()
            elif scan_type == "deep":
                findings = await orch.run_deep_scan()
            elif scan_type == "stealth":
                findings = await orch.run_stealth_scan()
            elif scan_type in ("web", "api"):
                findings = await orch.run_scan_web()
            else:
                findings = await orch.run_full_scan()

            record.findings = findings or []
            record.status = "completed"

            # Categorize findings for notification
            severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for f in record.findings:
                sev = f.get("severity", "info").lower()
                if sev in severity_counts:
                    severity_counts[sev] += 1

            await _notify_ws(
                scan_id,
                "scan.completed",
                {
                    "scan_id": scan_id,
                    "findings_count": len(record.findings),
                    "severity_counts": severity_counts,
                },
            )

        except Exception as e:
            logger.exception(f"Scan {scan_id} failed: {e}")
            record.status = "failed"
            record.error = str(e)
            await _notify_ws(
                scan_id,
                "scan.failed",
                {
                    "scan_id": scan_id,
                    "error": str(e),
                },
            )
        finally:
            record.completed_at = datetime.now(timezone.utc)

    # ── Auth ──────────────────────────────────────────────────────────────

    async def auth_token_required(x_api_token: str = Header(...)):
        """Validate the ``X-API-Token`` header against ``SECURAGENTX_API_TOKEN``.

        If the env var is unset, all requests are rejected (fail-closed).
        WebSocket endpoints are exempt (use query-param auth at the gateway
        instead — out of scope for this hardening pass).
        """
        expected = os.environ.get("SECURAGENTX_API_TOKEN")
        if not expected or x_api_token != expected:
            raise HTTPException(
                status_code=401, detail="Invalid or missing API token"
            )
        return x_api_token

    # ── Endpoints ─────────────────────────────────────────────────────────

    @_app.get("/health", tags=["System"])
    async def health_check(_: str = Depends(auth_token_required)):
        """System health check endpoint."""
        uptime_seconds = time.time() - _server_start_time
        return {
            "status": "healthy",
            "version": "2.0.0",
            "uptime_seconds": uptime_seconds,
            "active_scans": sum(1 for s in _scan_store.values() if s.status == "running"),
            "total_scans": len(_scan_store),
        }

    @_app.post("/scan", response_model=ScanStatus, tags=["Scan"])
    async def start_scan(
        req: ScanRequest,
        background_tasks: BackgroundTasks,
        _: str = Depends(auth_token_required),
    ):
        """Start a new security scan."""
        try:
            from main import normalize_target, validate_target  # type: ignore[attr-defined]

            normalized = normalize_target(req.target)
            if not validate_target(normalized):
                raise HTTPException(
                    status_code=400, detail=f"Invalid or out-of-scope target: {req.target}"
                )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        record = ScanRecord(normalized, req.scan_type)
        _scan_store[record.id] = record

        # Launch background scan
        background_tasks.add_task(_run_scan_task, normalized, req.scan_type, record.id)

        return ScanStatus(**record.to_dict())

    @_app.get("/scan/{scan_id}", response_model=ScanStatus, tags=["Scan"])
    async def get_scan(scan_id: str, _: str = Depends(auth_token_required)):
        """Get scan status and metadata."""
        record = _scan_store.get(scan_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Scan not found: {scan_id}")
        return ScanStatus(**record.to_dict())

    @_app.post("/scan/{scan_id}/stop", tags=["Scan"])
    async def stop_scan(scan_id: str, _: str = Depends(auth_token_required)):
        """Stop a running scan."""
        record = _scan_store.get(scan_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Scan not found: {scan_id}")
        if record.status != "running":
            raise HTTPException(
                status_code=400, detail=f"Scan is not running (status: {record.status})"
            )
        if record._task:
            record._task.cancel()
        record.status = "cancelled"
        record.completed_at = datetime.now(timezone.utc)
        return {"status": "cancelled", "scan_id": scan_id}

    @_app.get("/scan/{scan_id}/findings", tags=["Findings"])
    async def get_findings(
        scan_id: str,
        severity: Optional[str] = None,
        vuln_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        _: str = Depends(auth_token_required),
    ):
        """Get findings for a scan with optional filters."""
        record = _scan_store.get(scan_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Scan not found: {scan_id}")
        findings = record.findings
        if severity:
            findings = [f for f in findings if f.get("severity", "").lower() == severity.lower()]
        if vuln_type:
            findings = [f for f in findings if vuln_type.lower() in f.get("type", "").lower()]
        total = len(findings)
        findings = findings[offset : offset + limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "findings": findings,
            "scan_id": scan_id,
        }

    @_app.get("/findings", tags=["Findings"])
    async def search_findings(
        q: Optional[str] = None,
        severity: Optional[str] = None,
        target: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        _: str = Depends(auth_token_required),
    ):
        """Search across all findings."""
        all_findings: List[Dict[str, Any]] = []
        for record in _scan_store.values():
            for f in record.findings:
                enriched = dict(f)
                enriched["_scan_id"] = record.id
                enriched["_scan_target"] = record.target
                all_findings.append(enriched)
        # Filters
        if severity:
            all_findings = [
                f for f in all_findings if f.get("severity", "").lower() == severity.lower()
            ]
        if target:
            all_findings = [
                f for f in all_findings if target.lower() in str(f.get("url", "")).lower()
            ]
        if q:
            q_lower = q.lower()
            all_findings = [f for f in all_findings if q_lower in json.dumps(f).lower()]
        total = len(all_findings)
        all_findings = all_findings[offset : offset + limit]
        return {"total": total, "limit": limit, "offset": offset, "findings": all_findings}

    @_app.post("/findings/{finding_id}/suppress", tags=["Findings"])
    async def suppress_finding(
        finding_id: str,
        req: SuppressRequest,
        _: str = Depends(auth_token_required),
    ):
        """Mark a finding as suppressed (false positive)."""
        for record in _scan_store.values():
            for f in record.findings:
                if f.get("id") == finding_id or f.get("title") == finding_id:
                    f["suppressed"] = True
                    f["suppression_reason"] = req.reason
                    return {"status": "suppressed", "finding_id": finding_id}
        raise HTTPException(status_code=404, detail=f"Finding not found: {finding_id}")

    @_app.post("/report", tags=["Reports"])
    async def generate_report(
        req: ReportRequest,
        background_tasks: BackgroundTasks,
        _: str = Depends(auth_token_required),
    ):
        """Generate a compliance report from scan data."""
        scans = []
        for sid in req.scan_ids:
            record = _scan_store.get(sid)
            if record:
                scans.append(record)
        if not scans:
            raise HTTPException(status_code=404, detail="No valid scans found")
        # Gather all findings
        all_findings = []
        for s in scans:
            all_findings.extend(s.findings)
        report_id = f"report_{uuid.uuid4().hex[:8]}"
        output_path = Path(f"reports/{report_id}.{req.format}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate report
        try:
            from datetime import datetime, timezone

            from tools.report_gen import (
                ExecutiveSummary,
                FindingReport,
                ReportFormat,
                export_report,
            )

            summary = ExecutiveSummary(  # type: ignore[call-arg]
                target=", ".join(s.target for s in scans),
                scan_date=datetime.now(timezone.utc).isoformat(),
                duration_seconds=0,
                total_findings=len(all_findings),
                tool_version="2.0.0",
                risk_level="Unknown",
            )
            reports = []
            for f in all_findings:
                reports.append(
                    FindingReport(
                        id=str(hash(str(f))),
                        title=f.get("title", "Finding")[:100],
                        severity=f.get("severity", "Informational"),
                        cvss=f.get("cvss", 0),
                        url=f.get("url", ""),
                        vuln_class=f.get("type", "unknown"),
                        description=f.get("details", ""),
                        impact="",
                        remediation=f.get("remediation", ""),
                    )
                )
            fmt_map = {
                "html": ReportFormat.HTML,
                "json": ReportFormat.JSON,
                "sarif": ReportFormat.SARIF,
            }
            fmt = fmt_map.get(req.format, ReportFormat.HTML)
            export_report(summary, reports, str(output_path), fmt)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")
        return {
            "status": "generated",
            "report_id": report_id,
            "format": req.format,
            "standard": req.standard,
            "path": str(output_path),
            "findings_count": len(all_findings),
        }

    @_app.get("/report/{report_id}", tags=["Reports"])
    async def download_report(
        report_id: str,
        format: str = "html",
        _: str = Depends(auth_token_required),
    ):
        """Download a generated report."""
        report_path = Path(f"reports/{report_id}.{format}")
        if not report_path.exists():
            # Try to find any format
            for ext in ["html", "json", "md", "sarif.json", "txt"]:
                alt = Path(f"reports/{report_id}.{ext}")
                if alt.exists():
                    report_path = alt
                    break
            else:
                raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
        return FileResponse(
            str(report_path), media_type="application/octet-stream", filename=report_path.name
        )

    @_app.post("/webhook", tags=["Webhooks"])
    async def register_webhook(
        req: WebhookRequest,
        _: str = Depends(auth_token_required),
    ):
        """Register a CI/CD webhook."""
        webhook_id = f"wh_{uuid.uuid4().hex[:8]}"
        # Store webhook config to disk
        wh_dir = Path("data/webhooks")
        wh_dir.mkdir(parents=True, exist_ok=True)
        with open(wh_dir / f"{webhook_id}.json", "w") as f:
            json.dump(
                {
                    "id": webhook_id,
                    "url": req.url,
                    "secret": req.secret,
                    "events": req.events,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                f,
            )
        return {"status": "registered", "webhook_id": webhook_id, "url": req.url}

    @_app.get("/webhooks", tags=["Webhooks"])
    async def list_webhooks(_: str = Depends(auth_token_required)):
        """List all registered webhooks."""
        wh_dir = Path("data/webhooks")
        wh_dir.mkdir(parents=True, exist_ok=True)
        webhooks = []
        for f in wh_dir.glob("*.json"):
            try:
                with open(f) as fh:
                    webhooks.append(json.load(fh))
            except Exception as e:
                logger.debug("Suppressed Exception: %s", e)
        return {"webhooks": webhooks}

    @_app.delete("/webhook/{webhook_id}", tags=["Webhooks"])
    async def delete_webhook(
        webhook_id: str,
        _: str = Depends(auth_token_required),
    ):
        """Remove a registered webhook."""
        wh_path = Path(f"data/webhooks/{webhook_id}.json")
        if wh_path.exists():
            wh_path.unlink()
            return {"status": "deleted", "webhook_id": webhook_id}
        raise HTTPException(status_code=404, detail=f"Webhook not found: {webhook_id}")

    @_app.websocket("/ws/{scan_id}")
    async def websocket_endpoint(websocket: WebSocket, scan_id: str):
        """Real-time scan progress via WebSocket."""
        await websocket.accept()
        # Register under ``_ws_lock``: concurrent connect handlers for the
        # same scan_id would otherwise race on the ``if scan_id not in ...``
        # branch and one websocket could be lost.
        async with _ws_lock:
            _ws_connections.setdefault(scan_id, set()).add(websocket)
        try:
            # Send current status immediately
            record = _scan_store.get(scan_id)
            if record:
                await websocket.send_text(
                    json.dumps(
                        {
                            "event": "scan.status",
                            "data": record.to_dict(),
                        }
                    )
                )
            # Keep connection open
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text(json.dumps({"event": "pong"}))
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.debug("Suppressed Exception: %s", e)
        finally:
            async with _ws_lock:
                conns = _ws_connections.get(scan_id)
                if conns:
                    conns.discard(websocket)

    # ── Static Dashboard ─────────────────────────────────────────────────

    _DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SecurAgentX Security Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0a0a0f; color: #e0e0e0; }
  .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 20px 30px; border-bottom: 1px solid #2a2a4a; }
  .header h1 { font-size: 24px; color: #fff; }
  .header span { color: #ff4444; }
  .content { padding: 30px; max-width: 1400px; margin: 0 auto; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 30px; }
  .stat-card { background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%); border-radius: 12px; padding: 20px;
               border: 1px solid #2a2a4a; }
  .stat-card .label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; }
  .stat-card .value { font-size: 36px; font-weight: 700; margin: 8px 0; }
  .stat-card .value.critical { color: #ff4444; }
  .stat-card .value.high { color: #ff8844; }
  .stat-card .value.medium { color: #ffcc44; }
  .stat-card .value.low { color: #44cc44; }
  .table { background: #1a1a2e; border-radius: 12px; border: 1px solid #2a2a4a; overflow: hidden; }
  .table-header { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr 1fr 1fr; padding: 12px 16px;
                  background: #0f3460; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #888; }
  .table-row { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr 1fr 1fr; padding: 12px 16px;
               border-top: 1px solid #2a2a4a; font-size: 14px; }
  .table-row:hover { background: rgba(255,255,255,0.03); }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
  .badge.critical { background: #ff444420; color: #ff4444; border: 1px solid #ff444440; }
  .badge.high { background: #ff884420; color: #ff8844; border: 1px solid #ff884440; }
  .badge.medium { background: #ffcc4420; color: #ffcc44; border: 1px solid #ffcc4440; }
  .status { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
  .status.running { background: #44cc4420; color: #44cc44; }
  .status.completed { background: #4488ff20; color: #4488ff; }
  .status.failed { background: #ff444420; color: #ff4444; }
  .btn { background: #4488ff; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; }
  .btn:hover { background: #3366cc; }
  .new-scan { display: flex; gap: 12px; margin-bottom: 30px; }
  .new-scan input { flex: 1; background: #1a1a2e; border: 1px solid #2a2a4a; padding: 10px 16px; border-radius: 8px;
                    color: white; font-size: 14px; }
  .new-scan select { background: #1a1a2e; border: 1px solid #2a2a4a; padding: 10px 16px; border-radius: 8px;
                     color: white; font-size: 14px; }
  .footer { text-align: center; padding: 20px; color: #555; font-size: 12px; }
  .ws-status { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
  .ws-status.connected { background: #44cc44; }
  .ws-status.disconnected { background: #ff4444; }
</style>
</head>
<body>
<div class="header"><h1><span>SecurAgentX</span> Security Dashboard</h1></div>
<div class="content">
  <div class="new-scan">
    <input id="targetInput" placeholder="Target (URL, IP, or domain)" />
    <select id="scanType">
      <option value="full">Full Scan</option>
      <option value="quick">Quick Scan</option>
      <option value="deep">Deep Scan</option>
      <option value="stealth">Stealth Scan</option>
      <option value="web">Web Scan</option>
      <option value="api">API Scan</option>
    </select>
    <button class="btn" onclick="startScan()">Start Scan</button>
  </div>
  <div class="stats" id="stats">Loading...</div>
  <div class="table">
    <div class="table-header">
      <span>Target</span><span>Type</span><span>Status</span><span>Findings</span><span>Severity</span><span>Actions</span>
    </div>
    <div id="scans">Loading...</div>
  </div>
</div>
<div class="footer">SecurAgentX Security Framework v2.0.0 | <span id="wsIndicator" class="ws-status disconnected"></span><span id="wsLabel">Disconnected</span></div>
<script>
let ws = null; let scanIds = new Set();
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(proto + '//' + location.host + '/ws/global');
  ws.onopen = () => { document.getElementById('wsIndicator').className = 'ws-status connected';
    document.getElementById('wsLabel').textContent = 'Connected'; };
  ws.onclose = () => { document.getElementById('wsIndicator').className = 'ws-status disconnected';
    document.getElementById('wsLabel').textContent = 'Disconnected';
    setTimeout(connectWS, 3000); };
  ws.onmessage = (e) => { try { const m = JSON.parse(e.data);
    if (m.event === 'scan.completed' || m.event === 'scan.started' || m.event === 'scan.failed') refreshScans();
  } catch(e) {} };
}
function startScan() {
  const target = document.getElementById('targetInput').value;
  const type = document.getElementById('scanType').value;
  if (!target) return alert('Enter a target');
  fetch('/scan', { method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({target, scan_type: type}) })
  .then(r => r.json()).then(data => { refreshScans();
    document.getElementById('targetInput').value = ''; })
  .catch(e => alert('Error: '+e));
}
function refreshScans() {
  fetch('/health').then(r=>r.json()).then(h => {
    document.getElementById('stats').innerHTML =
      '<div class="stat-card"><div class="label">Active Scans</div><div class="value">'+h.active_scans+'</div></div>'+
      '<div class="stat-card"><div class="label">Total Scans</div><div class="value">'+h.total_scans+'</div></div>'+
      '<div class="stat-card"><div class="label">Uptime</div><div class="value" style="font-size:20px">'+Math.floor(h.uptime_seconds/3600)+'h</div></div>';
  });
  fetch('/findings?limit=5').then(r=>r.json()).then(d => {
    if(d.findings && d.findings.length) {
      let c=0,h=0,m=0,l=0;
      d.findings.forEach(f => { const s=(f.severity||'').toLowerCase();
        if(s==='critical') c++; else if(s==='high') h++; else if(s==='medium') m++; else if(s==='low') l++; });
    }
  });
  fetch('/scan/global').then(r=>r.json()).catch(()=>{});
  let html = '';
  fetch('/scan/all').catch(()=>{}).then(()=>{});
  // Just show health
}
setInterval(refreshScans, 5000); refreshScans(); connectWS();
</script>
</body>
</html>"""

    @_app.get("/", tags=["Dashboard"])
    async def web_dashboard(_: str = Depends(auth_token_required)):
        """Built-in web dashboard."""
        return HTMLResponse(_DASHBOARD_HTML)

    @_app.get("/scan/all", tags=["Scan"])
    async def list_all_scans(
        limit: int = 50,
        offset: int = 0,
        _: str = Depends(auth_token_required),
    ):
        """List all scans."""
        scans = sorted(_scan_store.values(), key=lambda s: s.created_at, reverse=True)
        scans = scans[offset : offset + limit]
        return {
            "total": len(_scan_store),
            "limit": limit,
            "offset": offset,
            "scans": [s.to_dict() for s in scans],
        }

    @_app.websocket("/ws/global")
    async def global_websocket(websocket: WebSocket):
        """Global WebSocket for all scan events."""
        await websocket.accept()
        _session_id = f"session_{uuid.uuid4().hex[:8]}"
        # Register under ``_ws_lock`` to race-condition-proof concurrent
        # connections (see ``websocket_endpoint`` above).
        async with _ws_lock:
            _ws_connections.setdefault("global", set()).add(websocket)
        try:
            while True:
                _data = await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            async with _ws_lock:
                conns = _ws_connections.get("global")
                if conns:
                    conns.discard(websocket)

    # Export module-level app reference
    globals()["app"] = _app


# ---------------------------------------------------------------------------
# CLI Server Launcher
# ---------------------------------------------------------------------------


def run_server(host: str = "127.0.0.1", port: int = 8443, reload: bool = False) -> None:
    """Launch the SecurAgentX Enterprise API server.

    Args:
        host: Bind address (default: 127.0.0.1 — loopback only; do NOT bind
            0.0.0.0 in production without an upstream reverse proxy that
            terminates TLS and enforces auth/rate-limiting).
        port: Listen port (default: 8443)
        reload: Auto-reload on code changes (default: False)
    """
    if not _HAS_FASTAPI:
        print("[FAIL] FastAPI not installed. Run: pip install fastapi uvicorn")
        return
    from cli.ui_components import console, print_info, print_success

    console.print("[bold red]  SecurAgentX Enterprise API[/bold red]")
    print_info(f"  Server: http://{host}:{port}")
    print_info(f"  Docs:   http://{host}:{port}/docs")
    print_info(f"  ReDoc:  http://{host}:{port}/redoc")
    print_info(f"  Dashboard: http://{host}:{port}/")
    print_success("  Press Ctrl+C to stop")

    import uvicorn

    uvicorn.run(
        "tools.api_server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


__all__ = ["app", "run_server"]
