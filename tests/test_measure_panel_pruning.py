"""rudi193-cmd/Forge#7: measure_panel walked tool caches, so `.mypy_cache` could manufacture
a convergent finding and route to human_required.

The reproduction from the issue, as a test: two tiny sources plus one 400 KB
tool-cache database. Before the fix the cache satisfied BOTH default
instruments at once — byte-share dominator (census) and a `.db` smell
(hygiene) — which is precisely the independent-agreement condition convergence
exists to detect, raised about a file no maker wrote.
"""
from __future__ import annotations

from pathlib import Path

from forge import measure_panel


def _tree_with_a_cache(tmp_path: Path, cache_dir: str) -> Path:
    d = tmp_path / "build"
    (d / "src").mkdir(parents=True)
    (d / "src" / "main.py").write_text("def main():\n    return 1\n")
    (d / "src" / "util.py").write_text("def helper():\n    return 2\n")
    cache = d / cache_dir / "3.14"
    cache.mkdir(parents=True)
    (cache / "cache.db").write_bytes(b"\0" * 400_000)
    return d


def _default_panel(d: Path) -> measure_panel.PanelReport:
    return measure_panel.run_panel(
        d, [measure_panel.CensusInstrument(), measure_panel.HygieneInstrument()]
    )


def test_a_mypy_cache_cannot_manufacture_a_convergent_finding(tmp_path):
    d = _tree_with_a_cache(tmp_path, ".mypy_cache")
    report = _default_panel(d)
    named = [f.artifact for f in report.findings]
    assert not any(".mypy_cache" in a for a in named), named
    assert report.convergent == [], report.convergent


def test_every_named_cache_is_pruned(tmp_path):
    for i, name in enumerate(sorted(measure_panel.PRUNED_DIRS - {".git"})):
        d = _tree_with_a_cache(tmp_path / f"case{i}", name)
        walked = {p.relative_to(d).as_posix() for p in measure_panel._iter_files(d)}
        assert walked == {"src/main.py", "src/util.py"}, (name, walked)


def test_an_egg_info_directory_is_pruned_by_suffix(tmp_path):
    d = _tree_with_a_cache(tmp_path, "forge_play.egg-info")
    walked = {p.relative_to(d).as_posix() for p in measure_panel._iter_files(d)}
    assert walked == {"src/main.py", "src/util.py"}, walked


def test_an_unlisted_directory_is_still_walked(tmp_path):
    """The prune list is a NAMED set, not a heuristic: a directory that merely
    looks cache-like is measured, so an unusual cache shows up rather than
    vanishing. Silence here would be the same failure in the other direction."""
    d = _tree_with_a_cache(tmp_path, ".mystery_cache")
    walked = {p.relative_to(d).as_posix() for p in measure_panel._iter_files(d)}
    assert "src/main.py" in walked
    assert any(p.startswith(".mystery_cache/") for p in walked), walked


def test_a_cache_does_not_route_to_the_governance_queue(tmp_path):
    d = _tree_with_a_cache(tmp_path, ".mypy_cache")
    report = _default_panel(d)
    root = tmp_path / "checkpoints"
    routed = measure_panel.route(report, builder_id="a" * 32, root=root)
    assert routed == [] or routed == 0 or not routed, routed
