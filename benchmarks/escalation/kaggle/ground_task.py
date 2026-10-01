# %% [markdown]
# # Escalation benchmark: ground
#
# Does the model answer a question from a passage, and say ESCALATE when the passage
# does not contain the answer? This task only collects replies. It sends each exported prompt (system + user)
# at temperature 0 and seed 0 and records the raw reply text per item. The reply is held to the
# answer schema and the output cap; nothing is scored here; the benchmark's own aggregator scores the downloaded run files.

# %%
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import kaggle_benchmarks as kbench
import pandas as pd
from kaggle_benchmarks.prompting import ResponseParsingError
from pydantic import BaseModel, ValidationError

SHAPE = "ground"
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


class Answer(BaseModel):
    """The reply envelope: runner.ANSWER_SCHEMA as a type the SDK accepts."""

    answer: str | dict[str, Any]
    confidence: float


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


def load_frame() -> pd.DataFrame:
    """One row per item: item_id, system, user. ESCALATION_LIMIT keeps the first N."""
    rows = []
    for line in find_prompts().read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        system, user = item["messages"]
        assert system["role"] == "system" and user["role"] == "user"
        exported = item["schema"]
        if set(exported["properties"]) != set(Answer.model_fields) or set(
            exported["required"]
        ) != set(Answer.model_fields):
            raise ValueError("the exported answer schema no longer matches the Answer type")
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
        return json.dumps(content.model_dump()), raw
    text = content if isinstance(content, str) else str(content)
    return recover_reply(text, Answer)


@kbench.task(name="escalation-bench-ground-item", store_task=False)
def answer_item(llm, item_id: str, system: str, user: str) -> dict:
    """One item, one call. A failed call is a result, never retried."""
    started = time.monotonic()
    cap = cap_kwargs(llm)
    reasoning = reasoning_kwargs(llm)
    result = {
        "item_id": item_id,
        "text": None,
        "error": None,
        "schema": "answer" if SCHEMA_ON else "none",
        "cap": cap or None,
        "reasoning": reasoning.get("reasoning"),
    }
    try:
        kbench.user.send(user)
        kwargs = {} if TEMPERATURE is None else {"temperature": TEMPERATURE}
        if SCHEMA_ON:
            kwargs["schema"] = Answer
        reply = llm.respond(system=system, seed=SEED, **kwargs, **cap, **reasoning)
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
            result["text"], result["raw_text"] = recover_reply(raw, Answer)
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
@kbench.task(name="escalation-bench-ground", description="Escalation benchmark: raw replies.")
def escalation_ground(llm) -> dict:
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


escalation_ground.run(kbench.llm)
