"""Tests for securagentx/paths.py — Path resolution."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from securagentx.paths import (
    SECURAGENTX_HOME,
    SECURAGENTX_DIRS,
    get_data_path,
    get_reports_path,
    get_data_dir,
    get_log_dir,
    get_tools_path,
)


class TestPathConstants:
    def test_securagentx_home(self):
        """SECURAGENTX_HOME should point to ~/.securagentx."""
        expected = Path("~/.securagentx").expanduser()
        assert SECURAGENTX_HOME == expected

    def test_securagentx_dirs_contains_all_keys(self):
        assert "data" in SECURAGENTX_DIRS
        assert "tools" in SECURAGENTX_DIRS
        assert "reports" in SECURAGENTX_DIRS
        assert "scripts" in SECURAGENTX_DIRS
        assert "plugins" in SECURAGENTX_DIRS


class TestGetDataPath:
    def test_returns_path_under_data(self):
        p = get_data_path("test.txt")
        assert str(p).endswith(".securagentx/data/test.txt")

    def test_creates_parent_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("securagentx.paths.SECURAGENTX_DIRS", {
                "data": Path(tmp) / ".securagentx" / "data",
                "tools": Path(tmp) / ".securagentx" / "tools",
                "reports": Path(tmp) / ".securagentx" / "reports",
                "scripts": Path(tmp) / ".securagentx" / "scripts",
                "plugins": Path(tmp) / ".securagentx" / "plugins",
            }):
                p = get_data_path("nested/deep/file.json")
                assert p.parent.exists()


class TestGetReportsPath:
    def test_returns_reports_root(self):
        p = get_reports_path()
        assert "reports" in str(p)

    def test_returns_reports_with_subdir(self):
        p = get_reports_path("pentest1")
        assert "pentest1" in str(p)

    def test_creates_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("securagentx.paths.SECURAGENTX_DIRS", {
                "data": Path(tmp) / ".securagentx" / "data",
                "tools": Path(tmp) / ".securagentx" / "tools",
                "reports": Path(tmp) / ".securagentx" / "reports",
                "scripts": Path(tmp) / ".securagentx" / "scripts",
                "plugins": Path(tmp) / ".securagentx" / "plugins",
            }):
                p = get_reports_path("subdir")
                assert p.exists()


class TestGetDataDir:
    def test_returns_data_root(self):
        p = get_data_dir()
        assert str(p).endswith(".securagentx/data")

    def test_returns_data_with_subdir(self):
        p = get_data_dir("chroma")
        assert "chroma" in str(p)


class TestGetLogDir:
    def test_returns_log_dir_under_data(self):
        p = get_log_dir()
        assert "logs" in str(p)

    def test_returns_log_dir_with_subdir(self):
        p = get_log_dir("scans")
        assert "scans" in str(p)


class TestGetToolsPath:
    def test_returns_path_under_tools(self):
        p = get_tools_path("nmap_wrapper.py")
        assert "tools" in str(p)

    def test_creates_parent_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("securagentx.paths.SECURAGENTX_DIRS", {
                "data": Path(tmp) / ".securagentx" / "data",
                "tools": Path(tmp) / ".securagentx" / "tools",
                "reports": Path(tmp) / ".securagentx" / "reports",
                "scripts": Path(tmp) / ".securagentx" / "scripts",
                "plugins": Path(tmp) / ".securagentx" / "plugins",
            }):
                p = get_tools_path("sub/tool.py")
                assert p.parent.exists()


class TestEnsureDirs:
    def test_ensure_dirs_creates_all_dirs(self):
        import securagentx.paths as _paths_mod
        with tempfile.TemporaryDirectory() as tmp:
            with patch("securagentx.paths.SECURAGENTX_DIRS", {
                "data": Path(tmp) / ".securagentx" / "data",
                "tools": Path(tmp) / ".securagentx" / "tools",
                "reports": Path(tmp) / ".securagentx" / "reports",
                "scripts": Path(tmp) / ".securagentx" / "scripts",
                "plugins": Path(tmp) / ".securagentx" / "plugins",
            }):
                from securagentx.paths import ensure_dirs
                ensure_dirs()
                # Reference the module attribute directly so we pick up the
                # patched dict. The module-level `from securagentx.paths import
                # SECURAGENTX_DIRS` at the top of this file binds the *original*
                # dict object into a local name, which the patch never updates.
                for d in _paths_mod.SECURAGENTX_DIRS.values():
                    assert d.exists(), f"{d} was not created"


class TestFindEnv:
    def test_env_override_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env.override"
            env_path.write_text("TEST=1\n")
            with patch("securagentx.paths.ENV_OVERRIDE", str(env_path)):
                from securagentx.paths import find_env
                result = find_env()
                assert result == env_path

    def test_env_override_not_found_falls_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("securagentx.paths.ENV_OVERRIDE", "/nonexistent/.env"):
                with patch("securagentx.paths.SECURAGENTX_HOME", Path(tmp)):
                    with patch("pathlib.Path.exists", return_value=False):
                        from securagentx.paths import find_env
                        result = find_env()
                        assert result is None


class TestFindConfig:
    def test_config_override_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.override.yaml"
            cfg_path.write_text("key: value\n")
            with patch("securagentx.paths.CONFIG_OVERRIDE", str(cfg_path)):
                from securagentx.paths import find_config
                result = find_config()
                assert result == cfg_path

    def test_config_override_not_found_falls_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("securagentx.paths.CONFIG_OVERRIDE", "/nonexistent/config.yaml"):
                with patch("securagentx.paths.SECURAGENTX_HOME", Path(tmp)):
                    with patch("pathlib.Path.exists", return_value=False):
                        from securagentx.paths import find_config
                        result = find_config()
                        assert result is None
