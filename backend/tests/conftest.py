"""Shared pytest fixtures.

Adds the backend directory to sys.path so tests can import the `app` package
without an editable install, and configures pytest-asyncio for the suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
