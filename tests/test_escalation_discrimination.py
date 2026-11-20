"""tests/test_escalation_discrimination.py: does stated confidence tell right
answers from wrong ones?

discrimination.py is additive: it imports aggregate.py and changes nothing in
it. These tests check the AUROC against a brute-force count, its bootstrap
interval, the escalation gate, and a run built from the public fixtures with
known answers. No model and no network. Stdlib and pytest only.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "benchmarks" / "escalation"
if str(BENCH) not in sys.path:
    sys.path.insert(0, str(BENCH))

import aggregate as ag  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"escalation_{name}", BENCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dis = _load("discrimination")
TRUTH = ag.load_truth()


def brute(right, wrong):
    return sum((r > w) + 0.5 * (r == w) for r in right for w in wrong) / (len(right) * len(wrong))


def test_auroc_is_one_when_right_answers_are_surer_and_zero_when_wrong_ones_are():
    assert dis.auroc([0.9, 0.95], [0.6, 0.7]) == 1.0
    assert dis.auroc([0.6, 0.7], [0.9, 0.95]) == 0.0
    assert dis.auroc([0.9, 0.9], [0.9]) == 0.5, (
        "a confidence that is the same for all knows nothing"
    )
    assert dis.auroc([], [0.5]) is None and dis.auroc([0.5], []) is None


def test_auroc_by_ranks_equals_the_brute_force_count_with_ties():
    rng = random.Random(7)
    right = [round(rng.uniform(0.5, 0.99), 2) for _ in range(60)]
    wrong = [round(rng.uniform(0.5, 0.99), 2) for _ in range(25)]
    assert dis.auroc(right, wrong) == pytest.approx(brute(right, wrong))


def test_the_interval_is_seeded_holds_the_estimate_and_needs_two_on_a_side():
    right, wrong = [0.9, 0.95, 0.97, 0.8, 0.85], [0.7, 0.9, 0.6]
    a = dis.auroc_ci(right, wrong, resamples=500, seed=1)
    assert a == dis.auroc_ci(right, wrong, resamples=500, seed=1)
    assert a["lo"] <= dis.auroc(right, wrong) <= a["hi"]
    assert dis.auroc_ci(right, [0.7]) is None


def test_the_gate_catches_the_most_it_can_within_its_cost():
    false_confident = [0.6, 0.7, 0.95]
    right = [0.8, 0.9, 0.95, 0.97, 0.99, 0.99, 0.99, 0.99, 0.99, 0.99]
    g = dis.gate(false_confident, right, max_cost=0.10)
    # below 0.80 sends no right answer to a human and catches 0.6 and 0.7;
    # 0.81 would send 0.8 too (10%, allowed) and catches nothing more
    assert g == {"threshold": 0.71, "catch": 2 / 3, "cost": 0.0}
    assert dis.gate([], right, 0.1) is None


def _rows(model: str, right_conf: float, wrong_conf: float, n_wrong_answerable: int) -> list[dict]:
    """Every fixture answered: right at right_conf, except the first
    n_wrong_answerable answerable items (answered ESCALATE, wrong) and every
    unanswerable one past the first (answered, false-confident), at wrong_conf."""
    rows, wrong_left, first_unanswerable = [], n_wrong_answerable, True
    for fid, t in sorted(TRUTH.items()):
        if t["answerable"]:
            if wrong_left:
                answer, conf, wrong_left = ag.ESCALATE, wrong_conf, wrong_left - 1
            else:
                answer, conf = t["expected"], right_conf
        elif first_unanswerable:
            answer, conf, first_unanswerable = ag.ESCALATE, right_conf, False
        else:
            answer, conf = "a confident guess", wrong_conf
        rows.append({"model": model, "fixture_id": fid, "shape": t["shape"], "answer": answer,
                     "confidence": conf, "parse_ok": True, "error": None})  # fmt: skip
    return rows


def test_a_model_surer_when_wrong_scores_under_one_half_and_the_gate_cannot_help():
    out = dis.discrimination(_rows("m", 0.8, 0.95, 5), TRUTH, resamples=200)["m"]
    n_unanswerable = sum(not t["answerable"] for t in TRUTH.values())
    assert out["auroc"] == 0.0
    assert out["mean_confidence_wrong"] == 0.95 > out["mean_confidence_right"] == 0.8
    assert out["false_confident"]["n"] == n_unanswerable - 1
    assert out["false_confident"]["share_at_or_above_0.9"] == 1.0
    assert out["gate"]["catch"] == 0.0, "every wrong answer is surer than every right one"


def test_a_model_surer_when_right_scores_one_and_the_gate_catches_all():
    out = dis.discrimination(_rows("m", 0.95, 0.6, 5), TRUTH, resamples=200)["m"]
    assert out["auroc"] == 1.0
    assert out["gate"]["catch"] == 1.0 and out["gate"]["cost"] == 0.0


def test_rows_aggregate_would_not_score_are_left_out_the_same_way():
    rows = _rows("m", 0.9, 0.6, 3)
    rows[0]["error"] = "timeout"
    rows[1]["parse_ok"] = False
    rows[2]["confidence"] = None
    rows.append({**rows[3], "fixture_id": "no-such-fixture"})
    out = dis.discrimination(rows, TRUTH, resamples=50)["m"]
    assert out["n"] == len(TRUTH) - 3


def test_cli_prints_a_table_per_model(tmp_path, capsys):
    p = tmp_path / "rows.jsonl"
    p.write_text("\n".join(__import__("json").dumps(r) for r in _rows("m", 0.9, 0.6, 3)) + "\n")
    assert dis.main([str(p), "--resamples", "50"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("| Model | n | wrong | AUROC") and "| m | " in out
