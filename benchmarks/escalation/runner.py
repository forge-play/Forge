#!/usr/bin/env python3
"""Run the escalation benchmark fixtures through a model backend (stdlib only).

One call per fixture per model, one JSON line per call. Nothing is retried: a
timeout or an exception becomes a row with ``error`` set, and the run moves on.
Scoring lives in ``aggregate.py``, which reads the rows this script writes.

A backend is one callable::

    complete(model: str, system: str, user: str) -> dict   # {text, tokens_in?, tokens_out?}

Built in: ``ollama_http`` (Ollama's ``/api/chat``, temperature 0, answers constrained by a
JSON schema, thinking off via ``think: false`` for Qwen and Gemma 4, plus a
``/no_think`` suffix for Qwen)
and, with ``--dry-run``, an echo backend that needs no model at all. Any other
backend loads with ``--backend module:function``.

Each row::

    {run_id, model, shape, fixture_id, prompt_sha256, raw, parsed, parse_ok,
     answer, confidence, latency_ms, tokens_in, tokens_out, done_reason, error}

``done_reason`` is the server's own (Ollama: ``stop``, or ``length`` when the reply hit
``MAX_OUTPUT_TOKENS``), or null when the backend does not report one.

``prompt_sha256`` is the SHA-256 of ``system + "\\n---\\n" + user``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ESCALATE = "ESCALATE"
SHAPES = ("route", "classify", "judge", "ground")
ROW_KEYS = (
    "run_id",
    "model",
    "shape",
    "fixture_id",
    "prompt_sha256",
    "raw",
    "parsed",
    "parse_ok",
    "answer",
    "confidence",
    "latency_ms",
    "tokens_in",
    "tokens_out",
    "done_reason",
    "error",
)
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_S = 300.0
#: The output cap every backend sends (Ollama ``num_predict``). Explicit, so the
#: server's own default (which has differed across versions) never decides it: too
#: small cuts a route answer mid-JSON, unbounded lets a model pad under a schema until
#: the call times out. A reply that hit the cap carries ``done_reason: "length"``.
MAX_OUTPUT_TOKENS = 512


# --- fixtures and prompts ----------------------------------------------------


def load_fixtures(shape: str, bench: Path = BENCH) -> list[dict]:
    lines = (bench / "fixtures" / f"{shape}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_catalog(bench: Path = BENCH) -> list[dict]:
    data = json.loads((bench / "catalog" / "tools.json").read_text(encoding="utf-8"))
    return data["tools"]


def system_prompt(shape: str, bench: Path = BENCH) -> str:
    """The shape's prompt file; the route prompt gets the tool catalogue filled in."""
    text = (bench / "prompts" / f"{shape}.txt").read_text(encoding="utf-8")
    if "{catalog}" in text:
        text = text.replace("{catalog}", json.dumps(load_catalog(bench), separators=(",", ":")))
    return text


def user_prompt(shape: str, item: dict) -> str:
    """What the model is shown for one fixture. Never includes expected or rationale."""
    data = item["input"]
    if shape == "judge":
        return f"Claim: {data['claim']}\nDocument: {data['document']}"
    if shape == "ground":
        return f"Passage: {data['passage']}\nQuestion: {data['question']}"
    return str(data)


def prompt_sha256(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n---\n" + user).encode("utf-8")).hexdigest()


# --- reply parsing -----------------------------------------------------------


def parse_reply(text) -> dict | None:
    """The JSON object with an ``answer`` key in a reply, or None when there is none."""
    if not isinstance(text, str):
        return None
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            value = json.loads(cand)
        except ValueError:
            continue
        if isinstance(value, dict) and "answer" in value:
            return value
    return None


def _confidence(parsed: dict | None) -> float | None:
    if parsed is None:
        return None
    conf = parsed.get("confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        return None
    conf = float(conf)
    return conf if math.isfinite(conf) else None


# --- backends ----------------------------------------------------------------


#: The JSON schema sent as Ollama's ``format``. It is the reply shape ``parse_reply`` and
#: the aggregator read: an ``answer`` (a string, or an object for route and classify) and a
#: numeric ``confidence``. Every shape's prompt asks for exactly this envelope.
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"anyOf": [{"type": "string"}, {"type": "object"}]},
        "confidence": {"type": "number"},
    },
    "required": ["answer", "confidence"],
}
NO_THINK_SUFFIX = "/no_think"


def is_qwen(model: str) -> bool:
    return "qwen" in model.lower()


def is_gemma4(model: str) -> bool:
    return model.lower().startswith("gemma4")


def thinks_by_default(model: str) -> bool:
    """Models that reason before answering unless told not to. Every model in the
    benchmark answers directly, so these get ``think: false``."""
    return is_qwen(model) or is_gemma4(model)


def build_chat_payload(model: str, system: str, user: str) -> dict:
    """The ``/api/chat`` body. Thinking is off for every model that thinks by default.

    Qwen and Gemma 4 reason before answering unless told not to; both get
    ``think: false``, so every model answers on the same terms. Ollama does not
    honour ``think: false`` alone for Qwen3 (ollama#12086), so a Qwen request also
    ends its user turn with ``/no_think``. Other models get no ``think`` field: some
    refuse it outright. Every model is held to ``ANSWER_SCHEMA``.
    """
    if is_qwen(model):
        user = f"{user}\n{NO_THINK_SUFFIX}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": ANSWER_SCHEMA,
        "options": {"temperature": 0, "num_predict": MAX_OUTPUT_TOKENS},
    }
    if thinks_by_default(model):
        payload["think"] = False
    return payload


def make_ollama_http(url: str = DEFAULT_OLLAMA_URL, timeout_s: float = DEFAULT_TIMEOUT_S):
    """A backend that calls ``<url>/api/chat`` with temperature 0 and a JSON schema format."""
    endpoint = url.rstrip("/") + "/api/chat"

    def complete(model: str, system: str, user: str) -> dict:
        payload = build_chat_payload(model, system, user)
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        message = body.get("message") or {}
        return {
            "text": message.get("content", ""),
            "tokens_in": body.get("prompt_eval_count"),
            "tokens_out": body.get("eval_count"),
            "done_reason": body.get("done_reason"),
        }

    return complete


def ollama_http(model: str, system: str, user: str) -> dict:
    """The public backend, configured from the environment (OLLAMA_URL, OLLAMA_TIMEOUT)."""
    url = os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL)
    timeout_s = float(os.environ.get("OLLAMA_TIMEOUT", DEFAULT_TIMEOUT_S))
    return make_ollama_http(url, timeout_s)(model, system, user)


def echo_backend(model: str, system: str, user: str) -> dict:
    """The dry-run backend: no model, no network. It always answers ESCALATE."""
    return {
        "text": json.dumps({"answer": ESCALATE, "confidence": 0.5}),
        "tokens_in": 0,
        "tokens_out": 0,
    }


def load_backend(spec: str):
    """Resolve ``module:function`` to a callable."""
    module_name, sep, func_name = spec.partition(":")
    if not sep or not module_name or not func_name:
        raise ValueError(f"backend must be 'module:function', got {spec!r}")
    func = getattr(importlib.import_module(module_name), func_name)
    if not callable(func):
        raise ValueError(f"{spec!r} is not callable")
    return func


def resolve_backend(spec: str, url: str, timeout_s: float):
    if spec == "ollama_http":
        return make_ollama_http(url, timeout_s)
    return load_backend(spec)


# --- the run -----------------------------------------------------------------


def make_row(run_id: str, model: str, shape: str, item: dict, system: str, user: str, complete):
    """One call, one row. Never raises and never retries."""
    row = dict.fromkeys(ROW_KEYS)
    row.update(
        run_id=run_id,
        model=model,
        shape=shape,
        fixture_id=item["id"],
        prompt_sha256=prompt_sha256(system, user),
        parse_ok=False,
    )
    t0 = time.monotonic()
    try:
        result = complete(model, system, user)
    except Exception as exc:
        row["latency_ms"] = int((time.monotonic() - t0) * 1000)
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row
    row["latency_ms"] = int((time.monotonic() - t0) * 1000)
    if not isinstance(result, dict):
        row["error"] = f"backend returned {type(result).__name__}, not a dict"
        return row
    text = result.get("text")
    row["raw"] = text if isinstance(text, str) or text is None else str(text)
    row["tokens_in"] = result.get("tokens_in")
    row["tokens_out"] = result.get("tokens_out")
    row["done_reason"] = result.get("done_reason")
    parsed = parse_reply(row["raw"])
    if parsed is not None:
        row["parsed"] = parsed
        row["parse_ok"] = True
        row["answer"] = parsed["answer"]
        row["confidence"] = _confidence(parsed)
    return row


def run_benchmark(
    complete,
    models,
    shapes,
    out,
    run_id: str,
    limit: int | None = None,
    bench: Path = BENCH,
) -> int:
    """Write one JSONL row per (model, shape, fixture) to ``out``; return the row count."""
    count = 0
    for model in models:
        for shape in shapes:
            system = system_prompt(shape, bench)
            items = load_fixtures(shape, bench)
            if limit is not None:
                items = items[:limit]
            for item in items:
                user = user_prompt(shape, item)
                row = make_row(run_id, model, shape, item, system, user, complete)
                out.write(json.dumps(row, sort_keys=True) + "\n")
                out.flush()
                count += 1
    return count


def make_run_id() -> str:
    return "run-" + time.strftime("%Y%m%dT%H%M%S", time.gmtime())


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--models", help="comma-separated model names (required unless --dry-run)")
    ap.add_argument("--shapes", default=",".join(SHAPES), help="comma-separated; default all four")
    ap.add_argument("--limit", type=int, default=None, help="first N fixtures of each shape")
    ap.add_argument("--out", default=None, help="rows file (default: escalation-<run_id>.jsonl)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument(
        "--backend",
        default="ollama_http",
        help="'ollama_http' (default) or 'module:function' returning {text, tokens_in?, tokens_out?}",
    )
    ap.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL))
    ap.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("OLLAMA_TIMEOUT", DEFAULT_TIMEOUT_S)),
        help="seconds per call for ollama_http",
    )
    ap.add_argument("--dry-run", action="store_true", help="use the echo backend; no model needed")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    shapes = [s.strip() for s in args.shapes.split(",") if s.strip()]
    bad = [s for s in shapes if s not in SHAPES]
    if bad or not shapes:
        ap.error(f"unknown shape(s) {bad or args.shapes!r}; choose from {', '.join(SHAPES)}")
    models = [m.strip() for m in (args.models or "").split(",") if m.strip()]
    if args.dry_run:
        complete = echo_backend
        models = models or ["dry-run"]
    else:
        if not models:
            ap.error("--models is required unless --dry-run is given")
        try:
            complete = resolve_backend(args.backend, args.ollama_url, args.timeout)
        except (ImportError, AttributeError, ValueError) as exc:
            ap.error(f"cannot load backend {args.backend!r}: {exc}")
    run_id = args.run_id or make_run_id()
    out_path = Path(args.out or f"escalation-{run_id}.jsonl")
    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        count = run_benchmark(complete, models, shapes, out, run_id, args.limit)
    print(f"wrote {count} rows to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
