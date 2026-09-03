#!/usr/bin/env python3
"""forge/plan_shape.py — the decision-bearing plan (Phase 4 of the engine build).

The host's `Plan` (safe-app-store, `apps/the-forge/src/the_forge/plan.py`) is
`app_name + entries`, and the only entry kind is `file_write`. A decision
cannot be extracted from a shape that cannot express one: the stub builder
emits two file writes and no choice, and nothing in the fleet has ever handed
the checkpoint router a `Decision` that was not typed in by a test.

So the engine defines the shape itself, and the host's plan is a strict
subset of it. One new entry kind:

    {"kind": "fork",
     "decision_type": "storage-for-dates",           # the calibration key (D9)
     "surface": "where do the dates live?",           # the question, as posed
     "options": [{"label": "sidecar json", "tradeoff": "…"},
                 {"label": "exif in place", "tradeoff": "…"}],
     "recommended": "sidecar json",                   # the proposer's default, or null
     "confidence": 0.8,                               # P(maker picks recommended) in [0.5, 1], or null
     "resolves": {"sidecar json": [<file_write>…],    # what each option becomes once chosen
                  "exif in place": [<file_write>…]}}

A fork is the seam for "the model proposes": a model-written plan carries
forks, and NOTHING ELSE it writes reaches the router — `decision_extract`
turns forks into `checkpoint.Decision`s by rule, and `build_loop` runs them
through memory. `confidence` is what the calibration ledger records before
the maker answers and resolves after: ground truth that arrives on its own.

`validate` refuses a plan that is not a plan (bad app_name, no entries, an
unknown kind, a fork whose `resolves` is not file writes). A fork that IS a
fork but a bad one (one option, a decision_type outside the charset, a
confidence outside the believed range) is parsed and carries its `problems()`
— the extractor refuses it WITH THE REASON rather than dropping it, and the
build loop refuses to resolve a plan that holds one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from . import _ids, checkpoint_memory

__all__ = ["PlanShapeError", "KIND_FILE_WRITE", "KIND_FORK", "FileWrite", "ForkOption",
           "Fork", "PlanDoc", "validate", "load"]

KIND_FILE_WRITE = "file_write"
KIND_FORK = "fork"
_KINDS = (KIND_FILE_WRITE, KIND_FORK)


class PlanShapeError(Exception):
    """Not a plan. Refused before anything reads it."""


@dataclass(frozen=True)
class FileWrite:
    dest_path: str
    content: str
    executable: bool = False

    def to_dict(self) -> dict:
        d = {"kind": KIND_FILE_WRITE, "dest_path": self.dest_path, "content": self.content}
        if self.executable:
            d["executable"] = True
        return d


@dataclass(frozen=True)
class ForkOption:
    label: str
    tradeoff: str = ""


@dataclass(frozen=True)
class Fork:
    decision_type: str
    surface: str
    options: tuple[ForkOption, ...]
    recommended: str | None = None
    confidence: float | None = None
    resolves: dict[str, tuple[FileWrite, ...]] = field(default_factory=dict)

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(o.label for o in self.options)

    def problems(self) -> list[str]:
        """Why this fork cannot be asked. Empty means it can."""
        out: list[str] = []
        try:
            checkpoint_memory._check_decision_type(self.decision_type)
        except Exception as e:  # noqa: BLE001 — the reason is the message
            out.append(f"decision_type: {e}")
        if not self.surface.strip():
            out.append("surface is empty — there is no question to ask")
        if len(self.options) < 2:
            out.append(f"{len(self.options)} option(s) — a fork needs at least two real choices")
        labels = [o.label for o in self.options]
        if len(set(labels)) != len(labels):
            out.append("duplicate option labels")
        if any(not o.label.strip() for o in self.options):
            out.append("an option has an empty label")
        if self.recommended is not None and self.recommended not in labels:
            out.append(f"recommended {self.recommended!r} is not one of the options")
        if self.confidence is not None:
            if self.recommended is None:
                out.append("confidence given with no recommended option — a confidence in nothing")
            elif not (0.5 <= self.confidence <= 1.0):
                out.append(f"confidence {self.confidence} outside [0.5, 1.0] — state it in the direction believed")
        for k in self.resolves:
            if k not in labels:
                out.append(f"resolves names {k!r}, which is not an option")
        return out

    def to_dict(self) -> dict:
        return {
            "kind": KIND_FORK, "decision_type": self.decision_type, "surface": self.surface,
            "options": [{"label": o.label, "tradeoff": o.tradeoff} for o in self.options],
            "recommended": self.recommended, "confidence": self.confidence,
            "resolves": {k: [w.to_dict() for w in v] for k, v in self.resolves.items()},
        }


Entry = Union[FileWrite, Fork]


@dataclass(frozen=True)
class PlanDoc:
    app_name: str
    entries: tuple[Entry, ...]

    @property
    def forks(self) -> list[tuple[int, Fork]]:
        return [(i, e) for i, e in enumerate(self.entries) if isinstance(e, Fork)]

    @property
    def has_forks(self) -> bool:
        return any(isinstance(e, Fork) for e in self.entries)

    def to_dict(self) -> dict:
        return {"app_name": self.app_name, "entries": [e.to_dict() for e in self.entries]}


def _file_write(raw: object, where: str) -> FileWrite:
    if not isinstance(raw, dict) or raw.get("kind", KIND_FILE_WRITE) != KIND_FILE_WRITE:
        raise PlanShapeError(f"{where}: expected a file_write entry, got {raw!r}")
    dest, content = raw.get("dest_path"), raw.get("content")
    if not isinstance(dest, str) or not dest.strip():
        raise PlanShapeError(f"{where}: file_write needs a dest_path")
    if not isinstance(content, str):
        raise PlanShapeError(f"{where}: file_write needs string content")
    return FileWrite(dest_path=dest, content=content, executable=bool(raw.get("executable", False)))


def _fork(raw: dict, where: str) -> Fork:
    opts_raw = raw.get("options")
    if not isinstance(opts_raw, list):
        raise PlanShapeError(f"{where}: fork needs an options list")
    options = []
    for j, o in enumerate(opts_raw):
        if not isinstance(o, dict) or not isinstance(o.get("label"), str):
            raise PlanShapeError(f"{where}: option {j} needs a string label")
        options.append(ForkOption(label=o["label"], tradeoff=str(o.get("tradeoff", ""))))
    resolves_raw = raw.get("resolves") or {}
    if not isinstance(resolves_raw, dict):
        raise PlanShapeError(f"{where}: resolves must map option label → entries")
    resolves: dict[str, tuple[FileWrite, ...]] = {}
    for label, ents in resolves_raw.items():
        if not isinstance(ents, list):
            raise PlanShapeError(f"{where}: resolves[{label!r}] must be a list of file_write entries")
        resolves[label] = tuple(_file_write(e, f"{where}.resolves[{label!r}][{k}]") for k, e in enumerate(ents))
    conf = raw.get("confidence")
    if conf is not None and not isinstance(conf, (int, float)):
        raise PlanShapeError(f"{where}: confidence must be a number or null")
    return Fork(
        decision_type=str(raw.get("decision_type", "")),
        surface=str(raw.get("surface", "")),
        options=tuple(options),
        recommended=raw.get("recommended") if isinstance(raw.get("recommended"), str) else None,
        confidence=float(conf) if conf is not None else None,
        resolves=resolves,
    )


def validate(plan: dict) -> PlanDoc:
    """The plan, or a refusal. Structural only — see the module docstring for
    the line between 'not a plan' (raised here) and 'a bad fork' (carried)."""
    if not isinstance(plan, dict):
        raise PlanShapeError(f"a plan is an object, got {type(plan).__name__}")
    app = plan.get("app_name")
    if not isinstance(app, str) or not _ids._ID_PATTERN.match(app or ""):
        raise PlanShapeError(f"app_name {app!r} fails the path-safety charset — it becomes a path component")
    entries_raw = plan.get("entries")
    if not isinstance(entries_raw, list) or not entries_raw:
        raise PlanShapeError("plan has no entries")
    entries: list[Entry] = []
    for i, raw in enumerate(entries_raw):
        where = f"entries[{i}]"
        if not isinstance(raw, dict):
            raise PlanShapeError(f"{where}: not an object")
        kind = raw.get("kind")
        if kind == KIND_FILE_WRITE:
            entries.append(_file_write(raw, where))
        elif kind == KIND_FORK:
            entries.append(_fork(raw, where))
        else:
            raise PlanShapeError(f"{where}: unknown kind {kind!r} (one of {_KINDS})")
    return PlanDoc(app_name=app, entries=tuple(entries))


def load(path: Path | str) -> PlanDoc:
    try:
        return validate(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as e:
        raise PlanShapeError(f"cannot read plan at {path}: {e}") from e
