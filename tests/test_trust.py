"""Tests for forge.trust — the forge's promotion trust as a §0.2 mechanism.

Skips if the cloud seam is absent (the module fail-closes on import). With it
present, this proves `verified_by` is no longer a string: enrollment is a
provisional gate-bound seal, ratification is a checkpoint signed by the
verifier's key, and `witnessed` refuses a same-hand or wrong-key ratification.
"""
import hashlib
import hmac
import os

import pytest

pytest.importorskip("willow_gate")
pytest.importorskip("nestor.cloud_seal")

from willow_gate import WillowGate
from willow_gate.custody import CustodyLedger

from forge.trust import WitnessResult, enroll, promotion_lineage, ratify, witnessed


class _KeySigner:
    """A deterministic key signer for the verifier — the home key stands in for
    a PGP/ed25519 key here. Two different keys are two different hands."""
    def __init__(self, key: bytes = b"verifier-key"):
        self.key = key

    def sign(self, data: bytes) -> str:
        return hmac.new(self.key, data, hashlib.sha256).hexdigest()

    def verify(self, data: bytes, sig: str) -> bool:
        return hmac.compare_digest(sig, self.sign(data))


AUTHOR = "agent:vishwakarma"
PROMO = {
    "app_id": "the-forge", "author": AUTHOR, "verified_by": "rudi193",
    "repo_url": "https://github.com/forge-play/Forge",
}


def _gate(tmp_path):
    g = WillowGate(base_dir=str(tmp_path / "gate"), require_pgp=False)
    secret = os.urandom(32)
    g.register_agent(AUTHOR, secret, max_trust=2)
    return g, secret


def test_enroll_ratify_witnessed_end_to_end(tmp_path):
    g, secret = _gate(tmp_path)
    cust = CustodyLedger()
    res = enroll(g, AUTHOR, secret, custody=cust, promotion=PROMO)
    assert res.canonical is False
    assert res.sealed == [promotion_lineage("the-forge")]

    signer = _KeySigner()  # the verifier's key (a different hand)
    cp = ratify(cust, signer)
    w = witnessed(cust, cp, signer, author_id=AUTHOR, verifier_id="rudi193", app_id="the-forge")
    assert isinstance(w, WitnessResult) and w.ok, w.reason


def test_author_cannot_ratify_itself(tmp_path):
    g, secret = _gate(tmp_path)
    cust = CustodyLedger()
    enroll(g, AUTHOR, secret, custody=cust, promotion=PROMO)
    signer = _KeySigner()
    cp = ratify(cust, signer)
    # same hand named as both author and verifier — §0.2 refuses it even with a
    # valid checkpoint
    w = witnessed(cust, cp, signer, author_id=AUTHOR, verifier_id=AUTHOR, app_id="the-forge")
    assert not w.ok


def test_a_wrong_verifier_key_does_not_witness(tmp_path):
    g, secret = _gate(tmp_path)
    cust = CustodyLedger()
    enroll(g, AUTHOR, secret, custody=cust, promotion=PROMO)
    real, forged = _KeySigner(b"real-home-key"), _KeySigner(b"forged-key")
    cp = ratify(cust, real)
    # the ratification was signed by `real`; verifying with a different key fails
    w = witnessed(cust, cp, forged, author_id=AUTHOR, verifier_id="rudi193", app_id="the-forge")
    assert not w.ok


def test_witness_requires_the_authors_provisional_seal(tmp_path):
    g, secret = _gate(tmp_path)
    cust = CustodyLedger()
    enroll(g, AUTHOR, secret, custody=cust, promotion=PROMO)  # sealed the-forge
    signer = _KeySigner()
    cp = ratify(cust, signer)
    # a valid checkpoint, but there is no provisional seal for a DIFFERENT app
    w = witnessed(cust, cp, signer, author_id=AUTHOR, verifier_id="rudi193", app_id="other-app")
    assert not w.ok


def test_enrollment_is_provisional_never_canonical(tmp_path):
    g, secret = _gate(tmp_path)
    res = enroll(g, AUTHOR, secret, custody=CustodyLedger(), promotion=PROMO)
    assert res.canonical is False  # canonical is only ever the verifier's checkpoint
