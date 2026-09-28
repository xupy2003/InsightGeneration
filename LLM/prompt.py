"""The prompt the model sees, and the judge feedback it gets back.

One prompt shape, used by both arms:

    PREAMBLE + statement + samples + execution limits [+ insight]

The insight block is the only difference between the two arms. Without it the
prompt is byte-identical to the baseline one, so an insight run differs from
its paired baseline run in exactly this block and nothing else.

Feedback is what a real ICPC judge returns: a bare verdict, AC/WA/TLE/RTE/CE,
with no indication of which test failed or how many passed. Handing the model
more would measure a different, much easier task.
"""
import re
from functools import lru_cache
from pathlib import Path

from problem import ARCHIVE_ROOT, load_problem


PREAMBLE = (
    "You are an expert competitive programmer taking part in an ICPC contest. "
    "You will be given a problem statement, constraints and sample input/output. "
    "Reason step by step about the solution, then provide a complete implementation "
    "in C++17. Your program communicates only through standard input and standard "
    "output, exactly as described in the Input/Output sections -- do not print "
    "prompts or debug output.\n"
    "Scoring is all-or-nothing: your submission is accepted only if it produces "
    "correct output on every secret test within the time limit. There is no partial "
    "credit.\n"
    "Put your final solution within a single code block: ```cpp\n<your code here>```"
)

_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}

def _fix_ligatures(text: str) -> str:
    for lig, plain in _LIGATURES.items():
        text = text.replace(lig, plain)
    return text

def _drop_braced_macro(text: str, macro: str) -> str:
    """Remove `\\macro{..}{..}` including nested braces (illustrations carry
    captions with their own braces, so a regex would cut them in half)."""
    out, i = [], 0
    needle = "\\" + macro
    while True:
        j = text.find(needle, i)
        if j == -1:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:j])
        k = j + len(needle)
        while k < len(text) and text[k] == "{":
            depth = 0
            while k < len(text):
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                    if depth == 0:
                        k += 1
                        break
                k += 1
            while k < len(text) and text[k] in " \t\n":
                if text[k] == "\n":
                    break
                k += 1
        i = k

def _limits_block(meta: dict) -> str:
    note = " (derived from the reference solutions; the package ships no absolute limit)" \
        if meta["time_limit_derived"] else ""
    s = (f"## Execution limits\n"
         f"{meta['time_limit']:g} second(s) CPU time and {meta['memory_mb']} MB memory "
         f"per test case{note}.\n")
    if meta["interactive"]:
        s += ("This is an INTERACTIVE problem: you exchange messages with the judge over "
              "stdin/stdout as described above. Flush after every write.\n")
    return s

_EXPLAIN = {
    "AC": "Accepted.",
    "WA": "Wrong answer.",
    "TLE": "Time limit exceeded.",
    "RTE": "Run-time error.",
    "CE": "Compile error.",
    "VE": "Judge error.",
}

def verdict_line(result: dict) -> str:
    v = result["verdict"] or "VE"
    short = v.split()[0].split("(")[0]
    return f"{v} -- {_EXPLAIN.get(short, '')}".strip()

def render_feedback(result, submission_num, elapsed_s, budget_s,
                    solved: bool, compile_error=None) -> str:
    """Single-problem mode. A real judge returns the verdict and nothing more."""
    remaining = max(0.0, budget_s - elapsed_s)
    header = (f"Submission #{submission_num} result "
              f"(elapsed {elapsed_s/60:.1f} min, {remaining/60:.1f} min remaining):\n")
    if compile_error is not None:
        body = f"CE -- Compile error.\n{compile_error[-2000:]}"
    else:
        body = verdict_line(result)
    if solved:
        return header + body + "\n\nProblem solved."
    footer = ("\n\nYou may submit again -- reason about what could be wrong and put the "
              "corrected solution in a single ```cpp code block. If you have no further "
              "ideas, reply without a code block to end the contest.")
    return header + body + footer


def load_statement(problem_dir: Path) -> tuple[str, str]:
    """(text, source_kind).

    `statement.txt` is already the pdftotext rendering of the official PDF, so
    unlike the regional archive there is nothing to extract or de-TeX. The
    trailing copyright/footer line and the "intentionally left blank" filler
    pages are dropped: they are page furniture, and leaving them in spends
    context on nothing.
    """
    path = problem_dir / "statement.txt"
    if not path.is_file():
        return "", "missing"
    text = _fix_ligatures(path.read_text(errors="replace"))
    keep = []
    for line in text.splitlines():
        s = line.strip()
        if "ICPC World Championship Problem" in s and "ICPC Foundation" in s:
            continue
        if s == "This page is intentionally left blank.":
            continue
        keep.append(line)
    out = "\n".join(keep).strip()
    return (out, "txt") if len(out) > 200 else (out, "short")

def format_samples(problem_dir: Path, max_bytes=4000) -> str:
    """The sample tests, from the archive's flat data/ directory.

    Interactive problems ship `sample-N.interaction` instead of an answer file
    -- a transcript with `<` for judge-to-you lines and `>` for yours. That is
    the only thing the model has to go on for the protocol, so it is shown
    rather than skipped.
    """
    data = problem_dir / "data"
    if not data.is_dir():
        return ""

    def clip(s):
        return s[:max_bytes] + "\n... (truncated)\n" if len(s) > max_bytes else s

    blocks = []
    for i, tin in enumerate(sorted(data.glob("sample-*.in")), 1):
        if tin.name.startswith("._"):
            continue
        inp = clip(tin.read_text(errors="replace"))
        ans = tin.with_suffix(".ans")
        interaction = tin.with_suffix(".interaction")
        if ans.is_file():
            out = clip(ans.read_text(errors="replace"))
            blocks.append(f"### Sample Input {i}\n```\n{inp.rstrip()}\n```\n"
                          f"### Sample Output {i}\n```\n{out.rstrip()}\n```")
        elif interaction.is_file():
            blocks.append(f"### Sample Interaction {i}\n"
                          f"(`<` is a line the judge writes to you, `>` a line you write)\n"
                          f"```\n{clip(interaction.read_text(errors='replace')).rstrip()}\n```")
        else:
            blocks.append(f"### Sample Input {i}\n```\n{inp.rstrip()}\n```")

    # An interactive problem with no .in at all still has its transcripts.
    if not blocks:
        for i, f in enumerate(sorted(data.glob("sample-*.interaction")), 1):
            blocks.append(f"### Sample Interaction {i}\n"
                          f"(`<` is a line the judge writes to you, `>` a line you write)\n"
                          f"```\n{clip(f.read_text(errors='replace')).rstrip()}\n```")
    return "\n\n".join(blocks)

@lru_cache(maxsize=None)
def _problem(problem_dir: str):
    """Load a WFProblem from whatever the caller had.

    The shared contest loop joins its --problem argument onto ARCHIVE_ROOT
    before handing it over, which turns the `2025/G` shorthand into a path that
    does not exist. So anything under ARCHIVE_ROOT is reduced back to its
    archive-relative form and passed to wf_eval, which resolves the shorthand,
    the full `2025/G-lava-moat` slug and a real directory alike.
    """
    p = Path(problem_dir)
    if p.is_dir():
        return load_problem(p)
    try:
        rel = p.resolve().relative_to(ARCHIVE_ROOT.resolve())
    except ValueError:
        rel = Path(*p.parts[-2:]) if len(p.parts) >= 2 else p
    return load_problem(str(rel))

def load_problem_meta(problem_dir) -> dict:
    """Same keys as icpc_contest_prompt.load_problem_meta, plus `problem`.

    `problem` is the loaded WFProblem. It is carried through so the grader can
    hand it straight to the evaluator: passing a bare path instead would make
    the shared evaluator re-resolve it as a Kattis package and fail.
    """
    problem = _problem(str(Path(problem_dir).resolve()))
    statement, kind = load_statement(problem.dir)
    return {
        "dir": problem.dir,
        "problem": problem,
        "contest": problem.contest,
        "name": problem.name,
        "title": problem.title,
        "time_limit": problem.time_limit,
        "time_limit_derived": False,      # WF limits are printed in the statement
        "memory_mb": problem.memory_mb,
        "interactive": problem.interactive,
        "statement": statement,
        "statement_kind": kind,
        "samples": format_samples(problem.dir),
        "n_tests": len(problem.tests()),
    }

def _lists_to_text(body: str) -> str:
    """itemize/enumerate -> bullets and numbered steps.

    The enumerations in these write-ups are the algorithm's steps, so an
    enumerate keeps its numbers instead of becoming bullets like everything
    else -- "do 3 before 4" is part of what the model is being told. Nesting is
    tracked because an enumerate step often contains an itemize of cases.
    """
    body = re.sub(r"\\(begin|end)\{(itemize|enumerate)\}(\[[^\]]*\])?", r"\n\\\1{\2}\n", body)
    out, stack = [], []
    for line in body.splitlines():
        s = line.strip()
        if s in (r"\begin{itemize}", r"\begin{enumerate}"):
            stack.append(["ol" if s.endswith("{enumerate}") else "ul", 0])
            continue
        if s in (r"\end{itemize}", r"\end{enumerate}"):
            if stack:
                stack.pop()
            continue
        m = re.match(r"\\item\s*(.*)", s)
        if m is None:
            # A line continuing the current item. The source wraps at 100
            # columns with its own indentation, which markdown would read as a
            # code block, so continuations are re-indented under their bullet.
            out.append(f"{'  ' * len(stack)}{s}" if stack and s else
                       ("" if not s else line))
            continue
        if not stack:                      # \item outside any list: a stray
            out.append(f"* {m.group(1)}")
            continue
        stack[-1][1] += 1
        kind, n = stack[-1]
        marker = f"{n}." if kind == "ol" else "*"
        out.append(f"{'  ' * (len(stack) - 1)}{marker} {m.group(1)}")
    return "\n".join(out)

def _detex_insight(text: str) -> str:
    """`solution.tex` as readable text.

    The same best-effort pass as icpc_contest_prompt._detex, with the
    constructs these write-ups actually use: sectioning, \\paragraph run-in
    headings (every lemma and proof is one) and the two list environments.
    Math is left alone for the same reason as there -- models read LaTeX math
    fine, and rewriting it would change what is being said.
    """
    m = re.search(r"\\begin\{document\}(.*)\\end\{document\}", text, re.S)
    body = m.group(1) if m else text
    for macro in ("title", "author", "date", "label"):
        body = _drop_braced_macro(body, macro)
    body = body.replace(r"\maketitle", "")
    body = re.sub(r"(?<!\\)%.*$", "", body, flags=re.M)
    # The insight block's own header is "##", so its sections sit below that.
    body = re.sub(r"\\section\*?\{([^}]*)\}", r"\n### \1\n", body)
    body = re.sub(r"\\subsection\*?\{([^}]*)\}", r"\n#### \1\n", body)
    # \paragraph is a run-in heading: "Lemma 1." then the text of the lemma.
    body = re.sub(r"\\paragraph\*?\{([^}]*)\}\s*", r"\n**\1** ", body)
    body = _lists_to_text(body)
    body = re.sub(r"\\texttt\{([^}]*)\}", r"`\1`", body)
    body = re.sub(r"\\(?:emph|textit|textbf)\{([^}]*)\}", r"*\1*", body)
    body = body.replace(r"\qed", "")
    body = body.replace("``", '"').replace("''", '"')
    body = re.sub(r"\\\\\s*$", "", body, flags=re.M)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()

def load_insight(path) -> str:
    """The problem's solution write-up, as text, from `solution.tex`.

    `path` is the problem directory or the .tex file itself. Returns "" when
    there is none, so the caller decides whether a missing write-up is fatal --
    silently falling back to the baseline prompt would put a baseline run in
    the insight results directory, which is the one mistake that cannot be
    spotted afterwards from the numbers.
    """
    path = Path(path)
    if path.is_dir():
        path = path / "solution.tex"
    if not path.is_file():
        return ""
    return _detex_insight(_fix_ligatures(path.read_text(errors="replace")))

def build_prompt(problem_dir, insight: str | None = None) -> tuple[str, dict]:
    """Single-problem prompt, identical in shape to the ICPC/IOI/CEOI ones.

    `insight` is the problem's solution write-up (see load_insight), appended
    after the limits block. With it left out the prompt is byte-identical to
    the baseline one, so an insight run differs from the baseline in exactly
    this block and nothing else.
    """
    meta = load_problem_meta(problem_dir)
    prompt = (f"{PREAMBLE}\n\n"
              f"# Problem: {meta['title']}\n"
              f"{meta['statement']}\n\n"
              f"{meta['samples']}\n\n"
              f"{_limits_block(meta)}")
    if insight:
        prompt += (f"\n## Insight: how to solve this problem\n"
                   f"Here is a correct solution write-up for this problem: the key "
                   f"observations, the algorithm, why it works and its complexity.\n\n"
                   f"{insight}\n")
    return prompt, meta