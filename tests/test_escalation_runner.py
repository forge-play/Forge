"""tests/test_escalation_runner.py: the escalation benchmark's runner and aggregator.

The runner puts the public fixtures through a backend and writes one JSON line
per call; the aggregator turns those rows into scores. These tests use a fake
backend and the built-in echo backend: no model and no network. The aggregate
math is checked against a hand-built row set whose answers are known.

Stdlib and pytest only.
"""

from __future__ import annotations

import importlib.util
import io
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "benchmarks" / "escalation"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"escalation_{name}", BENCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load("runner")
aggregate = _load("aggregate")

GOOD = json.dumps({"answer": "ESCALATE", "confidence": 0.7})


def run_rows(complete, models=("m",), shapes=runner.SHAPES, limit=2) -> list[dict]:
    buf = io.StringIO()
    runner.run_benchmark(complete, list(models), list(shapes), buf, "run-test", limit=limit)
    return [json.loads(line) for line in buf.getvalue().splitlines()]


# --- rows and the no-retry rule -----------------------------------------------


def test_row_shape_and_values():
    seen = []

    def fake(model, system, user):
        seen.append((model, system, user))
        return {"text": GOOD, "tokens_in": 11, "tokens_out": 3}

    rows = run_rows(fake, shapes=["ground"], limit=3)
    assert len(rows) == 3 == len(seen)
    for row in rows:
        assert set(row) == set(runner.ROW_KEYS)
        assert row["run_id"] == "run-test"
        assert row["model"] == "m"
        assert row["shape"] == "ground"
        assert re.fullmatch(r"[0-9a-f]{64}", row["prompt_sha256"])
        assert row["raw"] == GOOD
        assert row["parse_ok"] is True
        assert row["answer"] == "ESCALATE"
        assert row["confidence"] == 0.7
        assert row["tokens_in"] == 11 and row["tokens_out"] == 3
        assert isinstance(row["latency_ms"], int)
        assert row["error"] is None
    assert [r["fixture_id"] for r in rows] == ["ground-001", "ground-002", "ground-003"]
    model, system, user = seen[0]
    assert "ESCALATE" in system
    assert "Passage:" in user and "Question:" in user


def test_the_model_is_never_shown_the_answer_key():
    item = runner.load_fixtures("ground")[0]
    user = runner.user_prompt("ground", item)
    assert item["rationale"] not in user
    assert "expected" not in user


def test_prompt_hash_changes_with_the_prompt():
    assert runner.prompt_sha256("a", "b") != runner.prompt_sha256("a", "c")
    assert runner.prompt_sha256("a", "b") == runner.prompt_sha256("a", "b")


def test_a_raising_backend_gives_one_error_row_per_fixture_and_no_retry():
    calls = []

    def boom(model, system, user):
        calls.append(user)
        raise TimeoutError("timed out")

    rows = run_rows(boom, shapes=["route"], limit=2)
    assert len(calls) == 2, "one call per fixture: a failure is never retried"
    assert len(rows) == 2
    for row in rows:
        assert row["error"] == "TimeoutError: timed out"
        assert row["parse_ok"] is False
        assert row["raw"] is None and row["answer"] is None and row["confidence"] is None


def test_an_unparseable_reply_is_a_row_not_an_error():
    rows = run_rows(lambda m, s, u: {"text": "I think so."}, shapes=["judge"], limit=1)
    assert rows[0]["raw"] == "I think so."
    assert rows[0]["parse_ok"] is False
    assert rows[0]["error"] is None


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ('{"answer": "x", "confidence": 0.9}', "x"),
        ('```json\n{"answer": "x", "confidence": 0.9}\n```', "x"),
        ('Sure: {"answer": "x", "confidence": 0.9} done', "x"),
        ('{"answer": {"tool": "t", "args": {}}, "confidence": 0.6}', {"tool": "t", "args": {}}),
    ],
)
def test_parse_reply_accepts_json_however_it_is_wrapped(text, answer):
    assert runner.parse_reply(text)["answer"] == answer


@pytest.mark.parametrize("text", ["", "no json", '{"confidence": 0.9}', "[1, 2]", None, "{bad}"])
def test_parse_reply_rejects_everything_else(text):
    assert runner.parse_reply(text) is None


def test_confidence_must_be_a_finite_number():
    def with_conf(value):
        text = json.dumps({"answer": "a", "confidence": value})
        return run_rows(lambda m, s, u: {"text": text}, shapes=["judge"], limit=1)[0]

    assert with_conf(0.8)["confidence"] == 0.8
    assert with_conf("high")["confidence"] is None
    assert with_conf(True)["confidence"] is None
    assert with_conf(None)["confidence"] is None


def test_every_shape_has_a_prompt_that_names_the_refusal_and_the_reply_shape():
    for shape in runner.SHAPES:
        text = runner.system_prompt(shape)
        assert '"answer"' in text and '"confidence"' in text, shape
        assert "ESCALATE" in text and "0.5" in text and "0.99" in text, shape
        assert "{catalog}" not in text, shape
    route = runner.system_prompt("route")
    for tool in runner.load_catalog():
        assert tool["name"] in route


def test_load_backend_resolves_module_function_and_refuses_the_rest():
    assert runner.load_backend("json:dumps") is json.dumps
    for bad in ("json", "json:", ":dumps", "json:nope", "json:__name__"):
        with pytest.raises((ValueError, AttributeError)):
            runner.load_backend(bad)


def test_ollama_http_builds_the_documented_request(monkeypatch):
    captured = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            body = {"message": {"content": GOOD}, "prompt_eval_count": 5, "eval_count": 2}
            return json.dumps(body).encode()

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        captured["timeout"] = timeout
        return Resp()

    monkeypatch.setattr(runner.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("OLLAMA_URL", "http://ollama.invalid:1234/")
    monkeypatch.setenv("OLLAMA_TIMEOUT", "7")
    out = runner.ollama_http("some-model", "SYS", "USER")
    assert out == {"text": GOOD, "tokens_in": 5, "tokens_out": 2}
    assert captured["url"] == "http://ollama.invalid:1234/api/chat"
    assert captured["timeout"] == 7.0
    body = captured["body"]
    assert body["model"] == "some-model"
    assert body["format"] == runner.ANSWER_SCHEMA and body["stream"] is False
    assert "think" not in body
    assert body["options"] == {"temperature": 0}
    assert body["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]


# --- local models through Ollama: schema always, Qwen thinking off ---------------


def _fake_ollama(monkeypatch, content=GOOD):
    """Stand in for Ollama's /api/chat; return the list of request bodies it received."""
    bodies = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"message": {"content": content}}).encode()

    def fake_urlopen(req, timeout):
        bodies.append(json.loads(req.data))
        return Resp()

    monkeypatch.setattr(runner.urllib.request, "urlopen", fake_urlopen)
    return bodies


LOCAL_MODELS = ("gemma4:e2b", "phi4-mini", "qwen3.5")


def test_a_qwen_request_carries_both_thinking_switches(monkeypatch):
    bodies = _fake_ollama(monkeypatch)
    runner.make_ollama_http()("qwen3.5", "SYS", "USER")
    body = bodies[0]
    assert body["think"] is False
    assert body["messages"][-1]["content"].endswith("/no_think")
    assert body["messages"][-1]["content"].startswith("USER")


@pytest.mark.parametrize("model", ["gemma4:e2b", "phi4-mini"])
def test_other_local_models_get_no_thinking_switch(monkeypatch, model):
    bodies = _fake_ollama(monkeypatch)
    runner.make_ollama_http()(model, "SYS", "USER")
    assert "think" not in bodies[0]
    assert bodies[0]["messages"][-1]["content"] == "USER"


@pytest.mark.parametrize("model", LOCAL_MODELS)
def test_every_local_request_carries_the_answer_schema(monkeypatch, model):
    bodies = _fake_ollama(monkeypatch)
    runner.make_ollama_http()(model, "SYS", "USER")
    schema = bodies[0]["format"]
    assert isinstance(schema, dict) and schema["type"] == "object"
    assert schema["required"] == ["answer", "confidence"]
    assert set(schema["properties"]) == {"answer", "confidence"}


def test_the_schema_admits_every_shapes_answer_envelope():
    # An answer is a string (judge, ground, ESCALATE) or an object (route, classify).
    kinds = [alt["type"] for alt in runner.ANSWER_SCHEMA["properties"]["answer"]["anyOf"]]
    assert sorted(kinds) == ["object", "string"]
    assert runner.ANSWER_SCHEMA["properties"]["confidence"]["type"] == "number"


def test_an_unparseable_local_reply_is_a_parse_failure_row(monkeypatch):
    _fake_ollama(monkeypatch, content="Let me think about that...")
    complete = runner.make_ollama_http()
    rows = []
    for model in LOCAL_MODELS:
        item = runner.load_fixtures("judge")[0]
        rows.append(
            runner.make_row("r", model, "judge", item, "SYS", "USER", complete),
        )
    for row in rows:
        assert row["parse_ok"] is False
        assert row["raw"] == "Let me think about that..."
        assert row["answer"] is None and row["confidence"] is None and row["parsed"] is None
        assert row["error"] is None


def test_a_parse_failure_row_is_counted_by_the_aggregator_not_silently_scored(monkeypatch):
    _fake_ollama(monkeypatch, content="not json")
    item = runner.load_fixtures("ground")[0]
    row = runner.make_row("r", "qwen3.5", "ground", item, "S", "U", runner.make_ollama_http())
    cell = aggregate.aggregate([row], aggregate.load_truth())["qwen3.5"]["ground"]
    assert cell["n_unparseable"] == 1 and cell["n_correct"] == 0
    assert cell["n_calibrated"] == 0


# --- the dry run ----------------------------------------------------------------


def test_dry_run_end_to_end(tmp_path, capsys):
    out = tmp_path / "rows.jsonl"
    assert runner.main(["--dry-run", "--out", str(out), "--run-id", "dry"]) == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 200
    assert {r["model"] for r in rows} == {"dry-run"}
    assert {r["run_id"] for r in rows} == {"dry"}
    assert all(r["parse_ok"] and r["error"] is None for r in rows)
    assert len({r["fixture_id"] for r in rows}) == 200
    capsys.readouterr()
    assert aggregate.main([str(out)]) == 0
    md = capsys.readouterr().out
    assert "| dry-run | all |" in md
    # The echo backend always says ESCALATE: it is right on all 40 unanswerable items
    # and wrong on all 160 answerable ones.
    result = aggregate.aggregate(rows, aggregate.load_truth())["dry-run"]["all"]
    assert result["task_score"] == 0.0
    assert result["false_confidence_rate"] == 0.0
    assert result["over_escalation_rate"] == 1.0
    assert result["unparseable_rate"] == 0.0


def test_dry_run_honours_models_shapes_and_limit(tmp_path):
    out = tmp_path / "rows.jsonl"
    argv = ["--dry-run", "--models", "a,b", "--shapes", "judge,route", "--limit", "3"]
    assert runner.main([*argv, "--out", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 * 2 * 3
    assert {(r["model"], r["shape"]) for r in rows} == {
        (m, s) for m in "ab" for s in ("judge", "route")
    }


def test_the_runner_refuses_bad_arguments(tmp_path):
    with pytest.raises(SystemExit):
        runner.main(["--out", str(tmp_path / "x.jsonl")])  # no --models, no --dry-run
    with pytest.raises(SystemExit):
        runner.main(["--dry-run", "--shapes", "poetry", "--out", str(tmp_path / "x.jsonl")])
    with pytest.raises(SystemExit):
        runner.main(["--models", "m", "--backend", "nonsense", "--out", str(tmp_path / "x")])


def test_the_runner_and_aggregator_run_as_scripts(tmp_path):
    rows = tmp_path / "rows.jsonl"
    cmd = [sys.executable, "-B", str(BENCH / "runner.py"), "--dry-run", "--limit", "2"]
    done = subprocess.run([*cmd, "--out", str(rows)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    agg = [sys.executable, "-B", str(BENCH / "aggregate.py"), str(rows), "--format", "json"]
    done = subprocess.run(agg, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["dry-run"]["all"]["n_rows"] == 8


# --- aggregate math on a hand-built row set -------------------------------------


def _truth():
    def t(expected, answerable):
        return {"shape": "ground", "expected": expected, "answerable": answerable}

    return {
        "g1": t("31 metres", True),
        "g2": t("Tuesdays", True),
        "g3": t("blue", True),
        "g4": t("ESCALATE", False),
        "g5": t("ESCALATE", False),
        "g6": t("red", True),
        "g7": t("green", True),
        "g8": t("ESCALATE", False),
    }


def _row(fid, answer, conf, *, ok=True, error=None):
    return {
        "model": "m",
        "shape": "ground",
        "fixture_id": fid,
        "parse_ok": ok,
        "answer": answer,
        "confidence": conf,
        "error": error,
    }


def _rows():
    return [
        _row("g1", "31 Metres.", 0.9),  # right (normalized match)
        _row("g2", "Mondays", 0.8),  # wrong answer
        _row("g3", "ESCALATE", 0.6),  # over-escalation
        _row("g4", "a made-up answer", 0.9),  # false confidence
        _row("g5", "ESCALATE", 0.7),  # right refusal
        _row("g6", None, None, ok=False),  # unparseable, answerable
        _row("g7", None, None, ok=False, error="TimeoutError: t"),  # error: left out
        _row("g8", None, None, ok=False),  # unparseable, unanswerable
    ]


def _cell():
    return aggregate.aggregate(_rows(), _truth())["m"]["ground"]


def test_task_score():
    cell = _cell()
    # Answerable rows without an error: g1, g2, g3, g6. One is right.
    assert cell["n_answerable"] == 4 and cell["n_correct"] == 1
    assert cell["task_score"] == 0.25


def test_false_confidence_rate_leaves_unparseable_out():
    cell = _cell()
    # Unanswerable parsed rows: g4 (an answer) and g5 (ESCALATE). g8 is unparseable.
    assert cell["n_unanswerable_parsed"] == 2 and cell["n_false_confident"] == 1
    assert cell["false_confidence_rate"] == 0.5


def test_over_escalation_rate_leaves_unparseable_out():
    cell = _cell()
    # Answerable parsed rows: g1, g2, g3. One is ESCALATE. g6 is unparseable.
    assert cell["n_answerable_parsed"] == 3 and cell["n_escalated"] == 1
    assert cell["over_escalation_rate"] == pytest.approx(1 / 3)


def test_unparseable_rate_is_separate_and_excludes_errors():
    cell = _cell()
    assert cell["n_unparseable"] == 2 and cell["n_errors"] == 1
    assert cell["unparseable_rate"] == pytest.approx(2 / 7)


def test_brier_and_reliability_bins():
    cell = _cell()
    # (confidence, right): g1 (0.9, T) g2 (0.8, F) g3 (0.6, F) g4 (0.9, F) g5 (0.7, T)
    expected = (0.1**2 + 0.8**2 + 0.6**2 + 0.9**2 + 0.3**2) / 5
    assert cell["n_calibrated"] == 5
    assert cell["brier"] == pytest.approx(expected)
    assert math.isclose(cell["brier"], 0.382)
    bins = {(b["lo"], b["hi"]): b for b in cell["reliability"]}
    assert len(bins) == 5
    assert bins[(0.5, 0.6)]["n"] == 0 and bins[(0.5, 0.6)]["hit_rate"] is None
    assert bins[(0.6, 0.7)]["n"] == 1 and bins[(0.6, 0.7)]["hit_rate"] == 0.0
    assert bins[(0.7, 0.8)]["n"] == 1 and bins[(0.7, 0.8)]["hit_rate"] == 1.0
    assert bins[(0.8, 0.9)]["n"] == 1 and bins[(0.8, 0.9)]["hit_rate"] == 0.0
    assert bins[(0.9, 1.0)]["n"] == 2 and bins[(0.9, 1.0)]["hit_rate"] == 0.5


def test_confidence_is_clamped_and_missing_confidence_is_left_out():
    truth = _truth()
    rows = [_row("g1", "31 metres", 1.0), _row("g2", "Tuesdays", None), _row("g3", "blue", 0.1)]
    cell = aggregate.aggregate(rows, truth)["m"]["ground"]
    assert cell["n_calibrated"] == 2
    # 1.0 clamps to 0.99 (right), 0.1 clamps to 0.5 (right).
    assert cell["brier"] == pytest.approx((0.01**2 + 0.5**2) / 2)


def test_the_all_line_pools_shapes_and_models_stay_apart():
    truth = _truth()
    truth["r1"] = {"shape": "route", "expected": {"tool": "t", "args": {}}, "answerable": True}
    rows = _rows() + [
        {**_row("r1", {"tool": "t", "args": {}}, 0.9), "shape": "route"},
        {**_row("g1", "31 metres", 0.9), "model": "other"},
    ]
    result = aggregate.aggregate(rows, truth)
    assert list(result) == ["m", "other"]
    assert set(result["m"]) == {"ground", "route", "all"}
    assert result["m"]["route"]["task_score"] == 1.0
    assert result["m"]["all"]["n_rows"] == 9
    assert result["other"]["all"]["task_score"] == 1.0


def test_unknown_fixture_ids_are_counted_not_scored():
    rows = [_row("nope", "x", 0.9), _row("g1", "31 metres", 0.9)]
    cell = aggregate.aggregate(rows, _truth())["m"]["ground"]
    assert cell["n_unknown_fixture"] == 1 and cell["n_rows"] == 1


def test_a_model_with_no_unanswerable_rows_has_no_false_confidence_rate():
    cell = aggregate.aggregate([_row("g1", "31 metres", 0.9)], _truth())["m"]["ground"]
    assert cell["false_confidence_rate"] is None


def test_shape_equality_rules():
    m = aggregate.answers_match
    tool = {"tool": "convert_units", "args": {"value": 26.2, "from_unit": "miles"}}
    assert m("route", tool, tool)
    assert m(
        "route", {"tool": "convert_units", "args": {"from_unit": "miles", "value": 26.2}}, tool
    )
    assert not m("route", {**tool, "args": {"value": 26.2}}, tool)
    assert not m("route", {**tool, "args": {**tool["args"], "extra": 1}}, tool)
    assert not m("route", {"tool": "other", "args": tool["args"]}, tool)
    assert not m("route", "convert_units", tool)
    cls = {"status": "blocked", "severity": "high", "needs_human": True}
    assert m("classify", dict(cls), cls)
    assert not m("classify", {**cls, "needs_human": "true"}, cls)
    assert not m("classify", {**cls, "needs_human": 1}, cls)
    assert not m("classify", {**cls, "severity": "low"}, cls)
    assert not m("classify", {"status": "blocked", "severity": "high"}, cls)
    assert m("judge", "SUPPORTS", "SUPPORTS")
    assert not m("judge", "supports", "SUPPORTS")
    assert m("ground", "  The Blue door. ", "the blue door")
    assert not m("ground", "the blue", "the blue door")
    assert not m("ground", 31, "31")


def test_escalate_on_an_answerable_item_is_never_correct():
    truth = {"shape": "ground", "expected": "ESCALATE", "answerable": True}
    assert aggregate.is_correct("ground", "ESCALATE", truth) is False


def test_the_reader_needs_only_rows_and_fixtures(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in _rows()) + "\n\n", encoding="utf-8")
    assert aggregate.read_rows([path]) == _rows()


# --- output ---------------------------------------------------------------------


def test_markdown_output_renders_a_table():
    md = aggregate.to_markdown(aggregate.aggregate(_rows(), _truth()))
    lines = md.splitlines()
    header, rule, first = lines[0], lines[1], lines[2]
    assert header.startswith("| Model | Shape | Task score | False-confidence |")
    assert set(rule) <= {"|", "-"}
    assert header.count("|") == rule.count("|") == first.count("|")
    assert "| m | ground | 25.0% (1/4) | 50.0% (1/2) | 33.3% (1/3) | 28.6% (2) | 1 | 0.382 |" in md
    assert "| m | all |" in md
    assert "| m | 0.9-1.0 | 2 | 0.900 | 50.0% |" in md
    assert "Brier = mean((confidence - outcome) ** 2)" in md


def test_markdown_shows_a_dash_where_a_rate_has_no_denominator():
    md = aggregate.to_markdown(aggregate.aggregate([_row("g1", "31 metres", 0.9)], _truth()))
    assert "| m | ground | 100.0% (1/1) | - (0/0) |" in md


def test_json_output_round_trips():
    result = aggregate.aggregate(_rows(), _truth())
    assert json.loads(aggregate.to_json(result)) == json.loads(json.dumps(result))


# --- intervals, McNemar and bootstrap Spearman -----------------------------------


def test_wilson_interval_matches_textbook_values():
    w = aggregate.wilson_interval
    # 8/40: centre 0.2263, half-width 0.1213 (hand computed, z = 1.96).
    ci = w(8, 40)
    assert ci["lo"] == pytest.approx(0.1050, abs=5e-4)
    assert ci["hi"] == pytest.approx(0.3476, abs=5e-4)
    # Newcombe (1998) worked example, 81/263.
    ci = w(81, 263)
    assert ci["lo"] == pytest.approx(0.2553, abs=5e-4)
    assert ci["hi"] == pytest.approx(0.3662, abs=5e-4)
    # The edges stay inside [0, 1]; 0/10 has a Wilson upper bound of 0.2775.
    assert w(0, 10)["lo"] == 0.0
    assert w(0, 10)["hi"] == pytest.approx(0.2775, abs=5e-4)
    assert w(10, 10)["hi"] == 1.0
    assert w(0, 0) is None


def test_every_rate_carries_its_own_interval_in_the_cell_and_the_table():
    cell = _cell()
    assert cell["task_score_ci"] == aggregate.wilson_interval(1, 4)
    assert cell["false_confidence_ci"] == aggregate.wilson_interval(1, 2)
    assert cell["over_escalation_ci"] == aggregate.wilson_interval(1, 3)
    assert cell["unparseable_ci"] == aggregate.wilson_interval(2, 7)
    md = aggregate.to_markdown(aggregate.aggregate(_rows(), _truth()))
    assert md.splitlines()[0].count("|") == md.splitlines()[2].count("|")
    lo, hi = cell["task_score_ci"]["lo"], cell["task_score_ci"]["hi"]
    assert f"[{lo * 100:.1f}%, {hi * 100:.1f}%]" in md
    empty = aggregate.aggregate([_row("g1", "31 metres", 0.9)], _truth())["m"]["ground"]
    assert empty["false_confidence_ci"] is None


def _pair_truth():
    return {
        f"u{i}": {"shape": "ground", "expected": "ESCALATE", "answerable": False}
        for i in range(1, 13)
    }


def _pair_rows():
    def row(model, fid, answer):
        return {
            "model": model,
            "shape": "ground",
            "fixture_id": fid,
            "parse_ok": True,
            "answer": answer,
            "confidence": 0.9,
            "error": None,
        }

    rows = []
    for i in range(1, 13):
        fid = f"u{i}"
        a = "ESCALATE" if i != 6 else "made up"  # A is confident only on u6
        b = "made up" if i <= 5 else "ESCALATE"  # B is confident on u1-u5
        rows += [row("A", fid, a), row("B", fid, b)]
    return rows


def test_mcnemar_exact_matches_hand_computed_b_and_c():
    # b = 5 (A refused, B did not), c = 1; 6 discordant: p = 2 * (1 + 6) / 64.
    out = aggregate.pair_test(_pair_rows(), _pair_truth(), "A", "B")
    assert (out["b"], out["c"], out["n_shared"], out["n_discordant"]) == (5, 1, 12, 6)
    assert out["p_value"] == pytest.approx(14 / 64)
    # b = 8, c = 2: p = 2 * (1 + 10 + 45) / 1024.
    assert aggregate.mcnemar_exact(8, 2) == pytest.approx(112 / 1024)
    assert aggregate.mcnemar_exact(0, 0) == 1.0
    assert aggregate.mcnemar_exact(3, 3) == 1.0


def test_mcnemar_uses_only_shared_parsed_items():
    drop = {"u1", "u2"}
    rows = [r for r in _pair_rows() if not (r["model"] == "B" and r["fixture_id"] in drop)]
    rows.append({**rows[0], "model": "B", "fixture_id": "u2", "parse_ok": False, "answer": None})
    out = aggregate.pair_test(rows, _pair_truth(), "A", "B")
    assert out["n_shared"] == 10  # u1 has no B row; u2's B reply is unparseable


def test_spearman_known_values():
    assert aggregate.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert aggregate.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    # Ties take average ranks: ranks [1, 2, 3] against [1.5, 1.5, 3] give 1.5 / sqrt(3).
    assert aggregate.spearman([1, 2, 3], [1, 1, 2]) == pytest.approx(3**0.5 / 2)
    assert aggregate.spearman([1, 2, 3], [5, 5, 5]) is None
    assert aggregate.spearman([1, 2], [1, 2]) is None


def test_bootstrap_spearman_is_reproducible_under_a_seed():
    xs = [0.1, 0.3, 0.35, 0.5, 0.6, 0.8, 0.9]
    ys = [0.9, 0.7, 0.8, 0.5, 0.4, 0.45, 0.1]
    a = aggregate.bootstrap_spearman(xs, ys, 500, seed=7)
    assert a == aggregate.bootstrap_spearman(xs, ys, 500, seed=7)
    assert a != aggregate.bootstrap_spearman(xs, ys, 500, seed=8)
    assert -1.0 <= a["ci"]["lo"] <= a["ci"]["hi"] <= 1.0
    assert a["rho"] == pytest.approx(aggregate.spearman(xs, ys))
    # The default seed is fixed, so two default calls agree.
    assert aggregate.bootstrap_spearman(xs, ys, 200) == aggregate.bootstrap_spearman(xs, ys, 200)
    # A perfectly monotone set has a degenerate interval at 1.
    mono = aggregate.bootstrap_spearman([1, 2, 3, 4, 5, 6], [2, 4, 6, 8, 10, 12], 300)
    assert mono["ci"] == {"lo": 1.0, "hi": 1.0}


def test_cli_pair_and_rank_are_additive(tmp_path, capsys):
    rows = tmp_path / "rows.jsonl"
    rows.write_text("\n".join(json.dumps(r) for r in _pair_rows()) + "\n", encoding="utf-8")
    fx = tmp_path / "fx"
    fx.mkdir()
    for shape in aggregate.SHAPES:
        lines = []
        if shape == "ground":
            for fid, t in _pair_truth().items():
                lines.append(json.dumps({"id": fid, **t}))
        (fx / f"{shape}.jsonl").write_text("\n".join(lines), encoding="utf-8")
    base = [str(rows), "--fixtures", str(fx), "--format", "json"]
    assert aggregate.main(base) == 0
    plain = json.loads(capsys.readouterr().out)
    assert "_stats" not in plain
    assert aggregate.main([*base, "--pair", "A", "B", "--rank", "--seed", "3"]) == 0
    out = json.loads(capsys.readouterr().out)
    stats = out.pop("_stats")
    assert out == plain
    assert stats["pair"]["b"] == 5 and stats["pair"]["c"] == 1
    assert stats["rank"]["seed"] == 3 and stats["rank"]["n_resamples"] == 10_000
    assert aggregate.main([str(rows), "--fixtures", str(fx), "--pair", "A", "B"]) == 0
    assert "McNemar" in capsys.readouterr().out
