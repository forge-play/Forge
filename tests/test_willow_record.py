"""forge/willow_record.py — the person's record, asked through the kernel.

The kernel here is a stand-in script in tmp_path that answers from a map, so
these tests need no Willow checkout. One test runs against a real kernel when
WILLOW_KERNEL names one, and says so when it can't."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from forge import willow_record
from forge.willow_record import Sealed, WillowRecord, WillowRecordError

FAKE = """
import json, sys
from pathlib import Path
argv = sys.argv[1:]
box = Path(argv[argv.index("--box") + 1])
if not (box / "kernel.json").is_file():
    print("refused: not a kernel box; init first", file=sys.stderr); sys.exit(2)
words = argv[-1]
answers = json.loads((box / "answers.json").read_text())
if words in answers:
    print(json.dumps({"state": "sealed", "answer": answers[words], "by": "proposal:" + "ab" * 32}))
    sys.exit(0)
print(json.dumps({"state": "empty", "bite_key": "x", "served": []}))
sys.exit(42)
"""


@pytest.fixture
def fake(tmp_path):
    kernel = tmp_path / "kernel.py"
    kernel.write_text(FAKE)
    box = tmp_path / "box"
    box.mkdir()
    (box / "kernel.json").write_text("{}")
    decision = json.dumps({"word": "email", "chose": "mail", "over": ["apple-mail"], "why": ""})
    (box / "answers.json").write_text(
        json.dumps(
            {
                willow_record.question("willow-email"): decision,
                willow_record.question("willow-odd"): "not json",
                willow_record.question("willow-shape"): json.dumps({"chose": 3}),
                "read my email": "## for read my email\\n- mail -- --box {box}\\n",
            }
        )
    )
    return WillowRecord(kernel, box)


def test_decision_type_is_the_word_in_the_forges_charset():
    assert willow_record.decision_type("email") == "willow-email"
    assert willow_record.decision_type("coming up") == "willow-coming-up"
    assert willow_record.decision_type("l'été!") == "willow-l-t"
    assert willow_record.question("willow-email") == "forge decision willow-email"


def test_a_sealed_decision_is_read_back_through_the_kernel(fake):
    got = fake.has_sealed("willow-email")
    assert got == Sealed(
        decision_type="willow-email", chosen="mail", word="email", subject="proposal:" + "ab" * 32
    )


def test_nothing_sealed_is_none_not_an_error(fake):
    assert fake.has_sealed("willow-due") is None
    assert fake.stack_for("something else") is None


def test_a_sealed_stack_for_the_sentence_is_its_text(fake):
    assert fake.stack_for("read my email") == "## for read my email\\n- mail -- --box {box}\\n"


def test_a_sealed_answer_that_is_not_a_decision_is_refused(fake):
    with pytest.raises(WillowRecordError, match="not a decision"):
        fake.has_sealed("willow-odd")
    with pytest.raises(WillowRecordError, match="not a decision"):
        fake.has_sealed("willow-shape")


def test_the_kernels_refusal_is_raised_with_its_words(fake, tmp_path):
    rec = WillowRecord(fake.kernel, tmp_path / "not-a-box")
    with pytest.raises(WillowRecordError, match="not a kernel box"):
        rec.has_sealed("willow-email")


def test_an_answer_that_is_not_json_is_refused(tmp_path):
    kernel = tmp_path / "kernel.py"
    kernel.write_text("print('hello')\n")
    box = tmp_path / "box"
    box.mkdir()
    with pytest.raises(WillowRecordError, match="not JSON"):
        WillowRecord(kernel, box).ask("anything")


def test_the_name_says_which_record(fake):
    assert fake.name == f"willow record at {fake.box}"


_KERNEL = os.environ.get("WILLOW_KERNEL")


@pytest.mark.skipif(not _KERNEL, reason="WILLOW_KERNEL names no kernel.py")
def test_against_a_real_kernel_a_seal_is_served_and_a_forgery_is_not(tmp_path):
    """The real loop: init, bite the decision's words, propose, seal with the
    key, ask again. Then edit the proposal's bytes and ask again: the kernel
    serves nothing, and so does this."""

    def k(*argv):
        return subprocess.run(
            [sys.executable, _KERNEL, *argv], capture_output=True, text=True, check=False
        )

    pile = tmp_path / "pile"
    pile.mkdir()
    (pile / "a.txt").write_text("nothing about email here\n")
    box, key = tmp_path / "box", tmp_path / "k.key"
    assert k("init", "--box", str(box), "--pile", str(pile), "--key", str(key)).returncode == 0
    rec = WillowRecord(Path(_KERNEL), box)
    dt = willow_record.decision_type("email")
    assert rec.has_sealed(dt) is None
    data = json.dumps({"word": "email", "chose": "mail", "over": ["apple-mail"], "why": "simpler"})
    prop = {
        "path": willow_record.DECISION_PATH.format(dt),
        "data": data,
        "cites": [],
        "claim": "simpler",
    }
    f = tmp_path / "p.jsonl"
    f.write_text(json.dumps(prop) + "\n")
    got = k("propose", "--box", str(box), "--file", str(f))
    assert got.returncode == 42, got.stderr
    subj = got.stdout.split()[1]
    assert rec.has_sealed(dt) is None, "a proposal is not an answer until sealed"
    assert k("seal", "--box", str(box), subj).returncode == 0
    assert rec.has_sealed(dt) == Sealed(dt, "mail", "email", subj)
    pf = box / "proposals" / (subj[9:] + ".json")
    pf.write_text(pf.read_text().replace("simpler", "simplest"))
    assert rec.has_sealed(dt) is None, "a changed proposal is not served"
