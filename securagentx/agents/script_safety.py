"""securagentx/agents/script_safety.py — AST-based safety scanner for
AI-generated Python scripts.

This is a **pentest tool** — it is *expected* that the AI will write code
that uses ``socket``, ``subprocess``, ``urllib``, ``os.system``, etc.
Those are legitimate security-research primitives, not attacks.

The scanner therefore blocks ONLY patterns that are almost always malicious
even in a pentest context:

  * ``eval()`` / ``exec()`` / ``compile()`` — dynamic code execution
    (the AI should write the code directly, not generate code to run code)
  * ``__import__()`` — dynamic import bypass (circumvents the import
    visibility that the scanner relies on)
  * ``pickle.loads()`` / ``marshal.loads()`` — deserialization RCE
  * ``ctypes`` / ``cffi`` — native interop (memory corruption, not a
    pentest tool)

Everything else — ``socket``, ``subprocess``, ``urllib``, ``requests``,
``os.system``, ``os.popen``, ``importlib``, ``open(write)``, ``shelve`` —
is **allowed by default** because this is a cybersecurity framework and
those are the tools of the trade.

YOLO mode
---------
Set ``SECURAGENTX_YOLO=1`` (or pass ``--yolo`` on the CLI) to disable
ALL scanning. Every script is treated as safe. Use this only when you
have explicit written authorization and understand the risks.

Imported lazily by:
    agents/agent_executor.py         (execute_write_script)
    securagentx/scanning/executor.py (execute_write_script twin)
    securagentx/agent/vuln_agent.py  (_tool_run_python, _register_dynamic_tool)
"""

from __future__ import annotations

import ast
import os
from typing import Tuple

__all__ = ["scan_script_safety", "is_yolo_mode"]

# ── YOLO mode ────────────────────────────────────────────────────────────────


def is_yolo_mode() -> bool:
    """Return True if SECURAGENTX_YOLO is set (disables all safety checks)."""
    return os.environ.get("SECURAGENTX_YOLO", "").lower() in ("1", "true", "yes", "on")


# ── Blocklist (minimal — only truly dangerous patterns) ──────────────────────

# Bare builtin names blocked when CALLED.
_BLOCKED_BARE_CALLS = frozenset({
    "eval", "exec", "compile", "__import__",
})

# module -> set of attrs blocked when called via attribute access.
# Only patterns that are almost always malicious in a pentest context.
_BLOCKED_ATTR_CALLS: dict[str, frozenset[str]] = {
    "pickle":  frozenset({"loads", "load"}),
    "marshal": frozenset({"loads", "load"}),
    "ctypes":  frozenset("*"),   # native interop = memory corruption
    "cffi":    frozenset("*"),
}

# Modules whose import is unconditionally forbidden.
_BLOCKED_IMPORT_MODULES = frozenset({
    "ctypes", "cffi", "pickle", "marshal",
})


def _attr_chain(node: ast.AST) -> str | None:
    """Return dotted chain ('os.system') for an Attribute/Name root, or None."""
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def scan_script_safety(
    code: str,
    *,
    allow_network: bool = True,
) -> Tuple[bool, str]:
    """Scan Python source for unsafe patterns via AST walk.

    This is a **pentest tool** — the scanner is intentionally permissive.
    It only blocks patterns that are almost always malicious even in a
    security-research context (eval, exec, pickle.loads, ctypes, etc.).

    Socket, subprocess, urllib, os.system, importlib, open(write) are
    ALL ALLOWED because they are legitimate pentest primitives.

    Args:
        code: Python source to scan.
        allow_network: Kept for backward compat — network access is always
            allowed in a pentest tool. This parameter is a no-op now.

    Returns:
        (is_safe, reason). reason == "ok" when safe; otherwise a short
        human-readable explanation naming the first blocked pattern.

    YOLO mode:
        If SECURAGENTX_YOLO env var is set, returns (True, "yolo") always.
    """
    # YOLO mode — disable all checks
    if is_yolo_mode():
        return True, "yolo"

    if not isinstance(code, str) or not code.strip():
        return True, "ok"

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        # Let the caller's compile()/python3 produce the canonical error
        return True, f"ok (note: syntax error: {exc})"
    except (ValueError, TypeError, RecursionError) as exc:
        return True, f"ok (note: parse error: {exc})"

    for node in ast.walk(tree):
        # 1. Bare-name calls: eval(), exec(), compile(), __import__()
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = node.func.id
            if fn in _BLOCKED_BARE_CALLS:
                return False, f"blocked: call to builtin '{fn}()' is forbidden"

        # 2. Attribute calls: pickle.loads(...), ctypes.*, cffi.*
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            chain = _attr_chain(node.func)
            if chain:
                parts = chain.split(".")
                if len(parts) >= 2:
                    module, attr = parts[0], parts[-1]
                    blocked = _BLOCKED_ATTR_CALLS.get(module)
                    if blocked is not None and ("*" in blocked or attr in blocked):
                        return False, (
                            f"blocked: call to '{chain}()' is forbidden "
                            f"(module '{module}' is restricted)"
                        )

        # 3. Imports: 'import ctypes', 'from pickle import loads'
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BLOCKED_IMPORT_MODULES:
                    return False, f"blocked: import of '{alias.name}' is forbidden"
        if isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in _BLOCKED_IMPORT_MODULES:
                    return False, f"blocked: from '{node.module}' import is forbidden"
                # Also catch 'from pickle import loads'
                blocked_attrs = _BLOCKED_ATTR_CALLS.get(root)
                if blocked_attrs is not None and "*" not in blocked_attrs:
                    for alias in node.names:
                        if alias.name in blocked_attrs:
                            return False, (
                                f"blocked: from '{node.module}' import "
                                f"'{alias.name}' is forbidden"
                            )

    return True, "ok"
