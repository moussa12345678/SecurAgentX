"""Multi-format report export for SecurAgentX.

Renders a flow (with its tasks + subtasks) to any of the supported output
formats. All heavyweight third-party imports (``reportlab``, ``markdown_it``,
``pygments``) are performed *lazily* inside the functions that need them, so
the module imports cleanly even when those dependencies are not installed.

Public API (brutal-test contract)
---------------------------------
- ``SUPPORTED_FORMATS`` — constant list of format names
- ``export_report(flow_id, format, *, provider)`` — *async*, returns ``bytes``
- ``generate_filename(flow_id, title, format)`` — *async*, returns ``str``
- ``render_html(md, include_css=False)`` — returns a full HTML document string
- ``_slugify_title(title)`` — returns a filesystem-safe slug

Supplementary API (task-description contract)
---------------------------------------------
- ``supported_formats()`` — returns ``list[str]``
- ``ReportExporter`` — class wrapper around a findings list
- ``export_findings(findings, format, output_path=None)`` — convenience helper
"""

from __future__ import annotations

import csv
import html as _html_mod
import io
import json
import logging
import string
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__: list[str] = [
    "SUPPORTED_FORMATS",
    "export_report",
    "generate_filename",
    "render_html",
    "supported_formats",
    "ReportExporter",
    "export_findings",
    "_slugify_title",
]

# ---------------------------------------------------------------------------
# Format registry
# ---------------------------------------------------------------------------

#: Formats honoured by :func:`export_report` / :func:`ReportExporter.export`.
SUPPORTED_FORMATS: list[str] = ["markdown", "pdf", "html", "json", "csv", "sarif"]

#: Map of format name → canonical file extension (used by ``generate_filename``).
_FORMAT_EXTENSIONS: dict[str, str] = {
    "markdown": "md",
    "pdf": "pdf",
    "html": "html",
    "json": "json",
    "csv": "csv",
    "sarif": "sarif",
}


def supported_formats() -> list[str]:
    """Return a fresh copy of the supported format list."""
    return list(SUPPORTED_FORMATS)


# ---------------------------------------------------------------------------
# Slugify & filename helpers
# ---------------------------------------------------------------------------

_SLUG_ALLOWED: frozenset[str] = frozenset(string.ascii_lowercase + string.digits + "_")


def _slugify_title(title: str) -> str:
    """Slugify ``title`` into a filesystem-safe token.

    Transformation rules (verified by the brutal stress tests):
    - lowercase
    - spaces → underscores
    - every character outside ``[a-z0-9_]`` is dropped (so ``/`` and ``\\``
      never survive, and emoji / CJK / punctuation are stripped)
    - truncated to 150 characters
    - leading/trailing underscores stripped

    Examples
    --------
    >>> _slugify_title("Pentest Report!")
    'pentest_report'
    >>> _slugify_title("")
    ''
    """
    if not title:
        return ""
    s = str(title).lower().strip()
    s = s.replace(" ", "_")
    s = "".join(ch for ch in s if ch in _SLUG_ALLOWED)
    if len(s) > 150:
        s = s[:150]
    return s.strip("_")


async def generate_filename(flow_id: int, title: str, format: str) -> str:
    """Build the canonical export filename.

    Pattern: ``report_flow_{id}_{slug}_{timestamp}.{ext}`` where the
    timestamp is 14 digits (``YYYYMMDDHHMMSS`` in UTC). Unknown formats
    fall back to ``.txt``.
    """
    slug = _slugify_title(title) or "untitled"
    ext = _FORMAT_EXTENSIONS.get((format or "").lower().strip(), "txt")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"report_flow_{flow_id}_{slug}_{ts}.{ext}"


# ---------------------------------------------------------------------------
# Markdown generation (lazy import of securagentx.reports.markdown)
# ---------------------------------------------------------------------------

def _fallback_generate_markdown(flow: Any, tasks: list[Any], subtasks: list[Any]) -> str:
    """Minimal markdown generator used when ``securagentx.reports.markdown``
    is not importable. Produces the same overall shape (H1 title, TOC, per-task
    H3 sections with input/result) so downstream renderers (HTML, PDF) work.
    """
    title = getattr(flow, "title", None) or "Report"
    lines: list[str] = [f"# {title}", ""]
    if not tasks:
        lines.append("No tasks available.")
        return "\n".join(lines)

    lines.append("## Table of Contents")
    for t in tasks:
        ttitle = getattr(t, "title", None) or f"task-{getattr(t, 'id', '?')}"
        anchor = _slugify_title(ttitle) or "task"
        lines.append(f"- [{ttitle}](#{anchor})")
    lines.append("---")

    # Index subtasks by their parent task id for quick lookup.
    subtasks_by_task: dict[Any, list[Any]] = {}
    for st in subtasks or []:
        subtasks_by_task.setdefault(getattr(st, "task_id", None), []).append(st)

    for t in tasks:
        ttitle = getattr(t, "title", None) or f"task-{getattr(t, 'id', '?')}"
        lines.append("")
        lines.append(f"### {ttitle}")
        inp = getattr(t, "input", None) or ""
        res = getattr(t, "result", None) or ""
        if inp:
            lines.append("")
            lines.append("**Input:**")
            lines.append("")
            lines.append(inp)
        if res:
            lines.append("")
            lines.append("**Result:**")
            lines.append("")
            lines.append(res)
        for st in subtasks_by_task.get(getattr(t, "id", None), []):
            stitle = getattr(st, "title", None) or "subtask"
            sres = getattr(st, "result", None) or ""
            lines.append("")
            lines.append(f"#### {stitle}")
            if sres:
                lines.append("")
                lines.append(sres)
    lines.append("")
    return "\n".join(lines)


def _get_markdown_generator():
    """Return ``generate_report_markdown`` from ``securagentx.reports.markdown``
    if importable; otherwise return the local fallback implementation.

    The import is performed lazily so that ``export.py`` can be imported even
    before the sibling ``markdown`` module has been created.
    """
    try:
        from securagentx.reports.markdown import generate_report_markdown
        if callable(generate_report_markdown):
            return generate_report_markdown
    except Exception as e:
        logger.debug("Suppressed Exception: %s", e)
    return _fallback_generate_markdown


# ---------------------------------------------------------------------------
# HTML rendering (lazy markdown_it / pygments imports)
# ---------------------------------------------------------------------------

_MD_RENDERER = None  # type: Optional[Any]


def _get_md_renderer():
    """Lazily build and cache a ``markdown_it.MarkdownIt`` instance.

    Uses the ``default`` preset which has ``html=False`` — raw HTML in the
    markdown source is *escaped* (rendered as visible text), which is the
    XSS-safe behaviour verified by the brutal test suite. ``javascript:``
    URLs in links are dropped entirely by markdown-it's built-in
    ``validateLink``.
    """
    global _MD_RENDERER
    if _MD_RENDERER is None:
        from markdown_it import MarkdownIt
        _MD_RENDERER = MarkdownIt("default")
    return _MD_RENDERER


def render_html(md: str, include_css: bool = False) -> str:
    """Render ``md`` (markdown source) into a full HTML document.

    - Raw HTML in the markdown is escaped (XSS-safe).
    - ``javascript:`` link URLs are dropped by markdown-it's validateLink.
    - When ``include_css`` is true, a ``<style>`` block containing the
      Pygments syntax-highlighting CSS is embedded in ``<head>``.
    """
    renderer = _get_md_renderer()
    body = renderer.render(md or "")

    style_tag = ""
    if include_css:
        try:
            from pygments.formatters import HtmlFormatter
            css = HtmlFormatter().get_style_defs(".highlight")
            style_tag = f"<style>\n{css}\n</style>\n" if css else ""
        except Exception:
            style_tag = ""

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"{style_tag}"
        "</head>\n"
        "<body>\n"
        f"{body}"
        "</body>\n"
        "</html>\n"
    )


# ---------------------------------------------------------------------------
# PDF rendering (lazy reportlab import)
# ---------------------------------------------------------------------------

def _render_pdf_bytes(md: str) -> bytes:
    """Render markdown text to PDF bytes.

    First tries to delegate to ``securagentx.reports.pdf.render_to_pdf_bytes``
    (the canonical implementation owned by the sibling ``pdf`` module). If
    that module is unavailable, falls back to a minimal reportlab-based
    renderer so that export still produces a valid ``%PDF``-prefixed blob.
    """
    try:
        from securagentx.reports.pdf import render_to_pdf_bytes
        if callable(render_to_pdf_bytes):
            return render_to_pdf_bytes(md)
    except Exception as e:
        logger.debug("Suppressed Exception: %s", e)
    return _render_pdf_bytes_reportlab(md)


def _render_pdf_bytes_reportlab(md: str) -> bytes:
    """Minimal reportlab-based PDF generator (fallback when ``reports.pdf``
    is not importable)."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Preformatted,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    story: list[Any] = []

    in_code = False
    code_lines: list[str] = []

    def _flush_code() -> None:
        nonlocal code_lines
        if code_lines:
            story.append(Preformatted("\n".join(code_lines), styles["Code"]))
            story.append(Spacer(1, 0.1 * inch))
            code_lines = []

    for raw_line in (md or "").split("\n"):
        line = raw_line.rstrip("\r")
        if line.startswith("```"):
            if in_code:
                _flush_code()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            story.append(Spacer(1, 0.1 * inch))
            continue
        if line.startswith("###### "):
            story.append(Paragraph(_html_mod.escape(line[7:]), styles["Heading6"]))
        elif line.startswith("##### "):
            story.append(Paragraph(_html_mod.escape(line[6:]), styles["Heading5"]))
        elif line.startswith("#### "):
            story.append(Paragraph(_html_mod.escape(line[5:]), styles["Heading4"]))
        elif line.startswith("### "):
            story.append(Paragraph(_html_mod.escape(line[4:]), styles["Heading3"]))
        elif line.startswith("## "):
            story.append(Paragraph(_html_mod.escape(line[3:]), styles["Heading2"]))
        elif line.startswith("# "):
            story.append(Paragraph(_html_mod.escape(line[2:]), styles["Title"]))
        elif line.startswith("- ") or line.startswith("* "):
            story.append(Paragraph("&#8226; " + _html_mod.escape(line[2:]), styles["Normal"]))
        else:
            story.append(Paragraph(_html_mod.escape(line), styles["Normal"]))
    _flush_code()

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# JSON / CSV / SARIF payload builders
# ---------------------------------------------------------------------------

def _flow_to_dict(flow: Any) -> dict[str, Any]:
    return {
        "id": getattr(flow, "id", None),
        "title": getattr(flow, "title", "") or "",
        "status": str(getattr(flow, "status", "") or ""),
    }


def _task_to_dict(task: Any) -> dict[str, Any]:
    return {
        "id": getattr(task, "id", None),
        "title": getattr(task, "title", "") or "",
        "input": getattr(task, "input", "") or "",
        "result": getattr(task, "result", "") or "",
        "status": str(getattr(task, "status", "") or ""),
    }


def _subtask_to_dict(subtask: Any) -> dict[str, Any]:
    return {
        "id": getattr(subtask, "id", None),
        "title": getattr(subtask, "title", "") or "",
        "description": getattr(subtask, "description", "") or "",
        "result": getattr(subtask, "result", "") or "",
        "task_id": getattr(subtask, "task_id", None),
    }


def _build_json_payload(flow: Any, tasks: list[Any], subtasks: list[Any]) -> dict[str, Any]:
    return {
        "flow": _flow_to_dict(flow),
        "tasks": [_task_to_dict(t) for t in (tasks or [])],
        "subtasks": [_subtask_to_dict(st) for st in (subtasks or [])],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_csv(flow: Any, tasks: list[Any]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["flow_id", "task_id", "title", "status", "input", "result"])
    flow_id = getattr(flow, "id", "")
    for t in tasks or []:
        writer.writerow([
            flow_id,
            getattr(t, "id", ""),
            getattr(t, "title", "") or "",
            str(getattr(t, "status", "") or ""),
            getattr(t, "input", "") or "",
            getattr(t, "result", "") or "",
        ])
    return buf.getvalue()


def _build_sarif(flow: Any, tasks: list[Any], subtasks: list[Any]) -> dict[str, Any]:
    """Build a SARIF 2.1.0 log object.

    Each task becomes one ``result`` entry; rules are emitted with one entry
    per task so downstream tooling can correlate findings back to their rule.
    Spec: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
    """
    tasks = tasks or []
    flow_id = getattr(flow, "id", "?")
    results: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    for t in tasks:
        tid = getattr(t, "id", "?")
        rule_id = f"SA-{tid}"
        title = getattr(t, "title", "") or f"task-{tid}"
        message_text = getattr(t, "result", "") or title
        rules.append({
            "id": rule_id,
            "name": _slugify_title(title) or f"rule-{tid}",
            "shortDescription": {"text": title},
        })
        results.append({
            "ruleId": rule_id,
            "level": "note",
            "message": {"text": message_text},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": f"flows/{flow_id}/tasks/{tid}",
                    },
                },
            }],
        })
    return {
        "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "SecurAgentX",
                    "semanticVersion": "1.0.0",
                    "informationUri": "https://github.com/moussa12345678/SecurAgentX",
                    "rules": rules,
                },
            },
            "results": results,
        }],
    }


# ---------------------------------------------------------------------------
# Main async export_report (brutal-test entry point)
# ---------------------------------------------------------------------------

async def export_report(flow_id: int, format: str, *, provider: Any) -> bytes:
    """Export a flow's report as ``bytes`` in the requested ``format``.

    Parameters
    ----------
    flow_id
        Identifier of the flow to export.
    format
        One of :data:`SUPPORTED_FORMATS` (case-insensitive).
    provider
        Object exposing the async methods ``get_flow(flow_id)``,
        ``list_tasks(flow_id)`` and ``list_subtasks(task_id)``.

    Returns
    -------
    bytes
        The rendered report payload in the requested format.

    Raises
    ------
    ValueError
        If ``format`` is not in :data:`SUPPORTED_FORMATS`.
    """
    fmt = (format or "").lower().strip()
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported export format: {format!r}. "
            f"Supported: {SUPPORTED_FORMATS}"
        )

    flow = await provider.get_flow(flow_id)
    tasks = await provider.list_tasks(flow_id) or []
    subtasks: list[Any] = []
    for t in tasks:
        tid = getattr(t, "id", None)
        if tid is None:
            continue
        try:
            sts = await provider.list_subtasks(tid)
        except Exception:
            sts = []
        if sts:
            subtasks.extend(sts)

    if fmt == "markdown":
        gen = _get_markdown_generator()
        md = gen(flow, tasks, subtasks)
        return (md or "").encode("utf-8")

    if fmt == "html":
        gen = _get_markdown_generator()
        md = gen(flow, tasks, subtasks)
        return render_html(md, include_css=True).encode("utf-8")

    if fmt == "json":
        payload = _build_json_payload(flow, tasks, subtasks)
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    if fmt == "csv":
        return _build_csv(flow, tasks).encode("utf-8")

    if fmt == "sarif":
        payload = _build_sarif(flow, tasks, subtasks)
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    if fmt == "pdf":
        gen = _get_markdown_generator()
        md = gen(flow, tasks, subtasks)
        return _render_pdf_bytes(md)

    # Defensive — should be unreachable thanks to the membership check above.
    raise ValueError(f"Unsupported export format: {format!r}")


# ---------------------------------------------------------------------------
# Class-based ReportExporter (task-description API)
# ---------------------------------------------------------------------------

class ReportExporter:
    """Class-based exporter wrapping a flat list of findings.

    Provided for API completeness per the task-description contract. The
    brutal test suite drives :func:`export_report` directly, but this class
    offers a convenient OO façade for ad-hoc callers.
    """

    def __init__(self, findings: list, metadata: Optional[dict] = None) -> None:
        self.findings: list = list(findings or [])
        self.metadata: dict = dict(metadata or {})

    # ── markdown ──────────────────────────────────────────────────────────
    def to_markdown(self, output_path: Optional[str] = None) -> str:
        title = self.metadata.get("title", "Findings Report")
        lines: list[str] = [f"# {title}", ""]
        if not self.findings:
            lines.append("No findings available.")
        else:
            for i, finding in enumerate(self.findings, 1):
                if isinstance(finding, dict):
                    heading = finding.get("title") or finding.get("name") or f"Finding {i}"
                    lines.append(f"## {i}. {heading}")
                    for key, value in finding.items():
                        if key in ("title", "name"):
                            continue
                        lines.append(f"- **{key}**: {value}")
                else:
                    lines.append(f"## {i}. {finding}")
                lines.append("")
        md = "\n".join(lines)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(md)
        return md

    # ── html ──────────────────────────────────────────────────────────────
    def to_html(self, output_path: Optional[str] = None) -> str:
        md = self.to_markdown()
        page = render_html(md, include_css=True)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(page)
        return page

    # ── json ──────────────────────────────────────────────────────────────
    def to_json(self, output_path: Optional[str] = None) -> str:
        payload = {
            "metadata": self.metadata,
            "findings": [
                finding if isinstance(finding, dict) else {"value": str(finding)}
                for finding in self.findings
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(text)
        return text

    # ── csv ───────────────────────────────────────────────────────────────
    def to_csv(self, output_path: Optional[str] = None) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        if self.findings and isinstance(self.findings[0], dict):
            headers = list(self.findings[0].keys())
            writer.writerow(headers)
            for finding in self.findings:
                writer.writerow([finding.get(h, "") for h in headers])
        else:
            writer.writerow(["finding"])
            for finding in self.findings:
                writer.writerow([str(finding)])
        text = buf.getvalue()
        if output_path:
            with open(output_path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        return text

    # ── sarif ─────────────────────────────────────────────────────────────
    def to_sarif(self, output_path: Optional[str] = None) -> str:
        results: list[dict[str, Any]] = []
        rules: list[dict[str, Any]] = []
        for i, finding in enumerate(self.findings, 1):
            rule_id = f"SA-{i}"
            if isinstance(finding, dict):
                title = finding.get("title") or finding.get("name") or f"Finding {i}"
                message_text = finding.get("description") or finding.get("message") or str(finding)
            else:
                title = f"Finding {i}"
                message_text = str(finding)
            rules.append({
                "id": rule_id,
                "name": _slugify_title(title) or f"rule-{i}",
                "shortDescription": {"text": title},
            })
            results.append({
                "ruleId": rule_id,
                "level": "note",
                "message": {"text": message_text},
            })
        sarif = {
            "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": self.metadata.get("tool", "SecurAgentX"),
                        "rules": rules,
                    },
                },
                "results": results,
            }],
        }
        text = json.dumps(sarif, ensure_ascii=False, indent=2)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(text)
        return text

    # ── pdf ───────────────────────────────────────────────────────────────
    def to_pdf(self, output_path: str) -> bool:
        """Render findings to PDF at ``output_path``. Returns success."""
        try:
            md = self.to_markdown()
            data = _render_pdf_bytes(md)
            with open(output_path, "wb") as fh:
                fh.write(data)
            return True
        except Exception:
            return False

    # ── dispatch ──────────────────────────────────────────────────────────
    def export(self, format: str, output_path: Optional[str] = None) -> str:
        fmt = (format or "").lower().strip()
        if fmt == "markdown":
            return self.to_markdown(output_path)
        if fmt == "html":
            return self.to_html(output_path)
        if fmt == "json":
            return self.to_json(output_path)
        if fmt == "csv":
            return self.to_csv(output_path)
        if fmt == "sarif":
            return self.to_sarif(output_path)
        if fmt == "pdf":
            if not output_path:
                raise ValueError("PDF export requires an output_path")
            self.to_pdf(output_path)
            return output_path
        raise ValueError(
            f"Unsupported format: {format!r}. Supported: {SUPPORTED_FORMATS}"
        )


def export_findings(findings: list, format: str, output_path: Optional[str] = None) -> str:
    """Convenience helper: build a :class:`ReportExporter` and dispatch."""
    return ReportExporter(findings).export(format, output_path)
