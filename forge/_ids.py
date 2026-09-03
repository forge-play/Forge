"""forge/core/_ids.py — builder-id charset (vendored from safe-app-store principal.py).

The model side keys every per-builder record on a builder_id; principal.py (D2/D11)
is the one place that charset is defined, and checkpoint_memory imported
`principal._check_builder_id` from it. Rather than drag the 900-line SAFE identity
core into a dependency-light library, this vendors the ~10 lines actually used —
the same "vendor the primitive, not the package" discipline calibration/human_loop/
friction_floor follow. Bound as `principal` at the import site so the reference is
unchanged. If principal.py's charset moves, reconcile this copy.
"""
from __future__ import annotations

import re
from typing import Any

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_MAX_BUILDER_ID_LEN = 128


class PrincipalError(Exception):
    """Fail-closed refusal — a builder_id that is not a str or fails the
    path-safety charset (D11)."""


def _check_builder_id(builder_id: Any) -> str:
    if not isinstance(builder_id, str):
        raise PrincipalError(f"builder_id must be a str, got {type(builder_id).__name__}")
    if not builder_id or not _ID_PATTERN.match(builder_id):
        raise PrincipalError(f"builder_id {builder_id!r} fails the path-safety charset (D11)")
    if len(builder_id) > _MAX_BUILDER_ID_LEN:
        raise PrincipalError(f"builder_id is longer than {_MAX_BUILDER_ID_LEN} characters")
    return builder_id
