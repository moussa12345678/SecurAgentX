"""securagentx.api.routes.knowledge — Knowledge-base documents + semantic search.

Ports the original ``/knowledge/*`` REST endpoints (originally GraphQL
mutations ``createKnowledgeDocument`` / ``deleteKnowledgeDocument`` /
``searchKnowledge`` — see Task 1-c recommendation §2).

Routes
------
* ``GET    /knowledge/documents``         — list documents (paginated).
* ``POST   /knowledge/documents``         — upload a document. Accepts
                                            multipart/form-data (file
                                            upload) or JSON (text/URL).
* ``DELETE /knowledge/documents/{id}``    — delete a document (also
                                            removes its chunks from the
                                            vector store).
* ``POST   /knowledge/search``            — semantic search across all
                                            documents. Returns top-K
                                            hits with snippets + scores.

All routes are ``auth_token_required`` — both API tokens and sessions
are accepted.

The actual storage layer (vector DB + metadata DB) is provided by
``app.state.knowledge`` (a ``KnowledgeStore`` protocol implementation
added by a future task). The route layer is responsible for request
validation, response envelope formatting, and calling the store.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import time
from typing import Any, Optional
from urllib.parse import urlparse

from securagentx.utils.url import validate_url_scheme

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse

# Issue 32 (P8-C): TLS verification is ON by default. Set
# SECURAGENTX_INSECURE=1|true|yes to opt into verify=False for hostile
# targets (self-signed certs, pentest labs). See verify=not INSECURE calls.
INSECURE = os.environ.get("SECURAGENTX_INSECURE", "").lower() in ("1", "true", "yes")

from .._auth import Identity, auth_token_required
from .._models import (
    KnowledgeDocumentPublic,
    KnowledgeSearchHit,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    Page,
    error_response,
    success_response,
)

logger = logging.getLogger("securagentx.api.routes.knowledge")

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# Upload size cap — SecurAgentX uses 32 MB for multipart memory buffer.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024


# ---------------------------------------------------------------------------
# SSRF protection (issue 34)
# ---------------------------------------------------------------------------
# Networks that must NEVER be reachable via the ``url=`` payload of
# ``POST /knowledge/documents``. Without this guard, an authenticated user
# could abuse the server-side fetch to:
#   * read AWS / GCP / Azure instance metadata (``169.254.169.254``)
#   * port-scan and probe internal services (RFC1918 space)
#   * reach loopback services (databases, admin panels, etc.)
# The list is intentionally conservative — extend cautiously and NEVER
# add a public-IP allowlist exception without an explicit business need.
BLOCKED_RANGES: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("169.254.169.254/32"),  # Cloud metadata (AWS/GCP/Azure)
    ipaddress.ip_network("127.0.0.0/8"),          # IPv4 loopback
    ipaddress.ip_network("10.0.0.0/8"),           # RFC1918 private
    ipaddress.ip_network("172.16.0.0/12"),        # RFC1918 private
    ipaddress.ip_network("192.168.0.0/16"),       # RFC1918 private
    ipaddress.ip_network("0.0.0.0/8"),            # "This network"
    ipaddress.ip_network("::1/128"),              # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),             # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),            # IPv6 link-local
]


def is_ssrf_target(url: str) -> bool:
    """Return True if ``url`` resolves to a blocked SSRF target.

    Performs a DNS lookup on the URL's hostname and checks the resolved
    IP against :data:`BLOCKED_RANGES`. A missing hostname, an
    unresolvable hostname, or an IP in any blocked range all return
    ``True`` (i.e. "treat as SSRF — block").

    Note: this is a point-in-time check. DNS rebinding attacks (where
    the resolver flips between a public and a private IP) require
    additional defences (e.g. pinning the resolved IP for the actual
    fetch). The current guard blocks the common cases: cloud-metadata
    exfiltration and direct internal-address probes.
    """
    # Check 1 — scheme allowlist (raises ValueError on disallowed scheme).
    try:
        validate_url_scheme(url)
    except ValueError:
        return True

    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return True
    hostname = parsed.hostname
    if not hostname:
        return True
    try:
        # Resolve to a list of IPs (handles round-robin DNS).
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # Unresolvable → block (do not let the fetch layer surface the
        # DNS error to the client, which would enable DNS enumeration).
        return True
    for info in infos:
        ip_str = info[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        # Check the resolved IP against every blocked range. For IPv6
        # addresses that are IPv4-mapped (e.g. ::ffff:127.0.0.1), also
        # unwrap to the IPv4 form and re-check (C-002 fix).
        candidates = [ip_obj]
        if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
            candidates.append(ip_obj.ipv4_mapped)
        for cand in candidates:
            for network in BLOCKED_RANGES:
                if cand in network:
                    return True
    return False


# ---------------------------------------------------------------------------
# GET /knowledge/documents
# ---------------------------------------------------------------------------


@router.get("/documents", summary="List knowledge documents (paginated)")
async def list_documents(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    identity: Identity = Depends(auth_token_required),
) -> dict[str, Any]:
    """Return a paginated list of the user's knowledge documents."""
    p = Page(page=page, per_page=per_page)
    store = getattr(request.app.state, "knowledge", None)
    if store is None:
        return success_response(
            {"items": [], "page": p.page, "per_page": p.per_page, "total": 0}
        )
    try:
        rows: list[dict[str, Any]] = await store.list_documents(
            user_id=identity.user_id,
            offset=p.offset,
            limit=p.per_page,
        )
        total: int = await store.count_documents(identity.user_id)
    except Exception:
        logger.exception("knowledge.list_documents failed")
        return success_response(
            {"items": [], "page": p.page, "per_page": p.per_page, "total": 0}
        )

    items = [_row_to_public(r).model_dump() for r in rows]
    return success_response(
        {
            "items": items,
            "page": p.page,
            "per_page": p.per_page,
            "total": total,
        }
    )


# ---------------------------------------------------------------------------
# POST /knowledge/documents
# ---------------------------------------------------------------------------


@router.post("/documents", summary="Upload a knowledge document")
async def upload_document(
    request: Request,
    identity: Identity = Depends(auth_token_required),
    title: Optional[str] = Form(default=None),
    url: Optional[str] = Form(default=None),
    text: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
) -> JSONResponse:
    """Upload a document to the knowledge base.

    Accepts one of three payload shapes (mutually exclusive):

    * ``file``  — multipart/form-data file upload (binary content).
    * ``url``   — fetch the document from a URL (server-side).
    * ``text``  — raw text body.

    The document is queued for asynchronous processing (extraction,
    chunking, embedding). The response returns the document row with
    ``status="queued"``.
    """
    develop = bool(getattr(request.app.state, "develop", False))
    store = getattr(request.app.state, "knowledge", None)
    if store is None:
        return JSONResponse(
            status_code=503,
            content=error_response(
                "service_unavailable",
                "Knowledge store not configured",
                develop=develop,
            ),
        )

    # Pick the payload source — exactly one is required.
    if file is not None:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                status_code=413,
                content=error_response(
                    "bad_request",
                    f"Upload too large: {len(content)} bytes "
                    f"(max {MAX_UPLOAD_BYTES})",
                    develop=develop,
                ),
            )
        doc_title = title or (file.filename or "uploaded-file")
        mime = file.content_type or "application/octet-stream"
        try:
            row = await store.create_document_from_bytes(
                user_id=identity.user_id,
                title=doc_title,
                content=content,
                mime_type=mime,
                filename=file.filename,
            )
        except Exception as exc:
            logger.exception("create_document_from_bytes failed")
            return JSONResponse(
                status_code=500,
                content=error_response(
                    "internal",
                    "Failed to store document",
                    error=str(exc),
                    develop=develop,
                ),
            )
    elif url:
        # SECURITY (issue 34): SSRF protection — block requests to internal
        # networks (RFC1918, loopback, cloud metadata) before the store
        # fetches the URL server-side. Without this, an attacker could
        # exfiltrate cloud credentials by submitting
        # ``url=http://169.254.169.254/latest/meta-data/...`` or probe
        # internal services via ``url=http://10.0.0.1:8080/admin``.
        if is_ssrf_target(url):
            logger.warning("SSRF target rejected: %r", url)
            return JSONResponse(
                status_code=422,
                content=error_response(
                    "bad_request",
                    "URL targets a blocked internal address "
                    "(loopback, RFC1918, or cloud metadata)",
                    develop=develop,
                ),
            )
        try:
            row = await store.create_document_from_url(
                user_id=identity.user_id,
                title=title or url,
                url=url,
            )
        except Exception as exc:
            logger.exception("create_document_from_url failed")
            return JSONResponse(
                status_code=500,
                content=error_response(
                    "internal",
                    "Failed to fetch URL",
                    error=str(exc),
                    develop=develop,
                ),
            )
    elif text is not None and text:
        try:
            row = await store.create_document_from_text(
                user_id=identity.user_id,
                title=title or "inline-text",
                text=text,
            )
        except Exception as exc:
            logger.exception("create_document_from_text failed")
            return JSONResponse(
                status_code=500,
                content=error_response(
                    "internal",
                    "Failed to store text",
                    error=str(exc),
                    develop=develop,
                ),
            )
    else:
        return JSONResponse(
            status_code=400,
            content=error_response(
                "bad_request",
                "Must provide one of: file, url, or text",
                develop=develop,
            ),
        )

    return JSONResponse(
        status_code=201,
        content=success_response(_row_to_public(row).model_dump()),
    )


# ---------------------------------------------------------------------------
# DELETE /knowledge/documents/{id}
# ---------------------------------------------------------------------------


@router.delete("/documents/{doc_id}", summary="Delete a knowledge document")
async def delete_document(
    doc_id: int,
    request: Request,
    identity: Identity = Depends(auth_token_required),
) -> JSONResponse:
    """Delete a document AND all its vector chunks.

    Idempotent — deleting a non-existent ID returns 404. Deleting an
    already-deleted document returns 200 (mirrors the Go original).
    """
    develop = bool(getattr(request.app.state, "develop", False))
    store = getattr(request.app.state, "knowledge", None)
    if store is None:
        return JSONResponse(
            status_code=503,
            content=error_response(
                "service_unavailable",
                "Knowledge store not configured",
                develop=develop,
            ),
        )

    try:
        deleted: bool = await store.delete_document(
            doc_id=doc_id, user_id=identity.user_id
        )
    except Exception as exc:
        logger.exception("delete_document failed")
        return JSONResponse(
            status_code=500,
            content=error_response(
                "internal",
                "Failed to delete document",
                error=str(exc),
                develop=develop,
            ),
        )

    if not deleted:
        return JSONResponse(
            status_code=404,
            content=error_response(
                "not_found",
                f"Document not found: {doc_id}",
                develop=develop,
            ),
        )

    return JSONResponse(
        status_code=200,
        content=success_response({"deleted": True, "id": doc_id}),
    )


# ---------------------------------------------------------------------------
# POST /knowledge/search
# ---------------------------------------------------------------------------


@router.post("/search", summary="Semantic search across the knowledge base")
async def search_knowledge(
    body: KnowledgeSearchRequest,
    request: Request,
    identity: Identity = Depends(auth_token_required),
) -> JSONResponse:
    """Run a semantic search across all of the user's documents.

    Returns top-K hits with snippets + scores in the
    ``KnowledgeSearchResponse`` shape.
    """
    develop = bool(getattr(request.app.state, "develop", False))
    store = getattr(request.app.state, "knowledge", None)
    if store is None:
        return JSONResponse(
            status_code=503,
            content=error_response(
                "service_unavailable",
                "Knowledge store not configured",
                develop=develop,
            ),
        )

    t0 = time.time()
    try:
        hits_raw: list[dict[str, Any]] = await store.search(
            user_id=identity.user_id,
            query=body.query,
            top_k=body.top_k,
            min_score=body.min_score,
        )
    except Exception as exc:
        logger.exception("knowledge.search failed")
        return JSONResponse(
            status_code=500,
            content=error_response(
                "internal",
                "Search failed",
                error=str(exc),
                develop=develop,
            ),
        )

    hits = [
        KnowledgeSearchHit(
            document_id=int(h.get("document_id", 0)),
            title=str(h.get("title", "")),
            snippet=str(h.get("snippet", "")),
            score=float(h.get("score", 0.0)),
            metadata=dict(h.get("metadata", {}) or {}),
        )
        for h in hits_raw
    ]
    response = KnowledgeSearchResponse(
        query=body.query,
        hits=hits,
        took_ms=int((time.time() - t0) * 1000),
    )
    return JSONResponse(
        status_code=200,
        content=success_response(response.model_dump()),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_public(row: dict[str, Any]) -> KnowledgeDocumentPublic:
    """Coerce a raw store row into a ``KnowledgeDocumentPublic`` model."""
    return KnowledgeDocumentPublic(
        id=int(row.get("id", 0)),
        title=str(row.get("title", "")),
        type=str(row.get("type", "file")),
        mime_type=str(row.get("mime_type")) if row.get("mime_type") else None,
        size_bytes=int(row.get("size_bytes", 0)),
        status=str(row.get("status", "queued")),
        created_at=int(row.get("created_at", 0)),
        updated_at=(
            int(row["updated_at"]) if row.get("updated_at") else None
        ),
        checksum=str(row.get("checksum")) if row.get("checksum") else None,
    )


__all__ = ["router"]
