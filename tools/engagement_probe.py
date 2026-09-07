#!/usr/bin/env python3
"""tools/engagement_probe.py — what does the engagement gate actually reward?

    python tools/engagement_probe.py
    python tools/engagement_probe.py --json

A read-only probe over a fixed corpus of labelled rationales. Writes nothing,
calls no model, touches no store. Reports the authoritative
`checkpoint_engagement.engagement_score` per row and decomposes it into
`friction_score`'s four terms, so a reader can see which term carried it.

Exit 1 when a rationale labelled `not_a_decision` is NOT read as a rubber-stamp
— a string nobody typed as a reason scoring as engagement — so a hook can gate
on it; 0 otherwise.

The logic lives in `forge/engagement_probe.py` (tools/ is not in the wheel —
the same reason `tools/store_export.py` is a shim over `forge/bundle.py`).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge import engagement_probe  # noqa: E402

if __name__ == "__main__":
    sys.exit(engagement_probe.main())
