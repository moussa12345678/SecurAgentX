import os
import sys

# Ensure project root is on sys.path for test imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Provide a strong (>= 32 chars) session secret for the test suite so any
# cookie/session-touching code that consults SECURAGENTX_SESSION_SECRET does
# not reject every test. The ``securagentx.api`` package has been removed
# (dead code), but the env var is still surfaced here for any remaining
# consumers that may read it directly. Tests that need a different secret
# can override this via monkeypatch on the consuming module.
os.environ.setdefault(
    "SECURAGENTX_SESSION_SECRET",
    "brutal-test-secret-key-7e3c9d1a5b8f2e04",  # 38 chars — passes 32-char min
)
