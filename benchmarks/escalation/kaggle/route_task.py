# %% [markdown]
# # Escalation benchmark: route
#
# Does the model pick the right tool from a catalogue, and say ESCALATE when no tool
# fits? This task only collects replies. It sends each exported prompt (system + user)
# at temperature 0 and seed 0 and records the raw reply text per item. The reply is held to the
# answer schema and the output cap; nothing is scored here; the benchmark's own aggregator scores the downloaded run files.
#
# Hosted/local difference: the local runner sends ``runner.ANSWER_SCHEMA``, whose ``answer``
# is "a string or an open object". A hosted structured-output API drops an open object
# (Gemini removes ``additionalProperties``), so a hosted model could only emit ``{}``
# (gap a84645278b60). Here ``answer`` is typed: one explicit object per catalogue tool, or the
# string ESCALATE. The reply text is the same JSON the aggregator reads for a local reply.

# %%
import json
import os
import re
import time
from functools import reduce
from operator import or_
from pathlib import Path
from typing import Literal

import kaggle_benchmarks as kbench
import pandas as pd
from kaggle_benchmarks.prompting import ResponseParsingError
from pydantic import BaseModel, ConfigDict, ValidationError, create_model

SHAPE = "route"
DATASET_SLUG = "escalation-benchmark"
SEED = 0
# "0" sends temperature 0. Set ESCALATION_TEMPERATURE=none to leave it to the platform.
TEMPERATURE = None if os.environ.get("ESCALATION_TEMPERATURE", "0") == "none" else 0
# The local runner's output cap (runner.MAX_OUTPUT_TOKENS), sent to every hosted model.
MAX_OUTPUT_TOKENS = 512
# The answer schema is sent with every call. Set ESCALATION_SCHEMA=none for a model that
# rejects structured output; each row then records schema "none".
SCHEMA_ON = os.environ.get("ESCALATION_SCHEMA", "answer") != "none"

# --- model settings (one table for all four tasks; a test pins the four copies) ---
# Every task file is standalone on Kaggle, so this block is copied, not imported, and
# tests/test_escalation_kaggle.py fails if the four copies drift apart. A model gets one
# setting for all four shapes, so per-shape scores compare like with like.
#
# Settings are chosen by model-name prefix (the proxy names models "<vendor>/<model>"); a
# model with no entry gets nothing sent and keeps its own default.
#
# Reasoning. Hidden reasoning is billed against the output cap, so a reasoning model can
# spend the 512 on thought and cut the answer off (one smoke item: 488 of 497 tokens).
# kaggle_benchmarks 0.6.1 takes respond(reasoning="none"|"low"|"medium"|"high"):
# "reasoning_effort" for an OpenAI-style model, a thinking level for Google GenAI. "low" is
# the lowest level every model in a prefix is known to accept (Gemini 3 cannot switch
# thinking off; OpenAI reasoning models take low/medium/high). ESCALATION_REASONING
# overrides it: a level for every model, or "default" to send none. deepseek-ai/ is left
# out on purpose: its <think> block is stripped below, so the proxy is never asked to take a
# reasoning level for it. google/ is narrowed to google/gemini-: gemma does not think, and a
# thinking level sent to it is a parameter the proxy has no reason to accept.
REASONING_BY_PREFIX = {"google/gemini-": "low", "openai/": "low"}
REASONING = os.environ.get("ESCALATION_REASONING", "auto")
# Output cap. "auto" names the parameter by provider class: max_output_tokens for Google
# GenAI models; otherwise by prefix, max_completion_tokens for openai/ (the gpt-5 and
# gpt-oss reasoning models: the OpenAI API deprecates max_tokens and refuses it for
# reasoning models) and max_tokens for everything else. The SDK passes the name through to
# the proxy unchanged. ESCALATION_CAP_PARAM sets one name for every model, or "none" to
# send no cap. The value is always MAX_OUTPUT_TOKENS.
CAP_PARAM_BY_PREFIX = {"openai/": "max_completion_tokens"}
CAP_PARAM = os.environ.get("ESCALATION_CAP_PARAM", "auto")


def model_name(llm) -> str:
    """The proxy's "<vendor>/<model>" name for this model, or "" when it has none."""
    return str(getattr(llm, "model", None) or getattr(llm, "name", None) or "")


def cap_kwargs(llm) -> dict:
    """The per-call output cap, under the parameter name this model takes."""
    name = CAP_PARAM
    if name == "none":
        return {}
    if name == "auto":
        if "GoogleGenAI" in {cls.__name__ for cls in type(llm).__mro__}:
            name = "max_output_tokens"
        else:
            model = model_name(llm)
            name = next(
                (p for prefix, p in CAP_PARAM_BY_PREFIX.items() if model.startswith(prefix)),
                "max_tokens",
            )
    return {name: MAX_OUTPUT_TOKENS}


def reasoning_kwargs(llm) -> dict:
    """The ``reasoning`` level sent for this model, or nothing when it keeps its default."""
    if REASONING == "default":
        return {}
    if REASONING != "auto":
        return {"reasoning": REASONING}
    model = model_name(llm)
    for prefix, level in REASONING_BY_PREFIX.items():
        if model.startswith(prefix):
            return {"reasoning": level}
    return {}


# Temperature. TEMPERATURE (0) is sent unless the model's provider refuses it. The OpenAI
# gpt-5 family accepts only its default: gpt-5.4-nano answered every smoke2 call with
# a 400 "'temperature' does not support 0 with this model". The SDK has no per-model
# rule (respond() passes the value through; only prompt() gates it, and the proxy loader
# switches that off), so the set is ours: openai/gpt-5 (nano: confirmed by smoke2; gpt-5.5:
# inferred from the same family). gpt-oss-20b is not in it: smoke2 ran it with
# temperature 0 and 0 errors. Every row records what was sent: 0, or "default".
NO_TEMPERATURE_PREFIXES = ("openai/gpt-5",)


def temperature_kwargs(llm) -> dict:
    """The ``temperature`` sent for this model, or nothing when it keeps its default."""
    if TEMPERATURE is None or model_name(llm).startswith(NO_TEMPERATURE_PREFIXES):
        return {}
    return {"temperature": TEMPERATURE}


# Rate limits. A RateLimitError (HTTP 429) is the one failure that is retried: the call
# never reached the model, so it is safe to repeat. Every other failure is recorded once.
# Up to RETRY_MAX_ATTEMPTS calls in all; the wait before call n+1 is
# min(RETRY_MAX_WAIT_S, RETRY_BASE_WAIT_S * 2 ** (n - 1)): 4, 8, 16, 32, 60 s, 120 s at
# most per item. smoke2's 429s came in waves (deepseek 169 of 200), and the SDK's own client
# already retries twice inside one call, so this is the slower second line. Only
# ``llm.respond`` is repeated, never ``kbench.user.send``: the SDK appends the user turn to
# the chat before the call and the assistant turn only after a reply, so a call that
# raised leaves the chat as it was and the retry sends the same prompt. The row's
# ``attempts`` is the number of calls made (1 when none was retried).
RETRY_MAX_ATTEMPTS = 6
RETRY_BASE_WAIT_S = 4.0
RETRY_MAX_WAIT_S = 60.0


def is_rate_limit(exc: BaseException) -> bool:
    """True for the SDK's rate-limit exception (any class named RateLimitError in its MRO)."""
    return any(cls.__name__ == "RateLimitError" for cls in type(exc).__mro__)


def respond_with_retry(llm, result: dict, **kwargs) -> object:
    """``llm.respond(**kwargs)``, repeated while it raises a rate limit, up to the bound.

    ``result["attempts"]`` is the count of calls started, so an error row carries it too.
    The last rate-limit error is raised once the attempts are spent; any other exception
    is raised at once.
    """
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        result["attempts"] = attempt
        try:
            return llm.respond(**kwargs)
        except Exception as exc:
            if not is_rate_limit(exc) or attempt == RETRY_MAX_ATTEMPTS:
                raise
            time.sleep(min(RETRY_MAX_WAIT_S, RETRY_BASE_WAIT_S * 2 ** (attempt - 1)))


# A reasoning model behind the proxy can put its trace in the reply as a leading
# <think>...</think> block (deepseek-r1). kaggle_benchmarks 0.6.1 strips it only when a
# reasoning level was sent, and a structured-output call parses before it strips, so a
# think-prefixed reply otherwise fails the schema. These helpers run only when a parse has
# already failed, so a reply that parsed is never touched.
_THINK_BLOCK = re.compile(r"\A\s*<think>.*?</think>\s*", re.DOTALL)


def strip_think(text: str) -> str:
    """The text without a closed leading <think> block (unchanged when it has none)."""
    return _THINK_BLOCK.sub("", text, count=1)


def reply_in_error(exc: Exception) -> str | None:
    """The reply text an SDK parse failure carries, or None.

    ResponseParsingError carries it as ``value``. A pydantic ValidationError (the SDK's
    structured-output path) carries the whole text as the input of its json_invalid error.
    """
    if isinstance(exc, ValidationError):
        for err in exc.errors():
            if err.get("type") == "json_invalid" and isinstance(err.get("input"), str):
                return err["input"]
        return None
    value = getattr(exc, "value", None)
    return None if value is None else str(value)


def recover_reply(raw: str, answer_type: type[BaseModel], **dump) -> tuple[str, str | None]:
    """(text, raw_text) for a reply, with a leading <think> block taken off the text.

    A reply with no such block comes back as it is, with no raw_text. Otherwise text is the
    answer JSON when the rest validates as ``answer_type``, and the rest as plain text when it
    does not (it is then scored as an unparseable local reply); raw_text keeps the reply the
    model sent, think block and all.
    """
    stripped = strip_think(raw)
    if stripped == raw:
        return raw, None
    text = stripped.strip()
    try:
        text = json.dumps(answer_type.model_validate_json(text).model_dump(**dump))
    except ValidationError:
        pass
    return text, raw


# --- end model settings ---


# --- typed answer schema (hosted/local difference; a test pins it to the catalogue) ---
ESCALATE = "ESCALATE"
SCHEMA_LABEL = "answer-typed"  # the per-row ``schema`` value when the typed schema is sent
# tool -> {argument: (type, required)}, copied from catalog/tools.json.
TOOL_ARGS = {
    "calendar_add_event": {"title": (str, True), "date": (str, True), "time": (str, False)},
    "calendar_list_events": {"date": (str, True)},
    "weather_current": {"city": (str, True)},
    "weather_forecast": {"city": (str, True), "days": (int, True)},
    "library_search": {"query": (str, True), "author": (str, False)},
    "library_hold_book": {"isbn": (str, True), "branch": (str, True)},
    "recipe_search": {
        "ingredient": (str, True),
        "diet": (Literal["any", "vegetarian", "vegan", "gluten_free"], False),
    },
    "recipe_scale": {"recipe_id": (str, True), "servings": (int, True)},
    "transit_next_departure": {"stop": (str, True), "route": (str, True)},
    "transit_plan_trip": {"origin": (str, True), "destination": (str, True)},
    "convert_units": {"value": (float, True), "from_unit": (str, True), "to_unit": (str, True)},
    "convert_currency": {"amount": (float, True), "from_code": (str, True), "to_code": (str, True)},
    "timezone_convert": {"time": (str, True), "from_zone": (str, True), "to_zone": (str, True)},
    "dictionary_define": {"word": (str, True)},
    "translate_text": {"text": (str, True), "target_lang": (str, True)},
    "tide_table": {"harbour": (str, True), "date": (str, True)},
    "flight_status": {"flight_number": (str, True), "date": (str, True)},
    "parcel_track": {"tracking_number": (str, True)},
    "reminder_set": {"text": (str, True), "date": (str, True), "time": (str, True)},
    "math_evaluate": {"expression": (str, True)},
}
_STRICT = ConfigDict(extra="forbid")


def _tool_call_model(tool: str, args: dict) -> type[BaseModel]:
    """One explicit object: ``tool`` fixed to this name, ``args`` limited to its arguments.

    OpenAI strict structured output wants every property required, so an optional catalogue
    argument is a required key that may be null. A null is dropped from the recorded
    reply (``exclude_none``), so a call that leaves an optional argument out scores like a
    local reply that omits it.
    """
    stem = "".join(part.title() for part in tool.split("_"))
    fields = {
        name: (kind, ...) if required else (kind | None, ...)
        for name, (kind, required) in args.items()
    }
    args_model = create_model(f"{stem}Args", __config__=_STRICT, **fields)
    return create_model(
        f"{stem}Call", __config__=_STRICT, tool=(Literal[tool], ...), args=(args_model, ...)
    )


TOOL_CALLS = [_tool_call_model(tool, args) for tool, args in TOOL_ARGS.items()]


def inline_refs(schema: dict) -> dict:
    """The schema with every ``$ref`` replaced by its definition and ``$defs`` removed.

    kaggle_benchmarks 0.6.1 treats a schema with ``$defs`` as nested: for an OpenAI-style
    model it then drops ``response_format`` and only pastes the schema into the prompt, so
    nothing is enforced. An inlined schema keeps the structured-output path.
    """
    defs = schema.get("$defs", {})

    def walk(node: object) -> object:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
            return {key: walk(value) for key, value in node.items() if key != "$defs"}
        if isinstance(node, list):
            return [walk(value) for value in node]
        return node

    return walk(schema)


class Answer(BaseModel):
    """The reply envelope: ``answer`` is one tool call or the string ESCALATE."""

    model_config = _STRICT

    answer: reduce(or_, [*TOOL_CALLS, Literal[ESCALATE]])  # type: ignore[valid-type]
    confidence: float

    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> dict:
        return inline_refs(super().model_json_schema(*args, **kwargs))


def answer_arm_types(model: type[BaseModel] = Answer) -> set[str]:
    """The JSON types the typed ``answer`` admits: "object" and "string", read off its schema."""
    schema = model.model_json_schema()
    arms: set[str] = set()
    stack = [schema["properties"]["answer"]]
    while stack:
        node = stack.pop()
        stack.extend(node.get("anyOf", []))
        if node.get("type") in ("object", "string"):
            arms.add(node["type"])
    return arms


# --- end typed answer schema ---


# %%
def find_prompts() -> Path:
    """The exported prompt file for this shape in the attached dataset."""
    override = os.environ.get("ESCALATION_DATA_DIR")
    if override:
        return Path(override) / f"{SHAPE}.jsonl"
    root = Path("/kaggle/input")
    direct = root / DATASET_SLUG / f"{SHAPE}.jsonl"
    if direct.is_file():
        return direct
    for found in sorted(root.rglob(f"{SHAPE}.jsonl")):
        return found
    raise FileNotFoundError(f"{SHAPE}.jsonl not found under {root}; attach the dataset")


def check_exported_schema(exported: dict) -> None:
    """Refuse an exported schema the typed ``Answer`` does not cover.

    The typed model may be narrower than the exported one (the export's open object has no
    typed form), so equality is not the rule. The rule: the same envelope fields, the same
    required set, the same JSON type for ``confidence``; the export's ``answer`` arms stay
    within the runner's vocabulary (object, string); and the typed ``answer`` keeps the string
    arm (ESCALATE is a string) and adds no arm the export lacks. A typed answer may drop an
    arm the scorer cannot use for the shape (a string-only shape has no object arm), never
    gain one. A dropped string arm, a type added to the export, or a type added to the typed
    side is refused.
    """
    fields = set(Answer.model_fields)
    typed = Answer.model_json_schema()["properties"]
    exported_arms = {arm.get("type") for arm in exported["properties"]["answer"].get("anyOf", [])}
    typed_arms = answer_arm_types()
    if (
        set(exported["properties"]) != fields
        or set(exported["required"]) != fields
        or exported["properties"]["confidence"].get("type") != typed["confidence"].get("type")
        or not exported_arms <= {"object", "string"}
        or "string" not in typed_arms
        or not typed_arms <= exported_arms
    ):
        raise ValueError("the exported answer schema no longer matches the Answer type")


def load_frame() -> pd.DataFrame:
    """One row per item: item_id, system, user. ESCALATION_LIMIT keeps the first N."""
    rows = []
    checked = None
    for line in find_prompts().read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        system, user = item["messages"]
        assert system["role"] == "system" and user["role"] == "user"
        if item["schema"] != checked:  # every line carries the same schema; check it once
            check_exported_schema(item["schema"])
            checked = item["schema"]
        rows.append({"item_id": item["id"], "system": system["content"], "user": user["content"]})
    limit = os.environ.get("ESCALATION_LIMIT")
    return pd.DataFrame(rows[: int(limit)] if limit else rows)


# %%
def reply_text(reply) -> tuple[str | None, str | None]:
    """The reply as the JSON text the aggregator parses, and the raw text when the SDK kept it.

    With the schema on, the SDK hands back a parsed ``Answer``; it is written back out as
    JSON. The raw text the model returned is in the message meta as ``raw_content``. A plain
    text reply (schema off) loses a leading <think> block, and the reply as sent is kept.
    """
    content = reply.content
    raw = (getattr(reply, "_meta", None) or {}).get("raw_content")
    raw = raw if isinstance(raw, str) else None
    if isinstance(content, BaseModel):
        return json.dumps(content.model_dump(exclude_none=True)), raw
    text = content if isinstance(content, str) else str(content)
    return recover_reply(text, Answer, exclude_none=True)


@kbench.task(name="escalation-bench-route-item", store_task=False)
def answer_item(llm, item_id: str, system: str, user: str) -> dict:
    """One item. A failed call is a result; only a rate limit is retried (see above)."""
    started = time.monotonic()
    cap = cap_kwargs(llm)
    reasoning = reasoning_kwargs(llm)
    temperature = temperature_kwargs(llm)
    result = {
        "item_id": item_id,
        "text": None,
        "error": None,
        "schema": SCHEMA_LABEL if SCHEMA_ON else "none",
        "cap": cap or None,
        "reasoning": reasoning.get("reasoning"),
        "temperature": temperature.get("temperature", "default"),
        "attempts": 0,
    }
    try:
        kbench.user.send(user)  # once: a retry repeats respond() only, never this
        kwargs = dict(temperature)
        if SCHEMA_ON:
            kwargs["schema"] = Answer
        reply = respond_with_retry(
            llm, result, system=system, seed=SEED, **kwargs, **cap, **reasoning
        )
        meta = getattr(reply, "_meta", None) or {}
        result["text"], raw = reply_text(reply)
        if raw is not None:
            result["raw_text"] = raw
        result["tokens_in"] = meta.get("input_tokens")
        result["tokens_out"] = meta.get("output_tokens")
    except kbench.tasks.NonRecoverableError:
        raise
    except (ResponseParsingError, ValidationError) as exc:
        raw = reply_in_error(exc)
        if raw is not None and strip_think(raw) != raw:
            # A <think> block ahead of the answer broke the SDK's parse: strip it, keep the raw.
            result["text"], result["raw_text"] = recover_reply(raw, Answer, exclude_none=True)
        elif isinstance(exc, ResponseParsingError):
            # The model broke the schema. Like a local unparseable reply, it is kept as text.
            result["text"] = None if exc.value is None else str(exc.value)
        else:
            result["error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    return result


# %%
@kbench.task(name="escalation-bench-route", description="Escalation benchmark: raw replies.")
def escalation_route(llm) -> dict:
    frame = load_frame()
    runs = answer_item.evaluate(llm=[llm], evaluation_data=frame, on_failure="continue")
    failed = len(runs.errored_runs)
    replied = [r.result for r in runs.completed_runs if isinstance(r.result, dict)]
    errored = failed + sum(1 for r in replied if r.get("error"))
    return {
        "shape": SHAPE,
        "items": len(frame),
        "completed": len(runs) - errored,
        "errored": errored,
    }


escalation_route.run(kbench.llm)
