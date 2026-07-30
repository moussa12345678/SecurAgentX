"""core — DEPRECATED: Legacy core modules.

This package is no longer maintained. All functionality has been
consolidated into securagentx/ (cognitive loop) and securagentx/scanning/.
Kept only to prevent import errors for any remaining references.
"""

import warnings

warnings.warn(
    "core is deprecated and will be removed in a future release. "
    "Use securagentx/ instead.",
    DeprecationWarning,
    stacklevel=2,
)
