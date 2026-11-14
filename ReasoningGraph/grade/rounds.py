"""The rounds of an agentv2/agentv3 transcript, and which ones the grader reads (design.md §2.1).

The agent keeps only the last three turns' tool calls and no reasoning, so every round restates
the solver's model and approach: a round is a snapshot of what the solver believes then. The
grader reads the last substantive round (the final state; for an accepted run it is the round of
the accepted submission, since the contest stops there) together with the short rounds after it, and,
with --first-round, the first one (the initial model, before any feedback). Text work only, no model calls.
"""
import json
from pathlib import Path

import config as C

# What precedes the hint or editorial text in the prompt of round 0 (agentv2 agent_prompt.GENERATED_INSIGHT_LEAD,
# CategoryEval/agentv2 INSIGHT_HEAD).
INSIGHT_MARKERS = ("Here are some key insights that can help you solve this problem.",
                   "## Insight: how to solve this problem")


def records(trace):
    with Path(trace).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def round0(trace) -> dict:
    """The prompt record (round 0), or {}."""
    for rec in records(trace):
        return rec if rec.get("round") == 0 else {}
    return {}


def read_rounds(trace) -> list[dict]:
    """[{round, chars, reasoning_chars, reply_chars, tools, submits, finish_reason}] for rounds >= 1, in order."""
    out = []
    for rec in records(trace):
        rnd = rec.get("round")
        if rnd is None or rnd == 0:
            continue
        raw = rec.get("assistant_raw") or ""
        close = raw.rfind("</think>")
        reasoning = len(raw) if close < 0 else close
        tools = [c.get("name") for c in rec.get("tool_calls") or [] if isinstance(c, dict)]
        out.append({"round": rnd, "chars": len(raw), "reasoning_chars": reasoning,
                    "reply_chars": len(raw) - reasoning, "tools": tools, "submits": tools.count("submit"),
                    "finish_reason": rec.get("finish_reason")})
    return out


def insight_text(trace) -> str | None:
    """The hint or editorial text the solver was given, from the prompt of round 0: "" when the run had
    none, None when the record says it had one but the text cannot be found."""
    rec = round0(trace)
    if not rec or not rec.get("insight"):
        return ""
    prompt = rec.get("prompt") or ""
    for marker in INSIGHT_MARKERS:
        i = prompt.find(marker)
        if i >= 0:
            return prompt[i + len(marker):].strip()
    return None


def substantive(r: dict, min_chars: int = C.MIN_ROUND_CHARS) -> bool:
    return r["chars"] >= min_chars


def select(rounds: list[dict], first: bool = False, min_chars: int = C.MIN_ROUND_CHARS) -> dict:
    """{last, first, fallback, tail}: the last substantive round (else the longest), the first round when asked
    and different, the substantive round before the last one (read when the last says nothing about any
    node), and the tail: the rounds after the last one, all shorter than min_chars. The tail is read with the
    last round (since 2026-11-03): a fix made in a short final round belongs to the final state."""
    if not rounds:
        return {"last": None, "first": None, "fallback": None, "tail": []}
    subst = [r["round"] for r in rounds if substantive(r, min_chars)]
    last = subst[-1] if subst else max(rounds, key=lambda r: r["chars"])["round"]
    fallback = next((x for x in reversed(subst) if x < last), None)
    first_round = rounds[0]["round"]
    return {"last": last, "first": first_round if first and first_round != last else None, "fallback": fallback,
            "tail": [r["round"] for r in rounds if r["round"] > last]}
