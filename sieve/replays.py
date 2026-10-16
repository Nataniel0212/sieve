"""Prepare synthetic traces for publication without credential-shaped strings.

The attacker can invent an API-key-looking token in its text. Such text is not
needed for the state verdict and triggers hosting secret scanners. Disclose its
redaction in recording metadata; keep tool state, synthetic fixture tokens and
all metered numbers intact.
"""
from __future__ import annotations

import re

_CREDENTIAL = re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9_]{12,}\b")


def public_recording(recording: dict) -> dict:
    count = 0

    def clean(value):
        nonlocal count
        if isinstance(value, str):
            value, n = _CREDENTIAL.subn("[REDACTED SYNTHETIC TOKEN]", value)
            count += n
            return value
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        return value

    result = clean(recording)
    if count:
        result["redactions"] = count
        result["redaction_note"] = "Credential-shaped strings invented in the synthetic attack text are redacted. Timings, usage and verdicts are unchanged."
    return result
