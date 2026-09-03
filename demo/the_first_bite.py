#!/usr/bin/env python3
"""The first bite — one small thing, made, from the sentence to the seal.

    python demo/the_first_bite.py                 # the walk-through
    python demo/the_first_bite.py --keep DIR      # leave the playground behind
    python demo/the_first_bite.py --json          # the friction log, machine-readable

**This is fiction.** Rosalind Ffoulkes-Mbeki does not exist, the Vale Wanderers
did not exist, and no photograph below was ever taken. Every artifact this
script writes carries ``origin="fixture:first-bite"``, the playground is a
temporary directory removed on exit, and nothing outside it is written. A
fixture that could be mistaken for a real trail is a forged record, and the
thing this box sells is a trail.

What this is
------------
Every other demo in the fleet proves one organ. ``the_dogfooding`` points
Nestor at its own decisions; ``two_desks`` asks what a second matcher does to a
human surface; the gate demo shows a receipt refusing to be edited. None of
them needs more than one part of the box, which is why the box has never been
demonstrated as one thing.

This follows a single thread that cannot be walked without all of them:
somebody wants a small tool, and the box is honest at every step. The Forge
loop is the right thread because it is the only one with **ground truth that
arrives on its own** — the thing clears the bar or it does not, and no opinion
enters.

The beats, in dependency order. Each is what the next one assumes:

    1  the ask            a sentence with two keywords and no spec
    2  look in the box    Nestor, then the box, then remote — and it finds one
    3  she builds anyway  a preference. no procedure verifies a preference.
    4  the playground     work happens where work belongs, not in the product
    5  the build          sandboxed, network-isolated
    6  it wants the web   three keys, and exactly one of them is hers
    7  the review         adversarial, and it may say nothing at all
    8  the bar            promote_check — and it fails on the gate 39/42 fail
    9  the demo           the artifact that clears the bar is a demo. recursion.
   10  the seal           a hand. one tap. wherever she is.
   11  the calibration    the box finds out whether it was right

WHAT IT IS ALSO FOR
-------------------
The friction log is the second output and the more useful one. This walks the
day a person would actually have, and records every place the box asks for
something a person does not have, or answers in a language nobody speaks. A
demo that only shows the happy path is a brochure. On a box where the Forge has
never run, most of these beats will report MISSING, and the ordered list of what
is missing is a punch list that happens to read as a story.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import date
from pathlib import Path

HOME = Path.home()
GH = HOME / "github"
STORE = GH / "safe-app-store-public"
NESTOR = GH / "Die-Namic-Systems/nestor"
FORGE = GH / "forge-play/Forge"
# The engine this demo walks. Imported from the checkout the demo lives in, not
# from wherever `forge` happens to be installed — the demo is this repo's.
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
ROSALIND = "rosalind"          # her builder id in the playground
PROJECT = "rally-dates"        # the bite's project id (a per-project Nestor hangs off it)
WILLOW_HOME = Path(os.environ.get("WILLOW_HOME", GH / "willow-memory/.willow"))
WILLOW_MCP = WILLOW_HOME / "venvs/willow-mcp/bin/willow-mcp"

ORIGIN = "fixture:first-bite"
W = 78

LOG: list[dict] = []
# Machine-readable facts the beats establish (the entry's tiers, the scorecard) —
# emitted beside the friction log under --json, so a test can read what the
# demo actually did rather than what it said.
FACTS: dict = {}

# ── pacing ──────────────────────────────────────────────────────────────────
# A wall of text is not a demo, it is a dump. The beats below are paced so the
# thing reads at the speed a person reads, and so record_demo.py's capture has
# real inter-beat timing to record rather than one instantaneous flush.
#
# Every delay is presentation only. No pause changes what runs, what it finds,
# or what lands in the friction log — `--pace off` produces byte-identical
# content, which is what makes it safe in CI.
PACE = {
    "slow":   {"line": 0.055, "beat": 1.25, "say": 0.40, "out": 0.09},
    "normal": {"line": 0.030, "beat": 0.80, "say": 0.25, "out": 0.05},
    "fast":   {"line": 0.010, "beat": 0.25, "say": 0.08, "out": 0.02},
    "off":    {"line": 0.0,   "beat": 0.0,  "say": 0.0,  "out": 0.0},
}
_p = PACE["normal"]

# --json runs every beat, silently, so the log it emits is the WHOLE log rather
# than whichever beats happened to be cheap to run. Suppression lives here, at
# the one place that writes, so no caller has to remember it — the first cut of
# this ran a single beat and let it narrate, which produced an incomplete log
# wrapped in unparseable prose.
QUIET = False


def set_pace(name: str) -> None:
    global _p
    _p = PACE[name]


def set_quiet(on: bool) -> None:
    global QUIET
    QUIET = on


def _emit(text: str = "", delay: float = 0.0) -> None:
    """One line, flushed, then a beat. Flushing matters: a buffered demo
    arrives all at once no matter how long it slept."""
    if QUIET:
        return
    sys.stdout.write(text + "\n")
    sys.stdout.flush()
    if delay:
        time.sleep(delay)


def pause(kind: str = "beat") -> None:
    time.sleep(_p[kind])


# ── surface ─────────────────────────────────────────────────────────────────

def rule(ch: str = "─") -> None:
    _emit(ch * W, _p["line"])


def beat(n: int, title: str, blurb: str) -> None:
    pause("beat")
    _emit()
    rule("━")
    _emit(f"  {n:>2}.  {title}", _p["line"])
    rule("━")
    for line in textwrap.wrap(blurb, W - 2):
        _emit(f"  {line}", _p["line"])
    _emit()
    pause("say")


def says(who: str, text: str) -> None:
    for i, line in enumerate(textwrap.wrap(text, W - 16)):
        _emit(f"  {who if i == 0 else '':<13} {line}", _p["line"])
    _emit()
    pause("say")


def shows(text: str) -> None:
    for line in textwrap.dedent(text).strip("\n").splitlines():
        _emit(f"      {line}", _p["out"])
    _emit()
    pause("say")


def note(text: str) -> None:
    """An aside in the narrator's voice, paced like prose."""
    for line in textwrap.wrap(textwrap.dedent(text).strip(), W - 2):
        _emit(f"  {line}", _p["line"])
    _emit()


def run(cmd: list[str], cwd: Path | None = None, show: int = 12) -> tuple[int, str]:
    _emit(f"  $ {' '.join(str(c) for c in cmd)}", 0 if QUIET else _p["say"])
    try:
        p = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                           capture_output=True, text=True, timeout=120)
        out = (p.stdout + p.stderr).strip()
        rc = p.returncode
    except FileNotFoundError:
        _emit("      (not on this box)\n")
        return 127, ""
    except Exception as e:                                     # noqa: BLE001
        _emit(f"      (could not run: {e})\n")
        return 127, ""
    for line in out.splitlines()[:show]:
        _emit(f"      {line}", _p["out"])
    if len(out.splitlines()) > show:
        _emit(f"      … {len(out.splitlines()) - show} more")
    _emit()
    pause("say")
    return rc, out


def friction(n: int, what: str, expected: str, actual: str, fix: str,
             kind: str = "friction") -> None:
    LOG.append({"beat": n, "kind": kind, "what": what,
                "expected": expected, "actual": actual, "fix": fix})
    mark = "MISSING " if kind == "missing" else "FRICTION"
    if QUIET:
        return
    pause("say")
    _emit(f"  ▸ {mark} — {what}", _p["line"])
    _emit(f"    a person expects : {expected}", _p["line"])
    for i, line in enumerate(textwrap.wrap(actual, W - 24)):
        _emit(f"    {'what happens     :' if i == 0 else '':<19}{line}", _p["line"])
    _emit()
    pause("say")


# ── the fixture ─────────────────────────────────────────────────────────────

PHOTOS = [
    ("vale-1998-start-line.jpg", "1998-05-17"),
    ("vale-1998-hillclimb.jpg", None),
    ("vale-1999-paddock.jpg", "1999-06-02"),
    ("vale-1999-rain.jpg", None),
    ("vale-2001-finish.jpg", None),
    ("vale-2001-trophy.jpg", "2001-08-11"),
]


def lay_the_table(play: Path) -> Path:
    """Rosalind's photographs. Invented, and tagged as invented."""
    shed = play / "vale-wanderers"
    shed.mkdir(parents=True, exist_ok=True)
    for name, taken in PHOTOS:
        (shed / name).write_bytes(b"")
        side = shed / (name + ".json")
        side.write_text(json.dumps(
            {"file": name, "taken": taken, "origin": ORIGIN}, indent=2))
    return shed


# ── beats ───────────────────────────────────────────────────────────────────

def b1_the_ask() -> None:
    beat(1, "The ask", (
        "Rosalind ran a scooter rally for eleven years and has the photographs to "
        "prove it. She opens the app. Vishwakarma asks the only question the "
        "onboarding asks."))
    says("Vishwakarma", "What's the first bite?")
    sentence = "i need summit to tell me which rally pics aint got a date on em"
    says("Rosalind", sentence)

    # The scan is the engine's, over forge/keywords.toml — the first artifact.
    from forge import majors
    hits = majors.scan(sentence)
    by_major = majors.majors_for(hits)
    lines = [f"keywords found : {' · '.join(dict.fromkeys(h.matched for h in hits)) or '(none)'}",
             "candidate majors:"]
    for m, hs in by_major.items():
        caps = ", ".join(dict.fromkeys(c for h in hs for c in h.caps))
        lines.append(f"  {hs[0].matched:<6}→ {m:<16}({caps})")
    ask = majors.ambiguous_majors(hits)
    lines.append(f"{len(ask)} candidates, no way to choose" if ask else
                 (f"one major: {next(iter(by_major))}" if by_major else "no keyword matched"))
    shows("\n".join(lines))
    says("The box", "Do you want to look at the pictures, or fix what's written on them?")
    note("""Ambiguity is a detectable condition with a scripted response: ask.
            It is not a reasoning problem, and no model was consulted.""")

    # The entry: Nestor first, or refuse. Rosalind answers the one question.
    from forge import entry as forge_entry
    from forge.checkpoint import ChoiceResult

    class _Rosalind:
        def confirm(self, prompt):
            says("Rosalind", "same as before, yeah")
            return True

        def choose(self, decision):
            says("Rosalind", "fix what's written on em. the pics are fine")
            return ChoiceResult(chosen_label="metadata tool",
                                rationale="the pictures are fine; it's the dates that are wrong")

    try:
        e = forge_entry.open_bite(sentence, project_id=PROJECT, builder_id=ROSALIND,
                                  responder=_Rosalind(), root=Path(os.environ["FORGE_HOME"]) / "checkpoints")
    except forge_entry.EntryError as err:
        FACTS["entry"] = {"refused": str(err)}
        friction(1, "the entry refused: Nestor is not installed",
                 "the box asks its memory first, then asks her",
                 str(err),
                 "pip install nestor-meaning — the entry cannot start a build that never asked",
                 kind="missing")
    else:
        FACTS["entry"] = {"tiers": e.tiers, "major": e.major,
                          "band": e.decision_outcome.band if e.decision_outcome else None}
        shows("\n".join(f"{k:<7} {v}" for k, v in e.tiers.items()) + f"\nmajor   {e.major}")
        note("""Every tier answered out loud. The one that could not (remote) said
                so instead of pretending. The second time she says this, the
                box confirms instead of asking — that is the whole point.""")


def b2_look_in_the_box() -> None:
    beat(2, "Look in the box before you look outside it", (
        "Three tiers, strictly ordered: ask Nestor, look in the box — archives "
        "included — then, and only then, go remote, saying why the first two did "
        "not answer."))
    says("Rosalind", "Has anyone made this already?")

    note("Tier 1 — ask Nestor.")
    shows("""
        nestor_ask "a tool that finds photos with no date"
          state: pending      nothing verified matched
    """)
    note("Tier 2 — look in the box. 42 apps, and two of them are close:")
    for app, why in [("source-trail", "file_read, pattern_storage — follows a file's provenance"),
                     ("story-timeline", "store_write, store_add_edge — puts events on a line")]:
        m = STORE / "apps" / app / "safe-app-manifest.json"
        state = "declared" if m.exists() else "not found on this box"
        _emit(f"      {app:<16} {why}", _p["out"])
        _emit(f"      {'':<16} manifest: {state}", _p["out"])
    _emit()
    pause("say")
    says("The box", "You may not need to build this. source-trail already reads a "
                    "file and says where it came from. Do you want to look at it first?")
    note("""A demo where the box talks you out of the work is a better demo
            than one where it does the work.""")


def b3_she_builds_anyway() -> None:
    beat(3, "She builds anyway", (
        "She looks, and it is not what she wants. That is a preference. No "
        "procedure can verify a preference — so this one is a seal, not a check, "
        "and the box says which it is."))
    says("Rosalind", "It's close but it wants me to open each one. I want a list.")
    shows("""
        pair     source : Should rally-dates be built when source-trail exists?
                 target : Yes — the ask is a list, not a per-file lookup.
        kind     judged        no procedure can check this
        state    draft         awaiting a human
        warrant  attestation   ← the only kind this box has ever written
    """)
    friction(3, "every warrant on the box is an attestation",
             "'checkable things get checked; judgements get a person'",
             "warrant.check and warrant.expected_digest exist in the schema and are "
             "empty on all 606 sealed pairs — 100% assertion, 0% corroboration",
             "populate warrant.check for the claims a procedure can settle")


def b4_the_playground(play: Path) -> Path:
    beat(4, "The playground", (
        "Work happens where work belongs. Not in the product, not in the vault, "
        "not in a repo she has never heard of."))
    proj = play / "playground" / "rally-dates"
    proj.mkdir(parents=True, exist_ok=True)
    keeping = {
        "app_id": "rally-dates", "author": "fixture:rosalind",
        "made": str(date.today()), "for": "list the photographs with no date",
        "pins": [], "origin": ORIGIN,
    }
    (proj / ".forge.json").write_text(json.dumps(keeping, indent=2))
    shows(f"""
        ~/forge/playground/rally-dates/
          .forge.json     who made it, when, what it is for, what it pins
          worktrees/      Kart's scan root moves here
    """)
    note(f"(this run: {proj})")

    real = HOME / "forge" / "playground"
    if not real.exists():
        friction(4, "the playground does not exist on this box",
                 "a place a helper may write, that is not the product",
                 f"no {real} — WILLOW_ROOT resolves to willow-mcp/src and is bound "
                 "read-write, so today a task's work root is the product's own source",
                 "make the playground the work root; WHERE_KART_GOES.md gaps 1-2",
                 kind="missing")
    return proj


def b5_the_build(proj: Path, shed: Path) -> None:
    beat(5, "The build", (
        "Sandboxed. Network isolated. Credentials stripped. It reads her "
        "photographs and nothing else."))
    tool = proj / "rally_dates.py"
    tool.write_text(textwrap.dedent('''\
        import json, sys, pathlib
        shed = pathlib.Path(sys.argv[1])
        undated = [json.loads(p.read_text())["file"]
                   for p in sorted(shed.glob("*.json"))
                   if json.loads(p.read_text()).get("taken") is None]
        print(f"{len(undated)} of {len(list(shed.glob('*.json')))} have no date:")
        for u in undated:
            print("   ", u)
    '''))
    run([sys.executable, str(tool), str(shed)])
    says("Rosalind", "Three of them. I knew about the rain one.")


def b6_it_wants_the_web() -> None:
    beat(6, "It wants the web", (
        "To read the date out of the picture itself it needs an EXIF library. "
        "That is the first thing all day that leaves the house."))
    if WILLOW_MCP.exists():
        run([str(WILLOW_MCP), "net-status"], show=4)
    shows("""
        three keys, all required, checked before anything opens:
          1  task_net in the manifest        — capability   NOT HELD
          2  consent.internet                — standing     yes
          3  an operator lease + a signed per-task envelope  NONE
    """)
    says("The box", "I cannot reach the internet. Two of the three keys are missing, "
                    "and one of them is yours to turn — for this one task, expiring, "
                    "bound to this exact job.")
    friction(6, "a denial does not say which key is missing",
             "'you have not allowed this yet — allow it once, for this?'",
             "egress_denial: net_denied",
             "name the missing key and offer the one that is hers")
    friction(6, "the per-task envelope has never been exercised",
             "the narrow path is the well-worn one",
             "task_submit accepts network_authorization, sign-net-task mints it, and "
             "no task on this box has ever carried one",
             "run it once end-to-end so the demo can show the narrow grant",
             kind="missing")


def b7_the_review(proj: Path) -> None:
    beat(7, "The review", (
        "Loki reviews adversarially, and is entitled to say nothing. The "
        "engagement gate scores her rationale — not the code."))
    ff = FORGE / "forge" / "friction_floor.py"
    has_stance = ff.exists() and "def stance_friction" in ff.read_text(errors="ignore")
    rationale = ("It duplicates source-trail but returns a list instead of a lookup, "
                 "and I disagree that per-file is good enough for six hundred photos.")
    if has_stance:
        rc, out = run([sys.executable, "-c", textwrap.dedent(f'''
            import sys; sys.path.insert(0, {str(FORGE)!r})
            from forge import friction_floor as ff
            r = {rationale!r}
            ctx = "source-trail already does this; per-file lookup is good enough."
            print("friction_score  (stance-blind):", round(ff.friction_score(r, ctx), 3))
            print("stance_friction (stance-aware):", round(ff.stance_friction(r, ctx), 3))
        ''')], show=4)
    else:
        friction(7, "the stance-aware scorer is not present",
                 "the engagement gate measures opposition to the user's stance",
                 "forge/friction_floor.py lacks stance_friction; the gate runs the "
                 "stance-blind scorer, measured at chance on 9,000 labelled pairs",
                 "re-sync the vendored file from willow-mcp", kind="missing")
    pause("beat")
    says("Loki", "SILENCE.")
    note("""He is allowed to. A reviewer who always speaks is a reviewer
            nobody reads.""")


def b8_the_bar(proj: Path) -> None:
    beat(8, "The bar", (
        "promote_check runs the gates. A promotion needs every gate passing AND a "
        "hand. This is where 39 of 42 apps in the store stop."))
    check = STORE / "stores" / "promote_check.py"
    if check.exists():
        run([sys.executable, str(check), "--help"], show=8)
    else:
        friction(8, "promote_check.py not found where the README says it is",
                 "the bar is executable",
                 f"no {check.relative_to(GH)} on this box", "locate or restore it",
                 kind="missing")
    shows("""
        rally-dates, against the four:
          its own tests          no
          a manifest             no
          dependency-light       yes   (0 dependencies)
          a demo                 no
                                 1 / 4
    """)
    says("The box", "It does not clear the bar. It needs tests, a manifest, and a "
                    "demo. The demo is the one almost everybody misses — 39 of the "
                    "42 apps in the store do not have one.")
    friction(8, "the bar has never been pointed at a playground",
             "the same check that grades the store grades her work",
             "promote_check.py grades apps/ in the store; nothing runs it against "
             "a playground directory, because there is no playground",
             "point promote_check at the playground once it exists", kind="missing")


def b9_the_demo() -> None:
    beat(9, "The demo", (
        "The artifact that clears the bar is a demo. She writes one. It is the "
        "same shape as the file you are reading."))
    rec = NESTOR / "demo" / "record_demo.py"
    shows("""
        demo/rally_dates_demo.py     six invented photographs, three without dates
        recorded with                nestor/demo/record_demo.py
        produces                     .cast (asciinema v2) and .txt
        new dependencies             none
    """)
    note(f"recorder present: {'yes' if rec.exists() else 'no'} — "
         f"{rec.relative_to(GH) if rec.exists() else rec}")
    note("""The promotion path eats itself here, and that is the honest bit:
            the thing the Forge asks you to produce is the thing that shows
            it works.""")


def b10_the_seal() -> None:
    beat(10, "The seal", (
        "Every gate has passed. The last one is a person, and she is not at her "
        "desk."))
    shows("""
        Promote rally-dates?         1 / 1  awaiting a hand
        gates                        4 / 4  passed, recorded
        verifier                     ← a name, written into the seal
    """)
    says("The box", "Everything I can check, I checked. This one is yours.")
    friction(10, "the seal happens somewhere else",
             "one tap, where the question was asked",
             "sealing is a desktop UI against a store chosen by --db; `nestor ui` "
             "with no --db opens the store that has nothing pending",
             "a seal action on the surface that raised the question")
    friction(10, "the phone seat does not exist yet",
             "she taps it on her phone, because that is where she is",
             "willow-remote is designed (51 GREEN / 64 AMBER / 35 RED) and unbuilt; "
             "identity_bindings: 0 confirmed",
             "steps 4-6 of THE_PATH", kind="missing")


def b11_calibration() -> None:
    beat(11, "The calibration", (
        "The Forge is the only part of the box built to find out rather than to "
        "record. It stated a confidence before the bar ran. Now it learns."))
    # A plan with one fork in it: where do the dates live? The proposer
    # recommends sidecar json at 0.8. Rosalind decides. The ledger finds out.
    from forge import build_loop, calibration_ledger, plan_shape
    from forge.checkpoint import ChoiceResult

    class _Rosalind:
        def confirm(self, prompt):
            return True

        def choose(self, decision):
            says("Rosalind", "put it in the picture. i lose files, i dont lose pictures")
            return ChoiceResult(chosen_label="exif in place",
                                rationale="a sidecar file gets lost; the picture does not")

    root = Path(os.environ["FORGE_HOME"]) / "checkpoints"
    plan = plan_shape.load(REPO / "demo" / "fixtures" / "fork_plan.json")
    try:
        res = build_loop.resolve(plan, builder_id=ROSALIND, responder=_Rosalind(), root=root)
    except Exception as err:  # noqa: BLE001 — the demo reports, it does not crash
        FACTS["calibration"] = {"refused": f"{type(err).__name__}: {err}"}
        friction(11, "the build loop could not run",
                 "the box states a confidence, she answers, the box learns",
                 f"{type(err).__name__}: {err}",
                 "pip install nestor-meaning — the loop seals through memory", kind="missing")
    else:
        (pred,) = res.predictions
        (outcome,) = res.outcomes
        card = calibration_ledger.scorecard(ROSALIND, root=root)
        FACTS["calibration"] = {"claim": pred["claim"], "confidence": pred["confidence"],
                                "outcome": pred.get("outcome"), "resolved": card["resolved"],
                                "hit_rate": card["summary"]["hit_rate"],
                                "sealed": outcome.sealed, "band": outcome.band}
        # Without Nestor the checkpoint still asks (full Socratic) but cannot
        # seal; the ledger is a SOIL store and learns either way. Say which.
        sealed = ("sealed in her memory" if outcome.sealed
                  else "decided, NOT sealed — no memory to seal into (Nestor absent)")
        shows(f"""
            predicted   {pred['claim']:<40} {pred['confidence']:.2f}
            observed    she picked {res.chosen['where-the-dates-live']} — {sealed}
            resolved    {'hit' if pred.get('outcome') else 'miss'} — recorded in forge/calibration_ledger.py
            scorecard   {card['resolved']} resolved, hit rate {card['summary']['hit_rate']:.2f}
        """)
        if not outcome.sealed:
            friction(11, "the decision was made but not sealed",
                     "her answer is remembered, so she is not asked again next time",
                     "Nestor is not installed; run_checkpoint ran full Socratic on its soft path "
                     "and returned sealed=False. The calibration still learned.",
                     "pip install nestor-meaning", kind="missing")
        note("""Ground truth arrived on its own: her pick is the outcome, and no
                opinion entered. The box promised sidecar at 0.80 and was wrong.
                Enough of those and it routes itself a review.""")


# ── report ──────────────────────────────────────────────────────────────────

def report(as_json: bool) -> int:
    missing = [x for x in LOG if x["kind"] == "missing"]
    rough = [x for x in LOG if x["kind"] == "friction"]
    if as_json:
        print(json.dumps({"origin": ORIGIN, "missing": missing, "friction": rough,
                          "facts": FACTS}, indent=2, default=str))
        return 0
    pause("beat")
    _emit()
    rule("━")
    _emit(f"  WHAT IS NOT THERE YET — {len(missing)}", _p["line"])
    rule("━")
    _emit()
    for i, f in enumerate(missing, 1):
        _emit(f"  {i}. [{f['beat']:>2}] {f['what']}", _p["line"])
        for line in textwrap.wrap(f["actual"], W - 10):
            _emit(f"        {line}", _p["out"])
        _emit(f"        → {f['fix']}", _p["out"])
        _emit()
        pause("say")
    rule("━")
    _emit(f"  WHAT IS THERE AND READS WRONG — {len(rough)}", _p["line"])
    rule("━")
    _emit()
    for i, f in enumerate(rough, 1):
        _emit(f"  {i}. [{f['beat']:>2}] {f['what']}", _p["line"])
        _emit(f"        expects : {f['expected']}", _p["out"])
        for j, line in enumerate(textwrap.wrap(f["actual"], W - 20)):
            _emit(f"        {'gets    :' if j == 0 else '':<10}{line}", _p["out"])
        _emit(f"        → {f['fix']}", _p["out"])
        _emit()
        pause("say")
    rule()
    note("""The first list is a build order — each item is what the next beat
            assumes. The second is the vocabulary pass. Neither was found by
            reading code; both fell out of walking one person through one day.""")
    rule()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keep", metavar="DIR")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pace", choices=list(PACE), default="normal",
                    help="reading speed. 'off' for CI — content is identical")
    ap.add_argument("--fast", action="store_true", help="shorthand for --pace fast")
    args = ap.parse_args()

    set_pace("off" if args.json else ("fast" if args.fast else args.pace))
    set_quiet(args.json)

    if not args.json:
        _emit()
        rule("━")
        _emit("  THE FIRST BITE — one small thing, made", _p["line"])
        rule("━")
        note("""
            Rosalind Ffoulkes-Mbeki, the Vale Wanderers, and eleven years of
            photographs. All of it invented. Every artifact this writes carries
            origin='fixture:first-bite' and lives in a directory removed on exit.
        """)

    tmp = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="first-bite-"))
    tmp.mkdir(parents=True, exist_ok=True)
    # The engine's home lives inside the playground: the entry's project store,
    # the checkpoint memory, the calibration ledger — all under tmp, all removed
    # on exit. Nothing this demo seals leaks into a real ~/.forge.
    os.environ["FORGE_HOME"] = str(tmp / "forge-home")
    try:
        shed = lay_the_table(tmp)
        b1_the_ask()
        b2_look_in_the_box()
        b3_she_builds_anyway()
        proj = b4_the_playground(tmp)
        b5_the_build(proj, shed)
        b6_it_wants_the_web()
        b7_the_review(proj)
        b8_the_bar(proj)
        b9_the_demo()
        b10_the_seal()
        b11_calibration()
        return report(args.json)
    finally:
        if not args.keep:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
