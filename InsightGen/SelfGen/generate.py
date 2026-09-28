"""One round's generation session, run on the target model itself.

The session of ../GPT/openaiGen.py -- the same round message, the same five
tools, the same rules and the same step limits -- with the local model in
place of the OpenAI API. The one thing said differently is who the agent is:
the model is told that it is the agent, and asked to think first about where
it would itself go wrong on the problem.

What the Responses API did for GPT is done here by hand:

  * function calling      The chat template's <tool_call> XML, parsed below.
  * previous_response_id  The message list is kept here. Reasoning goes back in
                          as `reasoning_content`, and the template keeps it for
                          every turn after the last user message -- tool
                          results are not user messages -- so what the model
                          worked out in its first turn is still in front of it
                          when it submits.
  * tool_choice (forced)  The model reasons, then its turn is prefilled with
                          the opening of a submit_insight call and it writes
                          the arguments.
  * reasoning.effort      No equivalent. The model thinks as the agent does:
                          thinking on, the same sampling, the same per-turn cap.

selfGen.py imports this on the login node for --show-prompt, so nothing here
imports vllm at module level.
"""
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

GEN_DIR = Path(__file__).resolve().parent
CODEBASE = GEN_DIR.parents[1]
os.environ.setdefault("WF_ARCHIVE", str(CODEBASE / "data" / "problems"))
sys.path.insert(0, str(CODEBASE / "agent"))

import agent_prompt as AP  # noqa: E402
import history as H  # noqa: E402
import prompt as P  # noqa: E402
from problem import ARCHIVE_ROOT  # noqa: E402
# The agent's parser is bound to the agent's own five tools; its regexes and
# its JSON scanner are not, and they are what this model's calls look like.
from tools import (_FUNCTION_RE, _PARAM_RE, _TOOL_CALL_RE, _json_objects,  # noqa: E402
                   _stringify, split_think, strip_tool_calls)

MAX_STEPS = 40            # model calls in one generation session before submit is forced
MAX_FORCED = 5            # forced calls that may still be rejected before the round gives up


INSTRUCTIONS = """You write hints ("insights") for a competitive-programming agent, and improve them over several rounds from measured results.

# The agent

The agent is you: the same model as the one reading this, with the same weights, will attempt the problem with your insight. It starts in a new session and remembers nothing of this one. It has never seen the reference solution or the editorial, and nothing you write reaches it except the insight text.

It is attempting one ICPC World Finals problem under contest rules. It is shown the problem statement, samples and limits, followed by your insight, exactly like this:

    ## Key insights
    {lead}

    <your insight>

It then works in turns: it reasons, and acts by calling tools. `submit` sends a C++17 program to the judge; four free tools let it look back at its own earlier submissions. The judge returns only a verdict (AC, WA, TLE, RTE or CE) and never says which test failed, and the agent cannot run code before submitting it. A run ends when a submission is accepted, when the agent gives up, or when its {budget_min}-minute clock runs out.

Because the agent is you, you are the one best placed to predict where it will go wrong. Before you write an insight, think about how you would attempt this problem yourself with only the statement in front of you: which key observation you would be likely to miss, which wrong approach you would be drawn to, and at which step of the algorithm or the implementation you would most likely make a mistake. Write the insight to prevent those mistakes; you do not need to tell yourself what you would get right anyway.

# How an insight is scored

Every insight you submit is evaluated by running the agent on the problem {n_runs} times, independently. Two numbers come out of that:

- solved: how many of the {n_runs} runs ended with an accepted submission;
- mean tokens: the agent's completion tokens per run (its reasoning included, summed over all its turns), averaged over the runs, with an unsolved run counted as {fail:,} tokens.

An insight succeeds if its solved count reaches a required level and its mean tokens stay within a budget. For each insight you are told whether it succeeded and which requirement it missed, but not the thresholds.

The outcome of the whole process is the shortest successful insight over all rounds, with length measured in the agent's tokenizer. So first find an insight that succeeds, then make it as short as you can while it still succeeds. A failed round does not undo an earlier success, which makes it safe to try a much shorter version of something that has worked. {n_runs} runs are a small sample and the token count of a single run varies a lot, so read the numbers with that in mind.

# Rules for the insight

- Do not paste the reference solution or large verbatim parts of it. Pseudocode, formulas, recurrences, key constants and exact algorithmic steps are all allowed. A submission is rejected if it contains more than {leak_chars} consecutive characters of the reference code verbatim, or more than {leak_lines} of its lines.
- The insight must stand on its own. The agent never sees the reference code, the editorial, or anything else you are shown here.

# Each round

You have {rounds} rounds in total. In each you submit exactly one insight, and it is evaluated before the next round begins, in a fresh session like this one. Your memory between rounds is the record of your earlier insights: the index in the message below, and these tools.

- get_insight(round): an earlier insight's full text, and how each run of the agent went with it.
- get_run(round, run): one of those runs turn by turn: tokens per turn, the tools the agent called, and each submission's verdict with the one-line approach the agent recorded for it. The agent's reasoning is not available.
- get_submission(round, run, id): the C++ program the agent submitted.
- check_insight(insight): a draft's length in the agent's tokenizer and whether it passes the rules, without submitting it.
- submit_insight(insight, rationale): submit this round's insight, with a sentence or two on what it is meant to test or change. You will see the rationale in later rounds. An accepted submission ends the round."""


ROUND_MESSAGE = """# Round {k} of {rounds}

<problem>
{problem}
</problem>

<reference_solution>
```cpp
{code}
```
</reference_solution>

<editorial>
{editorial}
</editorial>

<your_insights_so_far>
{index}
</your_insights_so_far>

Think about where you would most likely go wrong on this problem, then write this round's insight and submit it with submit_insight."""

NO_CALL_NUDGE = ("You did not call a tool, so nothing has been submitted. Finish the round "
                 "by calling submit_insight.")
TRUNCATED_NUDGE = ("Your previous turn was cut off before it finished, so nothing has been "
                   "submitted. Reason more concisely and finish the round by calling "
                   "submit_insight.")
OUT_OF_STEPS = "This round is out of steps. Submit your insight now with submit_insight."
OUT_OF_TIME = "This round is out of time. Submit your insight now with submit_insight."
FORCED_PREFIX = "<tool_call>\n<function=submit_insight>\n<parameter=insight>\n"
FORCED_RESERVE = 8192     # window kept free for the call when a forced turn reasons


def _fn(name, description, **props):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props, "required": list(props)}}}


_ROUND = {"type": "integer", "description": "an earlier round number"}
_RUN = {"type": "integer", "description": "run number, 1 to 5"}

TOOLS = [
    _fn("get_insight", "An earlier round's insight in full, your rationale for it, and how "
        "each run of the agent went with it.", round=_ROUND),
    _fn("get_run", "One run of the agent with an earlier round's insight, turn by turn: "
        "completion tokens per turn, the tools it called, and each submission's verdict "
        "with the approach the agent recorded. The agent's reasoning is not available.",
        round=_ROUND, run=_RUN),
    _fn("get_submission", "The full C++ source of one submission the agent made in a run, "
        "with its verdict and recorded approach.",
        round=_ROUND, run=_RUN, id={"type": "integer", "description": "submission id"}),
    _fn("check_insight", "Measure a draft without submitting it: its length in the agent's "
        "tokenizer, and whether it passes the rules.",
        insight={"type": "string"}),
    _fn("submit_insight", "Submit this round's insight. If it passes the rules the round "
        "ends and the insight is evaluated; if not, the reason comes back and you can fix "
        "it and submit again.",
        insight={"type": "string",
                 "description": "exactly the text the agent will see under the heading"},
        rationale={"type": "string",
                   "description": "one or two sentences: what this insight tests or changes "
                                  "relative to your earlier ones"}),
]
_SCHEMA = {t["function"]["name"]: t["function"]["parameters"] for t in TOOLS}


# --------------------------------------------------------------------------- the prompt

def load_problem(problem: str) -> tuple[str, str, str]:
    """-> (the problem as the agent sees it, solution.cpp, the editorial)."""
    problem_msg, meta = AP.build_problem_message(ARCHIVE_ROOT / problem)
    pd = Path(meta["dir"])
    editorial = P.load_insight(pd)
    if not editorial:
        raise SystemExit(f"{problem}: no solution.tex under {pd}")
    return problem_msg, (pd / "solution.cpp").read_text(), editorial


def instructions(rounds: int, time_budget_seconds: float) -> str:
    return INSTRUCTIONS.format(
        lead=AP.GENERATED_INSIGHT_LEAD, budget_min=round(time_budget_seconds / 60),
        n_runs=len(H.SEEDS), fail=H.FAIL_TOKENS, leak_chars=H.LEAK_CHARS,
        leak_lines=H.LEAK_LINES, rounds=rounds)


def round_message(k: int, rounds: int, problem_msg: str, ref_code: str, editorial: str,
                  hist: H.History) -> str:
    return ROUND_MESSAGE.format(k=k, rounds=rounds, problem=problem_msg.strip(),
                                code=ref_code.rstrip(), editorial=editorial,
                                index=hist.render_index())


# --------------------------------------------------------------------------- the calls

def _arguments(name: str, raw: dict[str, str]) -> tuple[dict, str | None]:
    """Parameter strings -> typed arguments, or why the call cannot be run."""
    if name not in _SCHEMA:
        return {}, f"there is no tool named {name!r}; the tools are {', '.join(_SCHEMA)}"
    props = _SCHEMA[name]["properties"]
    out = {}
    for key, val in raw.items():
        if key not in props:
            return {}, f"{name} has no argument {key!r}; it takes {', '.join(props)}"
        if props[key]["type"] == "integer":
            try:
                out[key] = int(val.strip())
            except ValueError:
                return {}, f"{key} must be an integer, got {val.strip()[:40]!r}"
        else:
            out[key] = val
    missing = [p for p in props if p not in out]
    if missing:
        return out, f"{name} needs the argument(s) {', '.join(missing)}"
    return out, None


def parse_calls(visible: str) -> list[dict]:
    """The calls in one turn's visible text: `<function=...>` inside `<tool_call>`
    as the template asks, a bare `<function=...>` block failing that, and a JSON
    object naming one of the tools failing both. `format` records which."""
    blocks = [(name, body, "strict") for block in _TOOL_CALL_RE.findall(visible)
              for name, body in _FUNCTION_RE.findall(block)]
    if not blocks:
        blocks = [(name, body, "lenient") for name, body in _FUNCTION_RE.findall(visible)]
    calls = []
    for name, body, fmt in blocks:
        args, err = _arguments(name, {k: v.strip("\n") for k, v in _PARAM_RE.findall(body)})
        calls.append({"name": name, "arguments": args, "error": err, "format": fmt})
    if not calls:
        for obj in _json_objects(visible):
            raw = obj.get("arguments") or obj.get("parameters") or {}
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except ValueError:
                    continue
            if obj["name"] not in _SCHEMA or not isinstance(raw, dict):
                continue              # some other JSON in the prose, not a call
            args, err = _arguments(obj["name"], {k: _stringify(v) for k, v in raw.items()})
            calls.append({"name": obj["name"], "arguments": args, "error": err,
                          "format": "json"})
    return calls


class InsightTools:
    """The five tools of one round, over the rounds evaluated before it."""

    def __init__(self, hist: H.History, ref_code: str, n_tokens):
        self.hist, self.ref_code, self.n_tokens = hist, ref_code, n_tokens
        self.earlier = {e["round"]: e["insight"] for e in hist.evals}
        self.accepted = {}

    def __call__(self, call: dict) -> str:
        if call["error"]:
            return f"error: {call['error']}"
        name, a = call["name"], call["arguments"]
        try:
            if name == "get_insight":
                return self.hist.render_insight(a["round"])
            if name == "get_run":
                return self.hist.render_run(a["round"], a["run"])
            if name == "get_submission":
                return self.hist.render_submission(a["round"], a["run"], a["id"])
            text = a["insight"].strip()
            problems = H.rule_problems(text, self.ref_code, self.earlier)
            n = self.n_tokens(text)
            if name == "check_insight":
                return f"{n} tokens. " + ("Passes the rules." if not problems else
                                          "Would be rejected: " + "; ".join(problems) + ".")
            if self.accepted:
                return "This round's insight was already accepted; this call was ignored."
            if problems:
                return ("Rejected, nothing submitted: " + "; ".join(problems) +
                        ". Fix it and call submit_insight again.")
            self.accepted.update(insight=text, rationale=" ".join(a["rationale"].split()),
                                 insight_tokens=n)
            return f"Accepted ({n} tokens). It will now be evaluated."
        except (LookupError, ValueError, TypeError) as e:
            return f"error: {e}"


# --------------------------------------------------------------------------- the session

def write_atomic(path: Path, text: str):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def generate(llm, tokenizer, problem: str, pdir: Path, k: int, rounds: int, *,
             time_budget_seconds: float, max_model_len: int, max_tokens_per_round: int,
             compact_threshold: float, gen_time_seconds: float, model_name: str) -> dict:
    """Run round k's session to an accepted insight and write insight.txt and
    insight.json into the round's directory. `llm` is the loaded agent model."""
    from vllm import SamplingParams
    from vllm.inputs import TokensPrompt

    rd = H.round_dir(pdir, k)
    hist = H.History(pdir, H.slug_of(problem), before_round=k)
    problem_msg, ref_code, editorial = load_problem(problem)

    def encode(text: str) -> list[int]:
        return tokenizer.encode(text, add_special_tokens=False)

    tools = InsightTools(hist, ref_code, lambda text: len(encode(text)))
    messages = [{"role": "system", "content": instructions(rounds, time_budget_seconds)},
                {"role": "user", "content": round_message(k, rounds, problem_msg, ref_code,
                                                          editorial, hist)}]

    def prompt() -> tuple[str, list[int]]:
        """The next prompt. While it is over the threshold, the oldest reasoning
        still in it is dropped -- the one thing in the session that can be."""
        while True:
            text = tokenizer.apply_chat_template(messages, tools=TOOLS, tokenize=False,
                                                 add_generation_prompt=True,
                                                 enable_thinking=True)
            ids = encode(text)
            if len(ids) <= compact_threshold * max_model_len:
                return text, ids
            old = next((m for m in messages if m.get("reasoning_content")), None)
            if old is None:
                return text, ids
            old["reasoning_content"] = ""

    def sample(ids: list[int], stop=None, reserve: int = 0) -> tuple[str, int, str, int]:
        """-> (text, completion tokens, finish reason, seed). Sampling as the agent's;
        `reserve` leaves that much of the window for a continuation."""
        seed = random.randrange(2 ** 31)
        sp = SamplingParams(temperature=1.0, top_p=0.95, seed=seed, stop=stop,
                            max_tokens=min(max_tokens_per_round,
                                           max(256, max_model_len - len(ids) - 16 - reserve)))
        out = llm.generate([TokensPrompt(prompt_token_ids=ids)], sp, use_tqdm=False)[0]
        o = out.outputs[0]
        return o.text, len(o.token_ids), o.finish_reason, seed

    print(f"round {k}: generating ({len(hist.evals)} earlier rounds)", flush=True)
    usage = Counter()
    step, forced, no_call = 0, False, 0
    t0 = time.time()
    with (rd / "gen_session.jsonl").open("a") as log_f:
        def record(obj):
            log_f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
            log_f.flush()

        record({"event": "session_start", "round": k, "model": model_name,
                "messages": messages, "tools": [t["function"]["name"] for t in TOOLS],
                "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        while not tools.accepted:
            step += 1
            if step > MAX_STEPS + MAX_FORCED:
                raise RuntimeError(f"round {k}: no acceptable insight after {step - 1} calls")
            # GPT's session has no clock; this one runs inside a Slurm job that
            # still has five contests to run after it.
            if not forced and time.time() - t0 > gen_time_seconds:
                messages.append({"role": "user", "content": OUT_OF_TIME})
                forced = True
            forced = forced or step > MAX_STEPS
            text, ids = prompt()
            if forced:
                # tool_choice, by hand: the model reasons as usual, then the call
                # is opened for it and it writes the arguments.
                think, n1, _, seed = sample(ids, stop=["</think>"], reserve=FORCED_RESERVE)
                head = think + "</think>\n" + FORCED_PREFIX
                rest, n2, finish, _ = sample(encode(text + head))
                raw, n_out = head + rest, n1 + n2
            else:
                raw, n_out, finish, seed = sample(ids)
            reasoning, visible = split_think(raw)
            calls = parse_calls(visible)
            usage["prompt_tokens"] += len(ids)
            usage["completion_tokens"] += n_out
            usage["max_prompt_tokens"] = max(usage["max_prompt_tokens"], len(ids))
            record({"event": "response", "step": step, "forced": forced, "seed": seed,
                    "prompt_tokens": len(ids), "completion_tokens": n_out,
                    "finish_reason": finish, "reasoning_chars": len(reasoning),
                    "elapsed_s": round(time.time() - t0, 1), "raw": raw,
                    "calls": [{k_: c[k_] for k_ in ("name", "format", "error")} for c in calls]})
            print(f"round {k} step {step}: {len(ids):,} prompt + {n_out:,} completion tokens, "
                  f"{finish}, calls: {[c['name'] for c in calls] or 'none'}"
                  f"{' (forced)' if forced else ''}", flush=True)
            content = strip_tool_calls(visible)
            if not calls:
                no_call += 1
                forced = forced or no_call >= 2
                # A user message follows, so the template would drop this turn's
                # reasoning anyway.
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": TRUNCATED_NUDGE
                                 if finish == "length" and not visible else NO_CALL_NUDGE})
                continue
            messages.append({"role": "assistant", "content": content,
                             "reasoning_content": reasoning,
                             "tool_calls": [{"type": "function",
                                             "function": {"name": c["name"],
                                                          "arguments": c["arguments"]}}
                                            for c in calls]})
            for c in calls:
                out = tools(c)
                record({"event": "tool", "step": step, "name": c["name"],
                        "arguments": c["arguments"], "format": c["format"], "output": out})
                messages.append({"role": "tool", "content": out})
            if step == MAX_STEPS and not tools.accepted:
                messages.append({"role": "user", "content": OUT_OF_STEPS})

    info = {"round": k, **tools.accepted, "model": model_name, "steps": step,
            "usage": dict(usage), "gen_seconds": round(time.time() - t0, 1),
            "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    write_atomic(rd / "insight.json", json.dumps(info, indent=2, ensure_ascii=False))
    write_atomic(rd / "insight.txt", tools.accepted["insight"] + "\n")   # marks the step done
    print(f"round {k}: insight of {info['insight_tokens']} tokens after {step} calls, "
          f"{info['gen_seconds'] / 60:.1f} min -- {info['rationale'][:150]}", flush=True)
    return info
