"""forge/card_table.py — Willow's cards as rows for the keyword scan.

A small Willow checkout is made under tmp_path: five built cards, one deps
card, one planned idea, and an alias file. Nothing here reads a real Willow.
"""

from __future__ import annotations

import json

import pytest

from forge import card_table, majors

CARDS = {
    "stdlib/mail": ("Reading more kinds of files", "Email in .eml and mbox, as text.", "to"),
    "stdlib/apple-mail": (
        "Reading more kinds of files",
        "Apple Mail's .emlx messages, read as mail reads an .eml.",
        "to",
    ),
    "stdlib/coming-up": ("Keeping track", "Dates in your files in the next N days.", "nothing"),
    "stdlib/renewals": ("Keeping track", "What renews when, from your files.", "nothing"),
    "stdlib/all": ("Finding things", "Every passage that holds the words, not three.", "nothing"),
    "stdlib/claim-check": ("Trust and proof", "A claim split into its parts.", "nothing"),
    "deps/pdf": ("Reading more kinds of files", "Text out of PDFs.", "to"),
}

ALIASES = """# how people ask
email = mail, eml, mbox
due = coming, deadline, renewals
everything = all
"""


def make_willow(root, aliases=ALIASES, planned=None):
    for rel, (section, line, writes) in CARDS.items():
        folder = root / "adapters" / rel
        folder.mkdir(parents=True)
        needs = "needs: pypdf; BSD-3-Clause\n" if rel == "deps/pdf" else ""
        (folder / "README.md").write_text(
            f"<!-- willow-addon\nsection: {section}\nline: {line}\nsource: new\n"
            f"added: 2026-10-23\n{needs}writes: {writes}\nnetwork: none\n-->\n# card\n"
        )
    if planned is None:
        planned = [
            {
                "name": "email-ask",
                "kind": "stdlib",
                "section": "Ways to use it",
                "line": "Ask by email, answered by email.",
                "writes": "record",
                "network": "the mail server you name",
            }
        ]
    (root / "adapters" / "planned.json").write_text(json.dumps(planned, indent=1) + "\n")
    if aliases is not None:
        (root / "ui").mkdir()
        (root / "ui" / "search-words.txt").write_text(aliases)
    return root


@pytest.fixture
def willow(tmp_path):
    return make_willow(tmp_path / "Willow")


def test_every_card_is_read_built_first_then_ideas(willow):
    cards = card_table.read_cards(willow)
    assert [c.name for c in cards] == [
        "all",
        "apple-mail",
        "claim-check",
        "coming-up",
        "mail",
        "pdf",
        "renewals",
        "email-ask",
    ]
    pdf = next(c for c in cards if c.name == "pdf")
    assert (
        pdf.built and pdf.needs.startswith("pypdf") and pdf.where == "adapters/deps/pdf/README.md"
    )
    idea = cards[-1]
    assert not idea.built and idea.where == "adapters/planned.json"
    assert idea.line == "Ask by email, answered by email."


def test_where_is_posix_whatever_the_platform_separator(willow, monkeypatch):
    """`where` goes into proposals and is compared across machines: it is an
    identifier, so it is written with `/` even where the platform joins with
    `\\` (the Windows leg found this on the first run)."""
    cards = {c.name: c for c in card_table.read_cards(willow)}
    assert cards["pdf"].where == "adapters/deps/pdf/README.md"
    assert cards["email-ask"].where == "adapters/planned.json"
    assert "\\" not in "".join(c.where for c in cards.values())


def test_a_hyphenated_name_is_also_said_with_a_space(willow):
    cards = {c.name: c for c in card_table.read_cards(willow)}
    assert cards["coming-up"].spellings == ("coming-up", "coming up")
    assert cards["mail"].spellings == ("mail",)


def test_an_alias_reaches_a_card_by_name_or_by_a_meaningful_part(willow):
    rows = {r.major: r for r in card_table.load(willow)}
    assert "email" in rows["mail"].aliases
    assert "email" in rows["apple-mail"].aliases, "mail is a part of apple-mail"
    assert "due" in rows["coming-up"].aliases, "coming is a part of coming-up"
    assert "due" in rows["renewals"].aliases
    assert "email" not in rows["email-ask"].aliases, "email-ask is reached by name, not by `mail`"


def test_a_plain_part_reaches_nothing(tmp_path):
    w = make_willow(tmp_path / "W", aliases="verify = check\n")
    rows = {r.major: r for r in card_table.load(w)}
    assert "verify" not in rows["claim-check"].aliases
    assert card_table.PLAIN_PARTS >= {"check", "audit", "log"}


def test_an_ordinary_word_names_nothing_by_itself(willow):
    rows = {r.major: r for r in card_table.load(willow)}
    assert "all" in card_table.NOT_BY_NAME
    assert rows["all"].keyword == "everything" and rows["all"].aliases == ()
    hits = majors.scan("all my mail", table=list(rows.values()))
    assert [h.target for h in hits] == ["mail"], "`all` in a sentence names no add-on"
    assert [h.target for h in majors.scan("everything about it", table=list(rows.values()))] == [
        "all"
    ]


def test_an_ordinary_word_card_nothing_points_at_has_no_row(tmp_path):
    w = make_willow(tmp_path / "W", aliases="email = mail\n")
    assert "all" not in {r.major for r in card_table.load(w)}


def test_rows_carry_the_cards_promises_as_caps(willow):
    rows = {r.major: r for r in card_table.load(willow)}
    assert rows["pdf"].caps == (
        "writes:to",
        "network:none",
        "built",
        "needs:pypdf; BSD-3-Clause",
        "section:Reading more kinds of files",
    )
    assert "idea" in rows["email-ask"].caps and "built" not in rows["email-ask"].caps
    assert rows["mail"].reason == "Email in .eml and mbox, as text."


def test_the_scan_over_the_rows_hits_one_row_per_add_on(willow):
    table = card_table.load(willow)
    hits = majors.scan("read my email and say when the boiler is due", table=table)
    assert [(h.matched, h.target) for h in hits] == [
        ("email", "apple-mail"),
        ("email", "mail"),
        ("due", "coming-up"),
        ("due", "renewals"),
    ]
    assert majors.scan("a site for my running club", table=table) == []


def test_no_alias_file_is_a_catalogue_of_names_only(tmp_path):
    w = make_willow(tmp_path / "W", aliases=None)
    assert card_table.read_aliases(w) == {}
    rows = card_table.load(w)
    assert all(
        r.aliases in ((), ("coming up",), ("apple mail",), ("claim check",), ("email ask",))
        for r in rows
    )


@pytest.mark.parametrize(
    "spoil, said",
    [
        (lambda w: (w / "adapters").rename(w / "elsewhere"), "not a Willow checkout"),
        (
            lambda w: (w / "adapters" / "stdlib" / "mail" / "README.md").write_text("# mail\n"),
            "no willow-addon header",
        ),
        (
            lambda w: (w / "adapters" / "stdlib" / "mail" / "README.md").write_text(
                "<!-- willow-addon\nsection: x\nwrites: nothing\nnetwork: none\n-->\n"
            ),
            "no `line`",
        ),
        (
            lambda w: (w / "adapters" / "planned.json").write_text('[{"kind": "stdlib"}]\n'),
            "no name and line",
        ),
        (
            lambda w: (w / "adapters" / "planned.json").write_text(
                '[{"name": "mail", "line": "twice"}]\n'
            ),
            "built and still planned",
        ),
        (
            lambda w: (w / "ui" / "search-words.txt").write_text("email mail\n"),
            "not `word = words`",
        ),
    ],
)
def test_a_broken_catalogue_refuses_with_the_reason(tmp_path, spoil, said):
    w = make_willow(tmp_path / "W")
    spoil(w)
    with pytest.raises(card_table.CardTableError, match=said):
        card_table.load(w)
