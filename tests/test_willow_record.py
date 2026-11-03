"""forge/willow_record.py — the person's record, asked and proposed to
through the kernel.

The kernel here is a stand-in script in tmp_path that answers from a map and
takes proposals, so these tests need no Willow checkout. One test runs
against a real kernel when WILLOW_KERNEL names one, and says so when it
can't."""

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
import hashlib, json, sys
from pathlib import Path
argv = sys.argv[1:]
verb = argv[0]
box = Path(argv[argv.index("--box") + 1])
if not (box / "kernel.json").is_file():
    print("refused: not a kernel box; init first", file=sys.stderr); sys.exit(2)
log = box / "asked.log"
if verb == "bite":
    words = argv[-1]
    log.open("a", encoding="utf-8").write(words + "\\n")
    answers = json.loads((box / "answers.json").read_text(encoding="utf-8"))
    if words in answers:
        print(json.dumps({"state": "sealed", "answer": answers[words], "by": "proposal:" + "ab" * 32}))
        sys.exit(0)
    print(json.dumps({"state": "empty", "bite_key": "x", "served": []}))
    sys.exit(42)
if verb == "propose":
    line = Path(argv[argv.index("--file") + 1]).read_text(encoding="utf-8").splitlines()[0]
    prop = json.loads(line)
    if "bad" in prop["claim"]:
        print("refused  line 0: a claim says why"); sys.exit(42)
    (box / "proposed.jsonl").open("a", encoding="utf-8").write(line + "\\n")
    print("pass  proposal:" + hashlib.sha256(line.encode()).hexdigest() + "  waiting on your seal")
    sys.exit(42)
sys.exit(2)
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


def asked(rec: WillowRecord) -> list[str]:
    f = rec.box / "asked.log"
    return f.read_text(encoding="utf-8").splitlines() if f.is_file() else []


def test_decision_type_is_the_word_in_the_forges_charset():
    assert willow_record.decision_type("email") == "willow-email"
    assert willow_record.decision_type("coming up") == "willow-coming-up"
    assert willow_record.decision_type("l'été!") == "willow-l-t"
    assert willow_record.question("willow-email") == "forge decision willow-email"


def test_a_willow_record_is_a_record_lookup(fake):
    assert isinstance(fake, willow_record.RecordLookup)


def test_a_sealed_decision_is_read_back_through_the_kernel(fake):
    got = fake.has_sealed("willow-email")
    assert got == Sealed(
        decision_type="willow-email", chosen="mail", word="email", subject="proposal:" + "ab" * 32
    )
    assert asked(fake) == ["forge decision willow-email"], "every question is a row"


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
    with pytest.raises(WillowRecordError, match="not a kernel box"):
        rec.propose("major", "web", over=["cli"], why="")


def test_an_answer_that_is_not_json_is_refused(tmp_path):
    kernel = tmp_path / "kernel.py"
    kernel.write_text("print('hello')\n")
    box = tmp_path / "box"
    box.mkdir()
    with pytest.raises(WillowRecordError, match="not JSON"):
        WillowRecord(kernel, box).ask("anything")


def test_propose_bites_the_words_first_then_hands_one_line_to_the_door(fake):
    subject = fake.propose(
        "major", "web", over=["mobile", "desktop"], why="a site is served", surface="site or app?"
    )
    assert subject.startswith("proposal:") and len(subject) == 9 + 64
    assert asked(fake) == ["forge decision major"]
    line = (fake.box / "proposed.jsonl").read_text(encoding="utf-8").splitlines()[0]
    prop = json.loads(line)
    assert prop["path"] == "forge/decisions/major.json" and prop["cites"] == []
    assert prop["claim"] == "for 'major': web over mobile, desktop; a site is served"
    data = json.loads(prop["data"])
    assert data == {
        "chose": "web",
        "decision_type": "major",
        "over": ["mobile", "desktop"],
        "surface": "site or app?",
        "why": "a site is served",
        "word": "major",
    }
    assert "'word': 'major'" not in prop["data"], "the add-on reads word and chose from JSON"


def test_propose_names_the_word_said_when_given_one_and_says_no_reason(fake):
    fake.propose("willow-email", "mail", over=["apple-mail"], why="", word="email")
    prop = json.loads((fake.box / "proposed.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert json.loads(prop["data"])["word"] == "email"
    assert prop["claim"].endswith("no reason given")


def test_a_proposal_the_door_turns_back_is_raised(fake):
    with pytest.raises(WillowRecordError, match="turned the proposal back"):
        fake.propose("major", "web", over=[], why="bad")


def test_the_name_says_which_record(fake):
    assert fake.name == f"willow record at {fake.box}"


_KERNEL = os.environ.get("WILLOW_KERNEL")


@pytest.mark.skipif(not _KERNEL, reason="WILLOW_KERNEL names no kernel.py")
def test_against_a_real_kernel_a_seal_is_served_and_a_forgery_is_not(tmp_path):
    """The real loop: init, propose through this module, seal with the key,
    ask again. Then edit the proposal's bytes and ask again: the kernel
    serves nothing, and so does this. Then a second proposal for the same
    words, sealed: the kernel still serves the first."""

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
    subj = rec.propose(dt, "mail", over=["apple-mail"], why="simpler", word="email")
    assert rec.has_sealed(dt) is None, "a proposal is not an answer until sealed"
    assert k("seal", "--box", str(box), subj).returncode == 0
    assert rec.has_sealed(dt) == Sealed(dt, "mail", "email", subj)
    second = rec.propose(dt, "apple-mail", over=["mail"], why="changed my mind", word="email")
    assert k("seal", "--box", str(box), second).returncode == 0
    assert rec.has_sealed(dt).chosen == "mail", "the first standing seal is the kernel's answer"
    pf = box / "proposals" / (subj[9:] + ".json")
    pf.write_text(pf.read_text().replace("simpler", "simplest"))
    assert rec.has_sealed(dt).chosen == "apple-mail", "the first no longer stands; the second does"
    assert k("verify", "--box", str(box)).returncode == 42, "and verify says a sealed file drifted"
