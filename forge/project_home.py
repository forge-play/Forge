"""forge/project_home.py — the maker's folder, made once, after a successful bite.

    "After the first bite a dedicated project home appears."
                          (docs/design/the-workshop-surface-and-home.md)

`ensure_project_home(project_id)` creates `paths.project_home(project_id)` if
it is missing and writes a starter README on that first creation only. It is
idempotent, refuses a bad id, and never modifies an existing directory's
contents. It is called by the HOST after `open_bite` has succeeded — a refused
entry creates neither a home nor anything else, so `open_bite` stays pure and
this module never imports it.

What this folder is not: it is not the project store (that stays under
`paths.home()`), and it is not the git checkout (that carries the bundle). The
engine never writes a Nestor database or a `.forge/` here, and nothing in this
folder is verified by being here.
"""

from __future__ import annotations

from pathlib import Path

from . import _ids, paths

__all__ = ["ProjectHomeError", "README_NAME", "STARTER_README", "ensure_project_home"]

README_NAME = "README.md"


class ProjectHomeError(Exception):
    """Fail-closed refusal: a bad id, a symlinked path, or a path that exists
    and is not a directory."""


STARTER_README = """# {project_id}

This is the working folder for the project.

- Engine state (Nestor store, checkpoints, calibration) lives under `~/.forge`.
- The git repository is wherever you cloned or instantiated the workshop.
- This folder is yours for notes, experiments, pulled candidates, and local work.

Items pulled from Jeles, Almanac, or Awesome Sovereign Software are candidates only.
Only a human seal turns anything into a verified fact inside the project.
"""


def ensure_project_home(project_id: str) -> Path:
    """Idempotent. Creates the directory if missing. On first creation only,
    writes the starter README. Refuses on an empty or invalid id. Never
    modifies an existing directory's contents — a README the maker edited or
    deleted stays edited or deleted."""
    try:
        home = paths.project_home(project_id)
    except _ids.PrincipalError as e:
        raise ProjectHomeError(f"project_id rejected: {e}") from e

    # The same guard the checkpoint root and the SOIL store apply: a link is
    # a way to make "the project home" land somewhere else.
    if home.is_symlink():
        raise ProjectHomeError(f"refusing a symlinked project home: {home}")
    if home.exists():
        if not home.is_dir():
            raise ProjectHomeError(f"project home exists and is not a directory: {home}")
        return home  # already made; nothing inside is ours to touch

    home.mkdir(parents=True, exist_ok=False)
    readme = home / README_NAME
    if readme.is_symlink():
        raise ProjectHomeError(f"refusing a symlinked README: {readme}")
    readme.write_text(STARTER_README.format(project_id=project_id), encoding="utf-8")
    return home
