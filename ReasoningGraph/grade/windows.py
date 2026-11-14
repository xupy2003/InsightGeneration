"""A transcript cut into units and, per round, into windows the probe reads (from GPTv3/ErrorAnalysis/windows.py).

Reads agentv2/agentv3 *_transcript.jsonl. The first record (round 0) is the prompt and is skipped. In every
later record, assistant_raw holds all the solver wrote that round: its reasoning up to </think>, then the
visible reply with its tool calls, submitted code included; tool_results hold what the environment returned.
Units keep their position in the record, so a quote can be checked against the original. A window holds
consecutive units of ONE round, at most WINDOW_CHARS characters. Text work only, no model calls.
"""
import json
from pathlib import Path

import config as C


def pieces(text, limit, start=0, end=None):
    """Bounds of consecutive pieces of text[start:end], each at most limit characters, ending at a
    paragraph or line break when one is in the second half."""
    end = len(text) if end is None else end
    while start < end:
        stop = min(start + limit, end)
        if stop < end:
            floor = start + limit // 2
            for sep in ("\n\n", "\n"):
                found = text.rfind(sep, floor, stop)
                if found >= 0:
                    stop = found + len(sep)
                    break
        yield start, stop
        start = stop


def read_units(path, unit_chars=C.UNIT_CHARS, rounds=None, blind=False):
    """Units in trace order (only the given rounds when rounds is a set). Each says where it came from, so
    that text == record[field][start:end] for the record on line `line`. blind: leave out the tool results
    (the judge's verdicts and feedback), so the probe sees only what the solver wrote."""
    units = []
    with Path(path).open(encoding="utf-8") as stream:
        for line, raw_line in enumerate(stream, 1):
            if not raw_line.strip():
                continue
            record = json.loads(raw_line)
            raw = record.get("assistant_raw")
            rnd = record.get("round")
            if rnd == 0 or not isinstance(raw, str) or (rounds is not None and rnd not in rounds):
                continue
            close = raw.rfind("</think>")
            reply = close + len("</think>") if close >= 0 else len(raw)
            sources = [("assistant_raw", "reasoning", None, raw, 0, close if close >= 0 else len(raw)),
                       ("assistant_raw", "reply", None, raw, reply, len(raw))]
            for i, result in enumerate([] if blind else record.get("tool_results") or []):
                key = "content" if result.get("content") is not None else "error"
                text = result.get(key)
                if isinstance(text, str):
                    sources.append((f"tool_results[{i}].{key}", "tool_result", result.get("name"), text, 0, len(text)))
            for field, kind, tool, text, a, b in sources:
                if not text[a:b].strip():
                    continue
                for start, end in pieces(text, unit_chars, a, b):
                    units.append({"id": f"U{line:05d}_{len(units) + 1:04d}", "round": rnd, "kind": kind,
                                  "tool": tool, "line": line, "field": field, "start": start, "end": end,
                                  "text": text[start:end]})
    return units


def make_windows(units, prefix, window_chars=C.WINDOW_CHARS):
    """Consecutive units, at most window_chars characters each, never spanning two rounds."""
    groups, current, size = [], [], 0
    for unit in units:
        if current and (size + len(unit["text"]) > window_chars or unit["round"] != current[-1]["round"]):
            groups.append(current)
            current, size = [], 0
        current.append(unit)
        size += len(unit["text"])
    if current:
        groups.append(current)
    return [{"id": f"{prefix}W{i:02d}", "index": i, "units": group,
             "rounds": sorted({u["round"] for u in group if u["round"] is not None}),
             "chars": sum(len(u["text"]) for u in group),
             "submits": any(u["kind"] == "tool_result" and u["tool"] == "submit" for u in group)}
            for i, group in enumerate(groups, 1)]


def round_windows(path, rnd, unit_chars=C.UNIT_CHARS, window_chars=C.WINDOW_CHARS, blind=False):
    """The windows of one round of a transcript, in order (blind: without the tool results)."""
    if window_chars < unit_chars:
        raise ValueError("window_chars must be at least unit_chars")
    return make_windows(read_units(path, unit_chars, rounds={rnd}, blind=blind), f"R{rnd}", window_chars)


def text_windows(text, prefix="I", kind="insight", unit_chars=C.UNIT_CHARS, window_chars=C.WINDOW_CHARS):
    """Windows over a text that is not part of the trace (the hint the solver was given)."""
    units = [{"id": f"{prefix}{i + 1:04d}", "round": None, "kind": kind, "tool": None, "line": None,
              "field": kind, "start": a, "end": b, "text": text[a:b]}
             for i, (a, b) in enumerate(pieces(text, unit_chars)) if text[a:b].strip()]
    return make_windows(units, prefix, window_chars)
