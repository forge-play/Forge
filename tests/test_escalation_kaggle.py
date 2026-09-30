"""tests/test_escalation_kaggle.py: prompt export, task files, row converter, dataset gate.

Everything here is offline. The hosted SDK is never imported: the task files are read as
text and parsed, and the converter reads a small hand-built tree in the layout
``kaggle b t download`` writes (``tests/data/escalation_kaggle_download``; the run-file
shape was taken from a real kaggle-benchmarks 0.6.1 run against a scripted model).

Stdlib and pytest only.
"""

from __future__ import annotations

import ast
import gzip
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmarks" / "escalation"
TREE = Path(__file__).resolve().parent / "data" / "escalation_kaggle_download"
SHAPES = ("route", "classify", "judge", "ground")
SENTINEL = "zephyrquill"  # an invented deny-list term that appears nowhere in the data


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"escalation_{name}", BENCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


export = _load("kaggle_export")
rows_mod = _load("kaggle_rows")
stage = _load("kaggle_stage")
runner = export.runner
aggregate = _load("aggregate")


# --- export parity ---------------------------------------------------------------


@pytest.mark.parametrize("shape", SHAPES)
def test_export_messages_equal_the_runner_payload_for_every_item(shape):
    lines = export.export_shape(shape)
    items = runner.load_fixtures(shape)
    assert [line["id"] for line in lines] == [item["id"] for item in items]
    system = runner.system_prompt(shape)
    for line, item in zip(lines, items):
        payload = runner.build_chat_payload(
            "some-other-model", system, runner.user_prompt(shape, item)
        )
        assert line["messages"] == payload["messages"]
        assert line["schema"] == payload["format"] == runner.ANSWER_SCHEMA
        assert line["shape"] == shape


def test_export_carries_no_answer_key():
    for shape in SHAPES:
        for line in export.export_shape(shape):
            assert sorted(line) == ["id", "messages", "schema", "shape"]
            assert not {"expected", "answerable", "rationale"} & set(line)
    # the only place the runner differs by model is Qwen's suffix, which is not exported
    item = runner.load_fixtures("route")[0]
    user = runner.user_prompt("route", item)
    qwen = runner.build_chat_payload("qwen3", runner.system_prompt("route"), user)
    assert qwen["messages"][1]["content"] == user + "\n" + runner.NO_THINK_SUFFIX
    assert export.export_item("route", item, runner.system_prompt("route"))["messages"][1] == {
        "role": "user",
        "content": user,
    }


def test_export_refuses_a_directory_inside_a_git_tree():
    with pytest.raises(ValueError, match="outside every git tree"):
        export.write_export(ROOT / "staging-should-never-exist")
    assert not (ROOT / "staging-should-never-exist").exists()


def test_export_writes_one_line_per_fixture(tmp_path):
    counts = export.write_export(tmp_path / "out")
    assert counts == {"route": 60, "classify": 50, "judge": 50, "ground": 40}
    for shape, n in counts.items():
        lines = (tmp_path / "out" / f"{shape}.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == n


# --- task files ------------------------------------------------------------------

TASK_DIR = BENCH / "kaggle"


def _task_text(shape: str) -> str:
    return (TASK_DIR / f"{shape}_task.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("shape", SHAPES)
def test_task_file_follows_the_kaggle_benchmarks_conventions(shape):
    text = _task_text(shape)
    tree = ast.parse(text)
    assert "# %%" in text
    assert "__main__" not in text
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            assert node.returns is not None, f"{node.name} has no return annotation"
    last = tree.body[-1]
    assert ast.unparse(last) == f"escalation_{shape}.run(kbench.llm)"
    names = re.findall(r'name="([^"]+)"', text)
    assert names == [f"escalation-{shape}-item", f"escalation-{shape}"]
    assert all(re.fullmatch(r"[a-z0-9-]+", n) for n in names)  # slugifies to itself
    assert "store_task=False" in text
    assert 'on_failure="continue"' in text
    assert f'SHAPE = "{shape}"' in text


def test_the_four_task_files_differ_only_by_shape():
    bodies = {}
    for shape in SHAPES:
        text = _task_text(shape)
        body = text[text.index("# %%\nimport json") :]
        bodies[shape] = body.replace(shape, "SHAPE_WORD")
    assert len({*bodies.values()}) == 1


# --- converter -------------------------------------------------------------------


def _convert(tree=TREE, **kw):
    return rows_mod.convert(tree, "run-hosted", **kw)


def test_converter_writes_one_runner_format_row_per_fixture_item():
    rows = _convert()
    assert len(rows) == 60
    assert [r["fixture_id"] for r in rows] == [i["id"] for i in runner.load_fixtures("route")]
    assert all(set(r) == set(runner.ROW_KEYS) for r in rows)
    assert {r["run_id"] for r in rows} == {"run-hosted"}
    assert {r["model"] for r in rows} == {"google/model-x"}
    by_id = {r["fixture_id"]: r for r in rows}
    ok = by_id["route-001"]
    assert ok["parse_ok"] is True and ok["confidence"] == 0.9
    assert ok["answer"]["tool"] == "calendar_add_event"
    assert (ok["tokens_in"], ok["tokens_out"], ok["latency_ms"]) == (812, 41, 1500)
    assert ok["done_reason"] is None and ok["error"] is None
    system = runner.system_prompt("route")
    user = runner.user_prompt("route", runner.load_fixtures("route")[0])
    assert ok["prompt_sha256"] == runner.prompt_sha256(system, user)


def test_converter_records_errors_and_missing_items_as_error_rows():
    by_id = {r["fixture_id"]: r for r in _convert()}
    boom = by_id["route-002"]
    assert boom["error"] == "RuntimeError: boom"
    assert boom["raw"] is None and boom["answer"] is None and boom["parse_ok"] is False
    unparsed = by_id["route-003"]
    assert unparsed["error"] is None and unparsed["parse_ok"] is False
    assert unparsed["raw"] == "I think it is about 42 kilometres."
    missing = by_id["route-005"]
    assert missing["error"] == rows_mod.MISSING and missing["raw"] is None


def test_converter_model_name_can_come_from_the_directory():
    assert {r["model"] for r in _convert(model_from="dir")} == {"model-x"}


def test_converter_rows_score_like_runner_rows():
    """The same replies, scored through aggregate.py, whether the row came from a hosted
    run file or from runner.make_row."""
    hosted = aggregate.aggregate(_convert(), aggregate.load_truth())["google/model-x"]["route"]
    system = runner.system_prompt("route")
    replies = {
        "route-001": {
            "text": json.dumps(
                {
                    "answer": {
                        "tool": "calendar_add_event",
                        "args": {
                            "title": "Dentist appointment",
                            "date": "2027-03-14",
                            "time": "09:30",
                        },
                    },
                    "confidence": 0.9,
                }
            )
        },
        "route-003": {"text": "I think it is about 42 kilometres."},
        "route-004": {"text": json.dumps({"answer": "ESCALATE", "confidence": 0.7})},
    }
    local = []
    for item in runner.load_fixtures("route"):
        user = runner.user_prompt("route", item)
        reply = replies.get(item["id"])
        if reply is None:
            local.append(
                runner.make_row(
                    "r",
                    "google/model-x",
                    "route",
                    item,
                    system,
                    user,
                    lambda *_: (_ for _ in ()).throw(RuntimeError("x")),
                )
            )
        else:
            local.append(
                runner.make_row(
                    "r",
                    "google/model-x",
                    "route",
                    item,
                    system,
                    user,
                    lambda *_, reply=reply: reply,
                )
            )
    expected = aggregate.aggregate(local, aggregate.load_truth())["google/model-x"]["route"]
    for key in (
        "n_rows",
        "n_answerable",
        "n_correct",
        "n_unparseable",
        "n_unanswerable_parsed",
        "n_false_confident",
        "task_score",
        "false_confidence_rate",
        "brier",
    ):
        assert hosted[key] == expected[key], key
    assert hosted["n_rows"] == 60 and hosted["n_errors"] == 57
    assert (hosted["n_answerable"], hosted["n_correct"], hosted["n_unparseable"]) == (2, 1, 1)
    assert (hosted["n_unanswerable_parsed"], hosted["n_false_confident"]) == (1, 0)


def test_converter_output_reads_through_aggregate_cli(tmp_path, capsys):
    out = tmp_path / "rows.jsonl"
    assert rows_mod.main([str(TREE), "--run-id", "run-hosted", "--out", str(out)]) == 0
    assert aggregate.main([str(out), "--format", "json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["google/model-x"]["all"]["n_rows"] == 60


def test_converter_takes_the_newest_run_per_model(tmp_path):
    tree = tmp_path / "tree"
    shutil.copytree(TREE, tree)
    older = tree / "escalation-route" / "3" / "model-x" / "111"
    newer = older.parent / "222"
    shutil.copytree(older, newer)
    for path in newer.glob("*.run.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["endTime"] = "2026-10-02T10:00:00.000000Z"
        for run in rows_mod.iter_runs(data):
            found = rows_mod.item_result(run)
            if found and found["item_id"] == "route-003":
                found["text"] = json.dumps({"answer": "ESCALATE", "confidence": 0.6})
        path.write_text(json.dumps(data), encoding="utf-8")
    by_id = {r["fixture_id"]: r for r in _convert(tree)}
    assert by_id["route-003"]["answer"] == "ESCALATE"


def test_converter_ignores_trees_with_no_run_files(tmp_path):
    assert _convert(tmp_path) == []
    assert rows_mod.main([str(tmp_path), "--run-id", "r"]) == 1


# --- dataset gate ----------------------------------------------------------------


@pytest.fixture
def denylist(tmp_path):
    path = tmp_path / "deny" / "names.txt"
    path.parent.mkdir()
    path.write_text(f"# operator names, never committed\n{SENTINEL}\n", encoding="utf-8")
    return path


@pytest.fixture
def bench_copy(tmp_path):
    """A scratch copy of the benchmark tree that a test may plant a leak in."""
    dest = tmp_path / "bench"
    shutil.copytree(BENCH, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def _plant(bench: Path, shape: str, text: str) -> None:
    """Append ``text`` to the first route request (its input is a plain string)."""
    path = bench / "fixtures" / f"{shape}.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["input"] = f"{first['input']} {text}"
    lines[0] = json.dumps(first)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _staged(tmp_path, denylist):
    out = tmp_path / "staging"
    code, lines = stage.stage(out, "owner/escalation-benchmark", denylist)
    assert code == 0, lines
    return out


def test_stage_builds_the_dataset_and_passes_every_gate(tmp_path, denylist):
    out = _staged(tmp_path, denylist)
    files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    assert files == sorted(stage.EXPECTED_FILES)
    meta = json.loads((out / "dataset-metadata.json").read_text(encoding="utf-8"))
    assert meta["id"] == "owner/escalation-benchmark" and meta["licenses"]
    assert (out / "catalog" / "tools.json").read_bytes() == (
        BENCH / "catalog" / "tools.json"
    ).read_bytes()


@pytest.mark.parametrize(
    "leak, cls",
    [
        ("mail me at jo@example.org", "email"),
        ("see file" + ":" + "//share/notes.txt", "file-uri"),
        ("ticket a1b2c3d4 was closed", "store-id"),
        ("ref 9F3A61C2 done", "store-id"),
        (f"ask {SENTINEL}", "denylist"),
        (f"ask {SENTINEL[:-3]}іll", "denylist-lookalike"),
        ("pаssword reset", "lookalike-script"),
    ],
)
def test_stage_refuses_each_planted_leak_and_deletes_the_staging(
    tmp_path, denylist, bench_copy, leak, cls
):
    _plant(bench_copy, "route", leak)
    out = tmp_path / "staging"
    code, lines = stage.stage(out, "owner/escalation-benchmark", denylist, bench_copy)
    assert code == 1
    assert any(line.startswith(f"FAIL {cls} ") for line in lines), lines
    assert not out.exists()
    joined = "\n".join(lines)
    for secret in ("jo@example", "a1b2c3d4", "9F3A61C2", SENTINEL, "notes.txt"):
        assert secret not in joined  # a failure names a class and a place, never the text


def test_stage_refuses_a_count_mismatch_and_a_stray_file(tmp_path, denylist):
    out = _staged(tmp_path, denylist)
    judge = out / "judge.jsonl"
    judge.write_text(
        "".join(judge.read_text(encoding="utf-8").splitlines(True)[:-1]), encoding="utf-8"
    )
    (out / "notes.txt").write_text("hello\n", encoding="utf-8")
    code, lines = stage.run_gates(out, denylist)
    assert code == 1
    assert "FAIL line-count-mismatch judge.jsonl" in lines
    assert "FAIL unexpected-file notes.txt" in lines


def test_stage_refuses_a_missing_file_and_a_changed_catalogue(tmp_path, denylist):
    out = _staged(tmp_path, denylist)
    (out / "README.md").unlink()
    (out / "catalog" / "tools.json").write_text('{"tools": []}\n', encoding="utf-8")
    _, lines = stage.run_gates(out, denylist)
    assert "FAIL missing-file README.md" in lines
    assert "FAIL catalog-sha-mismatch catalog/tools.json" in lines


def test_stage_refuses_an_answer_key_in_a_prompt_line(tmp_path, denylist):
    out = _staged(tmp_path, denylist)
    path = out / "ground.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    leaked = json.loads(lines[0])
    leaked["expected"] = "x"
    lines[0] = json.dumps(leaked)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _, found = stage.run_gates(out, denylist)
    assert "FAIL answer-key ground.jsonl:1" in found
    assert "FAIL export-keys ground.jsonl:1" in found


def test_stage_refuses_a_compressed_payload_under_any_name(tmp_path, denylist):
    out = _staged(tmp_path, denylist)
    (out / "README.md").write_bytes(gzip.compress(b"readme"))
    _, lines = stage.run_gates(out, denylist)
    assert "FAIL compressed-payload README.md" in lines


def test_stage_usage_errors(tmp_path, denylist):
    ok_id = "owner/slug"
    assert stage.stage(tmp_path / "a", "no-slash", denylist)[0] == 2
    assert stage.stage(tmp_path / "a", ok_id, tmp_path / "missing.txt")[0] == 2
    empty = tmp_path / "empty.txt"
    empty.write_text("# nothing\n", encoding="utf-8")
    assert stage.stage(tmp_path / "a", ok_id, empty)[0] == 2
    assert stage.stage(ROOT / "staging-should-never-exist", ok_id, denylist)[0] == 2
    assert stage.stage(tmp_path / "a", ok_id, BENCH / "README.md")[0] == 2  # deny-list in git
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "x").write_text("x", encoding="utf-8")
    assert stage.stage(busy, ok_id, denylist)[0] == 2
    assert not (ROOT / "staging-should-never-exist").exists()
