"""Make `matt_box` importable from the src/ layout without a full install.

Useful for local pytest runs before `pip install -e .` has completed.
CI does install the package; this is just a developer convenience.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
