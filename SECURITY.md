# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in SecurAgentX itself (not findings from using SecurAgentX against a target), please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

Email: **AAAAAACD@proton.me**

**PGP Key Fingerprint:** `0000 0000 0000 0000 0000 0000 0000 0000 0000 0000` (replace with your actual fingerprint)

Download the public key from: https://keys.openpgp.org/ (or your preferred keyserver)

Include:
- Description of the vulnerability
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

### Response Timeline

| Stage | Timeframe |
|-------|-----------|
| Acknowledgment | 48 hours |
| Initial assessment | 5 business days |
| Patch release | 14 business days |

### Scope

The following are in scope:
- Command injection via agent inputs
- Governance bypass (executing DESTRUCTIVE commands)
- API key leakage through logs or outputs
- Arbitrary file read/write outside of designated directories
- Privilege escalation within the agent execution context

The following are out of scope:
- Vulnerabilities in third-party Go tools (subfinder, nuclei, etc.)
- Issues requiring physical access to the machine
- Social engineering attacks

## Security Architecture

SecurAgentX enforces defense-in-depth:

1. **Governance Gate** — Classifies every command as SAFE / PRIVILEGED / DESTRUCTIVE before execution
2. **Shell execution gated** — `shell=True` is used in `safe_exec.py` for native shell workflows; gated by Governance upstream
3. **Shell pipeline support** — Native shell pipelines (pipes, redirects) are supported; Governance classifies commands instead of relying on static character filtering
4. **Target validation** — All scan targets are validated before tool dispatch
5. **Scope enforcement** — Operations are confined to declared scope boundaries

## Supported Versions

| Version | Supported |
|---------|-----------|
| SecurAgentX 1.0.x | Yes (2026) |
| Older releases | No |
