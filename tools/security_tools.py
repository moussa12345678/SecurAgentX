"""
tools/security_tools.py — 30 CLI security tool wrappers for SecurAgentX.

Each class wraps a standard pentest CLI tool (nmap, sqlmap, nikto, nuclei,
ffuf, gobuster, etc.) so the AI agent can invoke them via the tool registry.

Tools auto-register on import. Availability is checked via shutil.which().
If the binary isn't installed, the tool is marked unavailable and the AI
gets a clear "not installed" error instead of a crash.

Installation: most tools are available via apt (Kali/Debian) or pip.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Union

import subprocess

from tools.tool_registry import (
    BaseTool,
    ToolCategory,
    ToolMetadata,
    ToolPriority,
    ToolResult,
    register_tool,
)

logger = logging.getLogger("securagentx.security_tools")


class _CLIToolWrapper(BaseTool):
    """Generic wrapper for CLI-based security tools.

    Subclasses set ``_COMMAND`` (the binary name) and ``_ARGS`` (the argument
    template with ``{target}`` and ``{report_dir}`` placeholders).
    """

    _COMMAND: str = ""
    _ARGS: List[str] = []
    _DESCRIPTION: str = ""

    def _check_binary(self) -> bool:
        return shutil.which(self._COMMAND) is not None

    async def execute(
        self,
        target: Union[str, List[str]],
        report_dir: Path,
        semaphore: asyncio.Semaphore,
        **kwargs,
    ) -> ToolResult:
        start_time = time.time()
        tgt = target if isinstance(target, str) else target[0]

        if not self._check_binary():
            return ToolResult(
                success=False,
                tool_name=self.metadata.name,
                category=self.metadata.category,
                error_message=f"{self._COMMAND} not installed. Install: apt install {self._COMMAND}",
                execution_time=0,
            )

        async with semaphore:
            try:
                report_dir.mkdir(parents=True, exist_ok=True)
                outfile = report_dir / f"{self.metadata.name}_output.txt"

                # Build command args
                args = [self._COMMAND]
                for arg in self._ARGS:
                    arg = arg.replace("{target}", tgt)
                    arg = arg.replace("{report_dir}", str(report_dir))
                    arg = arg.replace("{output}", str(outfile))
                    args.append(arg)

                logger.info("Running %s: %s", self.metadata.name, " ".join(args[:6]))

                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=self.metadata.timeout_seconds
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.communicate()
                    return ToolResult(
                        success=False,
                        tool_name=self.metadata.name,
                        category=self.metadata.category,
                        error_message=f"Timeout after {self.metadata.timeout_seconds}s",
                        execution_time=time.time() - start_time,
                    )

                output = (stdout or b"").decode("utf-8", errors="replace")[:10000]
                err = (stderr or b"").decode("utf-8", errors="replace")[:2000]

                # Save full output
                outfile.write_text(output + "\n--- STDERR ---\n" + err)

                findings = []
                if proc.returncode == 0:
                    # Parse basic findings from output
                    for line in output.splitlines():
                        line_lower = line.lower()
                        if any(kw in line_lower for kw in ["vulnerability", "vulnerable", "critical", "high", "sql injection", "xss", "exposed"]):
                            findings.append({"type": "finding", "detail": line.strip()[:200]})

                return ToolResult(
                    success=proc.returncode == 0,
                    tool_name=self.metadata.name,
                    category=self.metadata.category,
                    output=output[:5000],
                    findings=findings,
                    execution_time=time.time() - start_time,
                    error_message=err if proc.returncode != 0 else None,
                    raw_output_file=outfile,
                )
            except Exception as e:
                return ToolResult(
                    success=False,
                    tool_name=self.metadata.name,
                    category=self.metadata.category,
                    error_message=str(e),
                    execution_time=time.time() - start_time,
                )


# ── 30 Security Tools ─────────────────────────────────────────────────────────

@register_tool(ToolMetadata(name="nmap", category=ToolCategory.NETWORK, priority=ToolPriority.CRITICAL, binary_name="nmap", description="Network port scanner", timeout_seconds=300))
class NmapTool(_CLIToolWrapper):
    _COMMAND = "nmap"
    _ARGS = ["-sS", "-sV", "--top-ports", "1000", "-oN", "{output}", "{target}"]

@register_tool(ToolMetadata(name="sqlmap", category=ToolCategory.EXPLOITATION, priority=ToolPriority.CRITICAL, binary_name="sqlmap", description="SQL injection scanner", timeout_seconds=600))
class SQLMapTool(_CLIToolWrapper):
    _COMMAND = "sqlmap"
    _ARGS = ["-u", "{target}", "--batch", "--level=3", "--risk=2", "--output-dir={report_dir}"]

@register_tool(ToolMetadata(name="nikto", category=ToolCategory.SCANNER, priority=ToolPriority.HIGH, binary_name="nikto", description="Web server vulnerability scanner", timeout_seconds=300))
class NiktoTool(_CLIToolWrapper):
    _COMMAND = "nikto"
    _ARGS = ["-h", "{target}", "-Format", "txt", "-output", "{output}"]

@register_tool(ToolMetadata(name="nuclei", category=ToolCategory.SCANNER, priority=ToolPriority.CRITICAL, binary_name="nuclei", description="Template-based vulnerability scanner", timeout_seconds=600))
class NucleiTool(_CLIToolWrapper):
    _COMMAND = "nuclei"
    _ARGS = ["-u", "{target}", "-o", "{output}", "-severity", "low,medium,high,critical"]

@register_tool(ToolMetadata(name="ffuf", category=ToolCategory.FUZZING, priority=ToolPriority.HIGH, binary_name="ffuf", description="Web fuzzer for dirs/files/params", timeout_seconds=300))
class FfufTool(_CLIToolWrapper):
    _COMMAND = "ffuf"
    _ARGS = ["-u", "{target}/FUZZ", "-w", "/usr/share/wordlists/dirb/common.txt", "-o", "{output}", "-mc", "200,301,302,403"]

@register_tool(ToolMetadata(name="gobuster", category=ToolCategory.RECON, priority=ToolPriority.HIGH, binary_name="gobuster", description="Directory/file brute-forcer", timeout_seconds=300))
class GobusterTool(_CLIToolWrapper):
    _COMMAND = "gobuster"
    _ARGS = ["dir", "-u", "{target}", "-w", "/usr/share/wordlists/dirb/common.txt", "-o", "{output}"]

@register_tool(ToolMetadata(name="dirb", category=ToolCategory.RECON, priority=ToolPriority.MEDIUM, binary_name="dirb", description="Web content scanner", timeout_seconds=300))
class DirbTool(_CLIToolWrapper):
    _COMMAND = "dirb"
    _ARGS = ["{target}", "-o", "{output}"]

@register_tool(ToolMetadata(name="wpscan", category=ToolCategory.SCANNER, priority=ToolPriority.HIGH, binary_name="wpscan", description="WordPress vulnerability scanner", timeout_seconds=300))
class WPScanTool(_CLIToolWrapper):
    _COMMAND = "wpscan"
    _ARGS = ["--url", "{target}", "--enumerate", "vp,vt,u", "--output", "{output}", "--no-banner"]

@register_tool(ToolMetadata(name="whatweb", category=ToolCategory.RECON, priority=ToolPriority.HIGH, binary_name="whatweb", description="Web technology fingerprinter", timeout_seconds=120))
class WhatWebTool(_CLIToolWrapper):
    _COMMAND = "whatweb"
    _ARGS = ["-a", "3", "{target}"]

@register_tool(ToolMetadata(name="sslscan", category=ToolCategory.SCANNER, priority=ToolPriority.HIGH, binary_name="sslscan", description="SSL/TLS vulnerability scanner", timeout_seconds=120))
class SSLScanTool(_CLIToolWrapper):
    _COMMAND = "sslscan"
    _ARGS = ["{target}"]

@register_tool(ToolMetadata(name="sslyze", category=ToolCategory.SCANNER, priority=ToolPriority.MEDIUM, binary_name="sslyze", description="SSL/TLS configuration scanner", timeout_seconds=120))
class SSLyzeTool(_CLIToolWrapper):
    _COMMAND = "sslyze"
    _ARGS = ["--regular", "{target}"]

@register_tool(ToolMetadata(name="hydra", category=ToolCategory.EXPLOITATION, priority=ToolPriority.MEDIUM, binary_name="hydra", description="Password brute-forcer", timeout_seconds=300))
class HydraTool(_CLIToolWrapper):
    _COMMAND = "hydra"
    _ARGS = ["-L", "/usr/share/wordlists/metasploit/unix_users.txt", "-P", "/usr/share/wordlists/metasploit/unix_passwords.txt", "{target}", "ssh"]

@register_tool(ToolMetadata(name="masscan", category=ToolCategory.NETWORK, priority=ToolPriority.HIGH, binary_name="masscan", description="Fast port scanner", timeout_seconds=120))
class MasscanTool(_CLIToolWrapper):
    _COMMAND = "masscan"
    _ARGS = ["{target}", "-p1-65535", "--rate=1000", "-oJ", "{output}"]

@register_tool(ToolMetadata(name="amass", category=ToolCategory.RECON, priority=ToolPriority.HIGH, binary_name="amass", description="Subdomain enumeration", timeout_seconds=300))
class AmassTool(_CLIToolWrapper):
    _COMMAND = "amass"
    _ARGS = ["enum", "-d", "{target}", "-o", "{output}"]

@register_tool(ToolMetadata(name="subfinder", category=ToolCategory.RECON, priority=ToolPriority.HIGH, binary_name="subfinder", description="Subdomain discovery tool", timeout_seconds=120))
class SubfinderTool(_CLIToolWrapper):
    _COMMAND = "subfinder"
    _ARGS = ["-d", "{target}", "-o", "{output}"]

@register_tool(ToolMetadata(name="httpx", category=ToolCategory.RECON, priority=ToolPriority.HIGH, binary_name="httpx", description="HTTP toolkit for probing", timeout_seconds=120))
class HttpxTool(_CLIToolWrapper):
    _COMMAND = "httpx"
    _ARGS = ["-u", "{target}", "-status-code", "-title", "-tech-detect", "-o", "{output}"]

@register_tool(ToolMetadata(name="dnsrecon", category=ToolCategory.RECON, priority=ToolPriority.MEDIUM, binary_name="dnsrecon", description="DNS reconnaissance", timeout_seconds=120))
class DNSReconTool(_CLIToolWrapper):
    _COMMAND = "dnsrecon"
    _ARGS = ["-d", "{target}", "-t", "std,axfr,brt", "--lifetime=5"]

@register_tool(ToolMetadata(name="dnsenum", category=ToolCategory.RECON, priority=ToolPriority.MEDIUM, binary_name="dnsenum", description="DNS enumeration", timeout_seconds=120))
class DNSEnumTool(_CLIToolWrapper):
    _COMMAND = "dnsenum"
    _ARGS = ["{target}"]

@register_tool(ToolMetadata(name="theHarvester", category=ToolCategory.RECON, priority=ToolPriority.MEDIUM, binary_name="theHarvester", description="Email/subdomain harvester", timeout_seconds=120))
class TheHarvesterTool(_CLIToolWrapper):
    _COMMAND = "theHarvester"
    _ARGS = ["-d", "{target}", "-b", "all"]

@register_tool(ToolMetadata(name="wafw00f", category=ToolCategory.RECON, priority=ToolPriority.HIGH, binary_name="wafw00f", description="WAF detection tool", timeout_seconds=60))
class Wafw00fTool(_CLIToolWrapper):
    _COMMAND = "wafw00f"
    _ARGS = ["-a", "{target}"]

@register_tool(ToolMetadata(name="naabu", category=ToolCategory.NETWORK, priority=ToolPriority.MEDIUM, binary_name="naabu", description="Fast port scanner by ProjectDiscovery", timeout_seconds=120))
class NaabuTool(_CLIToolWrapper):
    _COMMAND = "naabu"
    _ARGS = ["-host", "{target}", "-top-ports", "1000", "-o", "{output}"]

@register_tool(ToolMetadata(name="testssl", category=ToolCategory.SCANNER, priority=ToolPriority.MEDIUM, binary_name="testssl.sh", description="SSL/TLS testing tool", timeout_seconds=300))
class TestSSLTool(_CLIToolWrapper):
    _COMMAND = "testssl.sh"
    _ARGS = ["--warnings", "off", "{target}"]

@register_tool(ToolMetadata(name="feroxbuster", category=ToolCategory.FUZZING, priority=ToolPriority.HIGH, binary_name="feroxbuster", description="Recursive content discovery", timeout_seconds=300))
class FeroxbusterTool(_CLIToolWrapper):
    _COMMAND = "feroxbuster"
    _ARGS = ["-u", "{target}", "-w", "/usr/share/wordlists/dirb/common.txt", "-o", "{output}"]

@register_tool(ToolMetadata(name="kiterunner", category=ToolCategory.API, priority=ToolPriority.MEDIUM, binary_name="kr", description="API endpoint scanner", timeout_seconds=300))
class KiterunnerTool(_CLIToolWrapper):
    _COMMAND = "kr"
    _ARGS = ["scan", "{target}", "-w", "/usr/share/wordlists/api/api-seen-in-openapi.txt"]

@register_tool(ToolMetadata(name="dirsearch", category=ToolCategory.FUZZING, priority=ToolPriority.MEDIUM, binary_name="dirsearch", description="Web path scanner", timeout_seconds=300))
class DirsearchTool(_CLIToolWrapper):
    _COMMAND = "dirsearch"
    _ARGS = ["-u", "{target}", "-o", "{output}"]

@register_tool(ToolMetadata(name="smap", category=ToolCategory.NETWORK, priority=ToolPriority.MEDIUM, binary_name="smap", description="Nmap-compatible port scanner (faster)", timeout_seconds=120))
class SmapTool(_CLIToolWrapper):
    _COMMAND = "smap"
    _ARGS = ["-sS", "--top-ports", "1000", "-oN", "{output}", "{target}"]

@register_tool(ToolMetadata(name="crackmapexec", category=ToolCategory.EXPLOITATION, priority=ToolPriority.MEDIUM, binary_name="crackmapexec", description="Network swiss army knife", timeout_seconds=120))
class CrackMapExecTool(_CLIToolWrapper):
    _COMMAND = "crackmapexec"
    _ARGS = ["smb", "{target}"]

@register_tool(ToolMetadata(name="enum4linux", category=ToolCategory.SCANNER, priority=ToolPriority.MEDIUM, binary_name="enum4linux", description="SMB/NetBIOS enumerator", timeout_seconds=120))
class Enum4LinuxTool(_CLIToolWrapper):
    _COMMAND = "enum4linux"
    _ARGS = ["-a", "{target}"]

@register_tool(ToolMetadata(name="smbclient", category=ToolCategory.RECON, priority=ToolPriority.LOW, binary_name="smbclient", description="SMB share scanner", timeout_seconds=60))
class SmbclientTool(_CLIToolWrapper):
    _COMMAND = "smbclient"
    _ARGS = ["-L", "//{target}", "-N"]

@register_tool(ToolMetadata(name="nbtscan", category=ToolCategory.NETWORK, priority=ToolPriority.LOW, binary_name="nbtscan", description="NetBIOS name scanner", timeout_seconds=60))
class NbtscanTool(_CLIToolWrapper):
    _COMMAND = "nbtscan"
    _ARGS = ["{target}"]
