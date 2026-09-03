#!/usr/bin/env python3
# ── home ────────────────────────────────────────────────────────────────────
# The DETECTION half of model egress — `model_host` / `_addresses` /
# `is_local_host`, the fail-closed "is the model on this machine?" primitive
# D7 turns on (only all-loopback is local; an unparseable URL, an unresolvable
# name, or a loopback/non-loopback mix all read as OFF the machine and require
# a declared permission) — lives HERE as of 2026-09-03. It was written in
# willow-mcp, vendored here on 2026-08-11, and came home once forge-play was
# on PyPI: willow-mcp's src/willow_mcp/model_egress.py imports these three from
# this module. What stays in willow-mcp on purpose: `denial()`, which reads
# that repo's standing consent.cloud_llm. The Forge gates egress on the BUILD'S
# MANIFEST instead — a cloud-fallback permission that rides inside the D4
# (sap-gate) manifest signature — and that policy is forge/model_route.py,
# which imports the detector below. Security-relevant and subtle: literal-IP
# handling, no caching so a re-pointed host cannot reuse an old authorization.
"""model_egress (detection half) — is the model host on this machine?

A model request is LOCAL (the vLLM/Ollama loopback default, no network) or it is
EGRESS (off the machine), and only egress needs a declared permission. This
module answers only that question, deterministically and with no policy of its
own — the policy is `forge/model_route.py`.
"""
from __future__ import annotations

import ipaddress
import os

#: Read from the environment on every call, never cached — an operator may
#: re-point the host between calls, and a cached answer would authorize the old
#: destination for the new one.
MODEL_HOST_ENV = "OLLAMA_HOST"
DEFAULT_MODEL_HOST = "http://localhost:11434"


def model_host() -> str:
    return os.environ.get(MODEL_HOST_ENV) or DEFAULT_MODEL_HOST


def _addresses(hostname: str) -> list[str]:
    """Every address `hostname` resolves to, or [] if it cannot be resolved.

    An unresolvable name is NOT treated as loopback — `is_local_host` fails
    closed on the empty list, because "I could not tell where this goes" must
    not read as "it goes nowhere".
    """
    import socket
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, ValueError):
        return []
    return [i[4][0] for i in infos]


def is_local_host(host_url: str) -> bool:
    """True only when every address this URL resolves to is loopback.

    Every branch that cannot positively establish loopback returns False, so an
    unparseable URL, an unresolvable name, or a name that resolves to a mix of
    loopback and non-loopback all require consent.
    """
    from urllib.parse import urlparse
    try:
        hostname = urlparse(host_url).hostname
    except ValueError:
        return False
    if not hostname:
        return False

    # A literal address needs no resolution and cannot be re-pointed by DNS.
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        pass

    addrs = _addresses(hostname)
    if not addrs:
        return False
    try:
        return all(ipaddress.ip_address(a).is_loopback for a in addrs)
    except ValueError:
        return False
