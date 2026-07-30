"""securagentx/reports/markdown.py — Markdown report assembly.

This module turns a Flow → Task → Subtask hierarchy (duck-typed objects
exposing the expected ``title``/``input``/``result``/``status``/``subtasks``
attributes) into a GitHub-Flavored-Markdown report.
The primary entry point is :func:`generate_report_markdown`, which is
invoked by the multi-format export pipeline (see
:mod:`securagentx.reports.export`).

(The historical ``securagentx.flows`` package and the
``GET /flows/{id}/report`` REST route have been removed as dead code;
this module now operates purely on structural duck-typed inputs.)

The report layout is::

    # {flow.title}

    ## Table of Contents

    - [task-1.title](#anchor-1)
    - [task-2.title](#anchor-2)

    ---

    ### {task-1.title}

    {task-1.input with headers shifted by 3 levels}

    **Result:** {status_emoji}

    {task-1.result}

    #### Subtask: {subtask-1a.title}

    {subtask-1a.description}

    **Result:** {status_emoji}

    {subtask-1a.result}

    ### {task-2.title}
    ...

In addition to the flow-assembler, this module exposes a small set of
helper primitives used by the report builder (and exercised directly by
the brutal integration test-suite):

* :func:`slugify_github` — GitHub-slugger-compatible heading anchor.
* :func:`shift_markdown_headers` — bump ATX header levels (capped at H6).
* :func:`generate_anchors` — disambiguate duplicate headings with -1, -2, ...
* :func:`status_emoji` — render a flow/task/subtask status as a glyph.

A higher-level :class:`MarkdownReport` builder plus the convenience
functions :func:`generate_markdown_report` and :func:`findings_to_markdown`
are provided for security-finding-oriented reports (used by the
vuln-finder pipeline and the TUI dashboard exporter).

All public functions are pure (no I/O, no shared mutable state) and are
safe to call concurrently from multiple threads.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    # Constants
    "DEFAULT_STATUS_EMOJI",
    "STATUS_EMOJI",
    # Flow → Task → Subtask assembly
    "generate_report_markdown",
    # Heading / slug helpers
    "slugify_github",
    "generate_anchors",
    "shift_markdown_headers",
    "status_emoji",
    # Finding-oriented builder API
    "MarkdownReport",
    "generate_markdown_report",
    "findings_to_markdown",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default glyph for unknown / unset statuses (📝 memo).
DEFAULT_STATUS_EMOJI: str = "\U0001F4DD"

#: Mapping of known status strings (lowercase) → emoji glyphs.
STATUS_EMOJI: dict[str, str] = {
    "created": "\U0001F4DD",  # 📝
    "running": "\u26A1",       # ⚡
    "waiting": "\u23F3",       # ⏳
    "finished": "\u2705",      # ✅
    "failed": "\u274C",        # ❌
}

#: Regex matching an ATX header line opener (1-6 hashes followed by
#: whitespace or end-of-line). The lookahead ``(?=\s|$)`` ensures we do
#: not consume the trailing space, so we can splice in the new hash run
#: without rebuilding the rest of the line.
_ATX_HEADER_RE = re.compile(r"^(#{1,6})(?=\s|$)")

#: Characters to drop in :func:`slugify_github` — anything that is not
#: an ASCII lowercase letter, digit, space, or hyphen. Mirrors the
#: JavaScript ``github-slugger`` package's ``[^\w\- ]+`` filter
#: (JavaScript's ``\w`` is ASCII-only, unlike Python's default).
_SLUG_DROP_RE = re.compile(r"[^a-z0-9 \-]")

#: One-or-more whitespace runs — collapsed to a single hyphen by
#: :func:`slugify_github`.
_SLUG_SPACE_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# slugify_github
# ---------------------------------------------------------------------------

def slugify_github(text: str) -> str:
    """Return a GitHub-slugger-compatible anchor for ``text``.

    The transformation mirrors the JavaScript ``github-slugger`` package
    used by GitHub Flavored Markdown for heading anchors:

    1. Lower-case the input.
    2. Strip leading/trailing whitespace.
    3. Drop every character that is not an ASCII alphanumeric, space, or
       hyphen. (Emoji, accents, and punctuation are removed — this
       matches JS ``\\w`` which is ASCII-only, unlike Python's default
       Unicode-aware ``\\w``.)
    4. Collapse runs of whitespace into a single hyphen.
    5. Strip leading/trailing hyphens.

    Examples::

        >>> slugify_github("Hello World")
        'hello-world'
        >>> slugify_github("Café ☕ Table")
        'caf-table'
        >>> slugify_github("⚡ Task Title")
        'task-title'
        >>> slugify_github("📝 created")
        'created'
        >>> slugify_github("")
        ''
    """
    if not text:
        return ""
    # 1. Lower-case + trim.
    s = text.lower().strip()
    # 2. Drop everything that is not [a-z0-9 space -].
    s = _SLUG_DROP_RE.sub("", s)
    # 3. Collapse whitespace runs into a single hyphen.
    s = _SLUG_SPACE_RE.sub("-", s)
    # 4. Strip leading/trailing hyphens.
    return s.strip("-")


# ---------------------------------------------------------------------------
# generate_anchors
# ---------------------------------------------------------------------------

def generate_anchors(headings: Sequence[str]) -> dict[str, str]:
    """Map each heading string to a unique anchor.

    The first occurrence of a heading receives the bare slug produced by
    :func:`slugify_github`; subsequent occurrences of the same heading
    string receive ``{slug}-1``, ``{slug}-2``, ... (matching the
    GitHub-slugger duplicate-suffix convention).

    Note: because the return type is ``dict``, if the *same* heading
    string appears multiple times the *last* occurrence's anchor wins
    (dict-overwrite semantics). This mirrors how GitHub renders multiple
    same-titled headings: the in-page anchor link always points to the
    last occurrence.

    Examples::

        >>> generate_anchors(["Intro", "Intro", "Intro", "Outro"])
        {'Intro': 'intro-2', 'Outro': 'outro'}
        >>> generate_anchors(["A", "B", "C", "D"])
        {'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd'}
    """
    result: dict[str, str] = {}
    counts: dict[str, int] = {}
    for heading in headings:
        slug = slugify_github(heading)
        if slug in counts:
            counts[slug] += 1
            anchor = f"{slug}-{counts[slug]}"
        else:
            counts[slug] = 0
            anchor = slug
        result[heading] = anchor
    return result


# ---------------------------------------------------------------------------
# shift_markdown_headers
# ---------------------------------------------------------------------------

def shift_markdown_headers(text: str, n: int = 1) -> str:
    """Shift every ATX header in ``text`` by ``n`` levels (capped at H6).

    Non-header lines are left untouched. ``n == 0`` (or empty input)
    returns the input unchanged. Headers shifted beyond level 6 are
    capped at ``######`` (the maximum ATX level per CommonMark).

    Examples::

        >>> shift_markdown_headers("# H1\\n## H2", 3)
        '#### H1\\n##### H2'
        >>> shift_markdown_headers("# H1", 6)
        '###### H1'
        >>> shift_markdown_headers("", 3)
        ''
        >>> shift_markdown_headers("regular text", 3)
        'regular text'
    """
    if not text or n == 0:
        return text
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        m = _ATX_HEADER_RE.match(line)
        if m is None:
            out.append(line)
            continue
        current = len(m.group(1))
        new_level = min(current + n, 6)
        # Splice the new hash run in place of the old one; preserve
        # everything after the original hashes (including the space).
        rest = line[current:]
        out.append("#" * new_level + rest)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# status_emoji
# ---------------------------------------------------------------------------

def status_emoji(status: Any) -> str:
    """Return the emoji glyph for a status string (or enum value).

    Unknown / ``None`` values fall back to :data:`DEFAULT_STATUS_EMOJI`
    (📝). Enum values that expose a ``.value`` attribute are unwrapped
    before lookup. The lookup is case-insensitive on the string form.

    Examples::

        >>> status_emoji("created")   # 📝
        '📝'
        >>> status_emoji("running")    # ⚡
        '⚡'
        >>> status_emoji("finished")   # ✅
        '✅'
        >>> status_emoji("failed")     # ❌
        '❌'
        >>> status_emoji("waiting")    # ⏳
        '⏳'
        >>> status_emoji("???")        # default 📝
        '📝'
        >>> status_emoji(None)         # default 📝
        '📝'
    """
    if status is None:
        return DEFAULT_STATUS_EMOJI
    # Enum values expose ``.value``; bare strings are used as-is.
    raw = getattr(status, "value", status)
    if not isinstance(raw, str):
        return DEFAULT_STATUS_EMOJI
    return STATUS_EMOJI.get(raw.lower(), DEFAULT_STATUS_EMOJI)


# ---------------------------------------------------------------------------
# generate_report_markdown — Flow → Task → Subtask assembly
# ---------------------------------------------------------------------------

def _attr(obj: Any, name: str, default: Any = "") -> Any:
    """Return ``obj.name`` if it exists, else ``default`` (duck-typed).

    The flow/task/subtask objects passed to :func:`generate_report_markdown`
    may be Pydantic models, dataclasses, or simple namespace objects —
    all of which expose attributes via ``getattr``. ``None`` is treated
    as a missing object and returns ``default``.
    """
    if obj is None:
        return default
    return getattr(obj, name, default)


def _safe_id(obj: Any) -> int:
    """Coerce an object's ``id`` attribute to ``int`` (0 on failure)."""
    raw = _attr(obj, "id", 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def generate_report_markdown(
    flow: Any,
    tasks: Sequence[Any] | None,
    subtasks: Sequence[Any] | None,
) -> str:
    """Assemble a Markdown report from a Flow + its Tasks + Subtasks.

    Parameters
    ----------
    flow
        Any object with a ``title`` attribute (Pydantic ``Flow``,
        dataclass, namespace, ...). Used as the H1 of the report.
    tasks
        Sequence of task objects. Each task should expose ``id``,
        ``title``, ``input``, ``result``, and (optionally) ``status``
        attributes. ``None`` is treated as an empty list.
    subtasks
        Sequence of subtask objects. Each subtask should expose ``id``,
        ``title``, ``description``, ``result``, ``task_id``, and
        (optionally) ``status`` attributes. Subtasks are grouped under
        their parent task (matched by ``task_id`` → task ``id``).
        ``None`` is treated as an empty list.

    Returns
    -------
    str
        The assembled Markdown report. The string always starts with
        ``# {flow.title}`` followed by a Table of Contents and one H3
        section per task. When ``tasks`` is empty / ``None``, a short
        ``No tasks available.`` placeholder is returned instead.

    Notes
    -----
    * Tasks are emitted in ascending ID order for deterministic output.
    * Subtasks are emitted in ascending ID order within their parent
      task's section.
    * Task ``input`` has its ATX headers shifted by 3 levels (H1 → H4,
      H2 → H5, H3 → H6, capped at H6) so input headings slot underneath
      the H3 task title without breaking the document hierarchy.
    * Unicode, emoji, CJK, and large inputs (1 MB+) are preserved
      verbatim — no escaping, no truncation. This makes the report safe
      to feed back into prompt-injection-vulnerable downstream consumers
      (the input is rendered as data, not interpreted as instructions).
    * The function is pure (no I/O, no shared state) and safe to call
      concurrently from multiple threads.
    """
    title = _attr(flow, "title", "Untitled Flow") or "Untitled Flow"

    # Short-circuit: empty task list → canonical placeholder.
    if not tasks:
        return f"# {title}\n\nNo tasks available.\n"

    # Sort tasks by ID (ascending) for deterministic output.
    sorted_tasks = sorted(tasks, key=_safe_id)

    # Group subtasks by parent task_id; sort each group by subtask ID.
    subtask_map: dict[int, list[Any]] = {}
    if subtasks:
        for st in subtasks:
            tid_raw = _attr(st, "task_id", None)
            if tid_raw is None:
                continue
            try:
                tid = int(tid_raw)
            except (TypeError, ValueError):
                continue
            subtask_map.setdefault(tid, []).append(st)
        for tid in subtask_map:
            subtask_map[tid].sort(key=_safe_id)

    # Pre-compute anchors for the TOC bullets.
    task_titles = [_attr(t, "title", "") or "" for t in sorted_tasks]
    anchors = generate_anchors(task_titles)

    parts: list[str] = []

    # --- H1 + Table of Contents -----------------------------------------
    parts.append(f"# {title}\n")
    parts.append("## Table of Contents\n")
    for t in sorted_tasks:
        t_title = _attr(t, "title", "") or ""
        anchor = anchors.get(t_title, slugify_github(t_title))
        parts.append(f"- [{t_title}](#{anchor})\n")
    parts.append("\n---\n\n")

    # --- Per-task sections ----------------------------------------------
    for t in sorted_tasks:
        t_id = _safe_id(t)
        t_title = _attr(t, "title", "") or ""
        t_input = _attr(t, "input", "") or ""
        t_result = _attr(t, "result", "") or ""
        t_status = _attr(t, "status", None)

        parts.append(f"### {t_title}\n\n")

        # Task input: shift H1/H2/H3 down by 3 levels so they slot
        # underneath the H3 task title without breaking the hierarchy.
        if t_input:
            shifted = shift_markdown_headers(t_input, 3)
            parts.append(shifted)
            parts.append("\n\n")

        # Result block with status emoji.
        parts.append(f"**Result:** {status_emoji(t_status)}\n\n")
        if t_result:
            parts.append(t_result)
            parts.append("\n\n")

        # Subtasks for this task (sorted by ID above).
        for st in subtask_map.get(t_id, []):
            s_title = _attr(st, "title", "") or ""
            s_desc = _attr(st, "description", "") or ""
            s_result = _attr(st, "result", "") or ""
            s_status = _attr(st, "status", None)

            parts.append(f"#### Subtask: {s_title}\n\n")
            if s_desc:
                parts.append(s_desc)
                parts.append("\n\n")
            parts.append(f"**Result:** {status_emoji(s_status)}\n\n")
            if s_result:
                parts.append(s_result)
                parts.append("\n\n")

    return "".join(parts)


# ---------------------------------------------------------------------------
# MarkdownReport — finding-oriented builder API
# ---------------------------------------------------------------------------

class MarkdownReport:
    """A fluent builder for security-finding Markdown reports.

    This is a higher-level API than :func:`generate_report_markdown`:
    it is intended for vuln-finder / dashboard-export pipelines that
    emit structured findings (title, severity, CVSS, description,
    evidence, recommendation) rather than the Flow → Task → Subtask
    hierarchy.

    Example
    -------
    >>> rpt = MarkdownReport(title="Q3 Pentest")
    >>> rpt.add_metadata({"target": "example.com", "author": "alice"})
    >>> rpt.add_findings([{
    ...     "title": "SQL Injection",
    ...     "severity": "critical",
    ...     "cvss": 9.8,
    ...     "description": "Unsanitized input in /login",
    ...     "evidence": "sqlmap --dump",
    ...     "recommendation": "Use parameterized queries",
    ... }])
    >>> md = rpt.render()
    >>> "# Q3 Pentest" in md
    True
    """

    def __init__(
        self,
        title: str = "",
        *,
        metadata: Mapping[str, Any] | None = None,
        template: str = "default",
    ) -> None:
        self.title: str = title
        self.template: str = template
        self.metadata: dict[str, Any] = dict(metadata) if metadata else {}
        self.sections: list[tuple[str, int, str]] = []  # (text, level, kind)
        self.findings: list[Mapping[str, Any]] = []
        self._toc_entries: list[tuple[str, str]] = []  # (heading, anchor)

    # ── headings / paragraphs / code / tables / lists ─────────────────

    def add_heading(self, text: str, level: int = 1) -> "MarkdownReport":
        """Append an ATX heading at ``level`` (1–6, clamped)."""
        level = max(1, min(6, int(level)))
        self.sections.append((text, level, "heading"))
        anchor = slugify_github(text)
        self._toc_entries.append((text, anchor))
        return self

    def add_paragraph(self, text: str) -> "MarkdownReport":
        """Append a paragraph of body text."""
        self.sections.append((text, 0, "paragraph"))
        return self

    def add_code_block(self, code: str, language: str = "") -> "MarkdownReport":
        """Append a fenced code block."""
        self.sections.append((code, 0, f"code:{language}"))
        return self

    def add_table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[Any]],
    ) -> "MarkdownReport":
        """Append a GFM table."""
        lines: list[str] = []
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("|" + "|".join("---" for _ in headers) + "|")
        for row in rows:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        self.sections.append(("\n".join(lines), 0, "table"))
        return self

    def add_list(self, items: Iterable[str], ordered: bool = False) -> "MarkdownReport":
        """Append a bulleted (``ordered=False``) or numbered list."""
        items_list = list(items)
        if ordered:
            lines = [f"{i}. {item}" for i, item in enumerate(items_list, 1)]
        else:
            lines = [f"- {item}" for item in items_list]
        self.sections.append(("\n".join(lines), 0, "list"))
        return self

    # ── findings / metadata / TOC ─────────────────────────────────────

    def add_findings(self, findings: Iterable[Mapping[str, Any]]) -> "MarkdownReport":
        """Append a batch of finding dicts.

        Each finding may carry any of these keys (all optional):
        ``id``, ``title``, ``severity``, ``cvss``, ``cvss_vector``,
        ``status``, ``description``, ``evidence``, ``recommendation``.
        """
        for f in findings:
            self.findings.append(dict(f))
        return self

    def add_metadata(self, metadata: Mapping[str, Any]) -> "MarkdownReport":
        """Merge ``metadata`` into the report's metadata map."""
        self.metadata.update(dict(metadata))
        return self

    def add_toc(self) -> "MarkdownReport":
        """Insert a Table of Contents section at the current position."""
        self.sections.append(("", 0, "toc"))
        return self

    # ── rendering ─────────────────────────────────────────────────────

    def _render_metadata_block(self) -> str:
        if not self.metadata:
            return ""
        lines: list[str] = []
        for key, value in self.metadata.items():
            lines.append(f"**{key}:** {value}")
        return "\n\n".join(lines) + "\n\n"

    def _render_findings_table(self) -> str:
        if not self.findings:
            return ""
        headers = ["ID", "Title", "Severity", "CVSS", "Status"]
        rows: list[list[str]] = []
        for idx, f in enumerate(self.findings, 1):
            rows.append([
                str(f.get("id", idx)),
                str(f.get("title", "")),
                str(f.get("severity", "")),
                str(f.get("cvss", "")),
                str(f.get("status", "")),
            ])
        out: list[str] = []
        out.append("## Findings\n\n")
        out.append("| " + " | ".join(headers) + " |")
        out.append("|" + "|".join("---" for _ in headers) + "|")
        for row in rows:
            out.append("| " + " | ".join(row) + " |")
        out.append("\n")
        return "\n".join(out)

    def _render_finding_detail(self, f: Mapping[str, Any], idx: int) -> str:
        title = f.get("title", f"Finding {idx}")
        out: list[str] = []
        out.append(f"### {idx}. {title}\n")
        if f.get("severity"):
            out.append(f"- **Severity:** {f['severity']}")
        if f.get("cvss") is not None:
            out.append(f"- **CVSS:** {f['cvss']}")
        if f.get("cvss_vector"):
            out.append(f"- **CVSS Vector:** `{f['cvss_vector']}`")
        if f.get("status"):
            out.append(f"- **Status:** {f['status']}")
        if out[-1].startswith("- "):
            out.append("")
        if f.get("description"):
            out.append("**Description:**\n")
            out.append(str(f["description"]).rstrip() + "\n")
        if f.get("evidence"):
            out.append("**Evidence:**\n")
            out.append("```\n" + str(f["evidence"]).rstrip() + "\n```\n")
        if f.get("recommendation"):
            out.append("**Recommendation:**\n")
            out.append(str(f["recommendation"]).rstrip() + "\n")
        return "\n".join(out) + "\n"

    def _render_toc(self) -> str:
        if not self._toc_entries:
            return ""
        out: list[str] = ["## Table of Contents\n"]
        for text, anchor in self._toc_entries:
            out.append(f"- [{text}](#{anchor})")
        out.append("\n---\n")
        return "\n".join(out) + "\n"

    def render(self) -> str:
        """Return the assembled Markdown document as a string."""
        parts: list[str] = []
        if self.title:
            parts.append(f"# {self.title}\n\n")
        parts.append(self._render_metadata_block())
        for text, level, kind in self.sections:
            if kind == "toc":
                parts.append(self._render_toc())
            elif kind == "heading":
                parts.append("#" * max(1, min(6, level)) + f" {text}\n\n")
            elif kind == "paragraph":
                parts.append(str(text).rstrip() + "\n\n")
            elif kind.startswith("code:"):
                lang = kind.split(":", 1)[1]
                parts.append(f"```{lang}\n{text}\n```\n\n")
            elif kind == "table":
                parts.append(str(text) + "\n\n")
            elif kind == "list":
                parts.append(str(text) + "\n\n")
        if self.findings:
            parts.append(self._render_findings_table())
            parts.append("## Detailed Findings\n\n")
            for idx, f in enumerate(self.findings, 1):
                parts.append(self._render_finding_detail(f, idx))
        return "".join(parts)

    def save(self, path: str) -> str:
        """Render the report and write it to ``path``; return the path."""
        rendered = self.render()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(rendered)
        return path


# ---------------------------------------------------------------------------
# Standalone convenience functions
# ---------------------------------------------------------------------------

def findings_to_markdown(findings: Iterable[Mapping[str, Any]]) -> str:
    """Render a sequence of finding dicts as a standalone Markdown fragment.

    Each finding may carry any of the keys documented on
    :meth:`MarkdownReport.add_findings`. The output is a list of H3
    sections (no H1, no metadata) suitable for embedding in a larger
    document.
    """
    findings_list = list(findings)
    parts: list[str] = []
    for idx, f in enumerate(findings_list, 1):
        title = f.get("title", f"Finding {idx}")
        parts.append(f"### {idx}. {title}\n")
        if f.get("severity"):
            parts.append(f"- **Severity:** {f['severity']}\n")
        if f.get("cvss") is not None:
            parts.append(f"- **CVSS:** {f['cvss']}\n")
        if f.get("cvss_vector"):
            parts.append(f"- **CVSS Vector:** `{f['cvss_vector']}`\n")
        if f.get("status"):
            parts.append(f"- **Status:** {f['status']}\n")
        parts.append("\n")
        if f.get("description"):
            parts.append(f"**Description:** {f['description']}\n\n")
        if f.get("evidence"):
            parts.append(f"```\n{f['evidence']}\n```\n\n")
        if f.get("recommendation"):
            parts.append(f"**Recommendation:** {f['recommendation']}\n\n")
    return "".join(parts)


def generate_markdown_report(
    findings: Iterable[Mapping[str, Any]],
    metadata: Mapping[str, Any] | None = None,
    template: str = "default",
) -> str:
    """Assemble a full Markdown report from findings + metadata.

    This is a convenience wrapper around :class:`MarkdownReport` that
    produces a complete document with title heading, metadata block,
    findings summary table, and detailed per-finding sections.

    Parameters
    ----------
    findings
        Iterable of finding dicts (see
        :meth:`MarkdownReport.add_findings` for the expected schema).
    metadata
        Optional mapping of metadata fields (e.g. ``target``, ``author``,
        ``date``, ``scope``). Rendered as a ``**key:** value`` block
        immediately under the H1.
    template
        Template name (reserved for future use; currently only
        ``"default"`` is supported).

    Returns
    -------
    str
        The assembled Markdown report.
    """
    findings_list = list(findings)
    meta = dict(metadata) if metadata else {}
    title = meta.pop("title", "Security Assessment Report")
    date = meta.pop("date", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    meta.setdefault("date", date)

    rpt = MarkdownReport(title=title, metadata=meta, template=template)
    rpt.add_toc()
    rpt.add_findings(findings_list)
    return rpt.render()
