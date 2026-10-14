"""Nebius Token Factory client (OpenAI-compatible).

All LLM traffic goes directly to Token Factory — never through any gateway.
Handles the documented Nemotron/Token Factory quirks:
  * tool-call XML can leak into content -> sanitize it out
  * reasoning toggled via extra_body.chat_template_kwargs.enable_thinking
  * force_nonempty_content for agent calls
  * tool-call arguments parsed back into a dict (object, not JSON string)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

_TOOLCALL_XML = re.compile(r"<tool_call>.*?</tool_call>", re.DOTALL | re.IGNORECASE)


def sanitize(content: str | None) -> str:
    if not content:
        return ""
    return _TOOLCALL_XML.sub("", content).strip()


@dataclass
class LLMResult:
    content: str
    tool_calls: list  # [{"id", "name", "args": dict}]
    usage: dict       # prompt_tokens, completion_tokens, reasoning_tokens
    latency_s: float
    model: str


class LiveClient:
    """Thin wrapper over the OpenAI SDK pointed at Token Factory."""

    def __init__(self, cfg) -> None:
        from openai import OpenAI  # imported lazily so dry-run needs no dep
        self._client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)

    def chat(self, model, messages, tools=None, max_tokens=8192,
             enable_thinking=False, force_nonempty=False) -> LLMResult:
        extra_body: dict = {"chat_template_kwargs": {"enable_thinking": enable_thinking}}
        if force_nonempty:
            extra_body["force_nonempty_content"] = True

        kwargs = dict(model=model, messages=messages, max_tokens=max_tokens,
                      extra_body=extra_body)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        t0 = time.time()
        resp = self._client.chat.completions.create(**kwargs)
        latency = time.time() - t0

        msg = resp.choices[0].message
        tool_calls = []
        for tc in (getattr(msg, "tool_calls", None) or []):
            args = tc.function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "args": args})

        u = resp.usage
        details = getattr(u, "completion_tokens_details", None)
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "reasoning_tokens": getattr(details, "reasoning_tokens", 0) or 0,
        }
        return LLMResult(sanitize(msg.content), tool_calls, usage, latency, model)
