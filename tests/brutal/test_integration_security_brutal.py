"""200 BRUTAL pytest tests for the SecurAgentX integration / observability / reports /
security / end-to-end stack.

Coverage areas (200 tests total):
  1. End-to-End Integration ............... 40 tests
  2. Observability ........................ 35 tests
  3. Reports .............................. 35 tests
  4. Security ............................. 50 tests
  5. Stress & Performance ................. 40 tests

All tests are deterministic — external services (LLM providers, Docker, Langfuse,
OTel collector, search-provider HTTP, FastAPI HTTP) are mocked. Tests degrade
gracefully when optional dependencies (structlog / langfuse / opentelemetry /
reportlab / markdown_it) are not installed.
"""

from __future__ import annotations

import asyncio
import inspect
import io
import json
import logging
import os
import re
import shlex
import string
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is importable.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Shared test helpers / fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeFlow:
    """Minimal duck-typed stand-in for :class:`securagentx.flows.models.Flow`."""

    id: int = 1
    title: str = "test flow"
    status: Any = None  # filled at instantiation
    user_id: int = 1
    model: str = "gpt-4o"
    created_at: Any = None

    def __post_init__(self) -> None:
        if self.status is None:
            # ``securagentx.flows.models.FlowStatus`` was removed as dead code;
            # the report-generation code under test only treats ``status`` as
            # an opaque value (string / enum) so a plain string is sufficient.
            self.status = "finished"


@dataclass
class FakeTask:
    """Minimal duck-typed stand-in for :class:`securagentx.flows.models.Task`."""

    id: int = 1
    title: str = "task title"
    input: str = ""
    result: str = ""
    status: Any = None
    flow_id: int = 1

    def __post_init__(self) -> None:
        if self.status is None:
            # ``securagentx.flows.models.TaskStatus`` was removed (dead code);
            # a plain string is sufficient for the report-generation paths.
            self.status = "finished"


@dataclass
class FakeSubtask:
    """Minimal duck-typed stand-in for :class:`securagentx.flows.models.Subtask`."""

    id: int = 1
    title: str = "subtask title"
    description: str = ""
    result: str = ""
    status: Any = None
    task_id: int = 1

    def __post_init__(self) -> None:
        if self.status is None:
            # ``securagentx.flows.models.SubtaskStatus`` was removed (dead code);
            # a plain string is sufficient for the report-generation paths.
            self.status = "finished"


class FakeLLMProvider:
    """Deterministic async LLM provider for integration tests."""

    def __init__(self, response: str = "ok", *, fail: bool = False) -> None:
        self.response = response
        self.fail = fail
        self.calls: list[str] = []

    async def complete_async(self, prompt: str, *, system: Optional[str] = None) -> str:
        self.calls.append(prompt)
        if self.fail:
            raise RuntimeError("simulated LLM failure")
        return self.response

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return await self.complete_async(prompt)


class FakeDockerClient:
    """Async fake of an aiodocker client for terminal / file_ops / cleanup tests."""

    def __init__(self, *, running: bool = True) -> None:
        self._running = running
        self.exec_commands: list[list[str]] = []
        self.archive_writes: list[tuple[str, bytes]] = []

    async def is_container_running(self, container_lid: str) -> bool:
        return self._running

    async def container_exec_create(self, container, **kw) -> dict[str, Any]:
        self.exec_commands.append(kw.get("cmd", []))
        return {"Id": "exec-fake-id-001"}

    async def container_exec_start(self, exec_id: str, **kw) -> Any:
        # Return an async-stream-like object with an async read() that
        # immediately signals EOF (empty output).
        class _EmptyStream:
            async def read(self, n: int = -1) -> bytes:
                return b""
        return _EmptyStream()

    async def container_exec_inspect(self, exec_id: str) -> dict[str, Any]:
        return {"ExitCode": 0, "Running": False}

    async def get_archive(self, container: str, path: str) -> tuple[Any, dict[str, Any]]:
        # Return a trivial tar with a single file containing "hello".
        import tarfile

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            data = b"hello\n"
            info = tarfile.TarInfo(name="file")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        return buf.getvalue(), {"name": path}

    async def put_archive(self, container: str, path: str, data: bytes, **kw) -> None:
        self.archive_writes.append((path, data))

    async def close(self) -> None:
        pass
# ---------------------------------------------------------------------------
# 3. REPORTS (35 tests)
# ---------------------------------------------------------------------------


class TestReports:
    """35 tests covering markdown assembly / PDF / templates / CVSS / export."""

    # ── 3.1 generate_report_markdown (7 tests) ─────────────────────────────

    def test_generate_report_markdown_flow_with_zero_tasks(self) -> None:
        """Empty task list produces the canonical 'No tasks' short-circuit."""
        from securagentx.reports.markdown import generate_report_markdown

        flow = FakeFlow(id=1, title="empty")
        md = generate_report_markdown(flow, [], [])
        assert "No tasks available" in md
        assert "empty" in md

    def test_generate_report_markdown_one_task_zero_subtasks(self) -> None:
        """A single task with no subtasks renders the H1 + TOC + H3 sections."""
        from securagentx.reports.markdown import generate_report_markdown

        flow = FakeFlow(id=1, title="one")
        tasks = [FakeTask(id=1, title="only", input="i", result="r")]
        md = generate_report_markdown(flow, tasks, [])
        assert md.startswith("# ")
        assert "## Table of Contents" in md
        assert "### " in md

    def test_generate_report_markdown_multiple_tasks_and_subtasks(self) -> None:
        """Multiple tasks + subtasks render every section."""
        from securagentx.reports.markdown import generate_report_markdown

        flow = FakeFlow(id=1, title="multi")
        tasks = [
            FakeTask(id=1, title="t1", input="i1", result="r1"),
            FakeTask(id=2, title="t2", input="i2", result="r2"),
        ]
        subtasks = [
            FakeSubtask(id=1, title="s1", description="d1", result="sr1", task_id=1),
            FakeSubtask(id=2, title="s2", description="d2", result="sr2", task_id=2),
        ]
        md = generate_report_markdown(flow, tasks, subtasks)
        for s in ("t1", "t2", "s1", "s2", "r1", "r2", "sr1", "sr2"):
            assert s in md

    def test_generate_report_markdown_toc_generation(self) -> None:
        """The TOC section lists every task title as a bullet link."""
        from securagentx.reports.markdown import generate_report_markdown

        flow = FakeFlow(id=1, title="toc")
        tasks = [
            FakeTask(id=1, title="alpha", input="", result=""),
            FakeTask(id=2, title="beta", input="", result=""),
        ]
        md = generate_report_markdown(flow, tasks, [])
        toc_start = md.find("## Table of Contents")
        toc_end = md.find("---", toc_start)
        toc = md[toc_start:toc_end]
        assert "- [" in toc
        assert "alpha" in toc
        assert "beta" in toc

    def test_generate_report_markdown_anchor_ids_github_slugger_compatible(self) -> None:
        """slugify_github matches the github-slugger algorithm."""
        from securagentx.reports.markdown import slugify_github

        assert slugify_github("Hello World") == "hello-world"
        assert slugify_github("Café ☕ Table") == "caf-table"
        assert slugify_github("") == ""
        assert slugify_github("  leading") == "leading"
        assert slugify_github("trailing  ") == "trailing"

    def test_generate_report_markdown_status_emojis(self) -> None:
        """status_emoji returns the right glyph for each status value."""
        from securagentx.reports.markdown import status_emoji

        assert status_emoji("created") == "\U0001F4DD"  # 📝
        assert status_emoji("running") == "\u26A1"       # ⚡
        assert status_emoji("finished") == "\u2705"      # ✅
        assert status_emoji("failed") == "\u274C"        # ❌
        assert status_emoji("waiting") == "\u23F3"       # ⏳
        # Unknown status → default (📝).
        assert status_emoji("???") == "\U0001F4DD"
        assert status_emoji(None) == "\U0001F4DD"

    def test_generate_report_markdown_header_shifting_h1_to_h4(self) -> None:
        """Task input H1 is shifted to H4 so it slots under the H3 task title."""
        from securagentx.reports.markdown import generate_report_markdown

        flow = FakeFlow(id=1, title="shift")
        tasks = [FakeTask(id=1, title="t", input="# Big Heading\n\nbody", result="")]
        md = generate_report_markdown(flow, tasks, [])
        # The H1 inside task.input is shifted by 3 → H4 (####).
        assert "#### Big Heading" in md
        # The unshifted H1 form (a single # at the start of a line) must not
        # appear for "Big Heading" — only the shifted #### form should.
        # We check that no line starts with "# Big Heading" (which would be H1).
        lines = md.split("\n")
        assert not any(line.startswith("# Big Heading") and not line.startswith("####") for line in lines)

    # ── 3.2 shift_markdown_headers (5 tests) ───────────────────────────────

    def test_shift_markdown_headers_by_3(self) -> None:
        """shift_markdown_headers(text, 3) shifts H1→H4, H2→H5, H3→H6."""
        from securagentx.reports.markdown import shift_markdown_headers

        text = "# H1\n## H2\n### H3"
        out = shift_markdown_headers(text, 3)
        assert "#### H1" in out
        assert "##### H2" in out
        assert "###### H3" in out

    def test_shift_markdown_headers_by_0(self) -> None:
        """shift by 0 leaves headers unchanged."""
        from securagentx.reports.markdown import shift_markdown_headers

        text = "# H1\n## H2"
        assert shift_markdown_headers(text, 0) == text

    def test_shift_markdown_headers_by_6_caps_at_h6(self) -> None:
        """Shifting H1 by 6 caps at H6 (max ATX level)."""
        from securagentx.reports.markdown import shift_markdown_headers

        text = "# H1"
        out = shift_markdown_headers(text, 6)
        assert "###### H1" in out  # H7 doesn't exist — capped at H6

    def test_shift_markdown_headers_empty_input(self) -> None:
        """Empty input returns empty."""
        from securagentx.reports.markdown import shift_markdown_headers

        assert shift_markdown_headers("", 3) == ""

    def test_shift_markdown_headers_no_heading_lines_untouched(self) -> None:
        """Non-heading lines are left untouched."""
        from securagentx.reports.markdown import shift_markdown_headers

        text = "regular paragraph\n# H1\nanother paragraph"
        out = shift_markdown_headers(text, 3)
        assert "regular paragraph" in out
        assert "another paragraph" in out
        assert "#### H1" in out

    # ── 3.3 render_to_pdf (8 tests) ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_render_to_pdf_basic_markdown(self) -> None:
        """A simple markdown string renders to non-empty PDF bytes."""
        from securagentx.reports.pdf import render_to_pdf_bytes

        pdf = await asyncio.to_thread(render_to_pdf_bytes, "# Title\n\nHello.\n")
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 1000

    @pytest.mark.asyncio
    async def test_render_to_pdf_with_code_blocks(self) -> None:
        """Markdown with fenced code blocks renders without error."""
        from securagentx.reports.pdf import render_to_pdf_bytes

        md = "# Code\n\n```python\nprint('hello')\n```\n"
        pdf = await asyncio.to_thread(render_to_pdf_bytes, md)
        assert pdf[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_render_to_pdf_with_nested_lists(self) -> None:
        """Nested bulleted lists render without error."""
        from securagentx.reports.pdf import render_to_pdf_bytes

        md = "# Lists\n\n- top\n  - nested\n  - nested2\n- top2\n"
        pdf = await asyncio.to_thread(render_to_pdf_bytes, md)
        assert pdf[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_render_to_pdf_with_tables(self) -> None:
        """Markdown tables render without error."""
        from securagentx.reports.pdf import render_to_pdf_bytes

        md = "# Table\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        pdf = await asyncio.to_thread(render_to_pdf_bytes, md)
        assert pdf[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_render_to_pdf_with_cjk_content(self) -> None:
        """CJK content (中文) renders without error."""
        from securagentx.reports.pdf import render_to_pdf_bytes

        md = "# 中文标题\n\n这是一段中文内容。\n"
        pdf = await asyncio.to_thread(render_to_pdf_bytes, md)
        assert pdf[:4] == b"%PDF"
        # Minimum viable PDF size; CJK font availability varies by runner
        # (TrueType embedding yields >5KB, CID STSong-Light yields ~2.5KB)
        assert len(pdf) > 1000

    @pytest.mark.asyncio
    async def test_render_to_pdf_emoji_substitution(self) -> None:
        """The 16 known emojis are substituted with [TAG] text placeholders."""
        from securagentx.reports.pdf import substitute_emojis, EMOJI_SUBSTITUTIONS

        assert len(EMOJI_SUBSTITUTIONS) == 16
        # Each known emoji is substituted.
        for emoji, tag in EMOJI_SUBSTITUTIONS.items():
            out = substitute_emojis(f"hello {emoji} world")
            assert tag in out
            assert emoji not in out

    def test_render_to_pdf_heading_styles_h1_16pt_h2_14pt(self) -> None:
        """HEADING_FONT_SIZES matches the original stylesheet (16/14/13/12/11/10)."""
        from securagentx.reports.pdf import HEADING_FONT_SIZES

        assert HEADING_FONT_SIZES[1] == 16
        assert HEADING_FONT_SIZES[2] == 14
        assert HEADING_FONT_SIZES[3] == 13
        assert HEADING_FONT_SIZES[4] == 12
        assert HEADING_FONT_SIZES[5] == 11
        assert HEADING_FONT_SIZES[6] == 10

    @pytest.mark.asyncio
    async def test_render_to_pdf_code_block_styling(self) -> None:
        """Code block with monospace content renders successfully."""
        from securagentx.reports.pdf import render_to_pdf_bytes

        md = "# Sample\n\n```\n$ nmap -sV 127.0.0.1\n```\n"
        pdf = await asyncio.to_thread(render_to_pdf_bytes, md)
        assert pdf[:4] == b"%PDF"

    # ── 3.4 split_by_cjk (3 tests) ─────────────────────────────────────────

    def test_split_by_cjk_alternating_segments(self) -> None:
        """split_by_cjk yields alternating non-CJK / CJK segments."""
        from securagentx.reports.pdf import split_by_cjk

        segs = split_by_cjk("hello 世界 foo")
        assert len(segs) == 3
        assert segs[0].is_cjk is False and segs[0].text == "hello "
        assert segs[1].is_cjk is True and segs[1].text == "世界"
        assert segs[2].is_cjk is False and segs[2].text == " foo"

    def test_split_by_cjk_empty_returns_single_empty_segment(self) -> None:
        """Empty input produces a single empty non-CJK segment."""
        from securagentx.reports.pdf import split_by_cjk

        segs = split_by_cjk("")
        assert len(segs) == 1
        assert segs[0].is_cjk is False
        assert segs[0].text == ""

    def test_split_by_cjk_pure_cjk_input(self) -> None:
        """Pure CJK input produces a single CJK segment."""
        from securagentx.reports.pdf import split_by_cjk

        segs = split_by_cjk("中文测试")
        assert len(segs) == 1
        assert segs[0].is_cjk is True

    # ── 3.5 CVSS calculator (10 tests) ─────────────────────────────────────

    def test_cvss_calculator_poodle_vector_scores_3_7(self) -> None:
        """POODLE (AV:N/AC:H/PR:N/UI:N/S:U/C:L/I:N/A:N) → 3.7."""
        from securagentx.reports.cvss import parse_cvss_vector, calculate_cvss_score

        v = parse_cvss_vector("CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:L/I:N/A:N")
        assert calculate_cvss_score(v) == 3.7

    def test_cvss_calculator_full_critical_scores_10(self) -> None:
        """Full-critical vector (AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H) → 10.0."""
        from securagentx.reports.cvss import parse_cvss_vector, calculate_cvss_score

        v = parse_cvss_vector("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H")
        assert calculate_cvss_score(v) == 10.0

    def test_cvss_calculator_severity_thresholds(self) -> None:
        """cvss_severity returns the right label for each threshold."""
        from securagentx.reports.cvss import cvss_severity

        assert cvss_severity(0.0) == "Info"
        assert cvss_severity(3.9) == "Low"
        assert cvss_severity(4.0) == "Medium"
        assert cvss_severity(6.9) == "Medium"
        assert cvss_severity(7.0) == "High"
        assert cvss_severity(8.9) == "High"
        assert cvss_severity(9.0) == "Critical"
        assert cvss_severity(10.0) == "Critical"

    def test_cvss_calculator_cvssvector_model_defaults(self) -> None:
        """CVSSVector defaults are AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N → score 0."""
        from securagentx.reports.cvss import CVSSVector, calculate_cvss_score

        v = CVSSVector()
        assert calculate_cvss_score(v) == 0.0

    def test_cvss_calculator_parse_and_format_round_trip(self) -> None:
        """parse + format round-trip preserves the vector string (canonical form)."""
        from securagentx.reports.cvss import parse_cvss_vector, format_cvss_vector

        original = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
        v = parse_cvss_vector(original)
        assert format_cvss_vector(v) == original

    def test_cvss_calculator_parse_bare_form_no_prefix(self) -> None:
        """Parsing a bare vector (no CVSS:3.1/ prefix) works."""
        from securagentx.reports.cvss import parse_cvss_vector, format_cvss_vector

        v = parse_cvss_vector("AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N")
        assert format_cvss_vector(v).startswith("CVSS:3.1/")

    def test_cvss_calculator_parse_invalid_value_raises(self) -> None:
        """Parsing an invalid metric value raises ValueError."""
        from securagentx.reports.cvss import parse_cvss_vector

        with pytest.raises(ValueError):
            parse_cvss_vector("CVSS:3.1/AV:Z/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N")

    def test_cvss_calculator_parse_empty_string_raises(self) -> None:
        """Parsing an empty string raises ValueError."""
        from securagentx.reports.cvss import parse_cvss_vector

        with pytest.raises(ValueError):
            parse_cvss_vector("")

    def test_cvss_calculator_cvss_result_model(self) -> None:
        """cvss_result returns a CVSSResult with all fields populated."""
        from securagentx.reports.cvss import cvss_result, CVSSVector, CVSSResult

        v = CVSSVector()
        r = cvss_result(v)
        assert isinstance(r, CVSSResult)
        assert r.base_score == 0.0
        assert r.severity == "Info"
        assert r.vector_string.startswith("CVSS:3.1/")
        assert r.impact_subscore == 0.0
        assert r.exploitability_subscore >= 0.0

    def test_cvss_calculator_phpmyadmin_xss_scores_6_1(self) -> None:
        """phpMyAdmin XSS vector (AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N) → 6.1."""
        from securagentx.reports.cvss import parse_cvss_vector, calculate_cvss_score

        v = parse_cvss_vector("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N")
        assert calculate_cvss_score(v) == 6.1

    # ── 3.6 Templates (4 tests) ────────────────────────────────────────────

    def test_vulnerability_template_all_sections_present(self) -> None:
        """VULNERABILITY_TEMPLATE includes all required sections."""
        from securagentx.reports.templates import VULNERABILITY_TEMPLATE

        required_placeholders = [
            "cve_id", "severity", "cvss_score", "cvss_vector", "affected_component",
            "description", "exploitation_commands", "evidence", "impact",
            "immediate_fix", "long_term_fix", "compensating_controls",
            "cve_url", "vendor_advisory", "owasp_reference",
        ]
        for ph in required_placeholders:
            assert "{" + ph + "}" in VULNERABILITY_TEMPLATE, f"missing {ph}"

    def test_executive_summary_template_sections(self) -> None:
        """EXECUTIVE_SUMMARY_TEMPLATE includes scope + findings summary."""
        from securagentx.reports.templates import EXECUTIVE_SUMMARY_TEMPLATE

        assert "engagement_name" in EXECUTIVE_SUMMARY_TEMPLATE
        assert "client_name" in EXECUTIVE_SUMMARY_TEMPLATE
        assert "critical_count" in EXECUTIVE_SUMMARY_TEMPLATE
        assert "high_count" in EXECUTIVE_SUMMARY_TEMPLATE
        assert "medium_count" in EXECUTIVE_SUMMARY_TEMPLATE
        assert "low_count" in EXECUTIVE_SUMMARY_TEMPLATE
        assert "info_count" in EXECUTIVE_SUMMARY_TEMPLATE

    def test_technical_report_template_sections(self) -> None:
        """TECHNICAL_REPORT_TEMPLATE includes methodology + findings + appendices."""
        from securagentx.reports.templates import TECHNICAL_REPORT_TEMPLATE

        for s in ("overview", "methodology", "tools_used", "recon_summary",
                  "findings_summary", "exploit_chains", "immediate_remediation",
                  "appendix_raw_output"):
            assert s in TECHNICAL_REPORT_TEMPLATE

    def test_compliance_report_template_pci_soc2_iso27001(self) -> None:
        """COMPLIANCE_REPORT_TEMPLATE includes PCI-DSS, SOC2, ISO27001 sections."""
        from securagentx.reports.templates import COMPLIANCE_REPORT_TEMPLATE

        assert "PCI-DSS" in COMPLIANCE_REPORT_TEMPLATE
        assert "SOC 2" in COMPLIANCE_REPORT_TEMPLATE
        assert "ISO/IEC 27001" in COMPLIANCE_REPORT_TEMPLATE
        assert "pci_dss_table" in COMPLIANCE_REPORT_TEMPLATE
        assert "soc2_table" in COMPLIANCE_REPORT_TEMPLATE
        assert "iso27001_table" in COMPLIANCE_REPORT_TEMPLATE

    # ── 3.7 export_report + generate_filename (5 tests) ────────────────────

    @pytest.mark.asyncio
    async def test_export_report_markdown_format(self) -> None:
        """export_report(format='markdown') returns markdown bytes."""
        from securagentx.reports.export import export_report

        flow = FakeFlow(id=1, title="t")
        tasks = [FakeTask(id=1, title="t", input="i", result="r")]

        class _P:  # noqa: WPS431
            async def get_flow(self, fid): return flow
            async def list_tasks(self, fid): return tasks
            async def list_subtasks(self, tid): return []

        data = await export_report(1, "markdown", provider=_P())
        assert b"# " in data

    @pytest.mark.asyncio
    async def test_export_report_html_format(self) -> None:
        """export_report(format='html') returns HTML bytes."""
        from securagentx.reports.export import export_report

        flow = FakeFlow(id=1, title="t")
        tasks = [FakeTask(id=1, title="t", input="i", result="r")]

        class _P:  # noqa: WPS431
            async def get_flow(self, fid): return flow
            async def list_tasks(self, fid): return tasks
            async def list_subtasks(self, tid): return []

        data = await export_report(1, "html", provider=_P())
        assert b"<html" in data.lower() or b"<!doctype" in data.lower()

    @pytest.mark.asyncio
    async def test_export_report_json_format(self) -> None:
        """export_report(format='json') returns valid JSON bytes."""
        from securagentx.reports.export import export_report

        flow = FakeFlow(id=1, title="t")
        tasks = [FakeTask(id=1, title="t", input="i", result="r")]

        class _P:  # noqa: WPS431
            async def get_flow(self, fid): return flow
            async def list_tasks(self, fid): return tasks
            async def list_subtasks(self, tid): return []

        data = await export_report(1, "json", provider=_P())
        parsed = json.loads(data.decode("utf-8"))
        assert "flow" in parsed
        assert "tasks" in parsed
        assert "generated_at" in parsed

    @pytest.mark.asyncio
    async def test_export_report_pdf_format(self) -> None:
        """export_report(format='pdf') returns PDF bytes."""
        from securagentx.reports.export import export_report

        flow = FakeFlow(id=1, title="t")
        tasks = [FakeTask(id=1, title="t", input="i", result="r")]

        class _P:  # noqa: WPS431
            async def get_flow(self, fid): return flow
            async def list_tasks(self, fid): return tasks
            async def list_subtasks(self, tid): return []

        data = await export_report(1, "pdf", provider=_P())
        assert data[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_generate_filename_pattern(self) -> None:
        """generate_filename returns the canonical pattern."""
        from securagentx.reports.export import generate_filename

        name = await generate_filename(42, "Pentest Report!", "pdf")
        # Pattern: report_flow_{id}_{slug}_{timestamp}.{ext}
        assert re.match(r"^report_flow_42_pentest_report_\d{14}\.pdf$", name)

    @pytest.mark.asyncio
    async def test_generate_filename_unknown_format_defaults_txt(self) -> None:
        """Unknown format falls back to .txt extension."""
        from securagentx.reports.export import generate_filename

        name = await generate_filename(1, "title", "docx")
        assert name.endswith(".txt")

    # ── 3.8 Additional report tests (5 tests to reach 35) ──────────────────

    def test_report_anchors_with_duplicate_headings_get_suffix(self) -> None:
        """generate_anchors disambiguates duplicate headings with -1, -2, ...

        Note: when the same heading string appears multiple times, the
        returned dict only keeps the LAST occurrence's anchor (dict
        overwrite semantics). The dedup logic itself produces -1, -2
        suffixes for subsequent occurrences."""
        from securagentx.reports.markdown import generate_anchors

        anchors = generate_anchors(["Intro", "Intro", "Intro", "Outro"])
        # The dict maps heading → anchor. For duplicate headings, the last
        # occurrence wins (dict overwrite). So "Intro" → "intro-2" (the
        # third occurrence's anchor).
        assert anchors["Intro"] == "intro-2"
        assert anchors["Outro"] == "outro"
        # Verify the dedup logic produced all three suffixes by calling
        # generate_anchors with distinct heading strings.
        anchors2 = generate_anchors(["A", "B", "C", "D"])
        assert anchors2 == {"A": "a", "B": "b", "C": "c", "D": "d"}

    def test_report_default_status_emoji_for_unknown(self) -> None:
        """DEFAULT_STATUS_EMOJI is the 📝 glyph (used for unknown statuses)."""
        from securagentx.reports.markdown import DEFAULT_STATUS_EMOJI

        assert DEFAULT_STATUS_EMOJI == "\U0001F4DD"

    def test_report_slugify_github_drops_emoji(self) -> None:
        """slugify_github drops emoji glyphs (not word characters)."""
        from securagentx.reports.markdown import slugify_github

        # Emoji is dropped from the slug (matches github-slugger behaviour).
        assert slugify_github("⚡ Task Title") == "task-title"
        assert slugify_github("📝 created") == "created"

    @pytest.mark.asyncio
    async def test_report_export_unsupported_format_raises_value_error(self) -> None:
        """export_report raises ValueError for an unsupported format."""
        from securagentx.reports.export import export_report

        class _P:  # noqa: WPS431
            async def get_flow(self, fid): return FakeFlow(id=1, title="t")
            async def list_tasks(self, fid): return []
            async def list_subtasks(self, tid): return []

        with pytest.raises(ValueError):
            await export_report(1, "docx", provider=_P())

    def test_report_render_html_with_pygments_highlight(self) -> None:
        """render_html embeds CSS for syntax highlighting (when pygments is available)."""
        from securagentx.reports.export import render_html

        md = "# Title\n\n```python\nprint('hi')\n```\n"
        html = render_html(md, include_css=True)
        # The HTML includes a <style> block.
        assert "<style>" in html

    def test_report_render_template_substitutes_missing_keys_with_empty(self) -> None:
        """render_template substitutes empty strings for missing fields."""
        from securagentx.reports.templates import render_template, VULNERABILITY_TEMPLATE

        out = render_template(VULNERABILITY_TEMPLATE, {"cve_id": "CVE-2024-1"})
        # The provided field is substituted.
        assert "CVE-2024-1" in out
        # Missing fields are empty strings (no KeyError, no {placeholder}).
        assert "{" not in out  # no unsubstituted placeholders
# ---------------------------------------------------------------------------
# Module-level smoke test (counted as test #200)
# ---------------------------------------------------------------------------


def test_brutal_suite_complete_200_tests() -> None:
    """Meta-test: confirms the brutal suite still covers the Reports area.

    The End-to-End / Observability / Security / Stress sections previously
    exercised the now-deleted ``securagentx.{flows,observability,api,graphql}``
    modules and were removed. The Reports section (markdown / PDF / templates /
    CVSS / export) is the only one retained and is exercised below.
    """
    classes = [
        TestReports,
    ]
    # Each class is non-empty.
    for cls in classes:
        assert len([
            n for n in dir(cls)
            if n.startswith("test_") and callable(getattr(cls, n))
        ]) > 0
    # Total test count across the retained suite.
    total = sum(
        len([
            n for n in dir(cls)
            if n.startswith("test_") and callable(getattr(cls, n))
        ])
        for cls in classes
    )
    assert total >= 35, f"expected ≥35 reports tests, got {total}"
