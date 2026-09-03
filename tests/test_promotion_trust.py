"""tools/promotion_trust.py — three hands, three commands, one witnessed block.

Skips without the trust seam (willow-gate + nestor.cloud_seal), exactly as
tests/test_trust.py does. With it: enroll → ratify → witness produces a trust
block; the same hand naming itself as verifier is refused; a wrong key does
not witness. Drives the CLI as a subprocess-free `main()` call so the
argument surface is what is tested.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("willow_gate")
pytest.importorskip("nestor.cloud_seal")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import promotion_trust as pt  # noqa: E402

AUTHOR = "agent:vishwakarma"


def _setup(tmp_path: Path):
    promo = tmp_path / "promotion.json"
    promo.write_text(json.dumps({
        "app_id": "the-forge", "author": AUTHOR, "verified_by": "rudi193",
        "repo_url": "https://github.com/forge-play/Forge", "host_repointed": True,
    }))
    secret = tmp_path / "author.secret"
    secret.write_bytes(os.urandom(32))
    key = tmp_path / "verifier.key"
    key.write_bytes(b"verifier-home-key")
    custody = tmp_path / "custody.jsonl"
    return promo, secret, key, custody


def _enroll(tmp_path, promo, secret, custody):
    return pt.main(["enroll", "--gate-dir", str(tmp_path / "gate"), "--custody", str(custody),
                    "--author-id", AUTHOR, "--secret-file", str(secret),
                    "--promotion", str(promo), "--register"])


def test_enroll_ratify_witness_produces_a_trust_block(tmp_path, capsys):
    promo, secret, key, custody = _setup(tmp_path)
    assert _enroll(tmp_path, promo, secret, custody) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["canonical"] is False and out["sealed"] == ["promotion:the-forge"]
    assert custody.exists() and custody.read_text().strip()

    cp = tmp_path / "checkpoint.json"
    assert pt.main(["ratify", "--custody", str(custody), "--key-file", str(key), "--out", str(cp)]) == 0
    capsys.readouterr()

    rc = pt.main(["witness", "--custody", str(custody), "--checkpoint", str(cp), "--key-file", str(key),
                  "--author-id", AUTHOR, "--verifier-id", "rudi193", "--promotion", str(promo),
                  "--write-into", str(promo)])
    assert rc == 0
    res = json.loads(capsys.readouterr().out)
    assert res["witnessed"] is True, res["reason"]
    assert res["trust"]["verifier_id"] == "rudi193" and res["trust"]["author_id"] == AUTHOR
    written = json.loads(promo.read_text())
    assert written["trust"]["checkpoint"] == json.loads(cp.read_text())


def test_the_same_hand_cannot_ratify(tmp_path, capsys):
    promo, secret, key, custody = _setup(tmp_path)
    _enroll(tmp_path, promo, secret, custody)
    cp = tmp_path / "checkpoint.json"
    pt.main(["ratify", "--custody", str(custody), "--key-file", str(key), "--out", str(cp)])
    capsys.readouterr()
    rc = pt.main(["witness", "--custody", str(custody), "--checkpoint", str(cp), "--key-file", str(key),
                  "--author-id", AUTHOR, "--verifier-id", AUTHOR, "--promotion", str(promo)])
    assert rc == 1
    res = json.loads(capsys.readouterr().out)
    assert res["witnessed"] is False and res["trust"] is None


def test_a_wrong_key_does_not_witness(tmp_path, capsys):
    promo, secret, key, custody = _setup(tmp_path)
    _enroll(tmp_path, promo, secret, custody)
    cp = tmp_path / "checkpoint.json"
    pt.main(["ratify", "--custody", str(custody), "--key-file", str(key), "--out", str(cp)])
    forged = tmp_path / "forged.key"
    forged.write_bytes(b"not-the-verifier")
    capsys.readouterr()
    rc = pt.main(["witness", "--custody", str(custody), "--checkpoint", str(cp), "--key-file", str(forged),
                  "--author-id", AUTHOR, "--verifier-id", "rudi193", "--promotion", str(promo)])
    assert rc == 1


def test_an_unregistered_author_is_refused_not_registered_silently(tmp_path, capsys):
    promo, secret, key, custody = _setup(tmp_path)
    rc = pt.main(["enroll", "--gate-dir", str(tmp_path / "gate"), "--custody", str(custody),
                  "--author-id", AUTHOR, "--secret-file", str(secret), "--promotion", str(promo)])
    assert rc == 2
    assert not custody.exists() or not custody.read_text().strip()
