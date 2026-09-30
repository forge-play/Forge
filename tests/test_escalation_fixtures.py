"""tests/test_escalation_fixtures.py: the escalation benchmark's public fixtures.

The fixtures under ``benchmarks/escalation/`` are invented, public and published.
These tests hold their shape: the per-file counts, the exact 20% of items whose
only correct reply is ``ESCALATE``, every line's schema, the tool catalogue the
route items are written against, the ground answers being verbatim in their
passages, the manifest, and the privacy gate exiting clean on the tree.

Stdlib and pytest only. The gate is run as a subprocess, the way CI runs it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "benchmarks" / "escalation"
FIXTURES = BENCH / "fixtures"
GATE = BENCH / "gate" / "privacy_gate.py"

COUNTS = {"route": 60, "classify": 50, "judge": 50, "ground": 40}
ESCALATE_COUNTS = {"route": 12, "classify": 10, "judge": 10, "ground": 8}
LINE_KEYS = {"id", "shape", "input", "expected", "answerable", "confidence_hint", "rationale"}
REQUIRED_KEYS = LINE_KEYS - {"confidence_hint"}
STATUSES = {"resolved", "in_progress", "blocked", "wontfix"}
SEVERITIES = {"low", "medium", "high"}
VERDICTS = {"SUPPORTS", "CONTRADICTS", "UNRELATED"}
ESCALATE = "ESCALATE"


def load(shape: str) -> list[dict]:
    lines = (FIXTURES / f"{shape}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def catalog() -> dict[str, dict]:
    data = json.loads((BENCH / "catalog" / "tools.json").read_text(encoding="utf-8"))
    return {tool["name"]: tool for tool in data["tools"]}


def run_gate(root: Path, *extra: str, env_extra: dict | None = None):
    env = {k: v for k, v in os.environ.items() if k != "ESCALATION_GATE_DENYLIST"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-B", str(root / "gate" / "privacy_gate.py"), "--root", str(root), *extra],
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def scratch(tmp_path):
    """A throwaway copy of the benchmark tree that a test may damage."""
    dest = tmp_path / "escalation"
    shutil.copytree(BENCH, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


# --- counts and the escalate share ------------------------------------------


@pytest.mark.parametrize("shape", COUNTS)
def test_per_file_counts(shape):
    assert len(load(shape)) == COUNTS[shape]


def test_two_hundred_items_in_all():
    assert sum(len(load(s)) for s in COUNTS) == 200


@pytest.mark.parametrize("shape", COUNTS)
def test_exactly_twenty_percent_escalate(shape):
    items = load(shape)
    unanswerable = [i for i in items if i["answerable"] is False]
    assert len(unanswerable) == ESCALATE_COUNTS[shape]
    assert len(unanswerable) * 5 == len(items)


@pytest.mark.parametrize("shape", COUNTS)
def test_escalate_and_answerable_agree(shape):
    for item in load(shape):
        assert (item["expected"] == ESCALATE) == (item["answerable"] is False), item["id"]


@pytest.mark.parametrize("shape", COUNTS)
def test_escalate_items_are_mixed_not_grouped(shape):
    run = longest = 0
    for item in load(shape):
        run = run + 1 if item["answerable"] is False else 0
        longest = max(longest, run)
    assert longest <= 2


# --- schema ------------------------------------------------------------------


@pytest.mark.parametrize("shape", COUNTS)
def test_line_schema(shape):
    for item in load(shape):
        keys = set(item)
        assert REQUIRED_KEYS <= keys <= LINE_KEYS, item["id"]
        assert item["shape"] == shape, item["id"]
        assert isinstance(item["id"], str) and item["id"].startswith(f"{shape}-")
        assert isinstance(item["answerable"], bool), item["id"]
        assert isinstance(item["rationale"], str) and item["rationale"].strip(), item["id"]
        if "confidence_hint" in item:
            hint = item["confidence_hint"]
            assert isinstance(hint, float) and 0.5 <= hint <= 0.99, item["id"]


def test_ids_are_unique_across_every_file():
    ids = [item["id"] for shape in COUNTS for item in load(shape)]
    assert len(ids) == len(set(ids))


def test_route_and_classify_input_is_a_nonempty_line():
    for shape in ("route", "classify"):
        for item in load(shape):
            assert isinstance(item["input"], str) and item["input"].strip(), item["id"]
            assert "\n" not in item["input"], item["id"]


def test_classify_expected_shape():
    for item in load("classify"):
        exp = item["expected"]
        if exp == ESCALATE:
            continue
        assert set(exp) == {"status", "severity", "needs_human"}, item["id"]
        assert exp["status"] in STATUSES, item["id"]
        assert exp["severity"] in SEVERITIES, item["id"]
        assert isinstance(exp["needs_human"], bool), item["id"]


def test_judge_shape():
    for item in load("judge"):
        assert set(item["input"]) == {"claim", "document"}, item["id"]
        assert all(isinstance(v, str) and v.strip() for v in item["input"].values()), item["id"]
        assert item["expected"] in VERDICTS | {ESCALATE}, item["id"]


def test_ground_shape():
    for item in load("ground"):
        assert set(item["input"]) == {"passage", "question"}, item["id"]
        assert all(isinstance(v, str) and v.strip() for v in item["input"].values()), item["id"]
        assert isinstance(item["expected"], str) and item["expected"].strip(), item["id"]


def test_ground_answers_appear_verbatim_in_the_passage():
    for item in load("ground"):
        if item["expected"] == ESCALATE:
            continue
        assert item["expected"] in item["input"]["passage"], item["id"]


# --- the tool catalogue and the route items ----------------------------------

_TYPES = {"string": str, "integer": int, "number": (int, float)}


def _valid_value(spec: dict, value) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, _TYPES[spec["type"]]):
        return False
    return value in spec["enum"] if "enum" in spec else True


def test_catalogue_has_twenty_distinct_documented_tools():
    tools = catalog()
    assert len(tools) == 20
    for name, tool in tools.items():
        assert name.replace("_", "").isalnum() and name == name.lower(), name
        assert tool["description"].strip() and tool["description"].endswith("."), name
        params = tool["parameters"]
        assert params["type"] == "object"
        assert set(params["required"]) <= set(params["properties"]), name
        for spec in params["properties"].values():
            assert spec["type"] in _TYPES, name


def test_every_route_answer_names_a_real_tool_with_valid_args():
    tools = catalog()
    for item in load("route"):
        exp = item["expected"]
        if exp == ESCALATE:
            continue
        assert set(exp) == {"tool", "args"}, item["id"]
        assert exp["tool"] in tools, item["id"]
        params = tools[exp["tool"]]["parameters"]
        args = exp["args"]
        assert set(args) <= set(params["properties"]), item["id"]
        assert set(params["required"]) <= set(args), item["id"]
        for key, value in args.items():
            assert _valid_value(params["properties"][key], value), (item["id"], key)


def test_every_tool_is_used_by_some_route_item():
    used = {i["expected"]["tool"] for i in load("route") if i["expected"] != ESCALATE}
    assert used == set(catalog())


# --- the manifest ------------------------------------------------------------


def test_manifest_matches_the_files():
    manifest = json.loads((BENCH / "manifest.json").read_text(encoding="utf-8"))
    listed = {entry["path"]: entry for entry in manifest["files"]}
    on_disk = sorted(
        p.relative_to(BENCH).as_posix()
        for sub in ("catalog", "fixtures")
        for p in (BENCH / sub).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    assert manifest["file_count"] == len(listed) == len(on_disk) == 5
    assert sorted(listed) == on_disk
    for rel, entry in listed.items():
        data = (BENCH / rel).read_bytes()
        assert entry["sha256"] == hashlib.sha256(data).hexdigest(), rel
        assert entry["lines"] == data.count(b"\n"), rel


def test_manifest_line_counts_agree_with_the_item_counts():
    manifest = json.loads((BENCH / "manifest.json").read_text(encoding="utf-8"))
    lines = {entry["path"]: entry["lines"] for entry in manifest["files"]}
    for shape, count in COUNTS.items():
        assert lines[f"fixtures/{shape}.jsonl"] == count


# --- the privacy gate --------------------------------------------------------


def test_privacy_gate_exits_zero_on_the_tree():
    result = run_gate(BENCH)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


@pytest.mark.parametrize(
    ("leak", "cls"),
    [
        ("see /home/someone/x for it", "abs-path"),
        ("open C:\\Users\\someone\\x now", "abs-path"),
        ("open file:///etc/hosts now", "file-uri"),
        ("write to person@example.org", "email"),
        ("call 415-555-0134 today", "phone"),
        ("call +14155550134 today", "phone"),
        ("key " + "ghp" + "_" + "a1B2c3D4e5F6g7H8", "token"),
        ("key " + "sk" + "-" + "a1B2c3D4e5F6g7H8", "token"),
        ("key " + "AKIA" + "ABCDEFGH12345678", "token"),
        ("digest " + "0123456789abcdef" * 2, "token"),
        ("blob " + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1dE3fG5", "token"),
    ],
)
def test_privacy_gate_flags_each_leak_class(scratch, leak, cls):
    with open(scratch / "fixtures" / "route.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"id": "route-999", "note": leak}) + "\n")
    result = run_gate(scratch)
    assert result.returncode == 1, result.stdout
    assert f"FAIL {cls} fixtures/route.jsonl:" in result.stdout
    assert leak not in result.stdout, "the gate must not echo what it found"


def test_privacy_gate_flags_a_leak_hidden_in_a_json_escape(scratch):
    # "\u002fhome\u002fx" decodes to an absolute path; the raw text has no slash.
    line = '{"id": "route-999", "note": "\\u002fhome\\u002fsomeone"}\n'
    with open(scratch / "fixtures" / "route.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
    result = run_gate(scratch)
    assert result.returncode == 1
    assert "FAIL abs-path fixtures/route.jsonl:61" in result.stdout


def test_privacy_gate_flags_binary_archive_and_non_utf8_files(scratch):
    (scratch / "fixtures" / "extra.zip").write_bytes(b"PK\x03\x04\x00\x00")
    (scratch / "fixtures" / "latin.txt").write_bytes(b"caf\xe9\n")
    result = run_gate(scratch)
    assert result.returncode == 1
    assert "FAIL archive-extension fixtures/extra.zip" in result.stdout
    assert "FAIL binary fixtures/extra.zip" in result.stdout
    assert "FAIL not-utf8 fixtures/latin.txt" in result.stdout


def test_privacy_gate_flags_a_lookalike_letter_in_a_key_and_an_id(scratch):
    # U+0430 is a Cyrillic letter that renders like a Latin a.
    bad = '{"\u0430nswer": 1, "id": "route-\u0430"}\n'
    with open(scratch / "fixtures" / "route.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.write(bad)
    result = run_gate(scratch)
    assert result.returncode == 1
    assert "FAIL confusable-key fixtures/route.jsonl:61" in result.stdout
    assert "FAIL confusable-id fixtures/route.jsonl:61" in result.stdout


def test_privacy_gate_flags_a_file_outside_the_layout(scratch):
    (scratch / "notes.md").write_text("hello\n", encoding="utf-8")
    result = run_gate(scratch)
    assert result.returncode == 1
    assert "FAIL unexpected-file notes.md" in result.stdout


def test_privacy_gate_flags_a_manifest_that_disagrees(scratch):
    path = scratch / "fixtures" / "ground.jsonl"
    path.write_bytes(path.read_bytes().replace(b"Corran", b"Corrin", 1))
    result = run_gate(scratch)
    assert result.returncode == 1
    assert "FAIL manifest-sha-mismatch fixtures/ground.jsonl" in result.stdout


def test_privacy_gate_denylist_is_read_at_run_time(scratch, tmp_path):
    deny = tmp_path / "deny.txt"
    deny.write_text("# a comment\n\nLIGHTHOUSE\n", encoding="utf-8")
    hit = run_gate(scratch, "--denylist", str(deny))
    assert hit.returncode == 1
    assert "FAIL denylist fixtures/" in hit.stdout
    assert "lighthouse" not in hit.stdout.lower()
    via_env = run_gate(scratch, env_extra={"ESCALATION_GATE_DENYLIST": str(deny)})
    assert via_env.returncode == 1
    deny.write_text("zzzz-no-such-term\n", encoding="utf-8")
    assert run_gate(scratch, "--denylist", str(deny)).returncode == 0


def test_privacy_gate_denylist_never_prints_its_terms(scratch, tmp_path):
    deny = tmp_path / "deny.txt"
    deny.write_text("secretterm-quux\n", encoding="utf-8")
    with open(scratch / "fixtures" / "route.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.write('{"id": "route-999", "note": "has SecretTerm-Quux inside"}\n')
    result = run_gate(scratch, "--denylist", str(deny))
    assert result.returncode == 1
    assert "FAIL denylist fixtures/route.jsonl:61" in result.stdout
    assert "quux" not in result.stdout.lower()


def test_privacy_gate_missing_denylist_file_is_a_usage_error(scratch, tmp_path):
    result = run_gate(scratch, "--denylist", str(tmp_path / "absent.txt"))
    assert result.returncode == 2
