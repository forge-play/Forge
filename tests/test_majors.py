"""forge/majors.py — the keyword → major scan over forge/keywords.toml."""
from __future__ import annotations

import pytest

from forge import majors

SHAPE_DOC_SENTENCE = "I got sum kol sites for app to spin"
DEMO_SENTENCE = "i need summit to tell me which rally pics aint got a date on em"


def test_the_table_loads_and_every_row_has_the_three_fields():
    rows = majors.load_table()
    assert rows, "the table is the first artifact — it must not be empty"
    for r in rows:
        assert r.keyword and r.major and r.reason, r


def test_the_shape_docs_sentence_finds_site_and_app():
    hits = majors.scan(SHAPE_DOC_SENTENCE)
    by_kw = {}
    for h in hits:
        by_kw.setdefault(h.source, set()).add(h.target)
    assert by_kw["site"] == {"web"}
    assert by_kw["app"] == {"web", "mobile", "desktop"}


def test_ambiguity_is_a_detectable_condition():
    hits = majors.scan(SHAPE_DOC_SENTENCE)
    ask = majors.ambiguous_majors(hits)
    assert set(ask) == {"web", "mobile", "desktop"}
    assert ask[0] == "web", "first-seen order: `sites` comes before `app` in the sentence"


def test_the_demos_sentence_yields_two_majors_and_no_way_to_choose():
    hits = majors.scan(DEMO_SENTENCE)
    m = majors.majors_for(hits)
    assert set(m) == {"image tool", "metadata tool"}
    assert majors.ambiguous_majors(hits) == ["image tool", "metadata tool"]


def test_one_keyword_one_major_is_not_ambiguous():
    hits = majors.scan("a tiny cli that renames files")
    assert majors.majors_for(hits).keys() == {"cli"}
    assert majors.ambiguous_majors(hits) == []


def test_no_keyword_is_an_honest_empty():
    assert majors.scan("hello there") == []
    assert majors.ambiguous_majors([]) == []


def test_word_boundaries_and_case():
    assert not majors.scan("the application-server's sitemap")  # no bare keyword
    assert {h.target for h in majors.scan("A SITE.")} == {"web"}


def test_the_origin_rides_through_untouched():
    hits = majors.scan("a site", path="docs/design/x.md", anchor="#L12")
    assert hits and all(h.path == "docs/design/x.md" and h.anchor == "#L12" for h in hits)
    assert all(h.path == "" and h.anchor == "" for h in majors.scan("a site"))


def test_a_broken_table_is_a_refusal_not_an_empty(tmp_path):
    bad = tmp_path / "keywords.toml"
    bad.write_text('[[map]]\nkeyword = "x"\nmajor = "y"\n')  # no reason
    with pytest.raises(majors.MajorsError):
        majors.load_table(bad)
    bad.write_text("this is not toml = = =")
    with pytest.raises(majors.MajorsError):
        majors.load_table(bad)


def test_scan_is_deterministic():
    a = majors.scan(SHAPE_DOC_SENTENCE)
    b = majors.scan(SHAPE_DOC_SENTENCE)
    assert a == b
