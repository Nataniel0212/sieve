"""The agent-under-test choices offered by the web demo. The API, the recorder
and the offline catalog all read this one definition, so labels and ids cannot
drift apart. Ids can be overridden from the environment, so a renamed model
never needs a code change.
"""

from __future__ import annotations

import os

# key -> (label, default model id, environment override)
_TARGETS = {
    "lightning": ("Nemotron 3.5 Lightning", "nvidia/Nemotron-3_5-Lightning",
                  "MODEL_TARGET_LIGHTNING"),
    "nano": ("Nemotron 3 Nano 30B", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
             "MODEL_TARGET_NANO"),
    "ultra": ("Nemotron 3 Ultra 550B", "nvidia/Nemotron-3-Ultra-550b-a55b",
              "MODEL_TARGET_ULTRA"),
}

# Display names for model ids found in saved results.
LABELS = {model: label for label, model, _ in _TARGETS.values()}


def web_targets(environ=os.environ) -> dict[str, tuple[str, str]]:
    """key -> (label, model id). The lightning slot has its own variable rather
    than the CLI's MODEL_TARGET, so a benchmark setting in .env cannot make a
    recording or live run labelled Lightning use another model."""
    return {key: (label, environ.get(var) or model)
            for key, (label, model, var) in _TARGETS.items()}
