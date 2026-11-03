"""forge/card_box.py — the box over Willow's cards, tier 2 of the entry."""

from __future__ import annotations

import pytest

from forge import card_box, majors
from tests.test_card_table import make_willow

SENTENCE = "I want to read my email about the flat and know when the boiler is due"


@pytest.fixture
def box(tmp_path):
    return card_box.CardBox(make_willow(tmp_path / "Willow"))


def test_the_box_names_itself_and_what_it_holds(box):
    assert box.name.endswith("(7 built, 1 ideas)")


def test_a_sentence_finds_the_cards_it_names_or_aliases(box):
    found = box.lookup(box.scan(SENTENCE))
    assert [c.name for c in found] == ["apple-mail", "mail", "coming-up", "renewals"]
    mail = found[1]
    assert mail.where == "adapters/stdlib/mail/README.md"
    assert mail.why == "what “email” usually means here"


def test_naming_a_card_is_said_as_such(box):
    found = box.lookup(box.scan("run coming up over my notes"))
    assert [(c.name, c.why) for c in found] == [("coming-up", "you named it")]


def test_an_idea_is_a_candidate_that_says_so(box):
    found = box.lookup(box.scan("I'd like email-ask on this"))
    assert [c.name for c in found] == ["email-ask"]
    assert found[0].why == "you named it (an idea, not built)"
    assert found[0].where == "adapters/planned.json"


def test_a_sentence_about_something_else_finds_nothing_honestly(box):
    hits = box.scan("a site for my running club with the race dates")
    assert hits == [] and box.lookup(hits) == [] and box.forks(hits) == {}


def test_hits_for_majors_the_box_does_not_hold_are_passed_over(box):
    web = majors.scan("a site", table=majors.load_table())
    assert [h.target for h in web] == ["web"]
    assert box.lookup(web) == []
    both = web + box.scan("and my email")
    assert [c.name for c in box.lookup(both)] == ["apple-mail", "mail"]


def test_forks_are_one_word_reaching_several_add_ons(box):
    hits = box.scan(SENTENCE)
    assert box.forks(hits) == {"email": ["apple-mail", "mail"], "due": ["coming-up", "renewals"]}
    assert box.forks(box.scan("coming up")) == {}, "one add-on is not a fork"


def test_each_add_on_is_a_candidate_once(box):
    found = box.lookup(box.scan("email, email, and more email"))
    assert [c.name for c in found] == ["apple-mail", "mail"]


def test_cli_found_none_and_refused(tmp_path, capsys):
    w = make_willow(tmp_path / "Willow")
    assert card_box.main([SENTENCE, "--willow", str(w)]) == 0
    out = capsys.readouterr().out
    assert "cand    mail" in out and "fork    “email” could be apple-mail, mail" in out
    assert card_box.main(["a site for my running club", "--willow", str(w)]) == 1
    assert "nothing named" in capsys.readouterr().out
    assert card_box.main([SENTENCE, "--willow", str(tmp_path)]) == 2
    assert "REFUSED: " in capsys.readouterr().err


def test_cli_json_carries_candidates_and_forks(tmp_path, capsys):
    import json

    w = make_willow(tmp_path / "Willow")
    assert card_box.main([SENTENCE, "--willow", str(w), "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert [c["name"] for c in d["candidates"]] == ["apple-mail", "mail", "coming-up", "renewals"]
    assert d["forks"]["due"] == ["coming-up", "renewals"]
