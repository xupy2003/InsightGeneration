"""Every submission this run has made, on disk, retrievable by tool call.

The baseline arm keeps its attempts in the context window: round 5 carries the
full text of rounds 1 through 4, so most of the window ends up spent
re-reading code the model already wrote, and `compact()` eventually throws it
away to make room. This is the same history written to one JSONL file
instead. The model keeps the last few turns in context and asks for the rest.

The file is the run's record as well as the model's memory: one line per
submission, appended the moment the judge returns, so an interrupted run still
has every attempt it made, with the code, the verdict and the model's own
description of what it was trying.

WHAT THE MODEL IS ALLOWED TO SEE
Each record also carries the judge's internals -- which test failed, how many
ran, the slowest one -- because that is what the analysis afterwards needs.
None of it is ever rendered into a tool result. A real ICPC judge returns the
bare verdict, the baseline arm returns the bare verdict, and a store that
leaked `failing_test` back to the model would be measuring a different and
much easier task while still looking like the same experiment. The render_*
methods below are the only thing the model sees; keep them that way.
"""
import difflib
import hashlib
import json
import re
from pathlib import Path


# A cap on every tool result, so that pulling history back in can never cost
# more context than leaving it there would have.
MAX_TOOL_CHARS = 24000


def _clip(text: str, limit: int = MAX_TOOL_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... (truncated, {len(text) - limit} more characters)"


class SubmissionStore:
    """The submissions of one run, in memory and appended to one JSONL file."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: list[dict] = []
        self._f = self.path.open("w")

    def __len__(self):
        return len(self.records)

    def close(self):
        self._f.close()

    def add(self, code: str, approach: str, result: dict, elapsed_s: float,
            round_no: int) -> dict:
        """Append one judged submission and return its record."""
        rec = {
            "id": len(self.records) + 1,
            "round": round_no,
            "elapsed_s": round(elapsed_s, 2),
            "verdict": result.get("verdict"),
            "accepted": bool(result.get("accepted")),
            "approach": (approach or "").strip() or "(none given)",
            "code": code,
            "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
            "code_lines": code.count("\n") + 1,
            # Judge internals: for the analysis, never for a tool result.
            "compile_error": result.get("compile_error"),
            "failing_test": result.get("failing_test"),
            "n_tests": result.get("n_tests"),
            "tests_run": result.get("tests_run"),
            "max_time_s": result.get("max_time_s"),
        }
        self.records.append(rec)
        self._f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._f.flush()
        return rec

    def _find(self, sid):
        for r in self.records:
            if r["id"] == sid:
                return r
        return None

    def _missing(self, sid) -> str:
        if not self.records:
            return "You have not submitted anything yet, so there is nothing to read back."
        return (f"There is no submission #{sid}. You have made {len(self.records)}: "
                f"#{self.records[0]['id']} through #{self.records[-1]['id']}.")

    # --- the four read-only tools ------------------------------------------

    def render_list(self) -> str:
        if not self.records:
            return ("You have not submitted anything yet. Call submit when you have a "
                    "complete C++17 program.")
        lines = [f"{len(self.records)} submission(s) so far, oldest first.", "",
                 "  id  verdict      at  lines  sha      approach"]
        for r in self.records:
            lines.append("  {:>2}  {:<7}  {:>5.1f}m  {:>5}  {}  {}".format(
                r["id"], r["verdict"] or "?", r["elapsed_s"] / 60.0, r["code_lines"],
                r["code_sha256"][:7], r["approach"].replace("\n", " ")[:90]))
        lines += ["",
                  "Rows with the same sha are the same program byte for byte -- resubmitting "
                  "one of those spends the clock and cannot change the verdict.",
                  "get_submission(id=N) returns the full source of one of them."]
        return _clip("\n".join(lines))

    def render_pinned_index(self, max_rows: int = 40) -> str:
        """The same table, pinned into the prompt and refreshed every round.

        A model whose turns have left the conversation is otherwise blind at
        the start of each round: it would have to spend a whole generation on
        `list_submissions` before it could act, every time. One line per
        submission is cheap enough to carry always, and it is the line that
        stops the model resubmitting something it already tried.

        Long runs are capped: the tail is what the model is working from, and
        list_submissions still returns everything.
        """
        if not self.records:
            return ("## Your submissions\n\nNone yet. This section is refreshed every "
                    "round and lists everything you have submitted.")
        shown = self.records[-max_rows:]
        omitted = len(self.records) - len(shown)
        head = ["## Your submissions",
                "",
                f"Refreshed every round. {len(self.records)} so far"
                + (f"; the {omitted} oldest are not shown here -- list_submissions has them."
                   if omitted else "."),
                "",
                "  id  verdict      at  lines  sha      approach"]
        for r in shown:
            head.append("  {:>2}  {:<7}  {:>5.1f}m  {:>5}  {}  {}".format(
                r["id"], r["verdict"] or "?", r["elapsed_s"] / 60.0, r["code_lines"],
                r["code_sha256"][:7], r["approach"].replace("\n", " ")[:90]))
        head.append("")
        head.append("get_submission(id=N) returns the full source of any of them.")
        return _clip("\n".join(head))

    def render_get(self, sid: int) -> str:
        r = self._find(sid)
        if r is None:
            return self._missing(sid)
        # The compiler's complaint is returned as well: the model already got
        # these exact bytes when it submitted, capped the same way, so handing
        # them back is not new information -- but leaving them out would mean a
        # CE that has scrolled out of the window can never be read again.
        ce = f"\n\nThe compiler said:\n{r['compile_error'][-2000:]}" if r["compile_error"] else ""
        return _clip(
            f"Submission #{r['id']} -- {r['verdict']}, submitted at "
            f"{r['elapsed_s'] / 60.0:.1f} min, {r['code_lines']} lines.\n"
            f"Approach you recorded: {r['approach']}\n\n"
            f"```cpp\n{r['code'].rstrip()}\n```{ce}")

    def render_diff(self, a: int, b: int) -> str:
        ra, rb = self._find(a), self._find(b)
        if ra is None:
            return self._missing(a)
        if rb is None:
            return self._missing(b)
        if ra["code_sha256"] == rb["code_sha256"]:
            return (f"Submissions #{a} ({ra['verdict']}) and #{b} ({rb['verdict']}) are the "
                    f"same program byte for byte.")
        diff = list(difflib.unified_diff(
            ra["code"].splitlines(), rb["code"].splitlines(),
            fromfile=f"submission {a} ({ra['verdict']})",
            tofile=f"submission {b} ({rb['verdict']})", lineterm="", n=3))
        changed = sum(1 for ln in diff if ln[:1] in "+-" and ln[:3] not in ("+++", "---"))
        return _clip(f"{changed} changed line(s) from #{a} to #{b}.\n\n" + "\n".join(diff))

    def render_search(self, pattern: str, max_hits: int = 40) -> str:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return f"`{pattern}` is not a valid regular expression: {e}"
        out, hits = [], 0
        for r in self.records:
            where = []
            if rx.search(r["approach"]):
                where.append(f"    approach: {r['approach'][:120]}")
            for i, line in enumerate(r["code"].splitlines(), 1):
                if hits >= max_hits:
                    break
                if rx.search(line):
                    where.append(f"    {i:>4}: {line.rstrip()[:160]}")
                    hits += 1
            if where:
                out.append(f"  #{r['id']} ({r['verdict']}):\n" + "\n".join(where))
        if not out:
            return (f"No submission matches `{pattern}`. "
                    f"({len(self.records)} submission(s) searched.)")
        head = f"Matches for `{pattern}` in {len(out)} of {len(self.records)} submission(s):"
        tail = "\n\n(more matches were cut off)" if hits >= max_hits else ""
        return _clip(head + "\n\n" + "\n\n".join(out) + tail)
