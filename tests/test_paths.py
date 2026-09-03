"""Tests for forge/paths.py — the one path resolver.

home() reads $FORGE_HOME with a `~/.forge` fallback.

NOTE (2026-08-18): the task this file was written against described
forge/paths.py as 44 lines with two functions, `home()` and `ensure()` —
`ensure()` created a directory under home() and refused to create one
outside it, resolving symlinks first so the guard couldn't be walked around
by a link. By the time this file was written, a concurrent edit already in
this worktree (uncommitted; see `git diff -- forge/paths.py`) had removed
`ensure()` — confirmed dead: no other module in forge/ called
`paths.ensure`, and each of checkpoint_memory.py, checkpoint_schedule.py,
and soil_store.py already implements its own `is_symlink()` guard +
`mkdir(parents=True, exist_ok=True)` inline rather than delegating to it.
`__all__` was trimmed to `["home"]` in the same edit. This file therefore
tests only `home()`, the function that still exists; if `ensure()` is
reintroduced, restore tests for it (git history has the removed version if
a reference is useful — `git log -p -- forge/paths.py`).
"""
from __future__ import annotations

from pathlib import Path

from forge import paths


# ── home() ───────────────────────────────────────────────────────────────────

def test_home_defaults_to_dot_forge_under_the_real_home(monkeypatch):
    monkeypatch.delenv("FORGE_HOME", raising=False)
    assert paths.home() == Path.home() / ".forge"


def test_home_respects_forge_home_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_HOME", str(tmp_path / "somewhere-else"))
    assert paths.home() == tmp_path / "somewhere-else"


def test_home_returns_a_path_object(monkeypatch):
    monkeypatch.delenv("FORGE_HOME", raising=False)
    assert isinstance(paths.home(), Path)


def test_home_with_forge_home_set_is_also_a_path_object(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_HOME", str(tmp_path))
    assert isinstance(paths.home(), Path)


def test_home_falls_back_when_forge_home_is_empty_string(monkeypatch):
    """`if override:` treats an empty string as unset — `FORGE_HOME=` in an
    environment (as opposed to not exporting it at all) must not resolve to
    a relative empty path."""
    monkeypatch.setenv("FORGE_HOME", "")
    assert paths.home() == Path.home() / ".forge"


def test_home_does_not_touch_the_filesystem(tmp_path, monkeypatch):
    """home() only computes a path; it must not create anything."""
    target = tmp_path / "not-yet-created"
    monkeypatch.setenv("FORGE_HOME", str(target))
    result = paths.home()
    assert result == target
    assert not target.exists()
