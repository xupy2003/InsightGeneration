"""Every turn's reasoning, on disk, retrievable by tool call.

The window never carries reasoning: it is stripped from every kept turn,
because it is the largest thing a turn produces (6.9k tokens at the median,
131k at worst) and replaying it would undo everything the window is for. In
../agent that made it unrecoverable. A model that had worked out on turn 3
why a greedy fails, or got two thirds through a derivation before the token
budget cut it off, had nothing on turn 4 but its one-line approach note.

This store is the reasoning's counterpart of SubmissionStore: one JSONL line
per turn, appended when the turn's calls have run, read back through three
tools that cost no submission.

    list_rounds        one line per earlier turn: when, how long, what it did
    get_reasoning      one turn's reasoning, a part at a time
    search_reasoning   grep every turn's reasoning

Reasoning is long, so it is served in parts of PART_CHARS characters, split at
line breaks, and the header of every part says how many there are and how to
get the next. A cut-off turn is kept like any other: picking up where it
stopped is one of the things this store is for.

WHAT THE MODEL IS ALLOWED TO SEE
Only its own words. A turn's record also holds the verdicts its submissions
got, rendered through store._only_verdict exactly as the submission tools
render them, so nothing here can show a judge detail the model was not shown
when it happened.
"""
import json
import re
from pathlib import Path

from store import MAX_TOOL_CHARS, _clip, _only_verdict


# One part of a turn's reasoning: about 3.5k tokens. Four calls a turn can
# bring back four of them, which is still a fraction of one median turn.
PART_CHARS = 12000
# What a turn wrote after its reasoning, shown with its last part.
SAID_CHARS = 2000


def split_parts(text: str, size: int = PART_CHARS) -> list[tuple[int, int]]:
    """(start, end) offsets of the parts, cut at line breaks where possible.

    A part ends at the last newline in its window; a single line longer than
    the window (a minified program, a long formula) is cut where the window
    ends. An empty text is one empty part, so every turn has a part 1.
    """
    bounds, start = [], 0
    while len(text) - start > size:
        cut = text.rfind("\n", start + 1, start + size)
        end = cut + 1 if cut != -1 else start + size
        bounds.append((start, end))
        start = end
    bounds.append((start, len(text)))
    return bounds


def pointer(round_no: int, n_parts: int) -> str:
    """Where the reasoning behind a submission is, said where it is needed.

    The tools and the system message describe the store, but the moment the
    model decides what to do next is right after a verdict, and there it was
    pointed only at the code: in the first real v2 run it read its earlier
    programs back three times and its reasoning never. So a wrong verdict
    and get_submission both name the call that returns the turn's reasoning,
    starting from the part where the model decided to submit.
    """
    rest = f"; parts 1-{n_parts} hold all of it" if n_parts > 1 else ""
    return (f"The reasoning that led to this program is saved as round {round_no}: "
            f"get_reasoning(round={round_no}, part={n_parts}) returns the part where you "
            f"decided to submit it{rest}.")


class ReasoningStore:
    """The turns of one run, in memory and appended to one JSONL file."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: list[dict] = []
        self._f = self.path.open("w")

    def __len__(self):
        return len(self.records)

    def close(self):
        self._f.close()

    def add(self, round_no: int, elapsed_s: float, reasoning: str, said: str,
            completion_tokens: int, finish: str, did: list[str],
            closed_think: bool) -> dict:
        """Append one finished turn. `did` is what it amounted to, one short
        phrase per action ("submit #3 -> WA", "get_submission(id=2)")."""
        rec = {"round": round_no,
               "elapsed_s": round(elapsed_s, 2),
               "completion_tokens": completion_tokens,
               "finish_reason": finish,
               "closed_think": closed_think,
               "did": did,
               "reasoning": reasoning,
               "said": said}
        self.records.append(rec)
        self._f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._f.flush()
        return rec

    def _find(self, round_no):
        for r in self.records:
            if r["round"] == round_no:
                return r
        return None

    def _missing(self, round_no, current_round: int | None) -> str:
        if round_no == current_round:
            return (f"Round {round_no} is the turn you are in now. Its reasoning is "
                    f"saved when the turn ends; from the next turn on, "
                    f"get_reasoning(round={round_no}) returns it.")
        if not self.records:
            return "This is your first turn, so there is no earlier reasoning to read back."
        return (f"There is no round {round_no}. Your earlier turns are rounds "
                f"{self.records[0]['round']} through {self.records[-1]['round']}.")

    def pointer_for(self, round_no: int) -> str:
        """pointer() for a stored turn; empty if the turn is not stored."""
        r = self._find(round_no)
        return pointer(round_no, len(split_parts(r["reasoning"]))) if r else ""

    @staticmethod
    def _did(r) -> str:
        return "; ".join(r["did"]) if r["did"] else "(no tool call)"

    # --- the three read-only tools ------------------------------------------

    def render_list(self) -> str:
        if not self.records:
            return "This is your first turn: no earlier reasoning has been saved yet."
        lines = [f"{len(self.records)} earlier turn(s), oldest first. The reasoning of "
                 f"every one is saved word for word.", "",
                 " round      at   tokens  parts  what the turn did"]
        for r in self.records:
            lines.append(" {:>5}  {:>5.1f}m  {:>7,}  {:>5}  {}".format(
                r["round"], r["elapsed_s"] / 60.0, r["completion_tokens"],
                len(split_parts(r["reasoning"])), self._did(r)[:110]))
        lines += ["",
                  "`at` is when the turn ended. get_reasoning(round=N) returns a turn's "
                  "reasoning from part 1, part=K any other part; the last part is where "
                  "you decided what to do. search_reasoning(pattern=...) finds the turns "
                  "where you discussed something."]
        return _clip("\n".join(lines))

    def render_get(self, round_no: int, part: int | None = None,
                   current_round: int | None = None) -> str:
        r = self._find(round_no)
        if r is None:
            return self._missing(round_no, current_round)
        text, bounds = r["reasoning"], split_parts(r["reasoning"])
        n = len(bounds)
        part = 1 if part is None else part
        if not 1 <= part <= n:
            return (f"Round {round_no}'s reasoning has {n} part(s), numbered 1 to {n}; "
                    f"there is no part {part}.")
        start, end = bounds[part - 1]
        head = (f"Round {round_no}, your reasoning, part {part} of {n} (characters "
                f"{start + 1:,}-{end:,} of {len(text):,}). The turn ended at "
                f"{r['elapsed_s'] / 60.0:.1f} min: {self._did(r)}.")
        body = text[start:end].strip() or "(this turn had no reasoning text)"
        tail = []
        if part < n:
            tail.append(f"(Next: get_reasoning(round={round_no}, part={part + 1}).)")
        elif r["said"].strip():
            said = r["said"].strip()
            if len(said) > SAID_CHARS:
                said = said[:SAID_CHARS].rstrip() + " [...]"
            tail.append(f"After this reasoning you wrote:\n{said}")
        out = head + "\n\n----- reasoning -----\n" + body + "\n----- end of part -----"
        return _clip(out + ("\n\n" + "\n\n".join(tail) if tail else ""),
                     MAX_TOOL_CHARS)

    def render_search(self, pattern: str, round_no: int | None = None,
                      max_hits: int = 40, per_round: int = 6, context: int = 160) -> str:
        """Matches grouped by turn, at most `per_round` shown from each, so
        one long turn that repeats a word cannot crowd out every other turn
        that mentions it; the rest are counted."""
        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"`{pattern}` is not a valid regular expression: {e}"
        pool = self.records if round_no is None else [r for r in self.records
                                                      if r["round"] == round_no]
        if round_no is not None and not pool:
            return self._missing(round_no, None)
        out, hits, full = [], 0, False
        for r in pool:
            bounds = split_parts(r["reasoning"])
            where, more = [], 0
            for src, text in (("reasoning", r["reasoning"]), ("wrote", r["said"])):
                pos = 0
                # Line by line: a pattern only ever sees one line, which keeps a
                # careless regex from backtracking across a 400k-character turn.
                for line in text.splitlines(keepends=True):
                    m = rx.search(line)
                    if m and (len(where) >= per_round or hits >= max_hits):
                        more += 1
                        full = full or hits >= max_hits
                    elif m:
                        a = max(0, m.start() - context // 2)
                        snippet = line[a:a + context].strip()
                        if src == "reasoning":
                            k = next(i for i, (s, e) in enumerate(bounds, 1)
                                     if pos < e or i == len(bounds))
                            where.append(f"    part {k}: {snippet}")
                        else:
                            where.append(f"    (after reasoning): {snippet}")
                        hits += 1
                    pos += len(line)
            if where:
                if more:
                    where.append(f"    ... and {more} more match(es) in this turn")
                out.append(f"  round {r['round']} ({self._did(r)[:60]}):\n" + "\n".join(where))
        scope = f"round {round_no}" if round_no is not None else f"{len(pool)} turn(s)"
        if not out:
            return f"Nothing in your reasoning matches `{pattern}` ({scope} searched, case-insensitive)."
        head = (f"Matches for `{pattern}` (case-insensitive) in {len(out)} of {len(pool)} "
                f"turn(s). get_reasoning(round=N, part=K) shows the surrounding text.")
        tail = ("\n\n(more turns matched than are shown; narrow the pattern or pass round=N)"
                if full else "")
        return _clip(head + "\n\n" + "\n\n".join(out) + tail)
