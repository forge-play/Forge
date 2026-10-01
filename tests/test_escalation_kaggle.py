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


# --- hosted parity: schema, output cap, done_reason -------------------------------------


class _Namespace:
    """What the stubbed SDK records while a task file runs against it."""

    def __init__(self):
        self.results: list[dict] = []
        self.llm = None


def _install_sdk_stub(monkeypatch, llm_class_name="OpenAI"):
    """Stand-ins for kaggle_benchmarks, pandas and pydantic, enough to run a task file."""
    ns = _Namespace()

    class BaseModel:
        model_fields: dict = {}

        def __init_subclass__(cls, **kw):
            cls.model_fields = dict(getattr(cls, "__annotations__", {}))

        def __init__(self, **kw):
            self.__dict__.update(kw)

        def model_dump(self):
            return dict(self.__dict__)

    class ResponseParsingError(ValueError):
        def __init__(self, value):
            super().__init__("Failed to parse model response.")
            self.value = value

    class NonRecoverableError(Exception):
        pass

    class _Run:
        def __init__(self, result):
            self.result = result

    class _Runs(list):
        errored_runs: list = []

        @property
        def completed_runs(self):
            return list(self)

    class _Task:
        def __init__(self, fn):
            self.fn = fn

        def evaluate(self, llm, evaluation_data, on_failure):
            runs = _Runs()
            for row in evaluation_data:
                result = self.fn(llm[0], **row)
                ns.results.append(result)
                runs.append(_Run(result))
            return runs

        def run(self, llm):
            return self.fn(llm)

    def task(name=None, **kw):
        return _Task

    class _Reply:
        def __init__(self, content, meta):
            self.content, self._meta = content, meta

    def _llm_class():
        def respond(self, system=None, schema=str, **kwargs):
            self.calls.append({"system": system, "schema": schema, **kwargs})
            return self.script(self, schema)

        return type(
            llm_class_name,
            (),
            {"respond": respond, "__init__": lambda self: setattr(self, "calls", [])},
        )

    llm = _llm_class()()

    def script(self, schema):
        content = json.dumps({"answer": "ESCALATE", "confidence": 0.5})
        if schema is not str:
            content = schema(answer="ESCALATE", confidence=0.5)
        return _Reply(
            content,
            {"input_tokens": 7, "output_tokens": 3, "raw_content": '{"answer": "ESCALATE"}'},
        )

    llm.script = script
    ns.llm = llm
    sdk = type(sys)("kaggle_benchmarks")
    sdk.task, sdk.llm = task, llm
    sdk.user = type("user", (), {"send": staticmethod(lambda *_: None)})
    sdk.tasks = type("tasks", (), {"NonRecoverableError": NonRecoverableError})
    prompting = type(sys)("kaggle_benchmarks.prompting")
    prompting.ResponseParsingError = ResponseParsingError
    pandas = type(sys)("pandas")
    pandas.DataFrame = list
    pydantic = type(sys)("pydantic")
    pydantic.BaseModel = BaseModel
    for name, module in (
        ("kaggle_benchmarks", sdk),
        ("kaggle_benchmarks.prompting", prompting),
        ("pandas", pandas),
        ("pydantic", pydantic),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    ns.ResponseParsingError = ResponseParsingError
    return ns


def _run_task(shape, monkeypatch, tmp_path, *, env=None, llm_class_name="OpenAI", script=None):
    ns = _install_sdk_stub(monkeypatch, llm_class_name)
    if script is not None:  # script(ns, schema) -> a reply, or raises
        ns.llm.script = lambda self, schema: script(ns, schema)
    data = tmp_path / "data"
    if not data.exists():
        export.write_export(data)
    monkeypatch.setenv("ESCALATION_DATA_DIR", str(data))
    monkeypatch.setenv("ESCALATION_LIMIT", "2")
    for key in ("ESCALATION_SCHEMA", "ESCALATION_CAP_PARAM"):
        monkeypatch.delenv(key, raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location(f"task_{shape}", TASK_DIR / f"{shape}_task.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, ns


@pytest.mark.parametrize("shape", SHAPES)
def test_the_schema_reaches_respond_for_every_shape(shape, monkeypatch, tmp_path):
    module, ns = _run_task(shape, monkeypatch, tmp_path)
    assert len(ns.llm.calls) == 2
    exported = export.export_shape(shape)[0]["schema"]
    assert (
        set(module.Answer.model_fields) == set(exported["properties"]) == {"answer", "confidence"}
    )
    for call in ns.llm.calls:
        assert call["schema"] is module.Answer
        assert call["seed"] == 0 and call["temperature"] == 0
    assert {r["schema"] for r in ns.results} == {"answer"}


def test_the_schema_can_be_switched_off_and_the_row_says_so(monkeypatch, tmp_path):
    _, ns = _run_task("route", monkeypatch, tmp_path, env={"ESCALATION_SCHEMA": "none"})
    assert all(call["schema"] is str for call in ns.llm.calls)  # respond's default: no schema
    assert {r["schema"] for r in ns.results} == {"none"}
    assert all(json.loads(r["text"])["answer"] == "ESCALATE" for r in ns.results)


@pytest.mark.parametrize("shape", SHAPES)
def test_the_output_cap_is_sent(shape, monkeypatch, tmp_path):
    module, ns = _run_task(shape, monkeypatch, tmp_path)
    assert module.MAX_OUTPUT_TOKENS == runner.MAX_OUTPUT_TOKENS == 512
    assert all(call["max_tokens"] == 512 for call in ns.llm.calls)
    assert all("max_output_tokens" not in call for call in ns.llm.calls)
    assert {json.dumps(r["cap"]) for r in ns.results} == {'{"max_tokens": 512}'}


def test_the_cap_parameter_follows_the_provider(monkeypatch, tmp_path):
    _, ns = _run_task("route", monkeypatch, tmp_path, llm_class_name="GoogleGenAI")
    assert all(
        call["max_output_tokens"] == 512 and "max_tokens" not in call for call in ns.llm.calls
    )
    _, ns = _run_task(
        "route", monkeypatch, tmp_path, env={"ESCALATION_CAP_PARAM": "max_completion_tokens"}
    )
    assert all(call["max_completion_tokens"] == 512 for call in ns.llm.calls)
    _, ns = _run_task("route", monkeypatch, tmp_path, env={"ESCALATION_CAP_PARAM": "none"})
    assert all(not {"max_tokens", "max_output_tokens"} & set(call) for call in ns.llm.calls)
    assert {r["cap"] for r in ns.results} == {None}


def test_a_parsed_reply_round_trips_through_rows_and_aggregate(monkeypatch, tmp_path):
    """The SDK hands back a parsed Answer; the recorded text is JSON the aggregator parses."""

    def script(ns, schema):
        reply = type("Reply", (), {})()
        reply.content = schema(
            answer={"tool": "calendar_add_event", "args": {"title": "x"}}, confidence=0.9
        )
        reply._meta = {"input_tokens": 5, "output_tokens": 9, "raw_content": "```json\n{}\n```"}
        return reply

    _, ns = _run_task("route", monkeypatch, tmp_path, script=script)
    first = ns.results[0]
    assert json.loads(first["text"]) == {
        "answer": {"tool": "calendar_add_event", "args": {"title": "x"}},
        "confidence": 0.9,
    }
    assert first["raw_text"] == "```json\n{}\n```"
    items = {r["item_id"]: r for r in ns.results}
    rd = type("RD", (), {"shape": "route", "items": items})()
    rows = rows_mod.make_rows(rd, "r", "m")
    done = {r["fixture_id"]: r for r in rows if r["fixture_id"] in items}
    assert all(r["parse_ok"] is True and r["error"] is None for r in done.values())
    assert all(r["done_reason"] == "unknown" for r in done.values())
    assert all(r["tokens_out"] == 9 for r in done.values())
    cell = aggregate.aggregate(rows, aggregate.load_truth())["m"]["route"]
    assert cell["n_unparseable"] == 0
    assert cell["n_truncated"] == 0 and cell["n_truncation_unknown"] == 2


def test_a_reply_that_breaks_the_schema_is_kept_as_unparseable_text(monkeypatch, tmp_path):
    def script(ns, schema):
        raise ns.ResponseParsingError("I think it is about 42 kilometres.")

    _, ns = _run_task("route", monkeypatch, tmp_path, script=script)
    first = ns.results[0]
    assert first["error"] is None and first["text"] == "I think it is about 42 kilometres."
    rd = type("RD", (), {"shape": "route", "items": {r["item_id"]: r for r in ns.results}})()
    row = rows_mod.make_rows(rd, "r", "m")[0]
    assert row["error"] is None and row["parse_ok"] is False
    assert row["raw"] == "I think it is about 42 kilometres."


def test_missing_done_reason_is_unknown_not_zero():
    truth = aggregate.load_truth()
    item = runner.load_fixtures("route")[0]
    base = {
        "run_id": "r",
        "model": "m",
        "shape": "route",
        "fixture_id": item["id"],
        "parse_ok": True,
        "answer": "ESCALATE",
        "confidence": 0.6,
        "error": None,
    }
    hosted = aggregate.aggregate([{**base, "done_reason": "unknown"}], truth)
    local_rows = [{**base, "done_reason": None}, {**base, "done_reason": "stop"}]
    local = aggregate.aggregate(local_rows, truth)
    assert hosted["m"]["route"]["n_truncated"] == 0
    assert hosted["m"]["route"]["n_truncation_unknown"] == 1
    md = aggregate.to_markdown(hosted)
    assert "unknown (1)" in md and "no finish reason" in md
    assert "n_truncation_unknown" not in local["m"]["route"]  # a local cell keeps its keys
    local_md = aggregate.to_markdown(local)
    assert "unknown" not in local_md and "no finish reason" not in local_md


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
    assert ok["done_reason"] == "unknown" and ok["error"] is None
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


def _renamed_tree(tmp_path, name):
    tree = tmp_path / "tree"
    shutil.copytree(TREE, tree)
    (tree / "escalation-route").rename(tree / name)
    return tree


def test_converter_accepts_the_pushed_bench_task_name(tmp_path):
    rows = _convert(_renamed_tree(tmp_path, "escalation-bench-route"))
    assert len(rows) == 60 and {r["shape"] for r in rows} == {"route"}
    assert {r["model"] for r in rows} == {"google/model-x"}


def test_converter_still_accepts_the_old_task_name(tmp_path):
    assert len(_convert(_renamed_tree(tmp_path, "escalation-route"))) == 60


@pytest.mark.parametrize("name", ["escalation-probe", "escalation-bench-foo", "escalation-bench-"])
def test_converter_skips_an_unrelated_task_name(tmp_path, name):
    assert _convert(_renamed_tree(tmp_path, name)) == []


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
