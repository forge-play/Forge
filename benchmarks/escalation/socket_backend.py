#!/usr/bin/env python3
"""A runner backend that reaches a local model through a Unix-socket delegate (stdlib only).

Some hosts keep the model server off the network the benchmark runs in and put a
small delegate on a Unix socket in front of it. The delegate speaks one JSON
line each way. This backend uses three of its ops:

    {"op": "chat", "model", "system", "user", "temperature", "format", "keep_alive"}
        -> {"ok": true, "text", "tokens_in", "tokens_out"} | {"ok": false, "error"}
    {"op": "unload", "model"} -> {"ok": true, ...} | {"ok": false, "error"}

The request matches the built-in ``ollama_http`` backend: temperature 0, the
same ``ANSWER_SCHEMA`` as the ``format``, and Qwen's ``/no_think`` suffix. A
refusal from the delegate raises, so the runner records it as a row with
``error`` set; nothing is retried.

Configuration is the environment, never a path in this file:

    ESCALATION_SOCKET             the delegate's socket path (required)
    ESCALATION_SOCKET_TIMEOUT     seconds per call (default 660)
    ESCALATION_KEEP_ALIVE         how long the model stays loaded between calls (default "10m")

As a runner backend::

    python benchmarks/escalation/runner.py --backend socket_backend:complete --models M --out rows.jsonl

``ladder`` walks several models one at a time and unloads each before the next,
so only one is ever held in memory::

    python benchmarks/escalation/socket_backend.py ladder --models A,B,C --out rows.jsonl

It refuses to overwrite a rows file that already has rows. ``--resume`` continues
one instead: rows already there are skipped (an error row counts as done, since a
failure is a result and is never retried), a torn last line from a killed run is
dropped, and the file's run id is kept. ``--tail`` prints one progress line per
row to stderr as it is written.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import runner  # noqa: E402

DEFAULT_TIMEOUT_S = 660.0
DEFAULT_KEEP_ALIVE = "10m"


class DelegateError(RuntimeError):
    """The delegate answered ``ok: false``; the message is its error text."""


def _socket_path() -> str:
    path = os.environ.get("ESCALATION_SOCKET", "").strip()
    if not path:
        raise DelegateError("ESCALATION_SOCKET is not set")
    return path


def _timeout_s() -> float:
    return float(os.environ.get("ESCALATION_SOCKET_TIMEOUT", DEFAULT_TIMEOUT_S))


def call(req: dict, path: str | None = None, timeout_s: float | None = None) -> dict:
    """Send one JSON line to the delegate and return its one-line JSON reply."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout_s if timeout_s is not None else _timeout_s())
    try:
        sock.connect(path or _socket_path())
        sock.sendall(json.dumps(req).encode("utf-8") + b"\n")
        data = b""
        while b"\n" not in data:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    finally:
        sock.close()
    line = data.split(b"\n", 1)[0].decode("utf-8").strip()
    if not line:
        raise DelegateError("empty reply from the delegate")
    reply = json.loads(line)
    if not isinstance(reply, dict):
        raise DelegateError("reply is not a JSON object")
    return reply


def chat_request(model: str, system: str, user: str) -> dict:
    """The delegate ``chat`` request: the same knobs ``build_chat_payload`` sets."""
    payload = runner.build_chat_payload(model, system, user)
    return {
        "op": "chat",
        "model": model,
        "system": payload["messages"][0]["content"],
        "user": payload["messages"][1]["content"],
        "temperature": payload["options"]["temperature"],
        "max_tokens": payload["options"]["num_predict"],
        "format": payload["format"],
        "keep_alive": os.environ.get("ESCALATION_KEEP_ALIVE", DEFAULT_KEEP_ALIVE),
    }


def complete(model: str, system: str, user: str) -> dict:
    """The runner backend: one ``chat`` call. A refusal raises ``DelegateError``."""
    reply = call(chat_request(model, system, user))
    if reply.get("ok") is not True:
        raise DelegateError(str(reply.get("error") or "delegate refused"))
    return {
        "text": reply.get("text", ""),
        "tokens_in": reply.get("tokens_in"),
        "tokens_out": reply.get("tokens_out"),
        "done_reason": reply.get("done_reason"),
    }


def unload(model: str) -> dict:
    """Ask the delegate to drop ``model`` from memory now."""
    return call({"op": "unload", "model": model})


def _items(shape: str, limit: int | None) -> list[dict]:
    items = runner.load_fixtures(shape)
    return items if limit is None else items[:limit]


def row_key(row: dict) -> tuple[str, str, str]:
    return (row["model"], row["shape"], row["fixture_id"])


def read_rows_file(path: Path) -> tuple[list[str], set, set, int]:
    """The rows already in ``path``: (good lines, done keys, run ids, torn-line count).

    A task killed mid-write can leave a partial last line; it is counted, not kept.
    A row with ``error`` set counts as done: a failure is a result, never retried.
    """
    good, keys, run_ids, torn = [], set(), set(), 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            key = row_key(row)
        except (ValueError, KeyError, TypeError):
            torn += 1
            continue
        good.append(line)
        keys.add(key)
        run_ids.add(row.get("run_id"))
    return good, keys, run_ids, torn


def tail_line(row: dict, n: int, total: int) -> str:
    if row["error"]:
        status = f"ERR {row['error']}"
    elif row["parse_ok"]:
        status = f"ok answer={json.dumps(row['answer'], sort_keys=True)[:60]}"
    else:
        status = "unparsed"
    return f"[{n}/{total}] {row['model']} {row['shape']} {row['fixture_id']} {status} {row['latency_ms']}ms"


def run_ladder(
    models,
    shapes,
    out,
    run_id: str,
    limit: int | None = None,
    log=sys.stderr,
    done: frozenset | set = frozenset(),
    tail: bool = False,
) -> int:
    """Each model through every shape, then unloaded, before the next model loads.

    ``done`` holds (model, shape, fixture_id) keys to skip (``--resume``). A model
    with nothing left to run is never called, so it is never loaded or unloaded.
    With ``tail``, one progress line per row goes to ``log`` as it is written.
    """
    todo = {
        model: [
            (shape, item)
            for shape in shapes
            for item in _items(shape, limit)
            if (model, shape, item["id"]) not in done
        ]
        for model in models
    }
    total = sum(len(v) for v in todo.values())
    count = 0
    for model in models:
        if not todo[model]:
            print(f"{model}: nothing left to run", file=log, flush=True)
            continue
        prompts: dict[str, str] = {}
        for shape, item in todo[model]:
            system = prompts.setdefault(shape, runner.system_prompt(shape))
            user = runner.user_prompt(shape, item)
            row = runner.make_row(run_id, model, shape, item, system, user, complete)
            out.write(json.dumps(row, sort_keys=True) + "\n")
            out.flush()
            count += 1
            if tail:
                print(tail_line(row, count, total), file=log, flush=True)
        try:
            result = unload(model)
        except (OSError, ValueError, DelegateError) as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        print(
            f"{model}: {len(todo[model])} rows; unload {json.dumps(result, sort_keys=True)}",
            file=log,
            flush=True,
        )
    return count


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    lad = sub.add_parser("ladder", help="run models one at a time, unloading each after its rows")
    lad.add_argument("--models", required=True, help="comma-separated, run in this order")
    lad.add_argument("--shapes", default=",".join(runner.SHAPES))
    lad.add_argument("--limit", type=int, default=None)
    lad.add_argument("--out", required=True)
    lad.add_argument("--run-id", default=None)
    lad.add_argument(
        "--resume",
        action="store_true",
        help="continue an existing --out: skip rows already there, append the rest",
    )
    lad.add_argument("--tail", action="store_true", help="one progress line per row on stderr")
    unl = sub.add_parser("unload", help="drop one model from memory")
    unl.add_argument("model")
    args = ap.parse_args(argv)

    if args.cmd == "unload":
        print(json.dumps(unload(args.model), sort_keys=True))
        return 0
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    shapes = [s.strip() for s in args.shapes.split(",") if s.strip()]
    bad = [s for s in shapes if s not in runner.SHAPES]
    if bad or not shapes or not models:
        ap.error(f"need models and shapes from {', '.join(runner.SHAPES)}; bad: {bad}")
    out_path = Path(args.out)
    exists = out_path.is_file() and out_path.stat().st_size > 0
    done: set = set()
    run_id = args.run_id
    if exists and not args.resume:
        ap.error(f"{out_path} already has rows; pass --resume to continue it")
    if exists:
        good, done, run_ids, torn = read_rows_file(out_path)
        if len(run_ids) > 1:
            ap.error(f"{out_path} mixes run ids {sorted(map(str, run_ids))}; not resuming")
        (existing,) = run_ids or {None}
        if run_id and existing and run_id != existing:
            ap.error(f"--run-id {run_id} does not match {existing} in {out_path}")
        run_id = run_id or existing
        if torn or not out_path.read_bytes().endswith(b"\n"):
            # Drop a torn line, and end the file on a newline, so an append
            # never glues two rows together.
            out_path.write_text("".join(line + "\n" for line in good), encoding="utf-8")
            print(f"dropped {torn} torn line(s) from {out_path}", file=sys.stderr)
        print(f"resuming {run_id}: {len(done)} row(s) already in {out_path}", file=sys.stderr)
    run_id = run_id or runner.make_run_id()
    mode = "a" if exists else "w"
    with out_path.open(mode, encoding="utf-8", newline="\n") as out:
        count = run_ladder(models, shapes, out, run_id, args.limit, done=done, tail=args.tail)
    print(f"wrote {count} rows to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
