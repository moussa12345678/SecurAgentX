import os
import sys

# Ensure project root is on sys.path for test imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Provide a strong (>= 32 chars) session secret for the test suite so the
# fail-closed SESSION_SECRET resolver in securagentx.api._auth does not
# reject every cookie-touching test. Tests that need a different secret
# can override this via monkeypatch + ``api_auth.SESSION_SECRET = None``
# (the lazy resolver re-reads the env var on next call).
# This MUST be set before any test module imports ``securagentx.api._auth``.
os.environ.setdefault(
    "SECURAGENTX_SESSION_SECRET",
    "brutal-test-secret-key-7e3c9d1a5b8f2e04",  # 38 chars — passes 32-char min
)
