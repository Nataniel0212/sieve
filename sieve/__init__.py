"""Sieve — automated prompt-injection red-teaming for tool-using LLM agents.

Does your agent leak like a sieve? Sieve runs a TAP-style attacker loop
(an NVIDIA Nemotron model, via Nebius Token Factory) against an agent you
control, verifies each outcome with a deterministic state check, and reports
the exact injections that got through.
"""

__version__ = "0.1.0"
