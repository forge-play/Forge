"""tests/test_escalation_socket_backend.py: the Unix-socket runner backend.

A fake delegate listens on a temporary Unix socket and answers one JSON line per
connection, the way the host delegate does. No model and no network.

Stdlib and pytest only.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "benchmarks" / "escalation"

pytestmark = pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="needs Unix sockets")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"escalation_{name}", BENCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


backend = _load("socket_backend")
runner = backend.runner

GOOD = json.dumps({"answer": "ESCALATE", "confidence": 0.7})


class FakeDelegate:
    """Records every request; ``replies`` maps an op to its reply (a dict or a callable)."""

    def __init__(self, path: str):
        self.path = path
        self.seen: list[dict] = []
        self.replies: dict = {
            "chat": {"ok": True, "text": GOOD, "tokens_in": 11, "tokens_out": 3},
            "unload": {"ok": True, "done_reason": "unload"},
        }
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(path)
        self.server.listen(8)
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                data = b""
                while b"\n" not in data:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                req = json.loads(data.split(b"\n", 1)[0])
                self.seen.append(req)
                reply = self.replies.get(req.get("op"), {"ok": False, "error": "unknown op"})
                if callable(reply):
                    reply = reply(req)
                conn.sendall(json.dumps(reply).encode() + b"\n")

    def close(self):
        self.server.close()


@pytest.fixture
def delegate(monkeypatch):
    # A short directory: a Unix socket path is limited to about 100 bytes.
    tmp = tempfile.mkdtemp(prefix="esc")
    fake = FakeDelegate(os.path.join(tmp, "d.sock"))
    monkeypatch.setenv("ESCALATION_SOCKET", fake.path)
    monkeypatch.setenv("ESCALATION_SOCKET_TIMEOUT", "5")
    monkeypatch.delenv("ESCALATION_KEEP_ALIVE", raising=False)
    try:
        yield fake
    finally:
        fake.close()
        shutil.rmtree(tmp, ignore_errors=True)


def test_chat_request_matches_the_ollama_http_payload(delegate):
    out = backend.complete("llama3.2:3b", "sys", "usr")
    assert out == {"text": GOOD, "tokens_in": 11, "tokens_out": 3, "done_reason": None}
    (req,) = delegate.seen
    payload = runner.build_chat_payload("llama3.2:3b", "sys", "usr")
    assert req == {
        "op": "chat",
        "model": "llama3.2:3b",
        "system": "sys",
        "user": "usr",
        "temperature": 0,
        "max_tokens": runner.MAX_OUTPUT_TOKENS,
        "format": runner.ANSWER_SCHEMA,
        "keep_alive": backend.DEFAULT_KEEP_ALIVE,
    }
    assert req["format"] == payload["format"]
    assert req["max_tokens"] == payload["options"]["num_predict"]


@pytest.mark.parametrize("model", ["gemma4:e2b", "qwen3:4b", "qwen3.5:latest"])
def test_thinking_off_reaches_the_delegate_for_models_that_think(delegate, model):
    backend.complete(model, "sys", "usr")
    assert delegate.seen[0]["think"] is False


@pytest.mark.parametrize("model", ["llama3.2:3b", "gemma3:4b", "phi4-mini:latest"])
def test_no_think_field_for_models_that_do_not_think(delegate, model):
    backend.complete(model, "sys", "usr")
    assert "think" not in delegate.seen[0]


def test_a_length_stop_from_the_delegate_reaches_the_row(delegate):
    delegate.replies["chat"] = {"ok": True, "text": '{"answer": ', "done_reason": "length"}
    buf = io.StringIO()
    runner.run_benchmark(backend.complete, ["m"], ["route"], buf, "run-test", limit=1)
    (row,) = [json.loads(line) for line in buf.getvalue().splitlines()]
    assert row["done_reason"] == "length"
    assert row["parse_ok"] is False and row["error"] is None


def test_qwen_gets_the_no_think_suffix(delegate):
    backend.complete("qwen3:4b", "sys", "usr")
    assert delegate.seen[0]["user"] == f"usr\n{runner.NO_THINK_SUFFIX}"


def test_keep_alive_comes_from_the_environment(delegate, monkeypatch):
    monkeypatch.setenv("ESCALATION_KEEP_ALIVE", "2m")
    backend.complete("m", "s", "u")
    assert delegate.seen[0]["keep_alive"] == "2m"


def test_a_refusal_raises_and_becomes_an_error_row(delegate):
    delegate.replies["chat"] = {
        "ok": False,
        "error": "EMODEL: 'm' is not in the local-model allow-list",
    }
    buf = io.StringIO()
    runner.run_benchmark(backend.complete, ["m"], ["judge"], buf, "run-test", limit=2)
    rows = [json.loads(line) for line in buf.getvalue().splitlines()]
    assert len(rows) == 2 == len(delegate.seen), "a refusal is never retried"
    for row in rows:
        assert row["error"].startswith("DelegateError: EMODEL")
        assert row["parse_ok"] is False


def test_no_socket_configured_raises(monkeypatch):
    monkeypatch.delenv("ESCALATION_SOCKET", raising=False)
    with pytest.raises(backend.DelegateError, match="ESCALATION_SOCKET"):
        backend.complete("m", "s", "u")


def test_unload_sends_the_unload_op(delegate):
    assert backend.unload("gemma3:4b")["ok"] is True
    assert delegate.seen == [{"op": "unload", "model": "gemma3:4b"}]


def test_ladder_unloads_each_model_before_the_next_loads(delegate):
    buf, log = io.StringIO(), io.StringIO()
    n = backend.run_ladder(["a", "b"], ["route", "ground"], buf, "run-test", limit=2, log=log)
    assert n == 8
    ops = [(r["op"], r["model"]) for r in delegate.seen]
    assert ops == [("chat", "a")] * 4 + [("unload", "a")] + [("chat", "b")] * 4 + [("unload", "b")]
    rows = [json.loads(line) for line in buf.getvalue().splitlines()]
    assert [r["model"] for r in rows] == ["a"] * 4 + ["b"] * 4
    assert all(r["run_id"] == "run-test" and r["error"] is None for r in rows)
    assert "a: 4 rows; unload" in log.getvalue()


def test_a_failed_unload_is_logged_and_the_ladder_goes_on(delegate):
    delegate.replies["unload"] = {"ok": False, "error": "ECHAT: connection refused"}
    log = io.StringIO()
    n = backend.run_ladder(["a", "b"], ["judge"], io.StringIO(), "run-test", limit=1, log=log)
    assert n == 2
    assert log.getvalue().count("ECHAT: connection refused") == 2


def test_ladder_cli_writes_rows(delegate, tmp_path):
    out = tmp_path / "rows.jsonl"
    rc = backend.main(
        [
            "ladder",
            "--models",
            "a",
            "--shapes",
            "classify",
            "--limit",
            "2",
            "--out",
            str(out),
            "--run-id",
            "r1",
        ]
    )
    assert rc == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [r["fixture_id"] for r in rows] == ["classify-001", "classify-002"]
    assert delegate.seen[-1] == {"op": "unload", "model": "a"}


# --- --resume and --tail -------------------------------------------------------


def _ladder(out, *extra):
    return backend.main(
        [
            "ladder",
            "--models",
            "a,b",
            "--shapes",
            "judge",
            "--limit",
            "3",
            "--out",
            str(out),
            *extra,
        ]
    )


def _rows(out):
    return [json.loads(line) for line in out.read_text().splitlines()]


def test_existing_rows_are_never_overwritten_without_resume(delegate, tmp_path):
    out = tmp_path / "rows.jsonl"
    assert _ladder(out, "--run-id", "r1") == 0
    before = out.read_text()
    with pytest.raises(SystemExit):
        _ladder(out, "--run-id", "r1")
    assert out.read_text() == before


def test_resume_runs_only_what_is_missing_and_appends(delegate, tmp_path):
    out = tmp_path / "rows.jsonl"
    assert _ladder(out, "--run-id", "r1") == 0
    kept = out.read_text().splitlines()
    # Keep a's three rows and b's first: as if the task died during b.
    out.write_text("\n".join(kept[:4]) + "\n")
    delegate.seen.clear()
    assert _ladder(out, "--resume") == 0
    assert [(r["op"], r["model"]) for r in delegate.seen] == [("chat", "b")] * 2 + [("unload", "b")]
    rows = _rows(out)
    assert out.read_text().splitlines()[:4] == kept[:4], "existing rows are left as they were"
    assert [(r["model"], r["fixture_id"]) for r in rows] == [
        ("a", "judge-001"),
        ("a", "judge-002"),
        ("a", "judge-003"),
        ("b", "judge-001"),
        ("b", "judge-002"),
        ("b", "judge-003"),
    ]
    assert {r["run_id"] for r in rows} == {"r1"}, "the file's run id is kept"


def test_resume_of_a_finished_file_calls_nothing(delegate, tmp_path):
    out = tmp_path / "rows.jsonl"
    assert _ladder(out, "--run-id", "r1") == 0
    delegate.seen.clear()
    assert _ladder(out, "--resume") == 0
    assert delegate.seen == [], "a model with nothing left is never loaded or unloaded"
    assert len(_rows(out)) == 6


def test_resume_counts_an_error_row_as_done(delegate, tmp_path):
    out = tmp_path / "rows.jsonl"
    delegate.replies["chat"] = {"ok": False, "error": "ECHAT: timed out"}
    assert _ladder(out, "--run-id", "r1") == 0
    delegate.replies["chat"] = {"ok": True, "text": GOOD}
    delegate.seen.clear()
    assert _ladder(out, "--resume") == 0
    assert delegate.seen == [], "a failure is a result: resume never retries it"


def test_resume_drops_a_torn_last_line(delegate, tmp_path):
    out = tmp_path / "rows.jsonl"
    assert _ladder(out, "--run-id", "r1") == 0
    kept = out.read_text().splitlines()
    out.write_text("\n".join(kept[:2]) + "\n" + kept[2][:25])
    delegate.seen.clear()
    assert _ladder(out, "--resume") == 0
    rows = _rows(out)
    assert len(rows) == 6
    assert len({(r["model"], r["fixture_id"]) for r in rows}) == 6


def test_resume_ends_an_unterminated_last_row_before_appending(delegate, tmp_path):
    out = tmp_path / "rows.jsonl"
    assert _ladder(out, "--run-id", "r1") == 0
    kept = out.read_text().splitlines()
    out.write_text("\n".join(kept[:3]))
    assert _ladder(out, "--resume") == 0
    assert len(_rows(out)) == 6


def test_resume_refuses_a_different_run_id(delegate, tmp_path):
    out = tmp_path / "rows.jsonl"
    assert _ladder(out, "--run-id", "r1") == 0
    with pytest.raises(SystemExit):
        _ladder(out, "--resume", "--run-id", "r2")


def test_resume_on_a_missing_file_starts_fresh(delegate, tmp_path):
    out = tmp_path / "rows.jsonl"
    assert _ladder(out, "--resume", "--run-id", "r1") == 0
    assert len(_rows(out)) == 6


def test_tail_prints_one_line_per_row(delegate):
    log = io.StringIO()
    backend.run_ladder(["a"], ["judge"], io.StringIO(), "r", limit=2, log=log, tail=True)
    lines = [ln for ln in log.getvalue().splitlines() if ln.startswith("[")]
    assert lines[0].startswith("[1/2] a judge judge-001 ok answer=")
    assert lines[1].startswith("[2/2] a judge judge-002 ok ")
    assert lines[1].endswith("ms")


def test_tail_shows_errors(delegate):
    delegate.replies["chat"] = {"ok": False, "error": "EMODEL: nope"}
    log = io.StringIO()
    backend.run_ladder(["a"], ["judge"], io.StringIO(), "r", limit=1, log=log, tail=True)
    assert "[1/1] a judge judge-001 ERR DelegateError: EMODEL: nope" in log.getvalue()


def test_no_tail_no_row_lines(delegate):
    log = io.StringIO()
    backend.run_ladder(["a"], ["judge"], io.StringIO(), "r", limit=2, log=log)
    assert not any(ln.startswith("[") for ln in log.getvalue().splitlines())
