#!/usr/bin/env python3
"""tools/promotion_trust.py — put a real `trust` block on a promotion (rudi193-cmd/Forge#8).

`promotion.json`'s `author` / `verified_by` are two strings. The store's gate
calls that the FLOOR — "exactly the hollow check this fleet already got burned
by: a name typed into a JSON field is not a ratification" — and offers a SEAL
tier when the attestation carries a `trust` block checked through
`forge.trust.witnessed()`. The module that makes §0.2 real lives in this repo
and had never been applied to this repo's own promotion. This tool is the
missing caller, in three acts that are three different hands on purpose:

    enroll   the AUTHOR, through the gate: a provisional, custody-chained seal
             of the canonical promotion JSON. Never canonical.
    ratify   the VERIFIER, with their key: a custody checkpoint that covers the
             author's seal. The key IS the ratification. This is the operator's
             act; nothing here can perform it for them.
    witness  anyone: recompute `forge.trust.witnessed()` from the custody file,
             the checkpoint and the verifier's key — the same check the store's
             gate runs — and print the `trust` block to paste into promotion.json.

The custody ledger is a JSONL file (`willow_gate.custody.CustodyLedger(path)`),
append-only and hash-chained, so `enroll` and `ratify` can be run on different
days from different chairs and the chain still verifies. The verifier's signer
here is HMAC-SHA256 over a key file — the same shape `tests/test_trust.py`
uses — standing in for the ed25519/PGP key a real home end holds; swap the
signer class, nothing else changes.

Requires the `trust` extra (`pip install 'forge-play[trust]'`): forge.trust
fail-closes on import without nestor.cloud_seal + willow-gate, and so does this.

    python tools/promotion_trust.py enroll  --gate-dir ~/.forge/gate --custody custody.jsonl \
        --author-id agent:vishwakarma --secret-file author.secret --promotion promotion.json [--register]
    python tools/promotion_trust.py ratify  --custody custody.jsonl --key-file verifier.key --out checkpoint.json
    python tools/promotion_trust.py witness --custody custody.jsonl --checkpoint checkpoint.json \
        --key-file verifier.key --author-id agent:vishwakarma --verifier-id rudi193 --promotion promotion.json
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from pathlib import Path

try:
    from willow_gate import WillowGate
    from willow_gate.custody import CustodyLedger
    from forge import trust
except ImportError as e:  # the seam is optional; this tool is not usable without it
    print(f"promotion_trust: the trust seam is not installed ({e}); "
          f"`pip install 'forge-play[trust]'`", file=sys.stderr)
    raise SystemExit(3)


class HmacKeySigner:
    """A key signer for the verifier: HMAC-SHA256 over the key file's bytes.
    Two different keys are two different hands. Stands in for a PGP/ed25519
    key — the interface (`sign`/`verify`) is what `forge.trust` needs."""

    def __init__(self, key: bytes):
        if not key:
            raise ValueError("an empty key is not a hand")
        self.key = key

    def sign(self, data: bytes) -> str:
        return hmac.new(self.key, data, hashlib.sha256).hexdigest()

    def verify(self, data: bytes, sig: str) -> bool:
        return hmac.compare_digest(sig, self.sign(data))


def _read_bytes(path: str) -> bytes:
    return Path(path).read_bytes().strip()


def _promotion(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_enroll(a: argparse.Namespace) -> int:
    promo = _promotion(a.promotion)
    gate = WillowGate(base_dir=str(Path(a.gate_dir).expanduser()), require_pgp=False)
    secret = _read_bytes(a.secret_file)
    if a.register:
        # Registration is the gate operator's act in a real gate; for the
        # author's own dev gate it is explicit here, never implicit.
        gate.register_agent(a.author_id, secret, max_trust=max(2, a.trust_level + 1))
    custody = CustodyLedger(path=a.custody)
    res = trust.enroll(gate, a.author_id, secret, custody=custody, promotion=promo,
                       trust_level=a.trust_level)
    print(json.dumps({
        "enrolled": promo.get("app_id"), "by": a.author_id,
        "lineage": trust.promotion_lineage(promo["app_id"]),
        "canonical": bool(getattr(res, "canonical", False)),
        "sealed": list(getattr(res, "sealed", [])),
        "custody": a.custody, "custody_events": len(custody),
        "note": "provisional — a different hand ratifies (see `ratify`)",
    }, indent=2))
    return 0


def cmd_ratify(a: argparse.Namespace) -> int:
    custody = CustodyLedger.load(a.custody)
    signer = HmacKeySigner(_read_bytes(a.key_file))
    cp = trust.ratify(custody, signer, ts=a.ts)
    Path(a.out).write_text(json.dumps(cp, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"checkpoint": a.out, "covers_to_seq": cp.get("covers_to_seq"),
                      "custody_events": len(custody)}, indent=2))
    return 0


def cmd_witness(a: argparse.Namespace) -> int:
    promo = _promotion(a.promotion)
    custody = CustodyLedger.load(a.custody)
    cp = json.loads(Path(a.checkpoint).read_text(encoding="utf-8"))
    signer = HmacKeySigner(_read_bytes(a.key_file))
    w = trust.witnessed(custody, cp, signer, author_id=a.author_id,
                        verifier_id=a.verifier_id, app_id=promo["app_id"])
    block = {
        "custody": a.custody,
        "checkpoint": cp,
        "author_id": a.author_id,
        "verifier_id": a.verifier_id,
        "signer": "hmac-sha256",
    }
    print(json.dumps({"witnessed": w.ok, "reason": w.reason,
                      "trust": block if w.ok else None}, indent=2))
    if w.ok and a.write_into:
        p = Path(a.write_into)
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["trust"] = block
        p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print(f"wrote trust block into {p}", file=sys.stderr)
    return 0 if w.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="promotion_trust.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enroll", help="author: provisional seal through the gate")
    e.add_argument("--gate-dir", required=True)
    e.add_argument("--custody", required=True, help="custody JSONL (created/appended)")
    e.add_argument("--author-id", required=True)
    e.add_argument("--secret-file", required=True, help="the author's gate secret (bytes)")
    e.add_argument("--promotion", default="promotion.json")
    e.add_argument("--trust-level", type=int, default=1)
    e.add_argument("--register", action="store_true",
                   help="register the author in this gate first (dev gate only)")
    e.set_defaults(fn=cmd_enroll)

    r = sub.add_parser("ratify", help="verifier: checkpoint the custody chain with your key")
    r.add_argument("--custody", required=True)
    r.add_argument("--key-file", required=True, help="the verifier's key (bytes)")
    r.add_argument("--out", default="checkpoint.json")
    r.add_argument("--ts", default=None)
    r.set_defaults(fn=cmd_ratify)

    w = sub.add_parser("witness", help="recompute §0.2 and print the trust block")
    w.add_argument("--custody", required=True)
    w.add_argument("--checkpoint", required=True)
    w.add_argument("--key-file", required=True)
    w.add_argument("--author-id", required=True)
    w.add_argument("--verifier-id", required=True)
    w.add_argument("--promotion", default="promotion.json")
    w.add_argument("--write-into", default=None,
                   help="also write the trust block into this promotion.json")
    w.set_defaults(fn=cmd_witness)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except Exception as e:  # noqa: BLE001 — one line, named, non-zero
        print(f"promotion_trust {a.cmd}: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
