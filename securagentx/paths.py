"""securagentx/paths.py — Centralized path resolution for SecurAgentX.

All file-system paths used by SecurAgentX should go through this module.
This ensures pip-installed copies work correctly — user data always
lives under ~/.securagentx/, never in site-packages.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("securagentx.paths")

# ── User home directory (pip-safe) ───────────────────────────────
SECURAGENTX_HOME = Path("~/.securagentx").expanduser()

# Subdirectory layout
SECURAGENTX_DIRS = {
    "data": SECURAGENTX_HOME / "data",
    "tools": SECURAGENTX_HOME / "tools",
    "reports": SECURAGENTX_HOME / "reports",
    "scripts": SECURAGENTX_HOME / "scripts",
    "plugins": SECURAGENTX_HOME / "plugins",
}


def get_data_path(name: str) -> Path:
    """Return ~/.securagentx/data/{name}, creating dirs as needed."""
    p = SECURAGENTX_DIRS["data"] / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_reports_path(subdir: str = "") -> Path:
    """Return ~/.securagentx/reports[/{subdir}], creating dirs as needed.

    If `subdir` looks like a filename (contains a "."), only the parent
    directory is created so that callers can safely write_text() to the
    returned path. Otherwise the full path is treated as a directory.
    """
    path = SECURAGENTX_DIRS["reports"]
    if subdir:
        full_path = path / subdir
        # If subdir looks like a filename (has extension), create parent only
        if "." in subdir:
            full_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            full_path.mkdir(parents=True, exist_ok=True)
        return full_path
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_dir(subdir: str = "") -> Path:
    """Return ~/.securagentx/data[/{subdir}], creating dirs as needed."""
    p = SECURAGENTX_DIRS["data"] / subdir if subdir else SECURAGENTX_DIRS["data"]
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_log_dir(subdir: str = "") -> Path:
    """Return ~/.securagentx/data/logs[/{subdir}], creating dirs as needed."""
    p = SECURAGENTX_DIRS["data"] / "logs" / subdir if subdir else SECURAGENTX_DIRS["data"] / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_tools_path(name: str) -> Path:
    """Return ~/.securagentx/tools/{name}, creating dirs as needed."""
    p = SECURAGENTX_DIRS["tools"] / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def ensure_dirs() -> None:
    """Create all ~/.securagentx/ subdirectories on startup."""
    for d in SECURAGENTX_DIRS.values():
        d.mkdir(parents=True, exist_ok=True)


# ── .env resolution (search order: env var > home > cwd) ────────
ENV_OVERRIDE = os.environ.get("SECURAGENTX_ENV")


def find_env() -> Optional[Path]:
    """Locate .env using priority: ENV var → ~/.securagentx/ → cwd."""
    if ENV_OVERRIDE:
        p = Path(ENV_OVERRIDE).expanduser().resolve()
        if p.exists():
            return p
    for candidate in (SECURAGENTX_HOME / ".env", Path(".env").resolve()):
        if candidate.exists():
            return candidate
    return None


# ── config.yaml resolution (search order: env var > home > cwd) ─
CONFIG_OVERRIDE = os.environ.get("SECURAGENTX_CONFIG")


def find_config() -> Optional[Path]:
    """Locate config.yaml using priority: ENV var → ~/.securagentx/ → cwd."""
    if CONFIG_OVERRIDE:
        p = Path(CONFIG_OVERRIDE).expanduser().resolve()
        if p.exists():
            return p
    for candidate in (SECURAGENTX_HOME / "config.yaml", Path("config.yaml").resolve()):
        if candidate.exists():
            return candidate
    return None
