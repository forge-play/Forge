"""forge/paths.py — the one path resolver. All Forge state hangs off home().

Mirrors homestead.keep.paths: this is the ONLY module permitted to resolve a
home directory, and `Path.home()` is the only spelling it may use — the store's
vault-leak linter can SEE `Path.home() / ...` but a bare `~`/`expanduser` string
disappears from its report (homestead's I-20), and a write the tooling cannot see
is exactly the leak that discipline exists to prevent. No fixed-location default:
`FORGE_HOME` exists for tests and for an operator who deliberately moves the root,
not as a convenience override (homestead's I-19).
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = ["home", "project_nestor", "project_nestor_ledger"]

_ROOT_ENV = "FORGE_HOME"
_ROOT_NAME = ".forge"
_PROJECTS = "projects"


def home() -> Path:
    """The Forge root. `$FORGE_HOME`, else `<home>/.forge` — the shared home the
    checkpoint memory, calibration ledger, soil store and schedules all hang off,
    the way homestead-law and homestead-ledger share `~/.homestead`."""
    override = os.environ.get(_ROOT_ENV)
    if override:
        return Path(override)
    return Path.home() / _ROOT_NAME


def project_nestor(project_id: str) -> Path:
    """The per-PROJECT Nestor store: `<home>/projects/<project_id>/nestor/keep/
    nestor.db`. "The project store is per-project nestor, not the fleet store"
    (the-forge-shape.md, Decisions taken) — a store whose whole content is one
    build's world: disposable, portable, ships with the project. Distinct from
    the per-BUILDER checkpoint memory under `<home>/checkpoints/` (a maker's own
    sealed decisions) and from the fleet store at `~/.nestor`.

    `project_id` is a path component and gets the same charset rule as
    `builder_id` (forge/_ids.py) — imported, not re-implemented."""
    from . import _ids  # local: paths.py must stay import-light
    pid = _ids._check_builder_id(project_id)
    return home() / _PROJECTS / pid / "nestor" / "keep" / "nestor.db"


def project_nestor_ledger(project_id: str) -> Path:
    """The audit ledger beside the project store — every seal, rejection,
    evidence and warrant append lands here, hash-chained."""
    return project_nestor(project_id).with_name("ledger.jsonl")
