#!/usr/bin/env python3
"""tools/store_export.py — a shim. The CLI itself lives in `forge/bundle.py`.

It moved there because `tools/` is not in the wheel: the build packages
`forge` alone, so a maker who ran `pip install forge-play` got the library
and no way to invoke it, and step 6 of the first-bite sequence
(docs/design/the-forge-workshop.md) was unreachable from a real install.
The installed entry point is `forge-export`; `python -m forge.bundle` works
too. This file stays so the path in the papers and in this checkout's own
habits keeps working.

    python tools/store_export.py --project-id my-workshop --repo-root .   # cut
    python tools/store_export.py --repo-root . --check                    # check
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge.bundle import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
