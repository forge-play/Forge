#!/usr/bin/env python3
"""tools/band_probe.py — does the band selector read the maker's calibration?

    python tools/band_probe.py --rounds 6
    python tools/band_probe.py --rounds 6 --json

Runs `docs/design/the-forge-pedagogy.md` §5: two simulated makers, maximally
apart in calibration (hit rate 1.0 against 0.0 at a stated 0.9), answer the same
decisions in the same order. Reports whether their band trajectories differ by
more than the operator-sealed harness-spread floor.

Writes only into a temporary FORGE_HOME it creates and removes. The logic lives
in `forge/band_probe.py` (tools/ is not in the wheel).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge import band_probe  # noqa: E402

if __name__ == "__main__":
    sys.exit(band_probe.main())
