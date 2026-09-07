#!/usr/bin/env python3
"""forge/band_probe.py — does the band selector look at the maker at all?

`docs/design/the-forge-pedagogy.md` §5 claims the `auto` band keys on the
ENGINE's confidence and the store's fill, not on the MAKER's demonstrated
calibration — so a maker who is reliably miscalibrated on a decision-type gets
just as many auto-applied answers as one who is reliably right, and gets more of
them as the store fills. This runs that claim.

**The measurement.** Two simulated makers answer the SAME decisions, in the same
order, for the same number of rounds. They differ in one respect only:

  * `aligned`  — always picks what the plan recommended. Every prediction about
                 them comes true: hit rate 1.0.
  * `contrary` — always picks the other option. Every prediction about them
                 fails: hit rate 0.0.

At a stated confidence of 0.9 these are the two extremes the calibration ledger
can express — an overconfidence of −0.10 against +0.90, a full 100 points apart.
If band selection read calibration in any way, no two makers on earth would
separate it more. The probe reports the difference in their band trajectories.

**Reading the result.** The finding is a NULL, and a null is only worth
reporting when the instrument could have seen the effect. Two guards:

  * The makers are constructed to be maximally different in the quantity under
    test, so a zero difference is not a weak contrast.
  * The reportability floor is the operator-sealed
    `benchmark-eval-harness-spread-pp` = 10–20 percentage points. A band-rate
    difference below that is not distinguishable from harness noise either way,
    so the probe reports `separable=False` rather than "no effect" — the honest
    claim is that the selector shows no calibration sensitivity ABOVE the floor,
    not that it provably has none.

The structural argument is the stronger one and does not depend on this run at
all: `run_checkpoint` reads `checkpoint_memory.check(surface)` and nothing else.
No calibration value is in scope at the branch. This probe measures the
consequence of that fact, so it stays measured rather than asserted.

Model-free, no egress. Writes only into the temp `FORGE_HOME` it is handed.

Usage:
    python -m forge.band_probe --rounds 6
    python -m forge.band_probe --rounds 6 --json
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from . import calibration_ledger, checkpoint, checkpoint_memory

__all__ = ["MAKERS", "run", "summary", "main"]

# Stated confidence for every prediction. Fixed so the two makers differ ONLY
# in outcome, never in what was claimed about them.
CONFIDENCE = 0.9

# The reportability floor: operator-sealed as `benchmark-eval-harness-spread-pp`
# in the main Nestor (10–20pp, verifier "sean campbell", 2026-09-02). Checked
# with `nestor_check`, not restated from memory.
HARNESS_SPREAD_PP = 10.0

MAKERS = ("aligned", "contrary")

# Three decision-types, each asked once per round. Two options apiece, with the
# first always the recommendation, so "picks the other" is unambiguous.
_TYPES: tuple[tuple[str, str, str, str], ...] = (
    ("where-the-dates-live", "When a picture gets a date, where does the date go?",
     "sidecar json", "exif in place"),
    ("auth-flow-for-user-facing-form", "How should the login form authenticate?",
     "session cookie + CSRF", "JWT bearer token"),
    ("cache-write-policy", "Should the cache be write-through or write-back?",
     "write-through", "write-back"),
)

# A substantive rationale, deliberately: a thin one would confound this
# measurement with the engagement defect (the-forge-engagement-defect.md).
_RATIONALE = ("the tradeoff we already argued applies here too, and the failure "
              "mode we measured last time has not changed")


class _Maker:
    """Confirms every prior (so the auto band is exercised, not escaped), and on
    a fresh decision picks by the maker's fixed policy."""

    def __init__(self, policy: str):
        self.policy = policy
        self.bands: list[str] = []

    def confirm(self, prompt: str) -> bool:
        return True

    def choose(self, decision: checkpoint.Decision) -> checkpoint.ChoiceResult:
        labels = [o.label for o in decision.options]
        label = labels[0] if self.policy == "aligned" else labels[1]
        return checkpoint.ChoiceResult(chosen_label=label, rationale=_RATIONALE)


def run(policy: str, rounds: int, root: Path) -> dict:
    """One maker, `rounds` passes over the same decisions. Returns their band
    trajectory and their calibration scorecard grouped by band."""
    builder_id = (policy[0] * 32)[:32]
    maker = _Maker(policy)
    per_round: list[dict[str, int]] = []

    for r in range(rounds):
        counts: dict[str, int] = {}
        for dtype, surface, first, second in _TYPES:
            decision = checkpoint.Decision(
                decision_type=dtype, surface=surface,
                options=[checkpoint.Option(first, "the recommended call"),
                         checkpoint.Option(second, "the other call")],
                recommended=first)
            # A fresh claim per round: record_prediction is idempotent on claim
            # text and refuses to re-record a settled one, which is correct and
            # would otherwise collapse every round into one data point.
            claim = f"{dtype} r{r}: maker picks {first}"
            pred = calibration_ledger.record_prediction(
                builder_id, claim, CONFIDENCE, kind="fork",
                decision_type=dtype, root=root)
            outcome = checkpoint.run_checkpoint(
                decision, builder_id=builder_id, responder=maker, root=root)
            chosen_label = outcome.chosen.split(":", 1)[0].strip()
            calibration_ledger.resolve_prediction(
                builder_id, pred["id"], chosen_label == first,
                decision=outcome, root=root)
            counts[outcome.band] = counts.get(outcome.band, 0) + 1
            maker.bands.append(outcome.band)
        per_round.append(counts)

    card = calibration_ledger.scorecard(builder_id, group_by="band", root=root)
    n = len(maker.bands)
    return {
        "policy": policy,
        "n_decisions": n,
        "auto_rate_pct": 100.0 * maker.bands.count("auto") / max(1, n),
        "band_counts": {b: maker.bands.count(b) for b in ("auto", "recognize", "socratic")},
        "per_round": per_round,
        "hit_rate": card["summary"]["hit_rate"],
        "brier": card["summary"]["brier"],
        "overconfidence": card["summary"]["overconfidence"],
        "by_band": {k: {"n": v["n"], "hit_rate": v["summary"]["hit_rate"],
                        "overconfidence": v["summary"]["overconfidence"]}
                    for k, v in card["groups"].items()},
    }


def summary(results: dict[str, dict]) -> dict:
    a, c = results["aligned"], results["contrary"]
    auto_gap = abs(a["auto_rate_pct"] - c["auto_rate_pct"])
    calib_gap = abs((a["overconfidence"] or 0.0) - (c["overconfidence"] or 0.0)) * 100
    return {
        "auto_rate_gap_pp": auto_gap,
        "calibration_gap_pp": calib_gap,
        "harness_spread_floor_pp": HARNESS_SPREAD_PP,
        "separable": auto_gap >= HARNESS_SPREAD_PP,
        "identical_trajectory": a["band_counts"] == c["band_counts"],
        "finding": (
            "band selection shows no calibration sensitivity above the harness "
            "floor: two makers 100pp apart in calibration took the same bands"
            if auto_gap < HARNESS_SPREAD_PP and a["band_counts"] == c["band_counts"]
            else "band selection differs between the two makers — investigate"
        ),
    }


def _render(results: dict[str, dict], s: dict) -> str:
    out = ["§5 — does the band selector read the maker?", ""]
    out.append(f"{'maker':<10} {'n':>4} {'auto':>5} {'recog':>6} {'socr':>5} "
               f"{'auto%':>7} {'hit':>6} {'overconf':>9}")
    out.append("-" * 62)
    for k in MAKERS:
        r = results[k]
        b = r["band_counts"]
        out.append(f"{r['policy']:<10} {r['n_decisions']:>4} {b['auto']:>5} "
                   f"{b['recognize']:>6} {b['socratic']:>5} "
                   f"{r['auto_rate_pct']:>6.1f}% {r['hit_rate']:>6.2f} "
                   f"{r['overconfidence']:>9.2f}")
    out += ["",
            f"calibration gap between them : {s['calibration_gap_pp']:.0f}pp",
            f"auto-band rate gap           : {s['auto_rate_gap_pp']:.1f}pp",
            f"reportability floor          : {s['harness_spread_floor_pp']:.0f}pp "
            f"(sealed benchmark-eval-harness-spread-pp)",
            f"separable above the floor    : {s['separable']}",
            "",
            s["finding"]]
    if results["contrary"]["by_band"]:
        out += ["", "the contrary maker's calibration, by band:"]
        for band, v in results["contrary"]["by_band"].items():
            out.append(f"  {band:<10} n={v['n']:<3} hit_rate={v['hit_rate']:.2f} "
                       f"overconfidence={v['overconfidence']:+.2f}")
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="band_probe.py",
        description="does the band selector read the maker's calibration?")
    p.add_argument("--rounds", type=int, default=6,
                   help="passes over the same decisions (default 6)")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not checkpoint_memory.nestor_available():
        print("refused: this probe needs Nestor — a band trajectory without "
              "memory is every decision in the socratic band by definition, "
              "which measures nothing.", file=__import__("sys").stderr)
        return 1
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "checkpoints"
        results = {m: run(m, args.rounds, root) for m in MAKERS}
    s = summary(results)
    if args.json:
        print(json.dumps({"summary": s, "makers": results}, indent=2, sort_keys=True))
    else:
        print(_render(results, s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
