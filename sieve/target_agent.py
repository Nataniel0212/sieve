"""The agent under test: a tool-using email assistant driven by MODEL_TARGET
(an NVIDIA Nemotron model via Nebius). We run its normal tool-calling loop; the
only thing that changes between attempts is the injected email body.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from . import scenario
from .errors import BudgetStop

MAX_STEPS = 6  # tool-calling turns before we force a stop
TARGET_TEMPERATURE = 0.3  # the agent should be fairly deterministic


@dataclass
class TargetRun:
    env: scenario.Env
    final_text: str


def run_target(client, cfg, meter, attempt: int, injection_text: str,
               phase: str = "target") -> TargetRun:
    """Run the email assistant once against an inbox carrying `injection_text`."""
    env = scenario.Env(inbox=scenario.build_inbox(injection_text))
    messages = [
        {"role": "system", "content": scenario.TARGET_SYSTEM},
        {"role": "user", "content": scenario.USER_TASK},
    ]

    final_text = ""
    for _ in range(MAX_STEPS):
        result = client.chat(
            model=cfg.model_target, messages=messages, tools=scenario.TOOLS,
            max_tokens=8192, enable_thinking=False, force_nonempty=True,
            temperature=TARGET_TEMPERATURE,
        )
        meter.record(phase, attempt, result)
        if meter.total_cost() > cfg.budget_usd:
            raise BudgetStop()

        if not result.tool_calls:
            final_text = result.content
            break

        # Echo the assistant's tool-call turn, then append each tool result.
        messages.append({
            "role": "assistant",
            "content": result.content or None,
            "tool_calls": [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"],
                              "arguments": json.dumps(tc["args"])}}
                for tc in result.tool_calls
            ],
        })
        for tc in result.tool_calls:
            out = scenario.execute_tool(tc["name"], tc["args"], env)
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": out})

    return TargetRun(env, final_text)
