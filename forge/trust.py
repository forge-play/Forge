#!/usr/bin/env python3
"""forge/trust.py — the forge's promotion trust as a MECHANISM (OPTIONAL).

§0.2 says proposing and ratifying never rest in the same hand. Today the forge's
`promote_check` enforces that as a STRING check: `verified_by` must be non-empty
and differ from `author`. A name anyone can type into a JSON field is not a
ratification — it is the hollow `verified_by` this fleet already got burned by.

This makes it real, reusing the cloud seam (nestor.cloud_seal + willow-gate) —
the same two-tier pattern, applied to a promotion instead of a decision:

  * ENROLL   — the author provisionally seals the promotion THROUGH THE GATE,
    under its own identity, at its earned rung: witnessed, custody-chained,
    never canonical (`nestor.cloud_seal.seal_through_gate`).
  * RATIFY   — a DIFFERENT hand confers CANONICAL: a custody `checkpoint()`
    signed by the verifier's key. This is the home-end act; the key IS the
    ratification, not the string.
  * WITNESSED — §0.2 as a gate that is *verified, not asserted*: author ≠
    verifier, the author's provisional seal of THIS promotion is in the chain,
    and a checkpoint signed by the verifier's key verifies and covers it.
    `verified_by` becomes the identity whose key signed — a machine cannot type
    its way past it.

Fail-closed on the seam: importing this requires `nestor.cloud_seal` (which
requires willow-gate). No gate at this end → no cloud trust; the host falls back
to whatever local check it applies. The forge engine core stays dependency-free;
this is the opt-in `forge[trust]` extra, and its absence is the off switch.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

try:  # FAIL-CLOSED ON THE SEAM
    from nestor.cloud_seal import seal_through_gate
    from willow_gate.custody import checkpoint, verify_checkpoint
except ImportError as e:  # pragma: no cover - exercised by the extra's absence
    raise ImportError(
        "forge.trust is the OPTIONAL promotion-trust seam; it requires the cloud "
        "path (nestor.cloud_seal + willow-gate) installed at this end. "
        "Install it: pip install forge[trust]."
    ) from e


def promotion_lineage(app_id: str) -> str:
    """The custody lineage a promotion's seals hang off — one per app."""
    return f"promotion:{app_id}"


def _canonical(promotion: dict) -> str:
    return json.dumps(promotion, sort_keys=True, separators=(",", ":"))


def enroll(gate, author_id: str, secret: bytes, *, custody, promotion: dict,
           trust_level: int = 1, tools=("read",)):
    """The author provisionally seals the promotion through the gate. PROVISIONAL,
    never canonical — reuses the cloud seam wholesale (rule 11). Returns its
    `ProvisionalSealResult`. Raises `GateError` on a bad identity/unearned rung."""
    app_id = promotion["app_id"]
    return seal_through_gate(
        gate, author_id, secret,
        [(promotion_lineage(app_id), _canonical(promotion))],
        custody=custody, trust_level=trust_level, tools=tools,
    )


def ratify(custody, verifier_signer, *, ts: str | None = None):
    """A DIFFERENT hand confers canonical: a custody checkpoint signed by the
    verifier's key. The home-end act; returns the checkpoint event."""
    return checkpoint(custody, verifier_signer, ts=ts)


@dataclass
class WitnessResult:
    ok: bool
    reason: str


def witnessed(custody, checkpoint_event: dict, verifier_signer, *,
              author_id: str, verifier_id: str, app_id: str) -> WitnessResult:
    """§0.2, verified not asserted. True only when all three hold:
      1. author_id != verifier_id — proposing and ratifying are different hands;
      2. the author's PROVISIONAL seal of this promotion is in the custody chain;
      3. a checkpoint signed by the verifier's KEY verifies and covers that seal.
    """
    if not verifier_id or author_id == verifier_id:
        return WitnessResult(False, "proposing and ratifying must be different hands "
                                    f"(author={author_id!r} verified_by={verifier_id!r})")

    lineage = promotion_lineage(app_id)
    seal = next((e for e in custody.events()
                 if e.get("kind") == "file.create"
                 and e.get("lineage_id") == lineage
                 and e.get("actor") == author_id), None)
    if seal is None:
        return WitnessResult(False, f"no provisional seal of {lineage!r} by author {author_id!r}")

    vr = verify_checkpoint(custody, checkpoint_event, verifier_signer)
    if not vr.ok:
        return WitnessResult(False, f"ratification checkpoint invalid: {vr.reason}")

    covers = checkpoint_event.get("covers_to_seq", -1)
    if not isinstance(seal.get("seq"), int) or seal["seq"] > covers:
        return WitnessResult(False, "ratification does not cover the provisional seal")

    return WitnessResult(True, f"witnessed: provisional by {author_id}, "
                               f"canonical by {verifier_id} (key-verified, ≠ author)")
