"""forge/store_diff.py — the build checks its store against the main one.

Paper: docs/design/the-store-diff.md. The operator, 2026-09-03: *"something I
have been fighting for a long long time is that the build has to check against
the main store to see what the difference is."* Tonight was the evidence: the
project store built the engine, the main store came to hold the seals, and
the entry asked the project store first and never knew.

The difference is four sets, all reads, no keyring needed to compute them:

- **verified upstream** — same question in both, draft here, sealed there,
  same answer. The seals that should come home.
- **proposed here** — in the project store, absent from main. What the pull
  carries up.
- **conflicts** — same question, different answer, at least one side sealed
  (or two drafts that diverged). Never resolved by a build; surfaced.
- **retired here, sealed there** — the project store superseded a question
  (by a `supersedes` edge from a newer row, or by revision) and main sealed
  the old one. Tonight had these.

`main` may be a live store, a path to one, or a Nestor bundle (a dict or a
path to `bundle.json`), because from a workshop on another box the main
store is only ever reachable as its export at the seam.

Write-free. Nothing here proposes, seals, imports or edges; bringing seals
home is the separate act that needs the keyring, and this is what says
whether it is worth doing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

__all__ = ["Diff", "diff", "load_main", "summary"]

DEFAULT_DOMAIN = "decision"


@dataclass
class Diff:
    domain: str
    project_live: int
    main_live: int
    agreed: int
    verified_upstream: list[dict] = field(default_factory=list)
    proposed_here: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    retired_here_sealed_there: list[dict] = field(default_factory=list)
    main_source: str = ""

    @property
    def behind(self) -> int:
        return len(self.verified_upstream)

    @property
    def ahead(self) -> int:
        return len(self.proposed_here)

    def to_dict(self) -> dict:
        return {
            "domain": self.domain, "project_live": self.project_live, "main_live": self.main_live,
            "agreed": self.agreed, "behind": self.behind, "ahead": self.ahead,
            "verified_upstream": list(self.verified_upstream), "proposed_here": list(self.proposed_here),
            "conflicts": list(self.conflicts), "retired_here_sealed_there": list(self.retired_here_sealed_there),
            "main_source": self.main_source,
        }


def _live(rows: Iterable[dict], domain: str) -> dict[str, dict]:
    """Live rows of one domain keyed by `source_norm`. A row without a norm
    (an old bundle) is keyed by its lower-cased source text, which is what the
    string matcher's normalisation approximates; never dropped silently."""
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("source_lang") != domain or r.get("target_lang") != domain:
            continue
        if r.get("superseded_by"):
            continue
        norm = r.get("source_norm") or (r.get("source_text") or "").strip().lower()
        if norm:
            out[norm] = r
    return out


def _project_rows(store: Any) -> list[dict]:
    store.memory_init()
    return list(store.memory_list(limit=1_000_000))


def _retired_norms(store: Any, live: dict[str, dict], all_rows: list[dict]) -> dict[str, dict]:
    """Questions the project retired: rows with `superseded_by` set, and rows
    that are the `dst` of a `supersedes` edge from a live row. The project
    store marks retirement both ways; the column is Nestor's revision, the
    edge is the store's own convention for a newer question replacing an
    older one."""
    by_id = {r["id"]: r for r in all_rows}
    retired: dict[str, dict] = {}
    for r in all_rows:
        if r.get("superseded_by"):
            retired[r.get("source_norm") or r["source_text"].strip().lower()] = r
    edges_from = getattr(store, "memory_edges_from", None)
    if callable(edges_from):
        for r in live.values():
            for e in edges_from(r["id"]):
                if e.get("kind") == "supersedes" and e.get("dst_id") in by_id:
                    d = by_id[e["dst_id"]]
                    retired[d.get("source_norm") or d["source_text"].strip().lower()] = d
    # a question both live and retired (an edge to a still-live older row) counts as retired
    return retired


def load_main(main: Any) -> tuple[list[dict], str]:
    """Rows of the main store, from a store object, a bundle dict, a path to a
    bundle (.json) or a path to a store (.db). Returns (rows, description)."""
    if isinstance(main, dict):
        return list(main.get("pairs") or []), f"bundle (digest {str(main.get('digest', ''))[:12]})"
    if isinstance(main, (str, Path)):
        p = Path(main)
        if p.suffix.lower() == ".json":
            b = json.loads(p.read_text(encoding="utf-8"))
            return list(b.get("pairs") or []), f"bundle {p.name} (digest {str(b.get('digest', ''))[:12]})"
        try:
            from nestor.sqlite_store import SqliteStore  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("Nestor is unavailable; pass the main store as a bundle instead") from e
        s = SqliteStore(str(p))
        s.memory_init()
        return list(s.memory_list(limit=1_000_000)), f"store {p.name}"
    # a store object
    main.memory_init()
    return list(main.memory_list(limit=1_000_000)), "store"


def _ref(r: dict) -> dict:
    return {"id": r.get("id", ""), "question": r.get("source_text", ""), "status": r.get("status", ""),
            "verifier": r.get("verifier", "")}


def diff(project_store: Any, main: Any, domain: str = DEFAULT_DOMAIN) -> Diff:
    """Compare the project store's live rows in `domain` with the main store's."""
    all_rows = _project_rows(project_store)
    proj = _live(all_rows, domain)
    retired = _retired_norms(project_store, proj, all_rows)
    main_rows, main_desc = load_main(main)
    mn = _live(main_rows, domain)

    d = Diff(domain=domain, project_live=len(proj), main_live=len(mn), agreed=0, main_source=main_desc)
    for norm, p in proj.items():
        if norm in retired:
            # A question this project retired by edge is still a live row, but
            # it is not "behind" and not "agreed": it is retired, and main's
            # seal on it is reported in its own set below.
            continue
        m = mn.get(norm)
        if m is None:
            d.proposed_here.append(_ref(p))
            continue
        same = (p.get("target_text") or "") == (m.get("target_text") or "")
        p_sealed, m_sealed = p.get("status") == "sealed", m.get("status") == "sealed"
        if same:
            if m_sealed and not p_sealed:
                d.verified_upstream.append({**_ref(p), "main_id": m.get("id", ""), "main_verifier": m.get("verifier", "")})
            else:
                d.agreed += 1
        else:
            d.conflicts.append({"question": p.get("source_text", ""), "here": _ref(p) | {"answer": p.get("target_text", "")},
                                "there": _ref(m) | {"answer": m.get("target_text", "")},
                                "kind": ("sealed_both" if p_sealed and m_sealed else "sealed_there" if m_sealed
                                         else "sealed_here" if p_sealed else "drafts_diverged")})
    for norm, r in retired.items():
        m = mn.get(norm)
        if m is not None and m.get("status") == "sealed":
            d.retired_here_sealed_there.append({**_ref(r), "main_id": m.get("id", ""), "main_verifier": m.get("verifier", "")})
    return d


def summary(d: Diff) -> str:
    """One line for a tier: counts, in the order a build should read them."""
    parts = [f"behind {d.behind} (sealed upstream)", f"ahead {d.ahead} (proposed here)",
             f"{len(d.conflicts)} conflict(s)"]
    if d.retired_here_sealed_there:
        parts.append(f"{len(d.retired_here_sealed_there)} retired here but sealed there")
    return ", ".join(parts) + f"; {d.agreed} agreed; main: {d.main_source}"
