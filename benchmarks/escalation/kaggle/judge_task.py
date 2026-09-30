# %% [markdown]
# # Escalation benchmark: judge
#
# Does the model say whether a document supports, contradicts or ignores a claim, and
# say ESCALATE when the document is on the subject but silent? This task only collects replies. It sends each exported prompt (system + user)
# at temperature 0 and seed 0 and records the raw reply text per item. The reply is held to the
# answer schema and the output cap; nothing is scored here; the benchmark's own aggregator scores the downloaded run files.

# %%
import json
import os
import time
from pathlib import Path
from typing import Any

import kaggle_benchmarks as kbench
import pandas as pd
from kaggle_benchmarks.prompting import ResponseParsingError
from pydantic import BaseModel

SHAPE = "judge"
DATASET_SLUG = "escalation-benchmark"
SEED = 0
# "0" sends temperature 0. Set ESCALATION_TEMPERATURE=none to leave it to the platform.
TEMPERATURE = None if os.environ.get("ESCALATION_TEMPERATURE", "0") == "none" else 0
# The local runner's output cap (runner.MAX_OUTPUT_TOKENS), sent to every hosted model.
MAX_OUTPUT_TOKENS = 512
# "auto" names the cap parameter by provider: max_output_tokens for Google GenAI models,
# max_tokens otherwise. Set ESCALATION_CAP_PARAM to a parameter name (for example
# max_completion_tokens) to override it, or to "none" to send no cap.
CAP_PARAM = os.environ.get("ESCALATION_CAP_PARAM", "auto")
# The answer schema is sent with every call. Set ESCALATION_SCHEMA=none for a model that
# rejects structured output; each row then records schema "none".
SCHEMA_ON = os.environ.get("ESCALATION_SCHEMA", "answer") != "none"


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
def cap_kwargs(llm) -> dict:
    """The per-call output cap, under the parameter name the model's provider takes."""
    name = CAP_PARAM
    if name == "none":
        return {}
    if name == "auto":
        classes = {cls.__name__ for cls in type(llm).__mro__}
        name = "max_output_tokens" if "GoogleGenAI" in classes else "max_tokens"
    return {name: MAX_OUTPUT_TOKENS}


def reply_text(reply) -> tuple[str | None, str | None]:
    """The reply as the JSON text the aggregator parses, and the raw text when the SDK kept it.

    With the schema on, the SDK hands back a parsed ``Answer``; it is written back out as
    JSON. The raw text the model returned is in the message meta as ``raw_content``.
    """
    content = reply.content
    raw = (getattr(reply, "_meta", None) or {}).get("raw_content")
    raw = raw if isinstance(raw, str) else None
    if isinstance(content, BaseModel):
        return json.dumps(content.model_dump()), raw
    return (content if isinstance(content, str) else str(content)), None


@kbench.task(name="escalation-judge-item", store_task=False)
def answer_item(llm, item_id: str, system: str, user: str) -> dict:
    """One item, one call. A failed call is a result, never retried."""
    started = time.monotonic()
    cap = cap_kwargs(llm)
    result = {
        "item_id": item_id,
        "text": None,
        "error": None,
        "schema": "answer" if SCHEMA_ON else "none",
        "cap": cap or None,
    }
    try:
        kbench.user.send(user)
        kwargs = {} if TEMPERATURE is None else {"temperature": TEMPERATURE}
        if SCHEMA_ON:
            kwargs["schema"] = Answer
        reply = llm.respond(system=system, seed=SEED, **kwargs, **cap)
        meta = getattr(reply, "_meta", None) or {}
        result["text"], raw = reply_text(reply)
        if raw is not None:
            result["raw_text"] = raw
        result["tokens_in"] = meta.get("input_tokens")
        result["tokens_out"] = meta.get("output_tokens")
    except kbench.tasks.NonRecoverableError:
        raise
    except ResponseParsingError as exc:
        # The model broke the schema. Like a local unparseable reply, it is kept as text.
        result["text"] = None if exc.value is None else str(exc.value)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    return result


# %%
@kbench.task(name="escalation-judge", description="Escalation benchmark: raw replies.")
def escalation_judge(llm) -> dict:
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


escalation_judge.run(kbench.llm)
