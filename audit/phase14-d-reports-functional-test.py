#!/usr/bin/env python3
"""Phase 14-D — Comprehensive functional test of securagentx.reports.

Sub-tasks exercised:
  1. Import all 5 reports submodules (cvss, markdown, pdf, templates, export).
  2. CVSS v3.1 base-score calculator against 10 standard FIRST.org vectors
     (verify expected score AND severity bucket for each).
  3. MarkdownReport builder — headings, paragraphs, findings table, render().
  4. PDFReport builder — sections + findings + tables + code + page-break,
     render to .pdf file (skipped if reportlab not installed).
  5. All 6 built-in templates (DEFAULT, EXECUTIVE_SUMMARY, DETAILED_FINDINGS,
     COMPLIANCE, VULNERABILITY, TECHNICAL_REPORT) — get_template, validate,
     render_template.
  6. ReportExporter across all 6 formats (markdown, pdf, html, json, csv,
     sarif) — both dedicated to_*() methods AND the generic export() dispatcher.

Output: prints a structured test log; exits 0 on full PASS, 1 on any FAIL.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from typing import Any, Callable

# ── ensure the securagentx-work tree is importable ──────────────────────
WORK_ROOT = "/home/z/my-project/securagentx-work"
if WORK_ROOT not in sys.path:
    sys.path.insert(0, WORK_ROOT)


# ── test infrastructure ─────────────────────────────────────────────────

PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0


def _record(ok: bool, label: str, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    tag = "PASS" if ok else "FAIL"
    line = f"[{tag}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    if ok:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1


def _skip(label: str, reason: str) -> None:
    global SKIP_COUNT
    print(f"[SKIP] {label} — {reason}")
    SKIP_COUNT += 1


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def expect_ok(label: str, fn: Callable[[], Any], predicate: Callable[[Any], bool],
              describe: Callable[[Any], str] | None = None) -> Any:
    """Run ``fn``, assert ``predicate(result)`` is True. Records PASS/FAIL."""
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 — surface all failures
        _record(False, label, f"raised {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return None
    try:
        ok = bool(predicate(result))
    except Exception as exc:  # noqa: BLE001
        _record(False, label, f"predicate raised {type(exc).__name__}: {exc}")
        return result
    detail = describe(result) if describe else ""
    _record(ok, label, detail)
    return result


# ── 1. IMPORT ALL 5 REPORTS SUBMODULES ──────────────────────────────────

section("STAGE 1 — Import all 5 reports submodules")

import_errors: list[str] = []

try:
    from securagentx.reports import cvss as cvss_mod
    _record(True, "import securagentx.reports.cvss")
except Exception as exc:  # noqa: BLE001
    import_errors.append(f"cvss: {exc}")
    _record(False, "import securagentx.reports.cvss", str(exc))

try:
    from securagentx.reports import markdown as md_mod
    _record(True, "import securagentx.reports.markdown")
except Exception as exc:  # noqa: BLE001
    import_errors.append(f"markdown: {exc}")
    _record(False, "import securagentx.reports.markdown", str(exc))

try:
    from securagentx.reports import pdf as pdf_mod
    _record(True, "import securagentx.reports.pdf")
except Exception as exc:  # noqa: BLE001
    import_errors.append(f"pdf: {exc}")
    _record(False, "import securagentx.reports.pdf", str(exc))

try:
    from securagentx.reports import templates as tpl_mod
    _record(True, "import securagentx.reports.templates")
except Exception as exc:  # noqa: BLE001
    import_errors.append(f"templates: {exc}")
    _record(False, "import securagentx.reports.templates", str(exc))

try:
    from securagentx.reports import export as export_mod
    _record(True, "import securagentx.reports.export")
except Exception as exc:  # noqa: BLE001
    import_errors.append(f"export: {exc}")
    _record(False, "import securagentx.reports.export", str(exc))

# Top-level package import (re-exports)
try:
    import securagentx.reports as pkg
    _record(True, "import securagentx.reports (package __init__)",
            f"__all__ has {len(pkg.__all__)} names")
except Exception as exc:  # noqa: BLE001
    import_errors.append(f"package: {exc}")
    _record(False, "import securagentx.reports (package __init__)", str(exc))


# ── 2. CVSS v3.1 — 10 standard FIRST.org test vectors ───────────────────

section("STAGE 2 — CVSS v3.1 base-score on 10 standard vectors")

# (vector, task_spec_expected_score, task_spec_expected_severity,
#  correct_spec_score, correct_spec_severity, note)
#
# NOTE: The task description's expected scores for vectors #5, #6, and #9 do
# NOT match the actual FIRST.org CVSS v3.1 specification. The securagentx
# implementation produces the CORRECT scores per the spec. The task-spec
# discrepancy is documented here so the test can flag both:
#   - "task_spec_match" — does the implementation match the task description?
#   - "spec_match"      — does the implementation match the actual CVSS v3.1 spec?
#
# Correct CVSS v3.1 scores verified by hand-computation per §7.1 of the spec
# and cross-checked against the NVD calculator (https://nvd.nist.gov/vuln-metrics/cvss/v3-calculator).
CVSS_VECTORS: list[tuple[str, float, str, float, str, str]] = [
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8, "Critical", 9.8, "Critical", ""),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H", 7.5, "High",     7.5, "High",     ""),
    ("CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:L", 3.7, "Low",      3.7, "Low",      ""),
    ("CVSS:3.1/AV:P/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", 0.0, "Info",     0.0, "Info",     ""),
    # Vector 5: task says 8.5/High, actual CVSS v3.1 spec says 9.1/Critical.
    # Hand-calc: ISC=0.9148, Impact(S:C)=6.0478, Exploit=2.2865,
    # Base=roundup(1.08*8.3343)=roundup(9.0008)=9.1
    ("CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:C/C:H/I:H/A:H", 8.5, "High",     9.1, "Critical",
     "task spec value incorrect; actual CVSS v3.1 score is 9.1 Critical"),
    # Vector 6: task says 9.6/Critical, actual CVSS v3.1 spec says 9.9/Critical.
    # Hand-calc: Impact(S:C)=6.0478, Exploit(PR:L,S:C)=3.1096,
    # Base=roundup(1.08*9.1574)=roundup(9.8899)=9.9
    ("CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H", 9.6, "Critical", 9.9, "Critical",
     "task spec score incorrect; actual CVSS v3.1 score is 9.9 Critical (severity label correct)"),
    ("CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:U/C:H/I:H/A:H", 8.0, "High",     8.0, "High",     ""),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:N/A:N", 6.5, "Medium",   6.5, "Medium",   ""),
    # Vector 9: task says 7.3/High, actual CVSS v3.1 spec says 7.8/High.
    # Hand-calc: Impact(S:U)=6.42*0.9148=5.8731, Exploit(AV:L,UI:R)=1.8346,
    # Base=roundup(7.7077)=7.8
    ("CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H", 7.3, "High",     7.8, "High",
     "task spec score incorrect; actual CVSS v3.1 score is 7.8 High (severity label correct)"),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:N/A:N", 8.6, "High",     8.6, "High",     ""),
]

cvss_pass = 0          # implementation matches the CORRECT spec
cvss_fail = 0
task_spec_mismatches: list[str] = []   # task-spec values that disagree with the actual spec

for idx, (vector, task_score, task_sev, spec_score, spec_sev, note) in enumerate(CVSS_VECTORS, 1):
    label = f"CVSS #{idx:02d}: {vector}"
    try:
        v = cvss_mod.parse_cvss_vector(vector)
        score = cvss_mod.calculate_base_score(v)
        sev = cvss_mod.cvss_severity(score)

        # Implementation is correct if it matches the actual CVSS v3.1 spec.
        spec_score_ok = abs(score - spec_score) < 1e-6
        spec_sev_ok = sev == spec_sev
        impl_ok = spec_score_ok and spec_sev_ok

        # Track whether the task description's expected value agrees with the spec.
        task_score_ok = abs(task_score - spec_score) < 1e-6
        task_sev_ok = task_sev == spec_sev
        if not (task_score_ok and task_sev_ok):
            task_spec_mismatches.append(
                f"  #{idx:02d}: task expects {task_score}/{task_sev}, "
                f"actual spec is {spec_score}/{spec_sev}"
            )

        detail = (
            f"impl score={score} (spec={spec_score}, task={task_score}), "
            f"impl severity={sev!r} (spec={spec_sev!r}, task={task_sev!r})"
        )
        if note:
            detail += f" | {note}"
        _record(impl_ok, label, detail)
        if impl_ok:
            cvss_pass += 1
        else:
            cvss_fail += 1
    except Exception as exc:  # noqa: BLE001
        _record(False, label, f"raised {type(exc).__name__}: {exc}")
        traceback.print_exc()
        cvss_fail += 1

# Report any task-spec / actual-spec discrepancies explicitly.
if task_spec_mismatches:
    print()
    print("── Task-spec vs. actual FIRST.org CVSS v3.1 spec discrepancies ──")
    print("The task description's expected scores for the following vectors do")
    print("NOT match the actual FIRST.org CVSS v3.1 specification. The")
    print("securagentx.reports.cvss implementation produces the CORRECT scores")
    print("(verified by hand-computation per spec §7.1 and cross-checked")
    print("against the NVD calculator).")
    for line in task_spec_mismatches:
        print(line)

# Bonus round-trip test: format_cvss_vector(parse_cvss_vector(v)) reproduces the input
try:
    sample = CVSS_VECTORS[0][0]
    rt = cvss_mod.format_cvss_vector(cvss_mod.parse_cvss_vector(sample))
    _record(rt == sample, "CVSS round-trip parse/format", f"got {rt!r}")
except Exception as exc:  # noqa: BLE001
    _record(False, "CVSS round-trip parse/format", f"raised {type(exc).__name__}: {exc}")


# ── 3. MarkdownReport generation with findings ──────────────────────────

section("STAGE 3 — MarkdownReport generation with findings")

SAMPLE_FINDINGS: list[dict[str, Any]] = [
    {
        "id": 1,
        "title": "SQL Injection in /login",
        "severity": "critical",
        "cvss": 9.8,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "status": "open",
        "description": "Unsanitized user input in the login form allows SQL injection.",
        "evidence": "sqlmap -u https://target/login --batch --dump",
        "recommendation": "Use parameterized queries / prepared statements.",
    },
    {
        "id": 2,
        "title": "Reflected XSS in search",
        "severity": "high",
        "cvss": 7.5,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H",
        "status": "open",
        "description": "Search endpoint reflects the q parameter without escaping.",
        "evidence": "curl 'https://target/search?q=<script>alert(1)</script>'",
        "recommendation": "Output-encode user input; set CSP headers.",
    },
    {
        "id": 3,
        "title": "Missing rate-limit on /api/login",
        "severity": "medium",
        "cvss": 6.5,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:N/A:N",
        "status": "verified",
        "description": "No throttling on the login endpoint enables credential stuffing.",
        "evidence": "hydra -L users.txt -P pass.txt https-target https-post-form",
        "recommendation": "Enforce per-IP rate limits and account lockout.",
    },
]

md_rendered: str | None = None

try:
    from securagentx.reports.markdown import MarkdownReport, findings_to_markdown, generate_markdown_report

    rpt = MarkdownReport(title="P14-D Functional Test Report")
    rpt.add_metadata({
        "author": "P14-D test harness",
        "target": "https://example.test",
        "date": "2026-07-15",
        "scope": "Web application security assessment",
    })
    rpt.add_toc()
    rpt.add_heading("Executive Summary", level=2)
    rpt.add_paragraph(
        "This report documents three findings discovered during the P14-D "
        "functional verification of the securagentx.reports module."
    )
    rpt.add_findings(SAMPLE_FINDINGS)
    rpt.add_heading("Methodology", level=2)
    rpt.add_paragraph("Manual + automated testing per OWASP WSTG.")

    md_rendered = rpt.render()

    ok_title = md_rendered.startswith("# P14-D Functional Test Report")
    _record(ok_title, "MarkdownReport renders H1 title",
            detail=f"first 60 chars: {md_rendered[:60]!r}")

    ok_meta = "**author:** P14-D test harness" in md_rendered
    _record(ok_meta, "MarkdownReport renders metadata block")

    ok_toc = "## Table of Contents" in md_rendered
    _record(ok_toc, "MarkdownReport inserts TOC section")

    ok_findings_table = "## Findings" in md_rendered and "| ID | Title | Severity | CVSS | Status |" in md_rendered
    _record(ok_findings_table, "MarkdownReport renders findings summary table")

    ok_detail_section = "## Detailed Findings" in md_rendered
    _record(ok_detail_section, "MarkdownReport renders detailed findings section")

    ok_finding_1 = "### 1. SQL Injection in /login" in md_rendered
    _record(ok_finding_1, "MarkdownReport renders finding #1 detail heading")

    ok_finding_cvss_vec = "`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H`" in md_rendered
    _record(ok_finding_cvss_vec, "MarkdownReport renders CVSS vector in code span")

    # findings_to_markdown helper
    frag = findings_to_markdown(SAMPLE_FINDINGS)
    ok_frag = "### 1. SQL Injection in /login" in frag and "- **Severity:** critical" in frag
    _record(ok_frag, "findings_to_markdown() renders standalone fragment",
            detail=f"length={len(frag)} chars")

    # generate_markdown_report wrapper
    full_md = generate_markdown_report(
        SAMPLE_FINDINGS,
        metadata={"title": "Wrapper Report", "author": "tester", "target": "test.local"},
    )
    ok_wrap = full_md.startswith("# Wrapper Report") and "## Findings" in full_md
    _record(ok_wrap, "generate_markdown_report() wrapper renders full doc",
            detail=f"length={len(full_md)} chars")

    # MarkdownReport.save()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tf:
        saved_path = tf.name
    try:
        rpt.save(saved_path)
        saved_size = os.path.getsize(saved_path)
        with open(saved_path, "r", encoding="utf-8") as fh:
            saved_text = fh.read()
        _record(saved_size > 0 and saved_text == md_rendered,
                "MarkdownReport.save() writes rendered content to disk",
                detail=f"{saved_size} bytes")
    finally:
        os.unlink(saved_path)

except Exception as exc:  # noqa: BLE001
    _record(False, "MarkdownReport test block", f"raised {type(exc).__name__}: {exc}")
    traceback.print_exc()

markdown_block_pass = "PASS" if md_rendered and md_rendered.startswith("# P14-D") else "FAIL"


# ── 4. PDFReport generation (skip if reportlab not installed) ────────────

section("STAGE 4 — PDFReport generation")

pdf_block_verdict = "SKIP"
try:
    import reportlab  # noqa: F401
    has_reportlab = True
    print(f"[INFO] reportlab version: {reportlab.Version}")
except ImportError as exc:
    has_reportlab = False
    _skip("PDFReport test block", f"reportlab not installed ({exc})")

if has_reportlab:
    try:
        from securagentx.reports.pdf import (
            PDFReport,
            render_to_pdf_bytes,
            markdown_to_pdf,
            generate_pdf_report,
        )

        # 4a. render_to_pdf_bytes — basic markdown → bytes
        pdf_bytes = render_to_pdf_bytes("# Hello\n\nThis is a test PDF.")
        ok_magic = pdf_bytes.startswith(b"%PDF-")
        _record(ok_magic, "render_to_pdf_bytes() returns %PDF- magic bytes",
                detail=f"{len(pdf_bytes)} bytes, head={pdf_bytes[:8]!r}")

        # 4b. markdown_to_pdf — writes to file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            pdf_file_path = tf.name
        try:
            markdown_to_pdf("# File Test\n\nPDF file rendering.", pdf_file_path)
            file_size = os.path.getsize(pdf_file_path)
            with open(pdf_file_path, "rb") as fh:
                head = fh.read(8)
            _record(file_size > 1000 and head.startswith(b"%PDF-"),
                    "markdown_to_pdf() writes valid PDF file",
                    detail=f"{file_size} bytes, head={head!r}")
        finally:
            os.unlink(pdf_file_path)

        # 4c. PDFReport builder — sections + findings + table + code + pagebreak
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            builder_pdf_path = tf.name
        try:
            prpt = PDFReport(
                title="P14-D PDF Builder Test",
                metadata={"author": "P14-D harness", "date": "2026-07-15", "target": "example.test"},
            )
            prpt.add_section("Executive Summary", "Three findings discovered during the test engagement.")
            prpt.add_findings(SAMPLE_FINDINGS)
            prpt.add_table(["Control", "Status"], [["WAF", "Present"], ["MFA", "Absent"]])
            prpt.add_code_block("nmap -sV --top-ports 1000 target", language="bash")
            prpt.add_page_break()
            prpt.add_section("Appendix", "See attached raw scan output.")
            prpt.render(builder_pdf_path)
            bpdf_size = os.path.getsize(builder_pdf_path)
            with open(builder_pdf_path, "rb") as fh:
                bpdf_head = fh.read(8)
            ok_bpdf = bpdf_size > 1000 and bpdf_head.startswith(b"%PDF-")
            _record(ok_bpdf, "PDFReport.render() writes structured PDF to disk",
                    detail=f"{bpdf_size} bytes, head={bpdf_head!r}")
        finally:
            os.unlink(builder_pdf_path)

        # 4d. PDFReport.to_bytes() — in-memory render
        try:
            prpt2 = PDFReport(title="In-Memory PDF", metadata={"k": "v"})
            prpt2.add_section("S1", "body")
            b2 = prpt2.to_bytes()
            ok_b2 = isinstance(b2, bytes) and b2.startswith(b"%PDF-")
            _record(ok_b2, "PDFReport.to_bytes() returns in-memory PDF bytes",
                    detail=f"{len(b2)} bytes")
        except Exception as exc:  # noqa: BLE001
            _record(False, "PDFReport.to_bytes()", f"raised {type(exc).__name__}: {exc}")

        # 4e. generate_pdf_report — high-level convenience helper
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            gen_pdf_path = tf.name
        try:
            generate_pdf_report(
                SAMPLE_FINDINGS,
                metadata={"title": "Generated", "author": "P14-D", "summary": "auto-generated"},
                output_path=gen_pdf_path,
            )
            gen_size = os.path.getsize(gen_pdf_path)
            with open(gen_pdf_path, "rb") as fh:
                gen_head = fh.read(8)
            _record(gen_size > 1000 and gen_head.startswith(b"%PDF-"),
                    "generate_pdf_report() high-level helper writes valid PDF",
                    detail=f"{gen_size} bytes")
        finally:
            os.unlink(gen_pdf_path)

        pdf_block_verdict = "PASS"
    except Exception as exc:  # noqa: BLE001
        _record(False, "PDFReport test block", f"raised {type(exc).__name__}: {exc}")
        traceback.print_exc()
        pdf_block_verdict = "FAIL"


# ── 5. All 6 built-in templates ─────────────────────────────────────────

section("STAGE 5 — All 6 built-in templates")

# Map task-spec name → (registry key for get_template, expected module constant)
TEMPLATES_TO_TEST: list[tuple[str, str]] = [
    ("DEFAULT",            "default"),
    ("EXECUTIVE_SUMMARY",  "executive_summary"),
    ("DETAILED_FINDINGS",  "detailed_findings"),
    ("COMPLIANCE",         "compliance"),
    ("VULNERABILITY",      "vulnerability"),
    ("TECHNICAL_REPORT",   "technical"),
]

# Per-template context (enough keys to fully populate the rendered output)
TEMPLATE_CONTEXTS: dict[str, dict[str, Any]] = {
    "default": {
        "title": "P14-D Default Template Report", "date": "2026-07-15",
        "author": "P14-D", "target": "example.test",
        "scope": "Web app assessment", "executive_summary": "Summary text.",
        "findings_table": "| ID | Title |\n|---|---|\n| 1 | XSS |",
        "findings_detail": "### 1. XSS\n- detail here",
        "methodology": "OWASP WSTG",
        "appendices": "N/A",
        "metadata_json": "{}",
    },
    "executive_summary": {
        "engagement_name": "Q3 Pentest", "client_name": "Acme Corp",
        "date": "2026-07-15", "author": "P14-D", "target": "example.test",
        "critical_count": 1, "high_count": 2, "medium_count": 3, "low_count": 0, "info_count": 0,
        "executive_summary": "Engagement summary.", "recommendations": "Fix findings.",
        "next_steps": "Re-test in 30 days.",
    },
    "detailed_findings": {
        "title": "P14-D Detailed Findings Report", "date": "2026-07-15",
        "author": "P14-D", "target": "example.test",
        "scope": "Web app", "executive_summary": "Summary.",
        "findings_table": "| ID | Title |\n|---|---|\n| 1 | XSS |",
        "findings_detail": "### 1. XSS\n- detail",
        "methodology": "Manual + automated",
        "appendices": "N/A", "metadata_json": "{}",
    },
    "compliance": {
        "title": "P14-D Compliance Report", "date": "2026-07-15",
        "author": "P14-D", "target": "example.test",
        "executive_summary": "Summary.",
        "pci_dss_table": "| Req | Status |\n|---|---|\n| 6.5 | Fail |",
        "soc2_table": "| Criteria | Status |\n|---|---|\n| CC7.1 | Pass |",
        "iso27001_table": "| Control | Status |\n|---|---|\n| A.14.2 | Pass |",
        "findings_detail": "### 1. Finding",
        "methodology": "Audit", "appendices": "N/A", "metadata_json": "{}",
    },
    "vulnerability": {
        "cve_id": "CVE-2026-9999", "severity": "Critical", "cvss_score": 9.8,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "affected_component": "/login", "cve_url": "https://nvd.nist.gov/vuln/detail/CVE-2026-9999",
        "vendor_advisory": "VENDOR-ADV-001", "owasp_reference": "A03:2021 Injection",
        "description": "SQL injection vulnerability.", "impact": "Full DB compromise.",
        "exploitation_commands": "sqlmap -u https://target/login --batch",
        "evidence": "Database dump obtained.",
        "immediate_fix": "Deploy WAF rule.", "long_term_fix": "Parameterized queries.",
        "compensating_controls": "Logging + monitoring.",
    },
    "technical": {
        "title": "P14-D Technical Report", "date": "2026-07-15",
        "author": "P14-D", "target": "example.test",
        "overview": "Overview text.",
        "methodology": "Methodology text.", "tools_used": "nmap, sqlmap, burp",
        "recon_summary": "Recon text.",
        "findings_summary": "3 findings.",
        "exploit_chains": "Chain 1: XSS → CSRF → RCE.",
        "immediate_remediation": "Patch immediately.",
        "appendix_raw_output": "raw scan output",
        "findings_detail": "### 1. Finding",
        "metadata_json": "{}",
    },
}

template_pass_count = 0
template_fail_count = 0

for task_name, reg_key in TEMPLATES_TO_TEST:
    label_lookup = f"Template {task_name} — get_template({reg_key!r})"
    try:
        tpl_str = tpl_mod.get_template(reg_key)
        ok_lookup = isinstance(tpl_str, str) and len(tpl_str) > 50
        _record(ok_lookup, label_lookup, detail=f"{len(tpl_str)} chars")
        if ok_lookup:
            template_pass_count += 1
        else:
            template_fail_count += 1
    except Exception as exc:  # noqa: BLE001
        _record(False, label_lookup, f"raised {type(exc).__name__}: {exc}")
        template_fail_count += 1
        continue

    label_validate = f"Template {task_name} — validate_template({reg_key!r})"
    try:
        ok_validate = tpl_mod.validate_template(reg_key)
        _record(ok_validate, label_validate)
        if ok_validate:
            template_pass_count += 1
        else:
            template_fail_count += 1
    except Exception as exc:  # noqa: BLE001
        _record(False, label_validate, f"raised {type(exc).__name__}: {exc}")
        template_fail_count += 1

    label_render = f"Template {task_name} — render_template with context"
    try:
        ctx = TEMPLATE_CONTEXTS[reg_key]
        rendered = tpl_mod.render_template(tpl_str, ctx)
        # All {identifier} placeholders should be substituted. We check for
        # *unsubstituted template placeholders* using the SAME regex the
        # template engine uses (\{[a-zA-Z_][a-zA-Z0-9_]*\}), rather than
        # any literal "{" or "}" character — the latter would false-positive
        # on legitimately-substituted values like metadata_json="{}".
        import re as _re
        leftover_placeholders = _re.findall(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", rendered)
        has_generated_marker = "Generated by SecurAgentX" in rendered or "Confidential" in rendered
        ok_render = (isinstance(rendered, str) and len(rendered) > 100
                     and len(leftover_placeholders) == 0 and has_generated_marker)
        detail = (f"len={len(rendered)}, leftover_placeholders={leftover_placeholders}, "
                  f"footer_marker={has_generated_marker}")
        _record(ok_render, label_render, detail)
        if ok_render:
            template_pass_count += 1
        else:
            template_fail_count += 1
    except Exception as exc:  # noqa: BLE001
        _record(False, label_render, f"raised {type(exc).__name__}: {exc}")
        traceback.print_exc()
        template_fail_count += 1

# Bonus: list_templates() returns ≥6 templates
try:
    all_tpl_names = tpl_mod.list_templates()
    ok_count = len(all_tpl_names) >= 6
    _record(ok_count, "list_templates() returns ≥6 registered templates",
            detail=f"got {len(all_tpl_names)}: {all_tpl_names}")
except Exception as exc:  # noqa: BLE001
    _record(False, "list_templates()", f"raised {type(exc).__name__}: {exc}")

# Bonus: TemplateEngine stateful API
try:
    eng = tpl_mod.TemplateEngine()
    ok_engine = eng.has("default") and "default" in eng
    eng.register_template("custom_test", "Hello {name}")
    ok_custom = eng.render("custom_test", {"name": "World"}) == "Hello World"
    _record(ok_engine and ok_custom, "TemplateEngine register + render custom template")
except Exception as exc:  # noqa: BLE001
    _record(False, "TemplateEngine API", f"raised {type(exc).__name__}: {exc}")

templates_verdict = "PASS" if template_fail_count == 0 else "FAIL"


# ── 6. ReportExporter — all 6 formats ───────────────────────────────────

section("STAGE 6 — ReportExporter with all 6 formats (markdown, pdf, html, json, csv, sarif)")

# Sanity: SUPPORTED_FORMATS matches the task spec's expected 6 formats
expected_formats = ["markdown", "pdf", "html", "json", "csv", "sarif"]
try:
    ok_supported = (isinstance(export_mod.SUPPORTED_FORMATS, list)
                    and export_mod.SUPPORTED_FORMATS == expected_formats)
    _record(ok_supported, "SUPPORTED_FORMATS == [markdown, pdf, html, json, csv, sarif]",
            detail=f"got {export_mod.SUPPORTED_FORMATS}")
except Exception as exc:  # noqa: BLE001
    _record(False, "SUPPORTED_FORMATS check", f"raised {type(exc).__name__}: {exc}")

exporter_pass_count = 0
exporter_fail_count = 0

try:
    from securagentx.reports.export import ReportExporter, export_findings

    exporter = ReportExporter(
        SAMPLE_FINDINGS,
        metadata={"title": "P14-D Exporter Report", "author": "P14-D", "target": "example.test"},
    )

    # 6a. markdown — to_markdown()
    label = "Exporter.format=markdown (to_markdown)"
    try:
        md = exporter.to_markdown()
        ok = isinstance(md, str) and "# P14-D Exporter Report" in md and "SQL Injection" in md
        _record(ok, label, detail=f"len={len(md)} chars")
        exporter_pass_count += 1 if ok else 0
        exporter_fail_count += 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        _record(False, label, f"raised {type(exc).__name__}: {exc}")
        exporter_fail_count += 1

    # 6b. html — to_html()
    label = "Exporter.format=html (to_html)"
    try:
        html = exporter.to_html()
        ok = (isinstance(html, str)
              and html.lstrip().startswith("<!DOCTYPE html>")
              and "<html" in html
              and "</html>" in html)
        _record(ok, label, detail=f"len={len(html)} chars")
        exporter_pass_count += 1 if ok else 0
        exporter_fail_count += 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        _record(False, label, f"raised {type(exc).__name__}: {exc}")
        exporter_fail_count += 1

    # 6c. json — to_json()
    label = "Exporter.format=json (to_json)"
    try:
        import json as _json
        js = exporter.to_json()
        parsed = _json.loads(js)
        ok = (isinstance(js, str)
              and isinstance(parsed, dict)
              and "findings" in parsed
              and "metadata" in parsed
              and "generated_at" in parsed
              and len(parsed["findings"]) == 3)
        _record(ok, label, detail=f"len={len(js)} chars, findings={len(parsed.get('findings', []))}")
        exporter_pass_count += 1 if ok else 0
        exporter_fail_count += 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        _record(False, label, f"raised {type(exc).__name__}: {exc}")
        exporter_fail_count += 1

    # 6d. csv — to_csv()
    label = "Exporter.format=csv (to_csv)"
    try:
        csv_text = exporter.to_csv()
        ok = (isinstance(csv_text, str)
              and "id" in csv_text.splitlines()[0]
              and "SQL Injection" in csv_text
              and csv_text.count("\n") >= 3)
        _record(ok, label, detail=f"len={len(csv_text)} chars, lines={csv_text.count(chr(10))}")
        exporter_pass_count += 1 if ok else 0
        exporter_fail_count += 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        _record(False, label, f"raised {type(exc).__name__}: {exc}")
        exporter_fail_count += 1

    # 6e. sarif — to_sarif()
    label = "Exporter.format=sarif (to_sarif)"
    try:
        import json as _json
        sarif_text = exporter.to_sarif()
        sarif_obj = _json.loads(sarif_text)
        ok = (isinstance(sarif_text, str)
              and sarif_obj.get("version") == "2.1.0"
              and "$schema" in sarif_obj
              and "runs" in sarif_obj
              and len(sarif_obj["runs"]) == 1
              and sarif_obj["runs"][0]["tool"]["driver"]["name"] == "SecurAgentX"
              and len(sarif_obj["runs"][0]["results"]) == 3)
        _record(ok, label,
                detail=f"version={sarif_obj.get('version')}, "
                       f"results={len(sarif_obj['runs'][0]['results'])}")
        exporter_pass_count += 1 if ok else 0
        exporter_fail_count += 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        _record(False, label, f"raised {type(exc).__name__}: {exc}")
        exporter_fail_count += 1

    # 6f. pdf — to_pdf(output_path) — skipped if reportlab not installed
    label = "Exporter.format=pdf (to_pdf)"
    if not has_reportlab:
        _skip(label, "reportlab not installed")
    else:
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                pdf_path = tf.name
            try:
                success = exporter.to_pdf(pdf_path)
                size = os.path.getsize(pdf_path)
                with open(pdf_path, "rb") as fh:
                    head = fh.read(8)
                ok = (success is True and size > 1000 and head.startswith(b"%PDF-"))
                _record(ok, label, detail=f"success={success}, size={size}, head={head!r}")
                exporter_pass_count += 1 if ok else 0
                exporter_fail_count += 0 if ok else 1
            finally:
                os.unlink(pdf_path)
        except Exception as exc:  # noqa: BLE001
            _record(False, label, f"raised {type(exc).__name__}: {exc}")
            exporter_fail_count += 1

    # 6g. Generic export() dispatcher — call once per format using export(format, output_path)
    print()
    print("── Generic ReportExporter.export(format, output_path) dispatcher ──")
    for fmt in expected_formats:
        label = f"Exporter.export(format={fmt!r})"
        if fmt == "pdf" and not has_reportlab:
            _skip(label, "reportlab not installed")
            continue
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                out_path = os.path.join(tmpdir, f"out.{fmt}")
                if fmt == "pdf":
                    result = exporter.export(fmt, output_path=out_path)
                    ok = (result == out_path and os.path.getsize(out_path) > 1000
                          and open(out_path, "rb").read(5) == b"%PDF-")
                else:
                    result = exporter.export(fmt, output_path=out_path)
                    ok = isinstance(result, str) and len(result) > 50 and os.path.exists(out_path)
                _record(ok, label,
                        detail=f"result_type={type(result).__name__}, file_written={os.path.exists(out_path)}")
                exporter_pass_count += 1 if ok else 0
                exporter_fail_count += 0 if ok else 1
        except Exception as exc:  # noqa: BLE001
            _record(False, label, f"raised {type(exc).__name__}: {exc}")
            exporter_fail_count += 1

    # 6h. export_findings convenience helper
    label = "export_findings() convenience helper"
    try:
        out = export_findings(SAMPLE_FINDINGS, "json")
        ok = isinstance(out, str) and "findings" in out
        _record(ok, label, detail=f"len={len(out)} chars")
        exporter_pass_count += 1 if ok else 0
        exporter_fail_count += 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        _record(False, label, f"raised {type(exc).__name__}: {exc}")
        exporter_fail_count += 1

except Exception as exc:  # noqa: BLE001
    _record(False, "Exporter test block", f"raised {type(exc).__name__}: {exc}")
    traceback.print_exc()

exporter_verdict = "PASS" if exporter_fail_count == 0 else "FAIL"


# ── Final summary ───────────────────────────────────────────────────────

section("FINAL SUMMARY")

print(f"Total PASS:        {PASS_COUNT}")
print(f"Total FAIL:        {FAIL_COUNT}")
print(f"Total SKIP:        {SKIP_COUNT}")
print()
print(f"CVSS vectors tested:           10")
print(f"CVSS vectors passed:           {cvss_pass}")
print(f"CVSS vectors failed:           {cvss_fail}")
print(f"MarkdownReport block:          {markdown_block_pass}")
print(f"PDFReport block:               {pdf_block_verdict}")
print(f"Templates block (6 templates): {templates_verdict}")
print(f"  (template sub-checks pass/fail: {template_pass_count}/{template_fail_count})")
print(f"Exporter block (6 formats):     {exporter_verdict}")
print(f"  (exporter sub-checks pass/fail: {exporter_pass_count}/{exporter_fail_count})")
print()

# Overall verdict
cvss_ok = (cvss_fail == 0)
md_ok = (markdown_block_pass == "PASS")
pdf_ok = (pdf_block_verdict in ("PASS", "SKIP"))  # SKIP is acceptable per task spec
tpl_ok = (templates_verdict == "PASS")
exp_ok = (exporter_verdict == "PASS")
all_ok = cvss_ok and md_ok and pdf_ok and tpl_ok and exp_ok and FAIL_COUNT == 0

overall = "PASS" if all_ok else "FAIL"
print(f"OVERALL VERDICT: {overall}")
print()

if overall == "PASS":
    print("✅ All securagentx.reports functional tests passed.")
else:
    print("❌ One or more securagentx.reports functional tests failed — see above.")

sys.exit(0 if overall == "PASS" else 1)
