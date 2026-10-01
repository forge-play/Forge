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
    # the names the tasks are live under on Kaggle (push2/), not the repo's old escalation-<shape>
    assert names == [f"escalation-bench-{shape}-item", f"escalation-bench-{shape}"]
    assert all(re.fullmatch(r"[a-z0-9-]+", n) for n in names)  # slugifies to itself
    assert "store_task=False" in text
    assert 'on_failure="continue"' in text
    assert f'SHAPE = "{shape}"' in text


def _body(shape: str, *, drop_typed: bool = False) -> str:
    text = _task_text(shape)
    body = text[text.index("# %%\nimport json") :]
    if drop_typed:
        body = re.sub(
            r"# --- typed answer schema.*?# --- end typed answer schema ---\n", "", body, flags=re.S
        )
        body = re.sub(
            r"^from (functools|operator|typing|pydantic) import .*\n", "", body, flags=re.M
        )
    return body.replace(shape, "SHAPE_WORD")


def test_judge_and_ground_task_files_differ_only_by_shape():
    assert _body("judge") == _body("ground")


def test_route_and_classify_task_files_differ_only_by_shape_and_the_typed_answer():
    """The typed answer schema is the one deliberate hosted/local difference per shape."""
    assert _body("route", drop_typed=True) == _body("classify", drop_typed=True)
    for shape in ("route", "classify"):
        text = _task_text(shape)
        assert text.count("# --- typed answer schema") == 1
        assert "hosted/local difference" in text.split("# %%")[1].lower()  # the header says so
    for shape in ("judge", "ground"):
        assert "typed answer schema" not in _task_text(shape)  # judge and ground are unchanged


# --- hosted parity: schema, output cap, done_reason -------------------------------------


class _Namespace:
    """What the stubbed SDK records while a task file runs against it."""

    def __init__(self):
        self.results: list[dict] = []
        self.llm = None


def _install_sdk_stub(monkeypatch, llm_class_name="OpenAI", model=None, real=None):
    """Stand-ins for kaggle_benchmarks and pandas, enough to run a task file.

    pydantic is the real one: the typed route and classify answers are pydantic models, and
    a stub could not tell a typed schema from an open one. ``real`` is ``(llm, error_class)``
    from ``_real_sdk_llm``: the stub then hands the task that llm, whose ``respond`` is the
    real SDK's, and the task catches the real ``ResponseParsingError``.
    """
    pytest.importorskip("pydantic")
    ns = _Namespace()

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
    if model is not None:
        llm.model = model

    def script(self, schema):
        content = json.dumps({"answer": "ESCALATE", "confidence": 0.5})
        if schema is not str:
            content = schema(answer="ESCALATE", confidence=0.5)
        return _Reply(
            content,
            {"input_tokens": 7, "output_tokens": 3, "raw_content": '{"answer": "ESCALATE"}'},
        )

    llm.script = script
    if real is not None:
        llm, ResponseParsingError = real
    ns.llm = llm
    sdk = type(sys)("kaggle_benchmarks")
    sdk.task, sdk.llm = task, llm
    sdk.user = type("user", (), {"send": staticmethod(lambda *_: None)})
    sdk.tasks = type("tasks", (), {"NonRecoverableError": NonRecoverableError})
    prompting = type(sys)("kaggle_benchmarks.prompting")
    prompting.ResponseParsingError = ResponseParsingError
    pandas = type(sys)("pandas")
    pandas.DataFrame = list
    for name, module in (
        ("kaggle_benchmarks", sdk),
        ("kaggle_benchmarks.prompting", prompting),
        ("pandas", pandas),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    ns.ResponseParsingError = ResponseParsingError
    return ns


def _run_task(
    shape,
    monkeypatch,
    tmp_path,
    *,
    env=None,
    llm_class_name="OpenAI",
    script=None,
    model=None,
    real=None,
):
    ns = _install_sdk_stub(monkeypatch, llm_class_name, model, real)
    if script is not None:  # script(ns, schema) -> a reply, or raises
        ns.llm.script = lambda self, schema: script(ns, schema)
    data = tmp_path / "data"
    if not data.exists():
        export.write_export(data)
    monkeypatch.setenv("ESCALATION_DATA_DIR", str(data))
    monkeypatch.setenv("ESCALATION_LIMIT", "2")
    for key in ("ESCALATION_SCHEMA", "ESCALATION_CAP_PARAM", "ESCALATION_REASONING"):
        monkeypatch.delenv(key, raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location(f"task_{shape}", TASK_DIR / f"{shape}_task.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, ns


TYPED_LABEL = {"route": "answer-typed", "classify": "answer-typed"}


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
    assert {r["schema"] for r in ns.results} == {TYPED_LABEL.get(shape, "answer")}


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
            answer={
                "tool": "calendar_add_event",
                "args": {"title": "x", "date": "2027-03-14", "time": None},
            },
            confidence=0.9,
        )
        reply._meta = {"input_tokens": 5, "output_tokens": 9, "raw_content": "```json\n{}\n```"}
        return reply

    _, ns = _run_task("route", monkeypatch, tmp_path, script=script)
    first = ns.results[0]
    # the unset optional argument is dropped from the recorded reply, as a local reply omits it
    assert json.loads(first["text"]) == {
        "answer": {"tool": "calendar_add_event", "args": {"title": "x", "date": "2027-03-14"}},
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


# --- typed answer schemas (route, classify) -------------------------------------------

TYPED = ("route", "classify")


def _answer_class(shape, monkeypatch, tmp_path):
    module, _ = _run_task(shape, monkeypatch, tmp_path)
    return module


def _walk(node):
    """Every dict in a JSON schema, depth first."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


@pytest.mark.parametrize("shape", TYPED)
def test_the_typed_answer_schema_has_no_open_object(shape, monkeypatch, tmp_path):
    """The defect (gap a84645278b60): an ``answer`` with no properties lets a hosted
    structured-output API emit only ``{}``. Every object in the schema now names its
    properties, requires all of them, and refuses extras; ESCALATE stays a string arm."""
    schema = _answer_class(shape, monkeypatch, tmp_path).Answer.model_json_schema()
    assert "$defs" not in schema and "$ref" not in json.dumps(schema)  # SDK keeps response_format
    objects = [n for n in _walk(schema) if n.get("type") == "object"]
    # the envelope and the answer object(s): route has one call and one args object per tool
    assert len(objects) >= (1 + 2 * 20 if shape == "route" else 2)
    for node in objects:
        assert node.get("properties"), f"open object in the {shape} schema: {node}"
        assert set(node["required"]) == set(node["properties"])
        assert node["additionalProperties"] is False
    arms = schema["properties"]["answer"]["anyOf"]
    assert {"const": "ESCALATE", "type": "string"} in [
        {k: v for k, v in arm.items() if k in ("const", "type")} for arm in arms
    ]
    assert {arm["type"] for arm in arms} == {"object", "string"}


def test_the_route_schema_matches_the_catalogue(monkeypatch, tmp_path):
    module = _answer_class("route", monkeypatch, tmp_path)
    catalog = {t["name"]: t["parameters"] for t in runner.load_catalog()}
    arms = {
        arm["properties"]["tool"]["const"]: arm
        for arm in module.Answer.model_json_schema()["properties"]["answer"]["anyOf"]
        if arm.get("type") == "object"
    }
    assert set(arms) == set(catalog)
    for tool, params in catalog.items():
        args = arms[tool]["properties"]["args"]
        assert set(args["properties"]) == set(params["properties"]), tool
        for name, spec in params["properties"].items():
            typed = args["properties"][name]
            required = name in params["required"]
            arm_types = {a.get("type") for a in typed.get("anyOf", [typed])}
            assert ("null" in arm_types) is (not required), (tool, name)
            wanted = {"string": "string", "integer": "integer", "number": "number"}[spec["type"]]
            assert wanted in arm_types, (tool, name)
            if "enum" in spec:
                enum = typed.get("enum") or next(a["enum"] for a in typed["anyOf"] if "enum" in a)
                assert set(enum) == set(spec["enum"]), (tool, name)


def test_the_classify_schema_matches_the_prompt(monkeypatch, tmp_path):
    module = _answer_class("classify", monkeypatch, tmp_path)
    arms = module.Answer.model_json_schema()["properties"]["answer"]["anyOf"]
    obj = next(arm for arm in arms if arm.get("type") == "object")
    assert set(obj["properties"]) == {"status", "severity", "needs_human"}
    assert obj["properties"]["status"]["enum"] == ["resolved", "in_progress", "blocked", "wontfix"]
    assert obj["properties"]["severity"]["enum"] == ["low", "medium", "high"]
    assert obj["properties"]["needs_human"]["type"] == "boolean"
    prompt = runner.system_prompt("classify")
    for value in obj["properties"]["status"]["enum"] + obj["properties"]["severity"]["enum"]:
        assert f'"{value}"' in prompt


def _typed_reply(shape, schema, item, escalate=False):
    """The typed model's reply for one fixture item: its expected answer, or ESCALATE."""
    expected = "ESCALATE" if escalate else item["expected"]
    if shape == "route" and isinstance(expected, dict):
        call = next(
            c for c in schema.model_fields["answer"].annotation.__args__ if _is(c, expected)
        )
        nulls = {k: None for k in call.model_fields["args"].annotation.model_fields}
        expected = {"tool": expected["tool"], "args": {**nulls, **expected["args"]}}
    return schema(answer=expected, confidence=0.8)


def _is(call, expected):
    tool = getattr(call, "model_fields", {}).get("tool")
    return tool is not None and tool.annotation.__args__ == (expected["tool"],)


@pytest.mark.parametrize("shape", TYPED)
def test_a_typed_reply_scores_like_the_equivalent_local_reply(shape, monkeypatch, tmp_path):
    """The same replies through the hosted path (task file, kaggle_rows, aggregate) and the
    local path (runner.make_row, aggregate) give the same cell."""
    items = runner.load_fixtures(shape)
    escalate_every_third = [i % 3 == 0 for i in range(len(items))]

    def script(ns, schema):
        n = len(ns.llm.calls) - 1
        reply = type("Reply", (), {})()
        reply.content = _typed_reply(shape, schema, items[n], escalate_every_third[n])
        reply._meta = {"input_tokens": 5, "output_tokens": 9, "raw_content": "{}"}
        return reply

    module, ns = _run_task(
        shape, monkeypatch, tmp_path, script=script, env={"ESCALATION_LIMIT": str(len(items))}
    )
    assert len(ns.results) == len(items)
    assert {r["schema"] for r in ns.results} == {"answer-typed"}
    by_id = {r["item_id"]: r for r in ns.results}
    rd = type("RD", (), {"shape": shape, "items": by_id})()
    hosted_rows = rows_mod.make_rows(rd, "r", "m")
    system = runner.system_prompt(shape)
    local_rows = []
    for item, esc in zip(items, escalate_every_third):
        text = by_id[item["id"]]["text"]
        assert json.loads(text)["answer"] == ("ESCALATE" if esc else item["expected"])
        local_rows.append(
            runner.make_row(
                "r",
                "m",
                shape,
                item,
                system,
                runner.user_prompt(shape, item),
                lambda *_: {"text": text},
            )
        )
    truth = aggregate.load_truth()
    hosted = aggregate.aggregate(hosted_rows, truth)["m"][shape]
    local = aggregate.aggregate(local_rows, truth)["m"][shape]
    assert hosted["n_correct"] > 0 and hosted["n_escalated"] > 0  # a mix, not all-or-nothing
    assert hosted["n_unparseable"] == 0
    for key in local:
        assert hosted[key] == local[key], key
    for hosted_row, local_row in zip(hosted_rows, local_rows):
        assert (hosted_row["answer"], hosted_row["confidence"], hosted_row["parse_ok"]) == (
            local_row["answer"],
            local_row["confidence"],
            True,
        )


@pytest.mark.parametrize("shape", TYPED)
def test_a_reply_the_typed_schema_rejects_still_scores_from_its_raw_text(
    shape, monkeypatch, tmp_path
):
    """A model that writes ``escalate`` in lower case breaks the typed arm, but the raw
    text is kept and aggregate.py scores it exactly as it scores a local reply."""
    raw = json.dumps({"answer": "ESCALATE", "confidence": 0.7})

    def script(ns, schema):
        raise ns.ResponseParsingError(raw)

    _, ns = _run_task(shape, monkeypatch, tmp_path, script=script)
    by_id = {r["item_id"]: r for r in ns.results}
    rows = rows_mod.make_rows(type("RD", (), {"shape": shape, "items": by_id})(), "r", "m")
    done = [r for r in rows if r["fixture_id"] in by_id]
    assert done and all(r["parse_ok"] and r["answer"] == "ESCALATE" for r in done)


@pytest.mark.parametrize("shape", TYPED)
def test_every_fixture_answer_is_expressible_in_the_typed_schema(shape, monkeypatch, tmp_path):
    module = _answer_class(shape, monkeypatch, tmp_path)
    for item in runner.load_fixtures(shape):
        reply = _typed_reply(shape, module.Answer, item)
        dumped = reply.model_dump(exclude_none=True)["answer"]
        assert dumped == item["expected"], item["id"]
        assert aggregate.is_correct(shape, dumped, {"answerable": item["answerable"], **item})


@pytest.mark.parametrize("shape", TYPED)
def test_the_guard_accepts_the_runner_schema_and_refuses_a_real_mismatch(
    shape, monkeypatch, tmp_path
):
    """Rule: same envelope fields, same required set, same ``confidence`` type, and the typed
    ``answer`` admits exactly the JSON types the export's ``answer`` admits (object, string)."""
    module = _answer_class(shape, monkeypatch, tmp_path)
    good = json.loads(json.dumps(runner.ANSWER_SCHEMA))
    module.check_exported_schema(good)
    assert module.answer_arm_types() == {"object", "string"}

    def broken(edit):
        schema = json.loads(json.dumps(good))
        edit(schema)
        with pytest.raises(ValueError, match="no longer matches"):
            module.check_exported_schema(schema)

    broken(lambda s: s["properties"].update(reason={"type": "string"}))  # a new field
    broken(lambda s: s["required"].remove("confidence"))  # a looser required set
    broken(lambda s: s["properties"]["confidence"].update(type="string"))
    broken(lambda s: s["properties"]["answer"]["anyOf"].append({"type": "array"}))  # a new arm
    broken(lambda s: s["properties"]["answer"]["anyOf"].pop(0))  # a dropped string arm
    broken(lambda s: s["properties"]["answer"]["anyOf"].pop(1))  # a dropped object arm
    # the typed side losing an arm is refused too
    monkeypatch.setattr(module, "answer_arm_types", lambda *_: {"object"})
    with pytest.raises(ValueError, match="no longer matches"):
        module.check_exported_schema(good)


def test_the_export_still_carries_the_open_runner_schema():
    """The local runner and the exported dataset are unchanged: the typed schema is hosted only."""
    for shape in TYPED:
        schema = export.export_shape(shape)[0]["schema"]
        assert schema == runner.ANSWER_SCHEMA
        assert schema["properties"]["answer"] == {"anyOf": [{"type": "string"}, {"type": "object"}]}


@pytest.mark.parametrize(
    "model, expected",
    [
        ("google/gemini-3.8-flash", "low"),
        ("google/gemini-3.1-pro-preview", "low"),
        ("openai/gpt-5.5", "low"),
        ("openai/gpt-oss-20b", "low"),
        ("anthropic/claude-opus-5", None),
        ("xai/grok-4.6", None),
        ("deepseek-ai/deepseek-r1-0528", None),
        ("qwen/qwen3-235b-a22b-instruct-2507", None),
        (None, None),
    ],
)
@pytest.mark.parametrize("shape", SHAPES)
def test_the_reasoning_level_follows_the_provider(shape, model, expected, monkeypatch, tmp_path):
    _, ns = _run_task(shape, monkeypatch, tmp_path, model=model)
    for call in ns.llm.calls:
        assert call.get("reasoning") == expected and ("reasoning" in call) is (expected is not None)
        assert [call[k] for k in CAP_NAMES if k in call] == [512]  # never raised to make room
    assert {r["reasoning"] for r in ns.results} == {expected}


@pytest.mark.parametrize("shape", SHAPES)
def test_the_reasoning_level_can_be_overridden_or_left_to_the_model(shape, monkeypatch, tmp_path):
    _, ns = _run_task(
        shape, monkeypatch, tmp_path, model="google/g", env={"ESCALATION_REASONING": "high"}
    )
    assert all(call["reasoning"] == "high" for call in ns.llm.calls)
    _, ns = _run_task(
        shape, monkeypatch, tmp_path, model="google/g", env={"ESCALATION_REASONING": "default"}
    )
    assert all("reasoning" not in call for call in ns.llm.calls)
    assert {r["reasoning"] for r in ns.results} == {None}


# --- one settings table for all four shapes --------------------------------------------

CAP_NAMES = ("max_tokens", "max_completion_tokens", "max_output_tokens")

# The ratified set (279aedee): slug -> (cap parameter name, reasoning level sent). The cap
# value is 512 for every slug; the reasoning level is None when nothing is sent.
RATIFIED = {
    "anthropic/claude-opus-5": ("max_tokens", None),
    "openai/gpt-5.5": ("max_completion_tokens", "low"),
    "google/gemini-3.1-pro-preview": ("max_tokens", "low"),
    "xai/grok-4.6": ("max_tokens", None),
    "anthropic/claude-sonnet-5": ("max_tokens", None),
    "google/gemini-3.8-flash": ("max_tokens", "low"),
    "deepseek-ai/deepseek-r1-0528": ("max_tokens", None),
    "anthropic/claude-haiku-4-5": ("max_tokens", None),
    "openai/gpt-5.4-nano": ("max_completion_tokens", "low"),
    "google/gemma-4-26b-a4b-it": ("max_tokens", None),
    "qwen/qwen3-235b-a22b-instruct-2507": ("max_tokens", None),
    "openai/gpt-oss-20b": ("max_completion_tokens", "low"),
}


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("slug", sorted(RATIFIED))
def test_every_ratified_slug_gets_its_cap_parameter_and_reasoning_on_every_shape(
    slug, shape, monkeypatch, tmp_path
):
    cap_name, level = RATIFIED[slug]
    _, ns = _run_task(shape, monkeypatch, tmp_path, model=slug)
    assert len(ns.llm.calls) == 2
    for call in ns.llm.calls:
        assert {k: call[k] for k in CAP_NAMES if k in call} == {cap_name: 512}, slug
        assert call.get("reasoning") == level, slug
    assert {json.dumps(r["cap"]) for r in ns.results} == {json.dumps({cap_name: 512})}
    assert {r["reasoning"] for r in ns.results} == {level}


@pytest.mark.parametrize("shape", SHAPES)
def test_the_cap_parameter_can_still_be_forced_for_an_openai_slug(shape, monkeypatch, tmp_path):
    _, ns = _run_task(
        shape,
        monkeypatch,
        tmp_path,
        model="openai/gpt-5.5",
        env={"ESCALATION_CAP_PARAM": "max_tokens"},
    )
    assert all(call["max_tokens"] == 512 for call in ns.llm.calls)
    assert all("max_completion_tokens" not in call for call in ns.llm.calls)


@pytest.mark.parametrize("shape", SHAPES)
def test_a_google_genai_client_keeps_max_output_tokens_whatever_its_name(
    shape, monkeypatch, tmp_path
):
    _, ns = _run_task(
        shape, monkeypatch, tmp_path, llm_class_name="GoogleGenAI", model="google/gemini-3.8-flash"
    )
    assert all(
        {k: call[k] for k in CAP_NAMES if k in call} == {"max_output_tokens": 512}
        for call in ns.llm.calls
    )


def _settings_block(shape: str) -> str:
    text = _task_text(shape)
    assert text.count("# --- model settings") == 1, shape
    assert text.count("# --- end model settings ---") == 1, shape
    return text[text.index("# --- model settings") : text.index("# --- end model settings ---")]


def test_the_four_task_files_carry_one_identical_settings_table():
    """Each task file is standalone on Kaggle, so the table is copied four times. A copy
    that drifts gives one shape a different cap parameter or reasoning level than another,
    and per-shape scores stop comparing like with like."""
    blocks = {shape: _settings_block(shape) for shape in SHAPES}
    drifted = sorted(shape for shape in SHAPES if blocks[shape] != blocks["route"])
    assert not drifted, f"settings table differs from route's in: {drifted}"
    assert "REASONING_BY_PREFIX" in blocks["route"] and "CAP_PARAM_BY_PREFIX" in blocks["route"]


def _project_test_extra() -> list[str]:
    """The requirement strings of pyproject.toml's ``test`` extra."""
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["optional-dependencies"]["test"]


def _ci_test_installs() -> int:
    """How many CI legs in tests.yml install the package with its ``test`` extra."""
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    return workflow.count('pip install -e ".[test]"')


def test_the_test_extra_installs_pydantic_so_ci_runs_the_typed_tests():
    """The typed kaggle tests importorskip pydantic. CI's matrix and Windows legs install
    ``.[test]``, so pydantic in that extra is what makes them run instead of skip."""
    extra = _project_test_extra()
    assert any(re.match(r"pydantic\b", dep) for dep in extra), extra
    assert _ci_test_installs() >= 2  # the Linux matrix and Windows legs


# --- a <think>-prefixed reply (deepseek-r1) --------------------------------------------

THINK = "<think>\nThe note does not say, so the safe answer is to escalate.\n</think>\n"
BODY_JSON = json.dumps({"answer": "ESCALATE", "confidence": 0.5})
PARSED = {"answer": "ESCALATE", "confidence": 0.5}
DEEPSEEK = "deepseek-ai/deepseek-r1-0528"


@pytest.mark.parametrize("shape", SHAPES)
def test_a_think_prefixed_reply_the_sdk_could_not_parse_is_stripped_and_the_raw_kept(
    shape, monkeypatch, tmp_path
):
    def script(ns, schema):
        raise ns.ResponseParsingError(THINK + BODY_JSON)

    _, ns = _run_task(shape, monkeypatch, tmp_path, script=script, model=DEEPSEEK)
    assert len(ns.results) == 2
    for r in ns.results:
        assert r["error"] is None
        assert json.loads(r["text"]) == PARSED
        assert r["raw_text"] == THINK + BODY_JSON  # the reply as the model sent it
    by_id = {r["item_id"]: r for r in ns.results}
    rows = rows_mod.make_rows(type("RD", (), {"shape": shape, "items": by_id})(), "r", "m")
    done = [r for r in rows if r["fixture_id"] in by_id]
    assert done and all(r["parse_ok"] and r["answer"] == "ESCALATE" for r in done)


@pytest.mark.parametrize("shape", SHAPES)
def test_a_think_prefixed_reply_that_fails_pydantic_first_is_recovered_too(
    shape, monkeypatch, tmp_path
):
    """The structured-output path parses before the SDK can strip: a pydantic
    ValidationError carries the whole text as the input of its json_invalid error."""

    def script(ns, schema):
        return schema.model_validate_json(THINK + BODY_JSON)  # raises ValidationError

    _, ns = _run_task(shape, monkeypatch, tmp_path, script=script, model=DEEPSEEK)
    for r in ns.results:
        assert r["error"] is None and json.loads(r["text"]) == PARSED
        assert r["raw_text"] == THINK + BODY_JSON


@pytest.mark.parametrize("shape", SHAPES)
def test_a_think_prefixed_text_reply_with_the_schema_off_is_stripped(shape, monkeypatch, tmp_path):
    def script(ns, schema):
        reply = type("Reply", (), {})()
        reply.content, reply._meta = THINK + BODY_JSON, {"raw_content": THINK + BODY_JSON}
        return reply

    _, ns = _run_task(
        shape, monkeypatch, tmp_path, script=script, env={"ESCALATION_SCHEMA": "none"}
    )
    for r in ns.results:
        assert json.loads(r["text"]) == PARSED and r["raw_text"] == THINK + BODY_JSON


@pytest.mark.parametrize("shape", SHAPES)
def test_a_reply_cut_off_inside_its_think_block_stays_unparseable_text(
    shape, monkeypatch, tmp_path
):
    """Nothing to strip when the block never closes (the 512 cap ended it): the text is kept
    as sent and scores as unparseable, which is the honest result."""
    cut = "<think>\nThe note says nothing about the status, so"

    def script(ns, schema):
        raise ns.ResponseParsingError(cut)

    _, ns = _run_task(shape, monkeypatch, tmp_path, script=script, model=DEEPSEEK)
    for r in ns.results:
        assert r["error"] is None and r["text"] == cut and "raw_text" not in r


@pytest.mark.parametrize("shape", SHAPES)
def test_a_pydantic_failure_with_no_think_block_is_still_an_error_row(shape, monkeypatch, tmp_path):
    def script(ns, schema):
        return schema.model_validate_json("not json at all")

    _, ns = _run_task(shape, monkeypatch, tmp_path, script=script, model=DEEPSEEK)
    for r in ns.results:
        assert r["text"] is None and r["error"].startswith("ValidationError")


def _real_sdk_llm(structured: bool, reply_content: str, seen: list, model: str = DEEPSEEK):
    """A real kaggle_benchmarks ``OpenAI`` actor over a canned HTTP transport (no network).

    Returns ``(llm, ResponseParsingError)``. The llm's ``respond`` is the real SDK's, so a
    reply goes through the SDK's own request building and parsing; the request bodies it
    sent are appended to ``seen``. Skipped where the SDK is not installed (Forge CI).
    """
    kbench = pytest.importorskip("kaggle_benchmarks")
    openai = pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")
    from kaggle_benchmarks import chats
    from kaggle_benchmarks.actors import llms
    from kaggle_benchmarks.prompting import ResponseParsingError

    def handler(request):
        seen.append(json.loads(request.content))
        message = {"role": "assistant", "content": reply_content}
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 1,
                "model": model,
                "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            },
        )

    client = openai.OpenAI(
        base_url="http://sdk.invalid/v1",
        api_key="not-a-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    actor = llms.OpenAI(client, model, support_structured_outputs=structured)

    class OpenAI:  # named like the SDK class: the task reads the class name and ``model``
        def __init__(self):
            self.model, self.calls = model, []

        def respond(self, **kwargs):
            self.calls.append(kwargs)
            with chats.new(name="probe"):
                kbench.user.send("hi")
                return actor.respond(**kwargs)

    return OpenAI(), ResponseParsingError


@pytest.mark.parametrize("prefix", [THINK, ""], ids=["think-prefixed", "plain"])
@pytest.mark.parametrize("structured", [False, True], ids=["text-path", "structured-path"])
@pytest.mark.parametrize("shape", SHAPES)
def test_a_deepseek_reply_parses_through_the_real_sdk_on_every_shape(
    shape, structured, prefix, monkeypatch, tmp_path
):
    """The same SDK parse path the task uses. deepseek-ai/ models are built with
    support_structured_outputs=False by kaggle_benchmarks' model proxy loader (the
    ``"deepseek" not in model`` check), so the text path is the live one; the structured
    path is run as well because a pydantic failure there arrives as a ValidationError."""
    pytest.importorskip("pydantic")
    seen: list = []
    real = _real_sdk_llm(structured, prefix + BODY_JSON, seen)
    _, ns = _run_task(shape, monkeypatch, tmp_path, real=real, model=DEEPSEEK)
    assert len(ns.results) == len(seen) == 2
    for r in ns.results:
        assert r["error"] is None, r
        assert json.loads(r["text"]) == PARSED
        assert r["raw_text"] == prefix + BODY_JSON
        assert r["reasoning"] is None and r["cap"] == {"max_tokens": 512}
    # nothing the proxy might refuse was added for deepseek: no reasoning_effort
    assert all("reasoning_effort" not in body and body["max_tokens"] == 512 for body in seen)


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
