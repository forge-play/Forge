# %% [markdown]
# # Escalation benchmark: classify
#
# Does the model file a work-log note under the right status, severity and needs-human
# flag, and say ESCALATE when the note does not say? This task only collects replies. It sends each exported prompt (system + user)
# at temperature 0 and seed 0 and records the raw reply text per item. Nothing is parsed
# or scored here; the benchmark's own aggregator scores the downloaded run files.

# %%
import json
import os
import time
from pathlib import Path

import kaggle_benchmarks as kbench
import pandas as pd

SHAPE = "classify"
DATASET_SLUG = "escalation-benchmark"
SEED = 0
# "0" sends temperature 0. Set ESCALATION_TEMPERATURE=none to leave it to the platform.
TEMPERATURE = None if os.environ.get("ESCALATION_TEMPERATURE", "0") == "none" else 0


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
        rows.append({"item_id": item["id"], "system": system["content"], "user": user["content"]})
    limit = os.environ.get("ESCALATION_LIMIT")
    return pd.DataFrame(rows[: int(limit)] if limit else rows)


# %%
@kbench.task(name="escalation-classify-item", store_task=False)
def answer_item(llm, item_id: str, system: str, user: str) -> dict:
    """One item, one call. A failed call is a result, never retried."""
    started = time.monotonic()
    result = {"item_id": item_id, "text": None, "error": None}
    try:
        kbench.user.send(user)
        kwargs = {} if TEMPERATURE is None else {"temperature": TEMPERATURE}
        reply = llm.respond(system=system, seed=SEED, **kwargs)
        meta = getattr(reply, "_meta", None) or {}
        result["text"] = reply.content if isinstance(reply.content, str) else str(reply.content)
        result["tokens_in"] = meta.get("input_tokens")
        result["tokens_out"] = meta.get("output_tokens")
    except kbench.tasks.NonRecoverableError:
        raise
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    return result


# %%
@kbench.task(name="escalation-classify", description="Escalation benchmark: raw replies.")
def escalation_classify(llm) -> dict:
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


escalation_classify.run(kbench.llm)
