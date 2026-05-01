"""pytest configuration for mcp-shim tests.

Adds the parent directory to sys.path so `import mcp_server` works without
installing the package, and exposes shared fixtures.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHIM_ROOT = Path(__file__).resolve().parent.parent
if str(_SHIM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHIM_ROOT))
