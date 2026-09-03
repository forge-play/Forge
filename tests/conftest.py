"""tests/conftest.py — resets Nestor's process-global state between tests.

Modeled on Nestor's own ``tests/conftest.py`` (``isolate_globals``, lines
76-104), trimmed to what the Forge's own tests actually touch. The Forge
never calls `nestor.storage.set_store`, `nestor.frank.set_forwarder`, or
`nestor.keyring.set_keyring` directly — only `checkpoint_memory._point_ledger_at`
reaches into Nestor, and it reaches into exactly one place:
`nestor.cascade.set_ledger_path` (module docstring's "process-wide path, same
as its `storage.set_store` global" note). That call happens on every
`open_checkpoint_memory`, pointed at that test's own `tmp_path`, so in
practice each test already repoints the ledger before using it — but a test
that reads `cascade._ledger_path()` or `cascade._LEDGER_OVERRIDE` directly
(as `tests/test_checkpoint_memory.py` does) would otherwise see whatever the
previous test left behind between the moment pytest starts collecting a new
test and the moment that test's own `open_checkpoint_memory` call runs. This
fixture closes that window the same way Nestor's own suite does: save the
override, reset it, yield, restore it.

`try/except ImportError` makes this a no-op when Nestor isn't installed —
soft-Nestor (`checkpoint_memory.nestor_available()`) means the Forge's own
test suite must stay green without it, and this fixture must not be the
thing that makes it require Nestor.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_nestor_globals(tmp_path):
    """Save/reset/restore `nestor.cascade`'s process-global ledger override
    around each test, so one test's ledger path can never leak into the
    next. No-op when `nestor` isn't installed (soft dependency, see
    `forge/checkpoint_memory.py`'s `_nestor()`)."""
    try:
        from nestor import cascade
    except ImportError:
        yield
        return

    saved_ledger = cascade._LEDGER_OVERRIDE
    cascade.set_ledger_path(tmp_path / "ledger.jsonl")
    yield
    cascade._LEDGER_OVERRIDE = saved_ledger
    cascade.reset_ledger_session()
