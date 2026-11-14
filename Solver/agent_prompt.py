"""What the agent is told: the system message, the problem, the judge's reply.

The problem message is built by slicing the baseline's own prompt, so the
statement, the samples, the limits and the insight block reach the model as
the exact same bytes in both arms. Everything that differs between the arms is
in this file and visible in one place:

  * the baseline's PREAMBLE is replaced by SYSTEM, because a preamble that
    ends "put your final solution in a single ```cpp block" describes an
    action this arm does not have;
  * SYSTEM adds the two things the baseline has no need to say -- that acting
    means calling a tool, and that earlier turns leave the conversation and
    live in the store instead.

The tool schemas and the call format are not in SYSTEM: the chat template
renders both into the system message itself from the `tools` argument.

SYSTEM is ../agent's, byte for byte, and is what a `--toolset v1` run is
told. SYSTEM_V2 is the same message with the count of free tools corrected and
one section added, saying that earlier reasoning is saved and how to read it.
SYSTEM_V3 (agentv3) replaces SYSTEM_V2's no-sandbox paragraph with the one
sandbox it has: `run_samples`, which compiles a program the way the judge does
and runs it on the statement's samples only.
"""
from judge import compile_excerpt
from prompt import PREAMBLE, build_prompt, verdict_line  # noqa: F401  (verdict_line re-exported)


SYSTEM = """You are an expert competitive programmer taking part in an ICPC contest.

You will be shown one problem: its statement, its samples and its execution \
limits. Reason about it, then submit a complete C++17 program by calling \
`submit`. Your program communicates only through standard input and standard \
output, exactly as described in the Input/Output sections -- do not print \
prompts or debug output.

Scoring is all-or-nothing: a submission is accepted only if it produces correct \
output on every secret test within the time limit. There is no partial credit, \
and the judge tells you only the verdict -- AC, WA, TLE, RTE or CE -- never \
which test failed or how many passed.

# Acting

Each turn you either call a tool or the contest ends. Think in plain language \
first if you want to; nothing you write after a call is read. If you have run \
out of ideas entirely, end a turn without calling anything and the contest is \
over.

Only `submit` costs you a submission and only `submit` can solve the problem: \
a program written out in a fenced code block has not been submitted. The other \
four tools are free and you may call them as often as you like.

There is no sandbox here -- no shell, no interpreter, no compiler you can \
reach -- so a program cannot be tried out before it is submitted, and the \
judge's verdict is the only feedback that exists.

# Your earlier attempts

The submissions listed above are there for reference, so that you do not \
repeat a mistake or resubmit a program you have already sent. You do not have \
to build on them: think the problem through again each round, and you are \
encouraged to explore a different algorithm entirely."""

REASONING_SECTION = """# Your earlier reasoning

Your reasoning does not carry over from one turn to the next. Each turn \
starts from the problem, the table of your submissions and your last few tool \
calls; what you thought on the way to them is no longer in the conversation. \
It is not lost: every turn's reasoning is saved word for word, including a \
turn that was cut off before it finished. `list_rounds` shows what each \
earlier turn did, `get_reasoning` reads one back and `search_reasoning` finds \
where you discussed something. Use them to recover an argument you made, a \
case you already ruled out, or a line of thought you did not get to finish."""

_FOUR = "The other four tools are free"
assert _FOUR in SYSTEM, "SYSTEM no longer says how many free tools there are; fix SYSTEM_V2"
SYSTEM_V2 = SYSTEM.replace(_FOUR, "The other tools are free") + "\n\n" + REASONING_SECTION

_NO_SANDBOX = """There is no sandbox here -- no shell, no interpreter, no compiler you can \
reach -- so a program cannot be tried out before it is submitted, and the \
judge's verdict is the only feedback that exists."""
SAMPLES_SECTION = """There is one sandbox: `run_samples` compiles a program exactly as `submit` \
does and runs it on this problem's sample inputs -- the ones printed in the \
statement, and no others. It shows the compiler's first errors, or for each \
sample your program's output next to the expected one, whether it is judged \
correct, its running time and the end of what it wrote to stderr. It does not \
count as a submission and cannot solve the problem; passing the samples does \
not mean the secret tests will pass. Standard output must stay exactly the \
answer, but you may print debugging information to stderr."""
assert _NO_SANDBOX in SYSTEM_V2, "SYSTEM_V2 no longer says there is no sandbox; fix SYSTEM_V3"
_NO_DEBUG = "do not print prompts or debug output."
assert _NO_DEBUG in SYSTEM_V2, "SYSTEM_V2 no longer forbids debug output; fix SYSTEM_V3"
SYSTEM_V3 = (SYSTEM_V2.replace(_NO_SANDBOX, SAMPLES_SECTION)
             .replace(_NO_DEBUG, "do not print prompts or debug output to standard output."))


def system_for(toolset: str) -> str:
    return {"v3": SYSTEM_V3, "v2": SYSTEM_V2}.get(toolset, SYSTEM)


def build_problem_message(problem_dir, insight: str | None = None) -> tuple[str, dict]:
    """The baseline prompt with its preamble removed, and nothing else changed.

    Taking the slice rather than rebuilding the body is deliberate: it cannot
    drift. If anyone edits the baseline's PREAMBLE or its assembly order, the
    assertion below fails loudly here instead of the two arms quietly ceasing
    to show the model the same problem.
    """
    full, meta = build_prompt(problem_dir, insight=insight)
    head = PREAMBLE + "\n\n"
    assert full.startswith(head), (
        "the baseline prompt no longer starts with PREAMBLE; agent and baseline arms "
        "would stop being comparable. Re-check build_prompt() in prompt.py.")
    return full[len(head):], meta


GENERATED_INSIGHT_LEAD = "Here are some key insights that can help you solve this problem."


def build_problem_message_with_insight(problem_dir, insight: str) -> tuple[str, dict]:
    """The problem message with a generated insight in place of the write-up.

    prompt.build_prompt announces its block as "a correct solution write-up
    ... the algorithm, why it works and its complexity", which misdescribes a
    hint a few lines long. Everything before the block is the no-insight
    message byte for byte; only the block's heading and lead line differ from
    the editorial arm's.
    """
    body, meta = build_problem_message(problem_dir)
    return body + f"\n## Key insights\n{GENERATED_INSIGHT_LEAD}\n\n{insight.strip()}\n", meta


def status_footer(n_submissions: int, elapsed_s: float, budget_s: float,
                  n_in_store: int, dropped_turns: int, toolset: str = "v1") -> str:
    """The one line of bookkeeping appended to every tool result.

    It rides on the tool result rather than a separate user message so the
    conversation stays assistant -> tool -> assistant, the shape the model was
    trained on. It carries the clock, which the baseline also puts on every
    verdict, and the number of turns that have left the context -- without
    which the model has no way to notice that its memory is now in the store.
    """
    remaining = max(0.0, budget_s - elapsed_s)
    bits = [f"{n_submissions} submission(s) made",
            f"{elapsed_s / 60.0:.1f} min elapsed",
            f"{remaining / 60.0:.1f} min remaining"]
    if dropped_turns > 0:
        keeps = ("list_submissions and list_rounds still have them" if toolset in ("v2", "v3")
                 else "list_submissions still has them")
        bits.append(f"{dropped_turns} earlier turn(s) no longer in this conversation; {keeps}")
    return "(" + ". ".join(bits) + ".)"


def render_verdict(result: dict, submission_num: int, solved: bool,
                   compile_error: str | None = None) -> str:
    """The judge's reply to one submit call.

    The same bare verdict the baseline returns, in the same words. On a CE,
    the compiler's first errors (agentv2 showed the tail, mostly candidate
    notes). Nothing about which test failed.
    """
    if compile_error is not None:
        body = f"CE -- Compile error.\n{compile_excerpt(compile_error)}"
    else:
        body = verdict_line(result)
    head = f"Submission #{submission_num}: {body}"
    if solved:
        return head + "\n\nProblem solved."
    return head


def render_samples(result: dict) -> str:
    """What `run_samples` tells the model: the first compile errors, or each
    sample's verdict, time, output next to the expected answer, and stderr."""
    if result.get("compile_error") is not None:
        return f"Compile error.\n{compile_excerpt(result['compile_error'])}"
    rows = result["samples"]
    lines = [f"{sum(r['ok'] for r in rows)}/{len(rows)} samples correct."]
    for r in rows:
        lines.append(f"\n## {r['name']}: {'correct' if r['ok'] else r['verdict']} ({r['time_s']:.2f} s)")
        lines.append(f"Input:\n{r['input'].rstrip()}")
        if r.get("expected") is not None:
            lines.append(f"Expected output:\n{r['expected'].rstrip()}")
        if r.get("output") is not None:
            lines.append(f"Your output:\n{r['output'].rstrip() or '(empty)'}")
        if r.get("stderr"):
            lines.append(f"Your stderr (end):\n{r['stderr'].rstrip()}")
    return "\n".join(lines)
