"""securagentx/agents/script_safety.py — AST-based safety scanner for
AI-generated Python scripts.

Single public function, scan_script_safety(), walks the AST of a Python
source string and rejects code that could break out of the agent's intended
scope: shell/process execution, dynamic code evaluation, network egress,
native interop, and unsafe deserialization. Conservative by design —
trivial scripts (print, math, json) always pass.

Imported lazily by:
    agents/agent_executor.py         (execute_write_script)
    securagentx/scanning/executor.py (execute_write_script twin)
    securagentx/agent/vuln_agent.py  (_tool_run_python, _register_dynamic_tool)
"""

from __future__ import annotations

import ast
from typing import Tuple

__all__ = ["scan_script_safety"]

# Bare builtin names blocked when CALLED (not when merely named).
_BLOCKED_BARE_CALLS = frozenset({
    "eval", "exec", "compile", "__import__",
})

# module -> set of attrs blocked when called via attribute access.
# "*" means every attribute of the module is blocked.
_BLOCKED_ATTR_CALLS: dict[str, frozenset[str]] = {
    "os": frozenset({
        "system", "popen", "popen2", "popen3", "popen4",
        "execv", "execve", "execvp", "execvpe",
        "execl", "execle", "execlp", "execlpe",
        "spawnl", "spawnle", "spawnlp", "spawnlpe",
        "spawnv", "spawnve", "spawnvp", "spawnvpe",
        "fork", "forkpty", "kill", "killpg",
        "setuid", "setgid", "seteuid", "setegid",
        "setreuid", "setregid", "setresuid", "setresgid",
        "chroot",
    }),
    "subprocess": frozenset({
        "run", "call", "check_call", "check_output", "Popen",
        "getoutput", "getstatusoutput",
    }),
    "pickle":  frozenset({"loads", "load"}),
    "marshal": frozenset({"loads", "load"}),
    "shelve":  frozenset({"open"}),
    "importlib": frozenset({"import_module"}),
    "socket":  frozenset("*"),
    "urllib":  frozenset("*"),
    "urllib2": frozenset("*"),
    "urllib3": frozenset("*"),
    "ctypes":  frozenset("*"),
    "cffi":    frozenset("*"),
}

# Modules whose import is unconditionally forbidden.
_BLOCKED_IMPORT_MODULES = frozenset({
    "subprocess", "socket", "urllib", "urllib2", "urllib3",
    "ctypes", "cffi", "pickle", "marshal", "shelve", "importlib",
})

_WRITE_MODE_CHARS = frozenset("wax+")


def _attr_chain(node: ast.AST) -> str | None:
    """Return dotted chain ('os.system', 'urllib.request.urlopen') for an
    Attribute/Name root, or None if the root is not a bare Name."""
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _is_write_mode(arg: ast.AST) -> bool:
    """True iff arg is a string-literal open() mode that writes/appends."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value:
        return any(ch in _WRITE_MODE_CHARS for ch in arg.value)
    return False  # non-literal mode: lenient to avoid false positives


def scan_script_safety(
    code: str,
    *,
    allow_network: bool = False,
) -> Tuple[bool, str]:
    """Scan Python source for unsafe patterns via AST walk.

    Args:
        code: Python source to scan.
        allow_network: If True, socket/urllib are permitted (default False).

    Returns:
        (is_safe, reason). reason == "ok" when safe; otherwise a short
        human-readable explanation naming the first blocked pattern.

    Notes:
        - Empty / whitespace-only input is treated as safe (callers reject it).
        - SyntaxError / parse failures are treated as SAFE so the caller's own
          compile()/python3 step produces the canonical error message.
        - Single AST walk; no module import; runs in microseconds.
    """
    if not isinstance(code, str) or not code.strip():
        return True, "ok"

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return True, f"ok (note: syntax error: {exc})"
    except (ValueError, TypeError, RecursionError) as exc:
        return True, f"ok (note: parse error: {exc})"

    for node in ast.walk(tree):
        # 1. Bare-name calls: eval(), exec(), compile(), __import__(), open(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = node.func.id
            if fn in _BLOCKED_BARE_CALLS:
                return False, f"blocked: call to builtin '{fn}()' is forbidden"
            if fn == "open":
                if len(node.args) >= 2 and _is_write_mode(node.args[1]):
                    return False, "blocked: open() with write/append mode is forbidden"
                for kw in node.keywords:
                    if kw.arg == "mode" and _is_write_mode(kw.value):
                        return False, "blocked: open(mode=...) with write/append is forbidden"

        # 2. Attribute calls: os.system(...), subprocess.run(...), socket.*(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            chain = _attr_chain(node.func)
            if chain:
                parts = chain.split(".")
                if len(parts) >= 2:
                    module, attr = parts[0], parts[-1]
                    blocked = _BLOCKED_ATTR_CALLS.get(module)
                    if blocked is not None and ("*" in blocked or attr in blocked):
                        if module in ("socket", "urllib", "urllib2", "urllib3") and allow_network:
                            continue
                        return False, (
                            f"blocked: call to '{chain}()' is forbidden "
                            f"(module '{module}' is restricted)"
                        )

        # 3. Imports: 'import subprocess', 'from os import system', etc.
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BLOCKED_IMPORT_MODULES:
                    if alias.name.startswith(("socket", "urllib")) and allow_network:
                        continue
                    return False, f"blocked: import of '{alias.name}' is forbidden"
        if isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in _BLOCKED_IMPORT_MODULES:
                    if node.module.startswith(("socket", "urllib")) and allow_network:
                        continue
                    return False, f"blocked: from '{node.module}' import is forbidden"
                # Also catch 'from os import system' (os itself is allowed,
                # but specific attrs are not)
                blocked_attrs = _BLOCKED_ATTR_CALLS.get(root)
                if blocked_attrs is not None and "*" not in blocked_attrs:
                    for alias in node.names:
                        if alias.name in blocked_attrs:
                            return False, (
                                f"blocked: from '{node.module}' import "
                                f"'{alias.name}' is forbidden"
                            )

    return True, "ok"
