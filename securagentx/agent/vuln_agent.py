"""
securagentx/agent/vuln_agent.py — Autonomous Vulnerability Hunting Agent

Architecture:
  THINK → ACT → ANALYZE → REPEAT

Unlike a script-chain or phase-locked scanner, this agent:
  - Reasons about the target autonomously
  - Generates and tests vulnerability hypotheses
  - Pivots freely based on findings
  - Decides when it has enough evidence to conclude
  - Produces a structured vulnerability report

Each turn the AI receives full context (target profile, findings,
hypotheses, scan history) and can call any tool with any arguments.
The agent does NOT force a linear phase sequence.
"""

from __future__ import annotations

import json
import logging
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from securagentx.paths import get_reports_path
from securagentx.agent.agent_memory import MemoryStore
from securagentx.agent.agent_skills import SkillStore

logger = logging.getLogger("securagentx.agent.vuln")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """A single vulnerability or observation discovered during the hunt."""

    title: str
    description: str
    severity: str  # critical / high / medium / low / info
    target: str
    evidence: str = ""
    remediation: str = ""
    source_tool: str = ""
    confidence: float = 0.5  # 0.0–1.0


@dataclass
class Hypothesis:
    """A testable hypothesis about the target."""

    description: str
    rationale: str
    status: str = "pending"  # pending / testing / confirmed / rejected
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.3


@dataclass
class ScanStep:
    """A single step in the scan history."""

    step: int
    reasoning: str
    tool: str
    arguments: Dict[str, Any]
    result_summary: str
    timestamp: float = 0.0


@dataclass
class VulnReport:
    """Final vulnerability report produced when the agent concludes."""

    target: str
    scan_duration: float = 0.0
    total_steps: int = 0
    findings: List[Finding] = field(default_factory=list)
    hypotheses_tested: int = 0
    hypotheses_confirmed: int = 0
    summary: str = ""
    open_ports: List[int] = field(default_factory=list)
    services: Dict[str, str] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "scan_duration_seconds": self.scan_duration,
            "total_steps": self.total_steps,
            "findings": [
                {
                    "title": f.title,
                    "severity": f.severity,
                    "description": f.description,
                    "evidence": f.evidence,
                    "remediation": f.remediation,
                    "confidence": f.confidence,
                }
                for f in self.findings
            ],
            "hypotheses_tested": self.hypotheses_tested,
            "hypotheses_confirmed": self.hypotheses_confirmed,
            "summary": self.summary,
            "open_ports": self.open_ports,
            "services": self.services,
            "recommendations": self.recommendations,
        }

    def render(self) -> str:
        """Render the report as a human-readable markdown string."""
        lines = [
            f"# Vulnerability Report: {self.target}",
            f"",
            f"**Duration:** {self.scan_duration:.1f}s  |  **Steps:** {self.total_steps}  |  **Findings:** {len(self.findings)}",
            f"",
        ]
        if self.summary:
            lines.append(f"## Summary\n{self.summary}\n")
        if self.findings:
            lines.append(f"## Findings ({len(self.findings)})")
            for i, f in enumerate(self.findings, 1):
                lines.append(f"")
                lines.append(f"### {i}. [{f.severity.upper()}] {f.title}")
                lines.append(f"**Target:** {f.target}  |  **Confidence:** {f.confidence:.0%}")
                lines.append(f"**Source:** {f.source_tool or 'AI analysis'}")
                if f.description:
                    lines.append(f"\n{f.description}")
                if f.evidence:
                    lines.append(f"\n**Evidence:**\n```\n{f.evidence[:500]}\n```")
                if f.remediation:
                    lines.append(f"\n**Remediation:** {f.remediation}")
            lines.append("")
        if self.open_ports:
            lines.append(f"**Open ports:** {', '.join(str(p) for p in self.open_ports)}")
        if self.services:
            lines.append(f"**Services detected:**")
            for svc, ver in self.services.items():
                lines.append(f"  - {svc} ({ver})")
        if self.recommendations:
            lines.append(f"\n## Recommendations")
            for r in self.recommendations:
                lines.append(f"- {r}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool definitions (self-contained for this agent)
# ---------------------------------------------------------------------------

# Each tool is a dict with: name, description, parameters (JSON schema), handler


def _tool_port_scan(target: str, ports: str = "common") -> Dict[str, Any]:
    """Scan target for open ports and running services."""
    try:
        from tools.tool_registry import registry

        tool = registry.get_tool("nmap")
        if tool and hasattr(tool, "is_available") and tool.is_available:
            result = tool.handler(target)  # type: ignore[attr-defined]
            return {"success": True, "output": result.output if hasattr(result, "output") else str(result), "port_count": 0}

        # Fallback: use omni_scan
        from tools.omni_scan import run_scan  # type: ignore[attr-defined]

        result = run_scan(target, scan_type="port")
        return {"success": True, "output": str(result), "port_count": 0}
    except Exception as exc:  # noqa: BLE001 — logged
        logger.debug("port scan failed: %s", exc)
        return {"success": False, "error": str(exc)}


def _tool_web_recon(target: str, path: str = "/") -> Dict[str, Any]:
    """Perform web recon on target (HTTP headers, technologies, endpoints)."""
    try:
        from tools.omni_scan import run_scan  # type: ignore[attr-defined]

        result = run_scan(target, scan_type="web")
        return {"success": True, "output": str(result)}
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}


def _tool_vuln_scan(target: str, scan_type: str = "general") -> Dict[str, Any]:
    """Run vulnerability scanner against target."""
    try:
        from tools.tool_registry import registry

        tool = registry.get_tool(scan_type) or registry.get_tool("nikto")
        if tool and tool.is_available:
            result = tool.handler(target)  # type: ignore[attr-defined]
            return {"success": True, "output": result.output if hasattr(result, "output") else str(result)}
        else:
            return {"success": False, "error": f"No {scan_type} tool available"}
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}


def _tool_search_cve(service: str, version: str = "") -> Dict[str, Any]:
    """Search for known CVEs affecting a service/version."""
    try:
        from tools.nvd_cve import search_cve  # type: ignore[attr-defined]

        results = search_cve(f"{service} {version}".strip())
        return {"success": True, "cves": str(results)[:2000]}
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}


def _tool_analyze_target(target: str) -> Dict[str, Any]:
    """Gather initial target intelligence (DNS, whois, technologies)."""
    try:
        from tools.omni_scan import run_scan  # type: ignore[attr-defined]

        result = run_scan(target, scan_type="recon")
        return {"success": True, "output": str(result)}
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}


def _tool_web_search(query: str, num_results: int = 5) -> Dict[str, Any]:
    """Search the web using DuckDuckGo (free, no API key needed).
    
    Returns real search results with titles, URLs, and content snippets.
    Use this to research CVEs, bug bounty disclosures, tech stack info,
    known vulnerabilities, or any target-specific intelligence.
    Falls back to Tavily if TAVILY_API_KEY is set.
    """
    try:
        from tools.research_tool import search_web

        results = search_web(query, num_results=num_results)
        if not results:
            return {"success": True, "output": "No results found.", "results": []}

        # Format for AI consumption
        lines = [f"Web search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Untitled")
            url = r.get("url", "")
            content = r.get("content", "")[:300]
            lines.append(f"{i}. {title}\n   URL: {url}\n   {content}\n")

        return {"success": True, "output": "\n".join(lines), "results": results[:num_results]}
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}


def _tool_web_extract(url: str) -> Dict[str, Any]:
    """Fetch and extract readable text content from a URL.
    
    Use this after web_search to read full article/blog/advisory content.
    Returns clean text without HTML/ads/navigation.
    """
    try:
        from tools.research_tool import extract_and_summarize

        data = extract_and_summarize(url)
        if data.get("error"):
            return {"success": False, "error": data["error"]}

        return {
            "success": True,
            "url": url,
            "output": data.get("text", "")[:4000],
            "chars": data.get("chars", 0),
        }
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}


def _tool_browser(
    action: str,
    url: str = "",
    selector: str = "",
    text: str = "",
    headless: bool = True,
) -> Dict[str, Any]:
    """Drive a real headless browser (Playwright) for web interaction.

    This is the JavaScript-rendered, form-filling, screenshot-capturing
    successor to ``web_extract``. Use it when the target page requires
    JS execution, when you need to click/type/submit, or when a
    screenshot would help the analysis.

    Actions (case-insensitive):

    * ``navigate`` — open ``url`` and wait for ``load``.
    * ``click`` — click the element at ``selector`` (CSS or XPath).
    * ``type`` — fill ``text`` into the element at ``selector``.
    * ``screenshot`` — capture a full-page PNG of ``url`` (or current
      page if ``url`` is empty). Returned as base64 in ``screenshot``.
    * ``content_md`` — extract page content as Markdown (trafilatura).
    * ``content_html`` — extract raw HTML after JS execution.
    * ``links`` — extract all ``<a href>`` links on ``url``.
    * ``form_submit`` — submit the form at ``selector`` (or the first
      ``<form>`` on the page if ``selector`` is empty).

    Requires the ``browser`` extra::

        pip install -e .[browser] && playwright install chromium

    Returns a dict with ``success``, ``output``, ``screenshot``
    (base64 PNG or ``None``), and action-specific extras.
    """
    import asyncio

    try:
        # Lazy import — keeps vuln_agent importable when the browser
        # extra is not installed.
        from securagentx.browser import BrowserTool

        if not BrowserTool().is_available():
            return {
                "success": False,
                "error": (
                    "Playwright is not installed. Install with: "
                    "pip install -e .[browser] && playwright install chromium"
                ),
                "output": "",
                "screenshot": None,
            }
    except ImportError as exc:
        return {
            "success": False,
            "error": f"securagentx.browser module unavailable: {exc}",
            "output": "",
            "screenshot": None,
        }

    async def _run() -> Dict[str, Any]:
        async with BrowserTool(headless=headless) as browser:
            return await browser.handle(action, url=url, selector=selector, text=text)

    try:
        # Bridge sync→async. If an event loop is already running in this
        # thread (rare for the vuln_agent dispatch path, but possible
        # inside Jupyter / hybrid_agent), fall back to a thread-pool
        # executor so we don't deadlock.
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False

        if in_loop:
            import concurrent.futures

            # Submit a closure that invokes ``asyncio.run`` on the
            # coroutine — ``pool.submit(asyncio.run, _run)`` would pass
            # the function itself, not its coroutine.
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(_run())).result(timeout=180)
        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        logger.error("browser tool failed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "output": "",
            "screenshot": None,
        }


def _tool_read_file(path: str, offset: int = 1, limit: int = 200) -> Dict[str, Any]:
    """Read a text file with line numbers. Use this to inspect source code,
    config files, logs, or any text file on the filesystem."""
    try:
        from pathlib import Path as _Path

        fpath = _Path(path).expanduser().resolve()
        if not fpath.exists():
            return {"success": False, "error": f"File not found: {fpath}"}
        if not fpath.is_file():
            return {"success": False, "error": f"Not a file: {fpath}"}

        text = fpath.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        total = len(lines)

        start = max(0, offset - 1)
        end = min(total, start + limit)
        snippet = lines[start:end]

        numbered = "\n".join(
            f"{i+1}|{line}" for i, line in enumerate(snippet, start + 1)
        )
        info = f"File: {fpath} ({total} lines, showing {start+1}-{end})\n"
        return {"success": True, "output": info + numbered, "total_lines": total}
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}


def _tool_write_file(path: str, content: str) -> Dict[str, Any]:
    """Create a new file or overwrite an existing one. Use this to save
    findings, write PoC scripts, create reports, or modify source code."""
    try:
        from pathlib import Path as _Path

        fpath = _Path(path).expanduser().resolve()
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
        return {"success": True, "output": f"Written {len(content)} bytes to {fpath}"}
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}


def _tool_edit_file(path: str, old_string: str, new_string: str) -> Dict[str, Any]:
    """Find and replace text in a file. Use this to make targeted edits
    without rewriting the whole file. The old_string must be unique."""
    try:
        from pathlib import Path as _Path

        fpath = _Path(path).expanduser().resolve()
        if not fpath.exists():
            return {"success": False, "error": f"File not found: {fpath}"}

        text = fpath.read_text(encoding="utf-8")
        count = text.count(old_string)
        if count == 0:
            return {"success": False, "error": "old_string not found in file"}
        if count > 1:
            return {"success": False, "error": f"old_string found {count} times (not unique)"}

        text = text.replace(old_string, new_string, 1)
        fpath.write_text(text, encoding="utf-8")
        return {"success": True, "output": f"Replaced 1 occurrence in {fpath}"}
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}


def _tool_search_files(pattern: str, path: str = ".", file_glob: str = "", limit: int = 20) -> Dict[str, Any]:
    """Search file contents using regex. Returns matching lines with context.
    Use this to find hardcoded credentials, API keys, vulnerable patterns,
    or any text across the filesystem.

    Routed through ``tools.safe_exec.execute_safely`` so the governance
    gate (CWE-78 hardening, timeout & output size limits) is enforced
    on the spawned ``grep`` process."""
    try:
        from tools.safe_exec import execute_safely

        cmd = ["grep", "-rn", "--color=never", pattern]
        if file_glob:
            cmd.extend(["--include", file_glob])
        cmd.append(path)

        # Execute via safe_exec so governance gate + CWE-78 hardening apply.
        # safe_exec expects a command string (applies shlex.split internally)
        # so build a shell-quoted string from the argv list.
        result = execute_safely(shlex.join(cmd), timeout=15)
        # grep returns exit_code 1 with empty stdout when no matches — that
        # is not an error, just "no hits". Preserve the legacy contract.
        # ``execute_safely`` is typed ``Dict[str, Union[str, int, bool]]`` so we
        # coerce stdout/stderr to ``str`` defensively before string ops.
        if result.get("exit_code") == 1 and not str(result.get("stdout") or "").strip():
            return {"success": True, "output": "No matches found."}

        lines = str(result.get("stdout") or "").strip().splitlines()
        truncated = len(lines) > limit
        output = "\n".join(lines[:limit])
        info = f"Searched '{pattern}' in {path}"
        if file_glob:
            info += f" (files: {file_glob})"
        info += f": {min(limit, len(lines))} matches"
        if truncated:
            info += f" (+{len(lines) - limit} more)"
        info += "\n"

        return {"success": True, "output": info + output, "total_matches": len(lines)}
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}


def _tool_run_command(command: str, timeout: int = 30) -> Dict[str, Any]:
    """Run a shell command and return its output. Use this to execute
    security tools, scripts, git commands, or any CLI program.
    WARNING: commands run directly on the host.

    Routed through ``tools.safe_exec.execute_safely`` so the governance
    gate (CWE-78 hardening: shlex.split + shell=False, timeout & output
    size limits) is enforced. ``execute_safely`` itself uses
    ``subprocess.run`` internally — that is intentional; the point of
    this indirection is to centralise command execution behind the
    governance layer rather than calling ``subprocess.run`` directly
    from agent code."""
    try:
        from tools.safe_exec import execute_safely

        # execute_safely expects a command string (it applies shlex.split
        # internally). Normalise list inputs to a shell-quoted string so
        # callers may pass either form, matching the legacy signature.
        if not isinstance(command, str):
            command = shlex.join(list(command))
        result = execute_safely(command, timeout=timeout)
        # Map safe_exec shape -> legacy tool shape consumed by the agent loop:
        #   safe_exec: {success, stdout, stderr, exit_code, error}
        #   legacy:    {success, output, exit_code} (or {success, error} on hard fail)
        # ``execute_safely`` is typed ``Dict[str, Union[str, int, bool]]`` so we
        # coerce stdout/stderr to ``str`` defensively before string ops.
        stdout = str(result.get("stdout") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        output = stdout
        if stderr:
            output += "\n[stderr]\n" + stderr[:2000]
        truncated = len(output) > 5000
        return {
            "success": bool(result.get("success", False)),
            "output": output[:5000] + ("\n...[truncated]" if truncated else ""),
            "exit_code": result.get("exit_code", -1),
        }
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}


def _tool_run_python(code: str, timeout: int = 30) -> Dict[str, Any]:
    """Execute arbitrary Python code and return its output.

    Use this when you need to:
    - Parse or transform complex scan results
    - Create custom HTTP requests with libraries
    - Write and test exploit PoCs
    - Analyze data programmatically beyond simple grep
    - Generate reports or visualizations

    Routed through ``tools.safe_exec.execute_safely`` so the governance
    gate (CWE-78 hardening, timeout & output size limits) is enforced
    on the spawned ``python3`` process."""
    import tempfile as _tf

    _tmp = None
    try:
        from tools.safe_exec import execute_safely

        _tmp = _tf.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        _tmp.write(code)
        _tmp.close()

        # Execute via safe_exec so governance gate + CWE-78 hardening apply.
        # safe_exec expects a command string (applies shlex.split internally)
        # so build a shell-quoted string from the argv list.
        cmd_str = shlex.join(["python3", _tmp.name])
        result = execute_safely(cmd_str, timeout=timeout)
        # Map safe_exec shape -> legacy tool shape.
        # ``execute_safely`` is typed ``Dict[str, Union[str, int, bool]]`` so we
        # coerce stdout/stderr to ``str`` defensively before string ops.
        stdout = str(result.get("stdout") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        output = stdout
        if stderr:
            output += "\n[stderr]\n" + stderr[:2000]
        truncated = len(output) > 5000
        return {
            "success": bool(result.get("success", False)),
            "output": output[:5000] + ("\n...[truncated]" if truncated else ""),
            "exit_code": result.get("exit_code", -1),
        }
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}
    finally:
        if _tmp:
            import os as _os

            try:
                _os.unlink(_tmp.name)
            except OSError:
                pass


def _tool_analyze_security(source: str, context: str = "") -> Dict[str, Any]:
    """Deep security analysis using AI reasoning.

    Feed source code, config files, logs, or scan output here for focused
    vulnerability analysis. The AI will examine the content with its full
    security expertise, separate from the main hunting loop.

    Use this when you need the AI to THINK deeply about security rather
    than just run a tool. Examples:
    - Analyze nginx.conf for misconfigurations
    - Review source code for SQL injection / XSS patterns
    - Examine log files for signs of exploitation
    - Evaluate a PoC or exploit script
    """
    try:
        from tools.universal_ai_client import UniversalAIClient, AIMessage

        prompt = f"""You are a senior application security engineer. Analyze the following for security vulnerabilities.

CONTEXT: {context}

SOURCE:
```
{source[:8000]}
```

Focus on:
1. **Vulnerabilities** — specific CVEs, misconfigs, weak patterns
2. **Exploitability** — how easy is it to exploit?
3. **Impact** — what's the worst case?
4. **Fix** — concrete remediation steps

Be specific. Reference line numbers, exact patterns, or CVE IDs when possible."""

        client = UniversalAIClient()
        messages = [AIMessage(role="user", content=prompt)]
        response = client.chat(messages)
        analysis = response.content.strip() if response else "No analysis returned."

        return {"success": True, "output": analysis[:6000]}
    except ImportError:
        return {"success": False, "error": "UniversalAIClient not available"}
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": str(exc)}



CHILD_AGENT_CODE = r"""True multi-AI child: runs as subprocess, has full VulnAgent reasoning loop."""

import sys as _sys
import json as _json
import tempfile as _tempfile
from pathlib import Path as _Path


def _run_child_agent(target: str, output_path: str) -> None:
    """Entry point called by delegate subprocess."""
    try:
        from securagentx.agent.vuln_agent import VulnAgent
        from securagentx.governance import GovernanceGate
        from tools.universal_ai_client import UniversalAIClient

        client = UniversalAIClient()
        agent = VulnAgent(
            client=client,
            target=target,
            max_steps=8,
            report_dir=_Path(_tempfile.mkdtemp(prefix="securagentx_delegate_")),
            governance=GovernanceGate(),
        )
        report = agent.hunt(verbose=False)

        result = {
            "target": target,
            "success": True,
            "findings": [
                {
                    "title": f.title,
                    "severity": f.severity,
                    "description": f.description[:300],
                    "evidence": f.evidence[:500],
                    "remediation": f.remediation[:300],
                }
                for f in report.findings
            ],
            "open_ports": report.open_ports,
            "services": report.services,
            "summary": report.summary[:600],
            "steps_used": report.total_steps,
        }
    except Exception as e:  # noqa: BLE001 — broad catch for resilience
        result = {"target": target, "success": False, "error": str(e)[:600]}

    _Path(output_path).write_text(_json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _run_child_agent(_sys.argv[1], _sys.argv[2])




CHILD_AGENT_CODE = r"""True multi-AI child: runs as subprocess, has full VulnAgent reasoning loop."""

import sys as _sys
import json as _json
import tempfile as _tempfile
from pathlib import Path as _Path


def _run_child_agent(target: str, output_path: str) -> None:  # type: ignore[no-redef]
    """Entry point called by delegate subprocess."""
    try:
        from securagentx.agent.vuln_agent import VulnAgent
        from securagentx.governance import GovernanceGate
        from tools.universal_ai_client import UniversalAIClient

        client = UniversalAIClient()
        agent = VulnAgent(
            client=client,
            target=target,
            max_steps=8,
            report_dir=_Path(_tempfile.mkdtemp(prefix="securagentx_delegate_")),
            governance=GovernanceGate(),
        )
        report = agent.hunt(verbose=False)

        result = {
            "target": target,
            "success": True,
            "findings": [
                {
                    "title": f.title,
                    "severity": f.severity,
                    "description": f.description[:300],
                    "evidence": f.evidence[:500],
                    "remediation": f.remediation[:300],
                }
                for f in report.findings
            ],
            "open_ports": report.open_ports,
            "services": report.services,
            "summary": report.summary[:600],
            "steps_used": report.total_steps,
        }
    except Exception as e:  # noqa: BLE001 — broad catch for resilience
        result = {"target": target, "success": False, "error": str(e)[:600]}

    _Path(output_path).write_text(_json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _run_child_agent(_sys.argv[1], _sys.argv[2])




CHILD_AGENT_CODE = r"""import sys, json, os
from pathlib import Path

# Add project root to path for 'tools' package
sys.path.insert(0, os.environ.get("__SECURAGENTX_CWD", os.getcwd()))

def _make_client():
    # Create UniversalAIClient from parent-passed config or auto-detect
    from tools.universal_ai_client import UniversalAIClient

    config_json = os.environ.get("__SECURAGENTX_AI_CONFIG")
    if config_json:
        try:
            cfg = json.loads(config_json)
            return UniversalAIClient(
                provider=cfg.get("provider", "auto"),
                api_key=cfg.get("api_key"),
                base_url=cfg.get("base_url"),
                model=cfg.get("model"),
            )
        except Exception:
            pass
    return UniversalAIClient()

def _run_child(target: str, output_path: str) -> None:
    try:
        from securagentx.agent.vuln_agent import VulnAgent
        from securagentx.governance import GovernanceGate
        client = _make_client()
        agent = VulnAgent(client=client, target=target, max_steps=8, report_dir=Path("/tmp/securagentx_delegate"), governance=GovernanceGate())
        report = agent.hunt(verbose=False)
        result = {
            "target": target,
            "success": True,
            "findings": [
                {"title": f.title, "severity": f.severity,
                 "description": f.description[:300],
                 "evidence": f.evidence[:500], "remediation": f.remediation[:300]}
                for f in report.findings
            ],
            "open_ports": report.open_ports,
            "services": report.services,
            "summary": report.summary[:600],
            "steps_used": report.total_steps,
        }
    except Exception as e:
        result = {"target": target, "success": False, "error": str(e)[:600]}
    Path(output_path).write_text(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    _run_child(sys.argv[1], sys.argv[2])
"""


def _delegate_via_primary_agent(
    task: str,
    targets: list,
    max_steps: int,
    timeout: int,
) -> Dict[str, Any]:
    """In-process multi-agent delegation via :class:`PrimaryAgent`.

    Lazily imports PrimaryAgent; builds a minimal specialist-handler set;
    runs one PrimaryAgent per target inside the current process (no
    subprocess spawn). Mirrors :func:`_tool_delegate`'s output shape so the
    parent AI consumes both paths identically.

    Raises on any import / construction error so :func:`_tool_delegate` can
    fall back to the subprocess path. Per-target runtime errors are captured
    into ``results[target]["error"]`` and never bubble up — only the wiring
    itself is allowed to fail loudly.

    Note: the specialist handlers are intentionally minimal stubs in P5. The
    point of this path is to exercise the PrimaryAgent orchestrator
    in-process so callers can swap in real specialists (Searcher, Pentester,
    Coder, ...) in a later phase without touching ``_tool_delegate`` again.
    """
    import asyncio

    from securagentx.agents.primary_agent import PrimaryAgent
    from securagentx.paths import find_env as _find_env

    # ------------------------------------------------------------------
    # Detect AI config from .env (mirrors the subprocess path's logic).
    # ------------------------------------------------------------------
    ai_config: Optional[Dict[str, str]] = None
    _env_path = _find_env()
    if _env_path and _env_path.exists():
        try:
            with open(_env_path) as _ef:
                for _line in _ef:
                    _line = _line.strip()
                    if not _line or _line.startswith("#") or "=" not in _line:
                        continue
                    _k, _v = _line.split("=", 1)
                    if _k.endswith("_API_KEY") and _v and "placeholder" not in _v:
                        _provider = _k.replace("_API_KEY", "").lower()
                        try:
                            from tools.universal_ai_client import UniversalAIClient
                            for _pname, _pcfg in UniversalAIClient.PROVIDER_CONFIGS.items():
                                if _pname == _provider:
                                    ai_config = {
                                        "provider": _provider,
                                        "api_key": _v,
                                        "base_url": _pcfg.get("base_url", ""),  # type: ignore[attr-defined]
                                        "model": _pcfg.get("default_model", ""),  # type: ignore[attr-defined]
                                    }
                                    break
                        except Exception as e:  # noqa: BLE001
                            logger.debug("UniversalAIClient provider scan failed: %s", e)
                        if ai_config:
                            break
        except Exception as e:  # noqa: BLE001
            logger.debug("AI config detection failed: %s", e)

    # ------------------------------------------------------------------
    # Build the LLM client.
    # ------------------------------------------------------------------
    llm_client: Any = None
    if ai_config:
        try:
            from tools.universal_ai_client import UniversalAIClient
            llm_client = UniversalAIClient(
                provider=ai_config["provider"],
                api_key=ai_config["api_key"],
                base_url=ai_config.get("base_url", ""),
                model=ai_config.get("model", ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("UniversalAIClient construction failed: %s", exc)

    if llm_client is None:
        raise RuntimeError(
            "no LLM client available for PrimaryAgent multi-agent path"
        )

    # ------------------------------------------------------------------
    # Minimal specialist handlers — P5 wiring only. Real specialists are
    # injected later by callers who construct PrimaryAgent directly.
    # ------------------------------------------------------------------
    def _specialist_handler(args_json: str, ctx: Any) -> str:
        return f"[P5 stub specialist] received: {args_json[:200]}"

    def _barrier_handler(tool_name: str, args_json: str, ctx: Any) -> str:
        return f"[P5 barrier:{tool_name}] {args_json[:200]}"

    tool_handlers = {
        "search":   _specialist_handler,
        "pentest":  _specialist_handler,
        "code":     _specialist_handler,
        "advice":   _specialist_handler,
        "memorize": _specialist_handler,
        "maintain": _specialist_handler,
        "barrier":  _barrier_handler,
    }

    # ------------------------------------------------------------------
    # Run one PrimaryAgent per target — serially to keep memory bounded.
    # ------------------------------------------------------------------
    results: Dict[str, Any] = {}
    errors: List[str] = []

    for target in targets:
        subtask = f"{task} (target={target})"
        try:
            agent = PrimaryAgent(
                llm_client=llm_client,
                tool_handlers=tool_handlers,
                max_iterations=max_steps,
            )
            perf = asyncio.run(agent.run(subtask))
            done = getattr(perf, "value", str(perf)) == "done"
            results[target] = {
                "target": target,
                "success": done,
                "steps_used": agent.stats.iterations,
                "summary": f"PrimaryAgent result: {perf}",
                "findings": [],
            }
        except Exception as exc:  # noqa: BLE001 — per-target isolation
            results[target] = {
                "target": target,
                "success": False,
                "error": str(exc)[:300],
            }
            errors.append(target)

    # ------------------------------------------------------------------
    # Aggregate — mirror _tool_delegate's output shape.
    # ------------------------------------------------------------------
    summary_lines = [
        f"Delegate (multi-agent): {task}",
        f"Targets: {len(targets)}  |  Max steps per PrimaryAgent: {max_steps}",
        "",
    ]
    success_count = sum(1 for r in results.values() if r.get("success"))
    for t in targets:
        info = results.get(t, {"success": False, "error": "No result"})
        if info.get("success"):
            summary_lines.append(f"  OK {t}: {info.get('summary', '')[:100]}")
        else:
            summary_lines.append(
                f"  FAIL {t}: {info.get('error', 'unknown error')[:100]}"
            )
    summary_lines.append(
        f"\nResults: {success_count}/{len(targets)} PrimaryAgents completed"
    )

    return {
        "success": len(errors) < len(targets),
        "output": "\n".join(summary_lines),
        "aggregated": results,
        "total_findings": 0,
    }


def _tool_delegate(
    task: str,
    targets: list,
    max_steps: int = 5,
    timeout: int = 120,
    multi_agent: bool = False,
) -> Dict[str, Any]:
    """Spawn TRUE VulnAgent instances per target — each child is an independent AI agent
    with its own THINK -> ACT -> ANALYZE loop, full tool access, and freedom to pivot.

    Unlike the old parallel-function approach, each child:
      - Reasons about its target autonomously
      - Chooses which tools to call and in what order
      - Pivots based on findings
      - Concludes independently when it has enough evidence

    Returns aggregated results with per-target findings, ports, and summary.
    The parent AI can then merge insights across targets.

    When ``multi_agent=True``, an in-process :class:`PrimaryAgent` orchestrator
    is attempted per target instead of spawning subprocess children. This is
    strictly optional — any failure (missing dependencies, missing specialist
    handlers, async runtime issues) falls back to the existing subprocess path.
    """
    # ------------------------------------------------------------------
    # Multi-agent path: try PrimaryAgent in-process; fall back on any error.
    # ------------------------------------------------------------------
    if multi_agent:
        try:
            return _delegate_via_primary_agent(task, targets, max_steps, timeout)
        except Exception as exc:  # noqa: BLE001 — multi-agent is best-effort
            logger.warning(
                "multi-agent delegate failed (%s) — falling back to subprocess", exc
            )

    import concurrent.futures
    import json
    import os
    import shutil
    import subprocess as sp
    import sys
    import tempfile
    from pathlib import Path as _Path

    workdir = _Path(tempfile.mkdtemp(prefix="securagentx_delegate_"))

    # Write child script once — self-contained VulnAgent
    child_script = workdir / "_child.py"
    child_script.write_text(CHILD_AGENT_CODE)

    results = {}
    errors = []

    # Detect and pack AI config for children
    env = dict(os.environ)
    env["__SECURAGENTX_CWD"] = os.getcwd()
    env["PYTHONUNBUFFERED"] = "1"

    # Try to find a real API key from .env for child agents
    from securagentx.paths import find_env as _find_env

    _env_path = _find_env()
    if _env_path and _env_path.exists():
        try:
            with open(_env_path) as _ef:
                for _line in _ef:
                    _line = _line.strip()
                    if not _line or _line.startswith("#") or "=" not in _line:
                        continue
                    _k, _v = _line.split("=", 1)
                    if _k.endswith("_API_KEY") and _v and "placeholder" not in _v:
                        _provider = _k.replace("_API_KEY", "").lower()
                        for _pname, _pcfg in __import__("tools.universal_ai_client", fromlist=["UniversalAIClient"]).UniversalAIClient.PROVIDER_CONFIGS.items():
                            if _pname == _provider:
                                env["__SECURAGENTX_AI_CONFIG"] = json.dumps({
                                    "provider": _provider,
                                    "api_key": _v,
                                    "base_url": _pcfg.get("base_url", ""),
                                    "model": _pcfg.get("default_model", ""),
                                })
                                break
                        if "__SECURAGENTX_AI_CONFIG" in env:
                            break
        except Exception as e:  # noqa: BLE001 — logged
            logger.debug("Suppressed Exception: %s", e)

    def _spawn_one(target: str) -> None:
        """Launch a VulnAgent subprocess for one target."""
        safe_name = target.replace(".", "_").replace(":", "_").replace("/", "_")
        out_file = workdir / f"result_{safe_name}.json"
        try:
            r = sp.run(
                [sys.executable, str(child_script), target, str(out_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except sp.TimeoutExpired:
            results[target] = {"target": target, "success": False, "error": f"Timed out after {timeout}s"}
            return
        except Exception as e:  # noqa: BLE001 — broad catch for resilience
            results[target] = {"target": target, "success": False, "error": str(e)[:300]}
            return

        if out_file.exists():
            try:
                results[target] = json.loads(out_file.read_text())
            except json.JSONDecodeError:
                results[target] = {"target": target, "success": False, "error": "Bad child result JSON"}
        else:
            results[target] = {"target": target, "success": False, "error": (r.stderr or "No output file")[:500]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(targets), 5)) as pool:
        pool.map(_spawn_one, targets)

    try:
        shutil.rmtree(workdir, ignore_errors=True)
    except Exception as e:  # noqa: BLE001 — logged
        logger.debug("Suppressed Exception: %s", e)

    summary_lines = [
        f"Delegate: {task}",
        f"Targets: {len(targets)}  |  Max steps per child: {max_steps}",
        "",
    ]
    success_count = 0
    total_findings = 0

    for t in targets:
        info = results.get(t, {"success": False, "error": "No result returned"})
        if info.get("success"):
            success_count += 1
            findings = info.get("findings", [])
            total_findings += len(findings)  # type: ignore[arg-type]
            ports = info.get("open_ports", [])
            services = info.get("services", {})
            steps = info.get("steps_used", "?")
            summary_lines.append(
                f"  [{steps} steps] {t}  "
                + (f"ports={ports}" if ports else "")
                + (f" services={list(services.keys())}" if services else "")  # type: ignore[attr-defined]
            )
            for f in findings[:3]:  # type: ignore[index]
                summary_lines.append(f"    - [{f['severity'].upper()}] {f['title'][:80]}")
            if len(findings) > 3:  # type: ignore[arg-type]
                summary_lines.append(f"    ... (+{len(findings)-3} more)")  # type: ignore[arg-type]
            if info.get("summary"):
                summary_lines.append(f"    summary: {info['summary'][:120]}")  # type: ignore[index]
        else:
            errors.append(t)
            summary_lines.append(f"  FAIL {t}: {info.get('error', 'unknown error')[:100]}")  # type: ignore[index]

    summary_lines.append(f"\nResults: {success_count}/{len(targets)} agents completed  |  {total_findings} total findings")
    if errors:
        summary_lines.append(f"Failed: {', '.join(errors)}")

    return {
        "success": len(errors) < len(targets),
        "output": "\n".join(summary_lines),
        "aggregated": results,
        "total_findings": total_findings,
    }


# ---------------------------------------------------------------------------
# Dynamic tool creation — AI can extend its own toolbox at runtime
# ---------------------------------------------------------------------------

_dynamic_tools: Dict[str, Callable] = {}
"""Runtime registry for AI-generated tools. Maps name → handler function."""

# Safety cage: max edits per session to prevent catastrophic self-modification
_edit_count = 0
_MAX_EDITS = 5


def _register_dynamic_tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    handler_code: str,
) -> Dict[str, Any]:
    """Register a dynamically generated tool.

    Writes the handler code to ~/.securagentx/tools/{name}.py for persistence,
    creates a wrapper function, and registers it so the agent can call it.

    Returns success/error dict.
    """
    import sys as _sys

    # 1. Validate the handler code compiles
    try:
        compile(handler_code, f"<{name}>", "exec")
    except SyntaxError as exc:
        return {"success": False, "error": f"Syntax error in handler code: {exc}"}

    # 2. Write to ~/.securagentx/tools/ for persistence
    gen_dir = Path("~/.securagentx/tools").expanduser()
    gen_dir.mkdir(parents=True, exist_ok=True)
    gen_path = gen_dir / f"{name}.py"
    try:
        gen_path.write_text(handler_code)
    except OSError as exc:
        return {"success": False, "error": f"Failed to write handler file: {exc}"}

    # 3. Import the module to get the handler function
    #    Expects a function named `handler(args: dict) -> dict` in the generated code
    _sys.path.insert(0, str(gen_dir))
    try:
        import importlib as _il

        mod = _il.import_module(name)
        _il.reload(mod)
        handler_fn = getattr(mod, "handler", None)
        if handler_fn is None:
            return {
                "success": False,
                "error": "Generated code must define a function named 'handler' that takes a dict and returns a dict",
            }
        # Test it compiles by running with empty args
        try:
            test_result = handler_fn({})
            if not isinstance(test_result, dict):
                return {"success": False, "error": "handler() must return a dict"}
        except Exception as e:  # noqa: BLE001 — broad catch for resilience
            # may legitimately require arguments
            logger.debug("Suppressed Exception (handler test): %s", e)
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        return {"success": False, "error": f"Failed to load generated tool module: {exc}"}
    finally:
        if str(gen_dir) in _sys.path:
            _sys.path.remove(str(gen_dir))

    # 4. Register in dynamic tools dict
    _dynamic_tools[name] = handler_fn

    # 5. Register in AVAILABLE_TOOLS
    tool_entry = {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": parameters.get("properties", {}),
            "required": parameters.get("required", []),
        },
        "handler_name": None,  # dynamic — resolved via _dynamic_tools
        "_is_dynamic": True,
    }
    # Remove if already present (refresh)
    AVAILABLE_TOOLS[:] = [t for t in AVAILABLE_TOOLS if t["name"] != name]
    AVAILABLE_TOOLS.append(tool_entry)

    logger.info("Dynamic tool registered: %s from %s", name, gen_path)
    return {
        "success": True,
        "output": f"Tool '{name}' created and registered. You can now call it like any other tool.",
        "tool_path": str(gen_path),
    }


def _tool_create_tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    handler_code: str,
) -> Dict[str, Any]:
    """Create a new tool at runtime.

    Args:
        name: Short unique name (snake_case, e.g. 'custom_port_scanner')
        description: What this tool does — will be shown to the AI
        parameters: JSON Schema object defining required/properties
        handler_code: Python code defining a 'handler(args: dict) -> dict' function

    The handler_code must define:
        def handler(args: dict) -> dict:
            # ... your logic ...
            return {"success": True, "output": "..."}

    Use this when you need a specialized capability not covered by existing tools.
    The new tool is immediately available for future turns.
    """
    return _register_dynamic_tool(name, description, parameters, handler_code)


def _tool_edit_own_tool(name: str, handler_code: str) -> Dict[str, Any]:
    """Edit an existing dynamic tool's handler code at runtime.

    Args:
        name: Tool name to edit (must be an AI-created dynamic tool)
        handler_code: New Python code defining 'handler(args: dict) -> dict'

    Use this to fix bugs, improve performance, or add new capabilities
    to a tool you created earlier with create_tool.
    The tool's name, description, and parameter schema stay the same —
    only the implementation changes.

    Safety: max 5 edits per session. Built-in tools cannot be edited.
    """
    global _edit_count

    # Safety cage: enforce session edit limit
    if _edit_count >= _MAX_EDITS:
        return {
            "success": False,
            "error": f"Edit limit ({_MAX_EDITS}) reached this session. "
                     f"Restart the agent to edit more tools.",
        }

    # Only allow editing dynamic (AI-created) tools
    if name not in _dynamic_tools:
        return {
            "success": False,
            "error": f"Tool '{name}' not found or is a built-in tool. "
                     f"Only AI-created dynamic tools can be edited. "
                     f"Available: {list(_dynamic_tools.keys())}",
        }

    # Find the existing tool entry to preserve metadata
    existing = None
    for t in AVAILABLE_TOOLS:
        if t["name"] == name:
            existing = t
            break
    if existing is None:
        return {"success": False, "error": f"Tool '{name}' not found in registry (race condition)"}

    # Validate syntax
    try:
        compile(handler_code, f"<{name}>", "exec")
    except SyntaxError as exc:
        return {"success": False, "error": f"Syntax error in handler code: {exc}"}

    # Write new handler to disk
    gen_dir = Path("~/.securagentx/tools").expanduser()
    gen_path = gen_dir / f"{name}.py"
    backup: Path | None = None
    try:
        # Backup first
        if gen_path.exists():
            backup = gen_path.with_suffix(".py.bak")
            gen_path.rename(backup)
        gen_path.write_text(handler_code)
    except OSError as exc:
        return {"success": False, "error": f"Failed to write handler file: {exc}"}

    # Re-import the module to get the new handler
    import sys as _sys

    _sys.path.insert(0, str(gen_dir))
    import importlib as _il
    try:
        mod = _il.import_module(name)
        _il.reload(mod)
        handler_fn = getattr(mod, "handler", None)
        if handler_fn is None:
            if backup is not None:
                backup.rename(gen_path)
            return {
                "success": False,
                "error": "Edited code must define a function named 'handler' that takes a dict and returns a dict",
            }
        # Quick test with empty args
        try:
            test_result = handler_fn({})
            if not isinstance(test_result, dict):
                if backup is not None:
                    backup.rename(gen_path)
                    # Re-import original
                    mod = _il.import_module(name)
                    _il.reload(mod)
                    handler_fn = getattr(mod, "handler", None)
                    if handler_fn is not None:
                        _dynamic_tools[name] = handler_fn
                return {"success": False, "error": "handler() must return a dict"}
        except Exception as e:  # noqa: BLE001 — broad catch for resilience
            # may legitimately require arguments
            logger.debug("Suppressed Exception (handler test): %s", e)
    except Exception as exc:  # noqa: BLE001 — broad catch for resilience
        # Restore backup on import failure
        if backup is not None:
            backup.rename(gen_path)
            try:
                mod = _il.import_module(name)
                _il.reload(mod)
                orig_fn = getattr(mod, "handler", None)
                if orig_fn is not None:
                    _dynamic_tools[name] = orig_fn
            except Exception as e:  # noqa: BLE001 — logged
                logger.debug("Suppressed Exception: %s", e)
        return {"success": False, "error": f"Failed to load edited tool module: {exc}"}
    finally:
        if str(gen_dir) in _sys.path:
            _sys.path.remove(str(gen_dir))

    # Register updated handler
    _dynamic_tools[name] = handler_fn  # type: ignore[assignment]

    # Clean up backup on success
    if backup is not None and backup.exists():
        backup.unlink(missing_ok=True)

    _edit_count += 1
    remaining = _MAX_EDITS - _edit_count

    logger.info("Tool edited: %s (%d/%d edits used)", name, _edit_count, _MAX_EDITS)
    return {
        "success": True,
        "output": f"Tool '{name}' updated successfully. "
                  f"{remaining} edit(s) remaining this session. "
                  f"The new handler is active immediately.",
        "tool_path": str(gen_path),
        "edits_remaining": remaining,
    }


# ---------------------------------------------------------------------------
# Memory tools
# ---------------------------------------------------------------------------

_MEMORY_STORE = MemoryStore()
_SKILL_STORE = SkillStore()


def _tool_save_memory(content: str, tags: str = "") -> Dict[str, Any]:
    """Save a fact or note to persistent cross-session memory."""
    entry = _MEMORY_STORE.save(content=content, tags=tags)
    total = _MEMORY_STORE.count()
    return {
        "success": True,
        "output": f"Saved memory [{entry['id']}]. You now have {total} memory entries. "
                  f"Use `recall_memory` to search later.",
        "memory_id": entry["id"],
    }


def _tool_recall_memory(query: str, limit: int = 5) -> Dict[str, Any]:
    """Search cross-session memory by keywords. Returns matching entries."""
    results = _MEMORY_STORE.search(query=query, limit=limit)
    if not results:
        return {"success": True, "output": f"No memories matching '{query}'. Save some with `save_memory`."}
    lines = [f"Found {len(results)} memory entries matching '{query}':"]
    for entry in results:
        lines.append(f"\n  [{entry['id']}] ({entry.get('tags','')})")
        lines.append(f"    {entry['content'][:300]}")
    return {"success": True, "output": "\n".join(lines), "entries": results}


def _tool_list_memories(limit: int = 10) -> Dict[str, Any]:
    """List recent memory entries."""
    entries = _MEMORY_STORE.list_all(limit=limit)
    if not entries:
        return {"success": True, "output": "No memories yet. Save some with `save_memory`."}
    lines = [f"Recent memories ({len(entries)} shown, {_MEMORY_STORE.count()} total):"]
    for entry in entries:
        lines.append(f"\n  [{entry['id']}] ({entry.get('tags','')})")
        lines.append(f"    {entry['content'][:300]}")
    return {"success": True, "output": "\n".join(lines), "entries": entries}


def _tool_forget_memory(memory_id: str) -> Dict[str, Any]:
    """Remove a specific memory entry by id."""
    if _MEMORY_STORE.forget(memory_id):
        return {"success": True, "output": f"Memory [{memory_id}] forgotten."}
    return {"success": False, "error": f"Memory [{memory_id}] not found. Use `list_memories` to see valid ids."}


# ---------------------------------------------------------------------------
# Skill tools
# ---------------------------------------------------------------------------


def _tool_create_skill(name: str, description: str, content: str) -> Dict[str, Any]:
    """Save a reusable technique/procedure as a named skill."""
    _SKILL_STORE.save(name=name, description=description, content=content)
    total = _SKILL_STORE.count()
    return {
        "success": True,
        "output": f"Skill '{name}' created ({total} skills total). "
                  f"Use `view_skill` to read it or `list_skills` to see all.",
    }


def _tool_view_skill(name: str) -> Dict[str, Any]:
    """Read a saved skill by name."""
    skill = _SKILL_STORE.get(name=name)
    if not skill:
        return {"success": False, "error": f"Skill '{name}' not found. Use `list_skills` to see available."}
    return {
        "success": True,
        "output": f"# {skill['name']}\n{skill['description']}\n\n{skill['content']}\n",
        "skill": skill,
    }


def _tool_list_skills() -> Dict[str, Any]:
    """List all saved skills."""
    skills = _SKILL_STORE.list_all()
    if not skills:
        return {"success": True, "output": "No skills yet. Create one with `create_skill`."}
    lines = [f"Skills ({len(skills)}):"]
    for s in skills:
        desc = s.get("description", "")[:100]
        lines.append(f"  - {s['name']}: {desc}")
    return {"success": True, "output": "\n".join(lines), "skills": skills}


def _tool_delete_skill(name: str) -> Dict[str, Any]:
    """Remove a skill by name."""
    if _SKILL_STORE.delete(name=name):
        return {"success": True, "output": f"Skill '{name}' deleted."}
    return {"success": False, "error": f"Skill '{name}' not found."}


# ---------------------------------------------------------------------------
# Knowledge Graph tool
# ---------------------------------------------------------------------------

def _tool_knowledge_graph(action: str = "help", **kwargs) -> Dict[str, Any]:
    """Access the SecurAgentX Knowledge Graph - a networkx-backed graph
    that tracks entities (domains, IPs, CVEs, services, credentials),
    relationships between them, observations, chat messages, and episodes
    (tool/agent runs).

    Supports 7 search types via the ``action`` parameter:
      - search_temporal             - args: start, end, max_results
      - search_entity_relationships - args: center_entity, max_depth, max_results
      - search_diverse              - args: query, max_results, diversity(low|medium|high)
      - search_episode_context      - args: episode_id, max_results
      - search_successful_tools     - args: task_type(optional), max_results
      - search_recent_context       - args: max_results, recency(1h|6h|24h|7d)
      - search_entity_by_label      - args: label, max_results

    Plus ingestion actions:
      - add_entity       - args: label, entity_type, properties
      - add_relationship - args: source, target, rel_type, properties
      - add_observation  - args: text, timestamp, metadata
      - add_message      - args: role, content, timestamp
      - add_episode      - args: episode_id(optional), description, metadata

    Plus utility actions: stats, clear, save, load, help.
    """
    try:
        from securagentx.knowledge_graph.kg_tool import KnowledgeGraphTool
    except Exception as exc:  # noqa: BLE001 - surfaced to agent
        return {
            "success": False,
            "error": f"Knowledge Graph subsystem unavailable: {exc}",
        }

    tool = KnowledgeGraphTool()
    if not tool.is_available():
        return {
            "success": False,
            "error": "Knowledge Graph subsystem unavailable (networkx missing?).",
        }

    output = tool.handle(action, kwargs)
    return {
        "success": True,
        "output": output,
        "action": action,
    }


# NOTE: handler_name is a string (not a function reference) so that
# unittest.mock.patch works correctly at runtime.
AVAILABLE_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "port_scan",
        "description": "Scan target for open ports and running services. Returns port numbers and service names.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target IP or domain"},
                "ports": {
                    "type": "string",
                    "description": "Port range: 'common' (top 1000), 'all', or '80,443,8080'",
                    "default": "common",
                },
            },
            "required": ["target"],
        },
        "handler_name": "_tool_port_scan",
    },
    {
        "name": "web_recon",
        "description": "Probe web server: HTTP headers, technologies, directories, endpoints.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target URL or domain"},
                "path": {
                    "type": "string",
                    "description": "Base path to scan (default: /)",
                    "default": "/",
                },
            },
            "required": ["target"],
        },
        "handler_name": "_tool_web_recon",
    },
    {
        "name": "vuln_scan",
        "description": "Run vulnerability scanner against target to find known vulnerabilities.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target IP or domain"},
                "scan_type": {
                    "type": "string",
                    "description": "Scanner type: 'general', 'web', 'network'",
                    "default": "general",
                },
            },
            "required": ["target"],
        },
        "handler_name": "_tool_vuln_scan",
    },
    {
        "name": "search_cve",
        "description": "Search for known CVEs affecting a specific software or service version.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name (e.g., 'apache', 'nginx', 'openssh')"},
                "version": {
                    "type": "string",
                    "description": "Version string (optional, e.g. '2.4.49')",
                    "default": "",
                },
            },
            "required": ["service"],
        },
        "handler_name": "_tool_search_cve",
    },
    {
        "name": "analyze_target",
        "description": "Initial intelligence gathering: DNS records, WHOIS, technology stack detection.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target domain or IP"}
            },
            "required": ["target"],
        },
        "handler_name": "_tool_analyze_target",
    },
    {
        "name": "web_search",
        "description": "Search the web for real-time information using DuckDuckGo. Returns titles, URLs and content snippets. Use to research CVEs, recent advisories, bug bounty reports, known attack patterns, or any target-specific intelligence.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query (e.g., 'nginx 1.18 CVE', 'Spring Boot RCE 2026', 'bug bounty SQL injection')"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (1-10, default 5)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        },
        "handler_name": "_tool_web_search",
    },
    {
        "name": "web_extract",
        "description": "Fetch and extract readable text content from a URL. Use after web_search to read the full content of an article, CVE advisory, or blog post. Returns clean text without HTML/ads/navigation.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The full URL to extract content from"}
            },
            "required": ["url"],
        },
        "handler_name": "_tool_web_extract",
    },
    {
        "name": "browser",
        "description": "Drive a real headless Chromium browser (Playwright) to navigate, click, type, screenshot, and extract content from JavaScript-rendered pages. Use this when web_extract fails (page needs JS), when you need to interact with forms (click/type/submit), or when a screenshot would help the analysis. Actions: navigate, click, type, screenshot, content_md, content_html, links, form_submit. Requires the [browser] extra (pip install -e .[browser] && playwright install chromium).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Browser action to perform. One of: navigate, click, type, screenshot, content_md, content_html, links, form_submit.",
                    "enum": ["navigate", "click", "type", "screenshot", "content_md", "content_html", "links", "form_submit"],
                },
                "url": {
                    "type": "string",
                    "description": "Target URL (required for navigate, screenshot, content_md, content_html, links). Ignored for click/type/form_submit which operate on the current page.",
                    "default": "",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS or XPath selector (required for click, type, form_submit; ignored otherwise).",
                    "default": "",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type into the element at `selector` (required for type action).",
                    "default": "",
                },
                "headless": {
                    "type": "boolean",
                    "description": "Run browser in headless mode (default: true). Set to false for debugging.",
                    "default": True,
                },
            },
            "required": ["action"],
        },
        "handler_name": "_tool_browser",
    },
    {
        "name": "read_file",
        "description": "Read a text file with line numbers. Use this to inspect source code, config files, logs, or any text file on the filesystem. Supports offset and limit for large files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
                "offset": {"type": "integer", "description": "Starting line number (1-based, default: 1)", "default": 1, "minimum": 1},
                "limit": {"type": "integer", "description": "Max lines to return (default: 200, max: 1000)", "default": 200, "maximum": 1000},
            },
            "required": ["path"],
        },
        "handler_name": "_tool_read_file",
    },
    {
        "name": "write_file",
        "description": "Create a new file or overwrite an existing one. Use this to save findings, write PoC scripts, create reports, or modify source code. Creates parent directories automatically.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["path", "content"],
        },
        "handler_name": "_tool_write_file",
    },
    {
        "name": "edit_file",
        "description": "Find and replace text in a file. Use this to make targeted edits without rewriting the whole file. The old_string must be unique in the file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
                "old_string": {"type": "string", "description": "Existing text to replace (must be unique)"},
                "new_string": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_string", "new_string"],
        },
        "handler_name": "_tool_edit_file",
    },
    {
        "name": "search_files",
        "description": "Search file contents using regex. Returns matching lines with file paths. Use this to find hardcoded credentials, API keys, vulnerable patterns, or any text across the codebase.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory to search (default: current dir)", "default": "."},
                "file_glob": {"type": "string", "description": "File pattern filter (e.g., '*.py', '*.conf'). Leave empty for all files.", "default": ""},
                "limit": {"type": "integer", "description": "Max results to return (default: 20)", "default": 20, "maximum": 100},
            },
            "required": ["pattern"],
        },
        "handler_name": "_tool_search_files",
    },
    {
        "name": "run_command",
        "description": "Run a shell command and return its output. Use this to execute security tools, scripts, git commands, or any CLI program. WARNING: runs directly on the host system. Prefer other tools when available.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30, max: 120)", "default": 30, "maximum": 120},
            },
            "required": ["command"],
        },
        "handler_name": "_tool_run_command",
    },
    {
        "name": "run_python",
        "description": "Execute arbitrary Python code and return its output. Use this to parse complex scan results, create custom HTTP requests, write exploit PoCs, analyze data programmatically, or generate reports. The code runs in a temporary file with full access to installed packages (requests, BeautifulSoup, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute (multi-line, full access to stdlib + pip-installed packages)"},
                "timeout": {"type": "integer", "description": "Max execution time in seconds (default: 30, max: 120)", "default": 30, "maximum": 120},
            },
            "required": ["code"],
        },
        "handler_name": "_tool_run_python",
    },
    {
        "name": "analyze_security",
        "description": "Deep security analysis using AI reasoning. Feed source code, config files, logs, or scan output here for focused vulnerability analysis. The AI will examine the content with its full security expertise — identifying CVEs, misconfigs, exploit paths, and fixes. Use this when you need to THINK deeply about security rather than just run a tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source code, config file, log, or scan output to analyze (up to 8000 chars)"},
                "context": {"type": "string", "description": "Optional context about what to focus on (e.g., 'nginx config for auth bypass', 'log analysis for exploitation signs')", "default": ""},
            },
            "required": ["source"],
        },
        "handler_name": "_tool_analyze_security",
    },
    {
        "name": "delegate",
        "description": "Spawn TRUE AI agents per target — each is an independent VulnAgent with its own reasoning loop, full tool access, and freedom to pivot. Instead of running fixed functions, each child THINKS, ACTS, and CONCLUDES on its own. Use this for multi-target campaigns where each target deserves intelligent analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Mission description (e.g., 'Scan nginx targets for known CVEs and misconfigs')"},
                "targets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of target IPs or domains — each gets its own AI agent"
                },
                "max_steps": {"type": "integer", "description": "Max reasoning steps per child agent (default: 5, max: 20). More steps = deeper analysis but slower.", "default": 5, "maximum": 20},
                "timeout": {"type": "integer", "description": "Max wall-clock seconds per child (default: 120, max: 600)", "default": 120, "maximum": 600}
            },
            "required": ["task", "targets"]
        },
        "handler_name": "_tool_delegate",
    },
    {
        "name": "create_tool",
        "description": "Create a brand-new tool at runtime that you can call in future turns. "
                       "Use this when existing tools don't cover what you need — e.g. "
                       "a specialized API scanner, custom exploit PoC runner, or data parser. "
                       "You provide: a unique name, description, JSON parameter schema, and "
                       "Python code for a 'handler(args: dict) -> dict' function. "
                       "The tool is saved to disk and registered immediately.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Unique tool name in snake_case, e.g. 'custom_api_scanner'"},
                "description": {"type": "string", "description": "Natural language description of what the tool does"},
                "parameters": {
                    "type": "object",
                    "description": "JSON Schema for tool parameters: {type: 'object', properties: {...}, required: [...]}"
                },
                "handler_code": {
                    "type": "string",
                    "description": "Python code defining 'def handler(args: dict) -> dict:'. "
                                   "Write complete, working code with proper error handling. "
                                   "The handler receives args dict and must return a dict with at least 'success' and 'output' keys."
                },
            },
            "required": ["name", "description", "parameters", "handler_code"]
        },
        "handler_name": "_tool_create_tool",
    },
    {
        "name": "edit_own_tool",
        "description": "Modify a tool you previously created with create_tool. "
                       "You provide the tool name and new handler code; the tool's "
                       "name, description, and parameter schema remain unchanged. "
                       "Use this to fix bugs, improve reliability, or add "
                       "capabilities to your own tools. "
                       "Limited to 5 edits per session for safety.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the dynamic tool to edit (must have been created with create_tool)"},
                "handler_code": {
                    "type": "string",
                    "description": "New Python code defining 'def handler(args: dict) -> dict:'. "
                                   "Write complete, working code with proper error handling. "
                                   "The handler receives args dict and must return a dict with at least 'success' and 'output' keys."
                },
            },
            "required": ["name", "handler_code"]
        },
        "handler_name": "_tool_edit_own_tool",
    },
    # ------------------------------------------------------------------
    # Memory tools
    # ------------------------------------------------------------------
    {
        "name": "save_memory",
        "description": "Save a fact or note to persistent cross-session memory. "
                       "Use this to remember findings, target traits, tool preferences, "
                       "or anything you want to recall in future sessions.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The fact or note to remember"},
                "tags": {"type": "string", "description": "Optional space-separated keywords for search (e.g. 'target nginx recon')"},
            },
            "required": ["content"]
        },
        "handler_name": "_tool_save_memory",
    },
    {
        "name": "recall_memory",
        "description": "Search cross-session memory by keywords. "
                       "Returns matching entries with their content and tags.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords to search for in memory content and tags"},
                "limit": {"type": "integer", "description": "Max results to return (default 5)"},
            },
            "required": ["query"]
        },
        "handler_name": "_tool_recall_memory",
    },
    {
        "name": "list_memories",
        "description": "List recent memory entries with their IDs and content.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of recent entries to show (default 10)"},
            },
            "required": []
        },
        "handler_name": "_tool_list_memories",
    },
    {
        "name": "forget_memory",
        "description": "Remove a specific memory entry by ID. "
                       "Use `list_memories` to find the ID first.",
        "parameters": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "Memory entry ID to remove (e.g. 'mem_1712345678000_3')"},
            },
            "required": ["memory_id"]
        },
        "handler_name": "_tool_forget_memory",
    },
    # ------------------------------------------------------------------
    # Skill tools
    # ------------------------------------------------------------------
    {
        "name": "create_skill",
        "description": "Save a reusable technique or procedure as a named skill. "
                       "Use this when you discover an effective workflow, scan technique, "
                       "or exploit method that you want to reuse in future sessions.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Unique skill name (e.g. 'nginx_cve_scan')"},
                "description": {"type": "string", "description": "Short description of what the skill does"},
                "content": {"type": "string", "description": "Step-by-step procedure, code, or notes for the skill"},
            },
            "required": ["name", "description", "content"]
        },
        "handler_name": "_tool_create_skill",
    },
    {
        "name": "view_skill",
        "description": "Read a saved skill by name. Returns its description and full content.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the skill to view"},
            },
            "required": ["name"]
        },
        "handler_name": "_tool_view_skill",
    },
    {
        "name": "list_skills",
        "description": "List all saved skills with their names and descriptions.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "handler_name": "_tool_list_skills",
    },
    {
        "name": "delete_skill",
        "description": "Remove a skill by name. Use `list_skills` to see available skills.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the skill to delete"},
            },
            "required": ["name"]
        },
        "handler_name": "_tool_delete_skill",
    },
    # ------------------------------------------------------------------
    # Knowledge Graph tool (7 search types + ingestion + utilities)
    # ------------------------------------------------------------------
    {
        "name": "knowledge_graph",
        "description": "Query or update the SecurAgentX Knowledge Graph - a networkx-backed "
                       "graph tracking entities (domains, IPs, CVEs, services, credentials), "
                       "relationships, observations, chat messages, and tool/agent episodes. "
                       "Supports 7 search types mirroring Graphiti: temporal_window, "
                       "entity_relationships, diverse_results, episode_context, "
                       "successful_tools, recent_context, entity_by_label. "
                       "Also supports ingestion (add_entity, add_relationship, add_observation, "
                       "add_message, add_episode) and utilities (stats, clear, save, load, help). "
                       "Use this to recall prior findings about a target, find related CVEs, "
                       "retrieve successful tool patterns, or persist new observations.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to perform. Search: 'search_temporal', "
                                   "'search_entity_relationships', 'search_diverse', "
                                   "'search_episode_context', 'search_successful_tools', "
                                   "'search_recent_context', 'search_entity_by_label'. "
                                   "Ingest: 'add_entity', 'add_relationship', 'add_observation', "
                                   "'add_message', 'add_episode'. "
                                   "Utility: 'stats', 'clear', 'save', 'load', 'help'.",
                    "default": "help",
                },
                "label": {"type": "string", "description": "Entity label (for add_entity, search_entity_by_label, search_entity_relationships center_entity)"},
                "entity_type": {"type": "string", "description": "Entity type e.g. 'domain', 'ip', 'vulnerability', 'service', 'credential' (for add_entity)", "default": "entity"},
                "properties": {"type": "object", "description": "Additional properties dict for add_entity/add_relationship"},
                "source": {"type": "string", "description": "Source entity label or id (for add_relationship)"},
                "target": {"type": "string", "description": "Target entity label or id (for add_relationship)"},
                "rel_type": {"type": "string", "description": "Relationship type e.g. 'has_vulnerability', 'mentions', 'exploits' (for add_relationship)", "default": "related_to"},
                "center_entity": {"type": "string", "description": "Center entity label/id for search_entity_relationships"},
                "max_depth": {"type": "integer", "description": "BFS depth for search_entity_relationships (1-3, default 2)", "default": 2, "minimum": 1, "maximum": 3},
                "query": {"type": "string", "description": "Query string for search_diverse"},
                "diversity": {"type": "string", "description": "Diversity level: 'low', 'medium', 'high' (default 'medium')", "default": "medium", "enum": ["low", "medium", "high"]},
                "episode_id": {"type": "string", "description": "Episode id for search_episode_context or add_episode"},
                "description": {"type": "string", "description": "Episode description (for add_episode)"},
                "task_type": {"type": "string", "description": "Optional task-type filter for search_successful_tools (e.g. 'recon', 'exploit', 'fuzz')"},
                "role": {"type": "string", "description": "Chat role for add_message (e.g. 'user', 'assistant', 'system')"},
                "content": {"type": "string", "description": "Message content for add_message"},
                "text": {"type": "string", "description": "Observation text for add_observation"},
                "timestamp": {"type": "string", "description": "ISO-8601 timestamp (optional, defaults to now) for add_observation/add_message"},
                "metadata": {"type": "object", "description": "Optional metadata dict for add_observation/add_episode"},
                "start": {"type": "string", "description": "Window start ISO-8601 timestamp for search_temporal"},
                "end": {"type": "string", "description": "Window end ISO-8601 timestamp for search_temporal"},
                "recency": {"type": "string", "description": "Recency window for search_recent_context: '1h', '6h', '24h', '7d' (default '24h')", "default": "24h", "enum": ["1h", "6h", "24h", "7d"]},
                "max_results": {"type": "integer", "description": "Max results to return (default varies by action: 10-25)", "minimum": 1, "maximum": 100},
                "path": {"type": "string", "description": "Optional filesystem path for save/load actions"},
            },
            "required": ["action"],
        },
        "handler_name": "_tool_knowledge_graph",
    },
]

def _get_tool_defs() -> str:
    """Build tool definitions JSON including dynamically created tools."""
    return json.dumps(
        [
            {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
            for t in AVAILABLE_TOOLS
        ],
        indent=2,
    )


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """You are SecurAgentX — an autonomous AI security research agent purpose-built for vulnerability discovery.

Your mission: thoroughly investigate the target and find security vulnerabilities.
You have complete autonomy over HOW you do this. There are no forced phases or sequences.

## MISSION
- You are given a target: "{target}"
- HUNT AGGRESSIVELY. Think like a real penetration tester.
- Use every tool at your disposal. Combine information from different sources.
- If one approach hits a dead end, pivot. Try another angle.

## CONTRACT

1. **Think before you act.** Explain your reasoning for each step.
2. **Call ONE tool per turn.** When you have results, analyze them.
3. **Build hypotheses.** "Port 80 open → likely Apache → try known CVEs"
4. **Pivot on evidence.** A finding changes direction. Follow it.
3. **Be thorough.** Check network, web, services, known vulnerabilities, misconfigurations.
4. **Extend yourself.** If existing tools are insufficient, create new ones with `create_tool`.
   If a tool behaves wrong, fix it with `edit_own_tool`.
5. **Conclude when ready.** When you have enough evidence to report findings, summarize.

## SELF-IMPROVEMENT

You can evolve your own capabilities at runtime:

- **`create_tool`** — when existing tools don't cover what you need, write a Python function
  and register it as a new tool. It's immediately available in future turns.
- **`edit_own_tool`** — when a tool you created has a bug or needs improvements,
  rewrite its handler code. Name, description, and params stay the same.
  Limited to 5 edits per session for safety.
- **Reflection** — if a tool fails, the system will ask you to analyze why.
  Use `create_tool` to fill a gap or `edit_own_tool` to fix a broken tool.
- Your created tools persist to disk and can be reused in future sessions.

## MEMORY & SKILLS

You have persistent cross-session memory and skill storage:

- **`save_memory(content, tags)`** — Remember facts, findings, or target traits
  across sessions. Tag your memories for easier search later.
- **`recall_memory(query)`** — Recall what you learned in past sessions.
- **`list_memories()`** — See your recent memory entries.
- **`forget_memory(id)`** — Remove outdated or incorrect memories.
- **`create_skill(name, description, content)`** — Save an effective technique
  or workflow as a reusable skill (e.g. an nginx CVE scan procedure).
- **`view_skill(name)`** — Read a saved skill's full procedure.
- **`list_skills()`** — See all saved skills.
- **`delete_skill(name)`** — Remove a skill you no longer need.

All memories and skills persist in `~/.securagentx/data/` and survive agent restarts.
Use them to compound knowledge across hunts — remember what worked, what didn't,
and how targets were configured.

**When to create a tool:**
- You need a specialized scanner (e.g. custom API fuzzer)
- You need to parse a specific format or service response
- Your tool failed because it didn't handle a case you can code for
- You want to automate a multi-step process into a single call

## Current state

Target: {target}
Target type: {target_type}
Steps used: {step_count}/{max_steps}

### Target profile accumulated
{target_profile}

### Current hypotheses
{hypotheses}

### Findings so far
{findings}

### Recent scan history
{scan_history}

### Previous sessions memory
{MEMORY_CONTEXT}

## Available tools

{TOOL_DEFS_TEXT}

## Response format

Respond with your reasoning, then call ONE tool:

Reasoning: <what you're thinking and why>

```json
{{
  "tool": "<tool_name>",
  "arguments": {{ ... }}
}}
```

Or if you have enough evidence, produce the final report:

```json
{{
  "conclude": true,
  "summary": "...",
  "findings": [...]
}}
```"""


# ---------------------------------------------------------------------------
# Vulnerability Agent
# ---------------------------------------------------------------------------


class VulnAgent:
    """Autonomous vulnerability hunting agent.

    The agent runs a reasoning loop where the AI thinks, picks a tool,
    executes it, analyzes results, and repeats. No forced sequence.
    """

    def __init__(
        self,
        client: Any,
        target: str,
        max_steps: int = 25,
        governance: Any = None,
        report_dir: Optional[Path] = None,
        memory: Any = None,
        multi_agent: bool = False,
    ):
        self.client = client
        self.target = target
        self.max_steps = max_steps
        self.governance = governance
        self.report_dir = report_dir or get_reports_path()
        self.memory = memory  # AgentMemory instance (optional)
        # Multi-agent delegation: when True, _tool_delegate prefers the
        # in-process PrimaryAgent orchestrator over spawning subprocesses.
        self._multi_agent = bool(multi_agent)
        # KnowledgeGraph lazy-init handle (None until first use). The KG is
        # imported lazily so vuln_agent.py stays import-safe even if
        # networkx / kg_store are unavailable.
        self._kg: Any = None

        # Initialize ~/.securagentx/ user-space directories (pip-safe)
        _securagentx_home = Path("~/.securagentx").expanduser()
        for subdir in ("tools", "scripts", "data", "reports"):
            (_securagentx_home / subdir).mkdir(parents=True, exist_ok=True)

        # Runtime state
        self.step = 0
        self.start_time: float = 0.0
        self.profile: Dict[str, Any] = {}
        self.findings: List[Finding] = []
        self.hypotheses: List[Hypothesis] = []
        self.scan_history: List[ScanStep] = []
        self.conversation: List[Dict[str, str]] = []
        self._conclusion: str = ""
        self._consecutive_failures: int = 0
        self._reflections: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Knowledge Graph (optional, lazy, import-safe)
    # ------------------------------------------------------------------

    def _get_kg(self) -> Any:
        """Lazy-init and return the KnowledgeGraph instance.

        Returns ``None`` if the KG module or its ``networkx`` dependency is
        unavailable — every caller must null-check the return value. This keeps
        the KG feature strictly optional and never bricks the hunt loop.
        """
        if self._kg is None:
            try:
                from securagentx.knowledge_graph.kg_store import KnowledgeGraph
                self._kg = KnowledgeGraph()
            except Exception as exc:  # noqa: BLE001 — KG must never break the scan
                logger.debug("KnowledgeGraph unavailable: %s", exc)
                self._kg = None
        return self._kg

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def hunt(self, verbose: bool = True) -> VulnReport:
        """Execute the autonomous hunting loop.

        Args:
            verbose: If True, prints AI reasoning and actions to console in real-time.

        Returns a VulnReport with all findings.
        """
        import sys
        logger.info("Hunt started: target=%s", self.target)
        self.start_time = time.time()
        self.step = 0

        # Pre-hunt: recall past memories
        memory_context = ""
        if self.memory is not None:
            try:
                recall = self.memory.pre_hunt(self.target)
                memory_context = self.memory.get_context(self.target)
                if recall["memories"]:
                    logger.info("Recalled %d past memories for %s", len(recall["memories"]), self.target)
            except Exception as e:  # noqa: BLE001 — logged
                logger.debug(f"Memory recall failed: {e}")

        if verbose:
            sys.stdout.write(f"\n🎯 Hunting: {self.target}\n")
            sys.stdout.write(f"{'─' * 50}\n")
            sys.stdout.flush()

        if memory_context and verbose:
            sys.stdout.write(f"🧠 Memory: {len(memory_context)} chars recalled\n")
            sys.stdout.flush()

        # Pre-hunt memory: inject into turn prompt for first step
        self._memory_context = memory_context

        while self.step < self.max_steps:
            self.step += 1
            logger.info("Step %d/%d", self.step, self.max_steps)

            # 1. REASON — AI decides what to do
            action = self._reason_step()
            if action is None:
                logger.warning("No action from AI, concluding")
                break

            # 2. If AI wants to conclude, stop the loop
            if action.get("conclude"):
                logger.info("AI concluded hunt")
                self._record_conclusion(action)
                if verbose:
                    sys.stdout.write(f"\n💡 AI concluded: {action.get('summary', '')[:200]}\n")
                    sys.stdout.flush()
                break

            # 3. ACT — execute the chosen tool
            if verbose:
                reasoning = action.get("reasoning", "")
                tool_name = action.get("tool", "?")
                args_str = action.get("arguments", {})
                if reasoning:
                    sys.stdout.write(f"\n🤔 {reasoning[:300]}\n")
                sys.stdout.write(f"⚡ {tool_name}({args_str})\n")
                sys.stdout.flush()

            result = self._execute_step(action)

            # 4. ANALYZE — record and feed back next iteration
            self._record_step(action, result)

            # 5. REMEMBER — store step in memory (cross-session)
            if self.memory is not None:
                try:
                    self.memory.post_step(
                        target=self.target,
                        step=self.step,
                        tool=action.get("tool", "?"),
                        arguments=action.get("arguments", {}),
                        result=result,
                        reasoning=action.get("reasoning", ""),
                    )
                except Exception as e:  # noqa: BLE001 — logged
                    logger.debug(f"Memory store failed: {e}")

            # 6. REFLECT — on consecutive failures, analyze and self-improve
            if not result.get("success"):
                self._consecutive_failures += 1
            else:
                self._consecutive_failures = 0

            if self._consecutive_failures > 0 and self._consecutive_failures % 2 == 0:
                reflection = self._reflect_step(action, result)
                if reflection:
                    self._reflections.append(reflection)
                    if verbose and reflection.get("action"):
                        tool_name = reflection["action"].get("tool", "?")
                        sys.stdout.write(f"🪞 {reflection.get('summary', 'Reflecting...')[:200]}\n")
                        sys.stdout.flush()
                    # If reflection suggests creating a tool, execute it
                    if reflection.get("action"):
                        fix_result = self._execute_step(reflection["action"])
                        if fix_result.get("success"):
                            sys.stdout.write(f"🛠 Self-improvement: {fix_result.get('output', '')[:200]}\n")
                            sys.stdout.flush()

            if verbose:
                status = "✅" if result.get("success") else "❌"
                output = result.get("output", result.get("error", ""))[:200]
                sys.stdout.write(f"{status} {output}\n")
                sys.stdout.flush()

        if verbose:
            sys.stdout.write(f"{'─' * 50}\n")
            sys.stdout.write(f"📋 Generating report...\n")
            sys.stdout.flush()

        report = self._generate_report()

        # Post-hunt: store report and findings in memory
        if self.memory is not None:
            try:
                self.memory.post_hunt(report)
                logger.info("Memory stored for %s", self.target)
            except Exception as e:  # noqa: BLE001 — logged
                logger.debug(f"Post-hunt memory store failed: {e}")

        return report

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    def _convert_messages(self, messages: List[Dict[str, str]]) -> List:
        """Convert dict messages to client's expected format.

        UniversalAIClient requires AIMessage dataclass objects.
        Mock/test clients accept plain dicts.
        Graceful fallback if AIMessage is unavailable.
        """
        try:
            from tools.universal_ai_client import AIMessage

            return [AIMessage(role=m["role"], content=m["content"]) for m in messages]
        except ImportError:
            return messages

    def _reason_step(self) -> Optional[Dict[str, Any]]:
        """Ask the AI what to do next. Returns parsed action dict."""
        prompt = self._build_turn_prompt()

        self.conversation.append({"role": "user", "content": prompt})
        try:
            messages = self._convert_messages(self.conversation)
            response = self.client.chat(messages)
            content = response.content.strip() if response else ""
        except Exception as exc:  # noqa: BLE001 — logged
            logger.error("AI call failed: %s", exc)
            return {"conclude": True, "summary": f"AI error: {exc}"}

        self.conversation.append({"role": "assistant", "content": content})

        # Parse JSON from the response
        action = self._extract_action(content)
        return action

    def _reflect_step(self, failed_action: Dict[str, Any], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Reflect on a step failure and decide if a tool should be created to fix the gap.

        When the AI hits N consecutive failures, this method sends the
        failure context back to the AI for analysis. The AI can suggest
        creating a new tool via a structured action dict.

        Returns an action dict (for create_tool) or None.
        """
        tool_name = failed_action.get("tool", "?")
        args = failed_action.get("arguments", {})
        error = result.get("error", result.get("output", "unknown error"))

        prompt = (
            f"You are the SecurAgentX self-improvement module. A tool call just failed.\n\n"
            f"Failed tool: {tool_name}\n"
            f"Arguments: {args}\n"
            f"Error: {error[:500]}\n\n"
            f"Consecutive failures: {self._consecutive_failures}\n\n"
            f"Analyze the failure. Can you fix this by:\n"
            f"1. Creating a NEW tool with create_tool that handles this case properly?\n"
            f"2. Editing an existing tool with edit_own_tool to fix the bug?\n"
            f"3. Pivoting to a different existing tool that might work?\n"
            f"4. Both — create a better tool now, then use it next turn?\n\n"
            f"Available tools: {_get_tool_defs()[:1000]}\n\n"
            f"If you want to create a tool, respond with:\n"
            f'{{"create_tool": true, "tool_name": "...", "description": "...", '
            f'"reasoning": "why this will fix the failure"}}\n'
            f"If you want to edit an existing tool, respond with:\n"
            f'{{"edit_tool": true, "tool_name": "...", '
            f'"handler_code": "...", "reasoning": "what this changes"}}\n'
            f"If no tool is needed, just respond with: {{\"skip\": true}}\n"
        )

        self.conversation.append({"role": "user", "content": prompt})
        try:
            messages = self._convert_messages(self.conversation)
            response = self.client.chat(messages)
            content = response.content.strip() if response else ""
        except Exception as exc:  # noqa: BLE001 — logged
            logger.error("Reflection AI call failed: %s", exc)
            return None

        self.conversation.append({"role": "assistant", "content": content})

        # Parse the reflection response
        action = self._extract_action(content)
        if not action:
            return None
        if action.get("skip"):
            return {"action": None, "summary": "No fix needed, pivoting."}

        if action.get("create_tool"):
            tool_name = action.get("tool_name", "")
            description = action.get("description", "")
            reasoning = action.get("reasoning", "")

            return {
                "action": {
                    "reasoning": reasoning,
                    "tool": "create_tool",
                    "arguments": {
                        "name": tool_name,
                        "description": description,
                        "parameters": action.get("parameters", {"type": "object", "properties": {}, "required": []}),
                        "handler_code": action.get("handler_code", ""),
                    },
                },
                "summary": f"🪞 Self-improvement: creating '{tool_name}' — {reasoning[:200]}",
            }

        if action.get("edit_tool"):
            tool_name = action.get("tool_name", "")
            reasoning = action.get("reasoning", "")

            return {
                "action": {
                    "reasoning": reasoning,
                    "tool": "edit_own_tool",
                    "arguments": {
                        "name": tool_name,
                        "handler_code": action.get("handler_code", ""),
                    },
                },
                "summary": f"🪞 Self-improvement: editing '{tool_name}' — {reasoning[:200]}",
            }

        return None

    def _resolve_handler(self, tool_name: str) -> Optional[Callable]:
        """Resolve a tool handler by name at call time.

        Checks:
        1. Static tools via getattr on module (supports mock.patch)
        2. Dynamic tools created with create_tool (from _dynamic_tools dict)
        """
        import sys

        module = sys.modules[__name__]
        for t in AVAILABLE_TOOLS:
            if t["name"] == tool_name:
                # Dynamic tool — resolved from runtime dict
                if t.get("_is_dynamic"):
                    return _dynamic_tools.get(tool_name)
                # Static tool — resolved via module attribute
                handler_name = t.get("handler_name", "")
                return getattr(module, handler_name, None)
        return None

    def _execute_step(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool call and return the result."""
        tool_name = action.get("tool", "")
        arguments = action.get("arguments", {})

        handler = self._resolve_handler(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        # Multi-agent delegation: when VulnAgent was constructed with
        # ``multi_agent=True`` and the AI invoked the ``delegate`` tool,
        # transparently inject ``multi_agent=True`` so the in-process
        # PrimaryAgent path is attempted before subprocess spawning.
        if tool_name == "delegate" and self._multi_agent:
            arguments = dict(arguments)
            arguments.setdefault("multi_agent", True)

        # Governance gate
        if self.governance:
            try:
                from securagentx.types import AIAction
                gov_action = AIAction(
                    action_type="scan",
                    tool=tool_name,
                    target=self.target,
                    risk_level="safe",
                )
                gate = self.governance.gate(
                    mission_id="vuln-hunt",
                    target=self.target,
                    action=gov_action,
                )
                if gate is not None and hasattr(gate, "decision"):
                    _decision = gate.decision
                    _decision_val = _decision.value if hasattr(_decision, "value") else str(_decision)
                    if _decision_val == "deny":
                        _rationale = getattr(gate, "rationale", "blocked by governance")
                        return {"success": False, "error": f"Blocked by governance: {_rationale}"}
            except Exception as gov_exc:  # noqa: BLE001 — governance must not brick the scan
                logger.warning("Governance gate error for %s (fail-open): %s", tool_name, gov_exc)

        logger.info("Executing: %s(%s)", tool_name, arguments)
        try:
            result = handler(**arguments)
            return result
        except Exception as exc:  # noqa: BLE001 — logged
            logger.error("Tool execution failed: %s", exc)
            return {"success": False, "error": str(exc)}

    def _record_step(self, action: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Record the step in history and extract findings."""
        step_record = ScanStep(
            step=self.step,
            reasoning=action.get("reasoning", ""),
            tool=action.get("tool", ""),
            arguments=action.get("arguments", {}),
            result_summary=str(result)[:300],
            timestamp=time.time(),
        )
        self.scan_history.append(step_record)

        # Knowledge Graph: log every tool execution as an observation so
        # future hunts / searches can recover what was tried and what came
        # back. Lazy + try/except — KG is strictly optional.
        kg = self._get_kg()
        if kg is not None:
            try:
                tool_name = action.get("tool", "?")
                result_snippet = str(result)[:200]
                kg.add_observation(
                    f"Tool: {tool_name}, Result: {result_snippet}",
                    metadata={"target": self.target, "step": self.step},
                )
            except Exception as exc:  # noqa: BLE001 — KG must not brick the scan
                logger.debug("KG add_observation failed: %s", exc)

        # If successful, extract knowledge
        if result.get("success"):
            self._update_profile(result)
            self._maybe_generate_hypothesis(result)

    def _record_conclusion(self, action: Dict[str, Any]) -> None:
        """Record the final conclusion."""
        self._conclusion = action.get("summary", "")
        self.conversation.append(
            {
                "role": "assistant",
                "content": f"# HUNT COMPLETE\n\n{self._conclusion}",
            }
        )

    # ------------------------------------------------------------------
    # Knowledge management
    # ------------------------------------------------------------------

    def _update_profile(self, result: Dict[str, Any]) -> None:
        """Update target profile with new knowledge."""
        output = result.get("output", "")
        if not output:
            return

        # Pattern: opened ports
        import re

        ports = re.findall(r"(?:port|)\s*(\d+)\/(?:tcp|udp)", output, re.I)
        if ports:
            existing = set(self.profile.get("open_ports", []))
            for p in ports:
                existing.add(int(p))
            self.profile["open_ports"] = sorted(existing)

        # Service names
        services = re.findall(r"(\w+)\s+(\d+\.\d+(?:\.\d+)?)", output)
        for svc, ver in services:
            svc_lower = svc.lower()
            if svc_lower not in ("http", "https", "running"):
                self.profile.setdefault("services", {})[svc_lower] = ver

    def _maybe_generate_hypothesis(self, result: Dict[str, Any]) -> None:
        """Generate a hypothesis based on new findings."""
        output = result.get("output", "")
        if not output:
            return

        import re

        # Known patterns that suggest testing
        patterns = [
            (r"apache[\s/]*(\d+\.\d+(?:\.\d+)?)", "Apache version detected, possible vuln"),
            (r"nginx[\s/]*(\d+\.\d+(?:\.\d+)?)", "nginx version detected, possible vuln"),
            (r"openssh[\s/]*(\d+\.\d+(?:\.\d+)?)", "SSH version detected, check auth bypass"),
            (r"port\s+80", "HTTP service → explore web endpoints"),
            (r"port\s+443", "HTTPS service → explore web endpoints"),
            (r"port\s+22", "SSH access → check version and auth"),
            (r"port\s+3306", "MySQL exposed → potential database access"),
            (r"port\s+6379", "Redis exposed → potential RCE"),
            (r"port\s+27017", "MongoDB exposed → potential data leak"),
        ]

        for pattern, desc in patterns:
            if re.search(pattern, output, re.I):
                hyp = Hypothesis(
                    description=desc,
                    rationale=f"Found via pattern match: {pattern}",
                    status="pending",
                )
                # Avoid duplicates
                if not any(h.description == hyp.description for h in self.hypotheses):
                    self.hypotheses.append(hyp)

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    def _build_turn_prompt(self) -> str:
        """Build the prompt for the current turn."""
        profile_text = json.dumps(self.profile, indent=2) if self.profile else "(nothing yet)"
        hypotheses_text = self._format_hypotheses()
        findings_text = self._format_findings()
        history_text = self._format_history()
        target_type = "domain" if "." in self.target and not self.target.replace(".", "").isdigit() else "IP" if self.target.replace(".", "").isdigit() else "identifier"
        memory_text = getattr(self, "_memory_context", "") or ""

        return SYSTEM_PROMPT_TEMPLATE.format(
            target=self.target,
            target_type=target_type,
            step_count=self.step,
            max_steps=self.max_steps,
            target_profile=profile_text,
            hypotheses=hypotheses_text,
            findings=findings_text,
            scan_history=history_text,
            TOOL_DEFS_TEXT=_get_tool_defs(),
            MEMORY_CONTEXT=memory_text,
        )

    def _format_hypotheses(self) -> str:
        if not self.hypotheses:
            return "No hypotheses yet."
        lines = []
        for h in self.hypotheses:
            status_mark = "🔄" if h.status == "testing" else "⏳" if h.status == "pending" else "✅" if h.status == "confirmed" else "❌"
            lines.append(f"- [{status_mark}] ({h.status}) {h.description} (conf: {h.confidence:.1f})")
            if h.evidence:
                lines.append(f"  Evidence: {h.evidence[-1][:100]}")
        return "\n".join(lines)

    def _format_findings(self) -> str:
        if not self.findings:
            return "No findings yet."
        lines = []
        for f in self.findings:
            sev_mark = "🔴" if f.severity == "critical" else "🟠" if f.severity == "high" else "🟡" if f.severity == "medium" else "🔵"
            lines.append(f"- [{sev_mark}] [{f.severity.upper()}] {f.title} (via {f.source_tool})")
        return "\n".join(lines)

    def _format_history(self) -> str:
        if not self.scan_history:
            return "(no steps yet)"
        lines = []
        for s in self.scan_history[-5:]:  # last 5 steps
            lines.append(f"  Step {s.step}: {s.tool}({s.arguments}) → {s.result_summary[:80]}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _extract_action(self, content: str) -> Dict[str, Any]:
        """Extract a JSON action block from the AI response."""
        import re

        # 1) Try JSON code fence first
        m = re.search(r"```json\s*\n(.*?)\n```", content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # 2) Try bare JSON with brace matching
        # Find every '{' and try to parse from there with matched braces
        for idx, ch in enumerate(content):
            if ch != "{":
                continue
            depth = 1
            for end in range(idx + 1, len(content)):
                c = content[end]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        blob = content[idx : end + 1]
                        if '"tool"' in blob or '"conclude"' in blob:
                            try:
                                return json.loads(blob)
                            except json.JSONDecodeError:
                                pass
                        break

        # 3) Try conclude pattern
        m = re.search(r"conclude.*?(?:true|yes)", content, re.I)
        if m:
            return {"conclude": True, "summary": content[:500]}

        # 4) Fallback
        return {"conclude": True, "summary": content[:500]}

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _generate_report(self) -> VulnReport:
        """Generate the final vulnerability report."""
        duration = time.time() - self.start_time
        confirmed = [h for h in self.hypotheses if h.status == "confirmed"]
        tested = [h for h in self.hypotheses if h.status in ("confirmed", "rejected")]

        # Knowledge Graph: persist the target domain + every finding as
        # entities, and link them via ``has_vulnerability`` relationships.
        # Lazy + try/except — KG is strictly optional.
        kg = self._get_kg()
        if kg is not None:
            try:
                kg.add_entity(self.target, "domain")
                for f in self.findings:
                    kg.add_entity(f.title, "vulnerability")
                    kg.add_relationship(self.target, f.title, "has_vulnerability")
            except Exception as exc:  # noqa: BLE001 — KG must not brick the report
                logger.debug("KG report-side update failed: %s", exc)

        report = VulnReport(
            target=self.target,
            scan_duration=duration,
            total_steps=self.step,
            findings=self.findings,
            hypotheses_tested=len(tested),
            hypotheses_confirmed=len(confirmed),
            open_ports=self.profile.get("open_ports", []),
            services=self.profile.get("services", {}),
            summary=self._build_summary(),
            recommendations=self._build_recommendations(),
        )

        # Save report
        self.report_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.report_dir / f"vuln_report_{self.target}_{int(self.start_time)}.json"
        try:
            report_path.write_text(json.dumps(report.to_dict(), indent=2))
            logger.info("Report saved: %s", report_path)
        except Exception as exc:  # noqa: BLE001 — logged
            logger.warning("Failed to save report: %s", exc)

        return report

    def _build_summary(self) -> str:
        """Build a natural-language summary of findings."""
        # Use AI's conclusion if available
        if self._conclusion:
            return f"# Vulnerability Report: {self.target}\n\n{self._conclusion}"

        parts = [f"# Vulnerability Report: {self.target}"]
        if self.findings:
            by_sev = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
            for f in self.findings:
                by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
            parts.append(f"\n## Summary")
            parts.append(f"Found {len(self.findings)} vulnerabilities:")
            for sev, count in by_sev.items():
                if count:
                    parts.append(f"  - {sev}: {count}")
        else:
            parts.append("\nNo vulnerabilities found.")

        if self.profile.get("open_ports"):
            ports = ", ".join(str(p) for p in self.profile["open_ports"][:20])
            parts.append(f"\nOpen ports: {ports}")

        return "\n".join(parts)

    def _build_recommendations(self) -> List[str]:
        """Build remediation recommendations from findings."""
        recs = []
        for f in self.findings:
            if f.remediation:
                recs.append(f.remediation)
        if self.profile.get("open_ports"):
            recs.append("Review and close unnecessary open ports")
        return recs or ["No specific recommendations generated"]
