"""A run's submitted programs, and the few the program probe reads: the final judged program, the last
judged program of the rounds read, and the accepted one. A program is the solver's committed state,
what it actually computes. Text work only, no model calls."""
import json
from collections import Counter
from pathlib import Path

import config as C


def submissions(trace) -> list[dict]:
    """A run's submissions, from the *_submissions.jsonl beside its transcript ([] when there is none)."""
    path = Path(str(trace).replace("_transcript.jsonl", "_submissions.jsonl"))
    if path == Path(trace) or not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def judged(sub: dict) -> bool:
    """A program the judge ran: it compiled, and it has code."""
    return bool(sub.get("code")) and not str(sub.get("verdict") or "").startswith("CE")


def profile(subs: list[dict]) -> dict:
    return {"submissions": len(subs), "judged": sum(map(judged, subs)),
            "verdicts": dict(Counter(str(s.get("verdict") or "?").split()[0] for s in subs).most_common())}


def select(subs: list[dict], rounds_read, k: int = C.PROGRAMS_PER_RUN) -> list[dict]:
    """[{id, round, verdict, approach, code, role}] in submission order, at most k: the run's final judged
    program (role final), the accepted one (accepted) and the last judged program submitted in a round the
    grader read (round), each once."""
    picks = {}
    final = next((s for s in reversed(subs) if judged(s)), None)
    if final is not None:
        picks[final["id"]] = "final"
    accepted = next((s for s in subs if s.get("accepted") or s.get("verdict") == "AC"), None)
    if accepted is not None and accepted["id"] not in picks:
        picks[accepted["id"]] = "accepted"
    in_round = next((s for s in reversed(subs) if judged(s) and s.get("round") in set(rounds_read)), None)
    if in_round is not None and in_round["id"] not in picks:
        picks[in_round["id"]] = "round"
    out = [{"id": s["id"], "round": s.get("round"), "verdict": s.get("verdict"), "approach": s.get("approach"),
            "code": s["code"], "role": picks[s["id"]]} for s in subs if s.get("id") in picks]
    return out[-k:] if len(out) > k else out
