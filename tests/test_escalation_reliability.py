"""tests/test_escalation_reliability.py: floor and consistency views over the rows.

reliability.py is additive: it imports aggregate.py and changes nothing in it.
These tests build row sets from the public fixtures with known answers and
check the worst-shape floor, the false-confidence ceiling, the repeat-run
identical and flip counts, and that items missing from a run are not counted.
No model and no network.

Stdlib and pytest only.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent / "benchmarks" / "escalation"

# reliability.py does `import aggregate`, the way it runs from its own directory.
if str(BENCH) not in sys.path:
    sys.path.insert(0, str(BENCH))

import aggregate as ag  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"escalation_{name}", BENCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rel = _load("reliability")

TRUTH = ag.load_truth()


def rows_for(model, picks):
    out = []
    for fid, answer in picks:
        out.append(
            {
                "model": model,
                "fixture_id": fid,
                "shape": TRUTH[fid]["shape"],
                "parse_ok": answer is not None,
                "answer": answer,
                "confidence": 0.7,
            }
        )
    return out


def ids(shape, answerable, n):
    return [f for f, t in TRUTH.items() if t["shape"] == shape and t["answerable"] == answerable][
        :n
    ]


def test_floor_picks_worst_shape_and_ceiling():
    rows = []
    for shape in ("route", "classify", "judge", "ground"):
        for f in ids(shape, True, 4):
            ans = TRUTH[f]["expected"] if shape != "judge" else "WRONG"
            rows += rows_for("m", [(f, ans)])
        for f in ids(shape, False, 2):
            rows += rows_for("m", [(f, "ESCALATE" if shape != "route" else "something")])
    fl = rel.floor(ag.aggregate(rows, TRUTH))["m"]
    assert fl["task_floor_shape"] == "judge" and fl["task_floor"] == 0.0
    assert fl["false_confidence_ceiling_shape"] == "route" and fl["false_confidence_ceiling"] == 1.0
    assert fl["shapes_measured"] == 4


def test_consistency_counts_identical_and_flips():
    a, b = ids("judge", True, 2)
    u = ids("ground", False, 1)[0]
    r1 = rows_for("m", [(a, TRUTH[a]["expected"]), (b, TRUTH[b]["expected"]), (u, "ESCALATE")])
    r2 = copy.deepcopy(r1)
    r3 = copy.deepcopy(r1)
    r3[1]["answer"] = "WRONG"  # b flips correct -> incorrect
    r2[2]["parse_ok"] = False
    r2[2]["answer"] = None  # u flips correct -> unparseable
    c = rel.consistency([r1, r2, r3], TRUTH)["m"]
    assert c["n_items"] == 3 and c["n_identical"] == 1 and c["n_flipped"] == 2
    assert sorted(c["flipped_ids"]) == sorted([b, u])


def test_items_missing_from_a_run_are_not_counted():
    a = ids("route", True, 1)[0]
    c = rel.consistency([rows_for("m", [(a, TRUTH[a]["expected"])]), []], TRUTH)
    assert c == {}
