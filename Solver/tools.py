"""The tools, the parser for the model's calls, and the dispatcher.

Two toolsets. `v1` is ../agent's five, unchanged; `v2` adds three that read
back the model's own earlier reasoning (trace_store.py). Structured tools
rather than one general-purpose shell. The 2026 harness
literature is fairly consistent that a small set of typed tools beats a bash
escape hatch on accuracy, tokens and wall time for a task this narrow, and the
narrower surface is also what keeps this arm comparable to the baseline: there
is exactly one action that changes the world, `submit`, and it does precisely
what the baseline's code-block extraction did.

    submit              compile and judge a program. Costs a submission.
    list_submissions    the index of everything submitted so far.
    get_submission      one past submission, in full.
    diff_submissions    what changed between two of them.
    search_submissions  grep the sources and the approach lines.

    list_rounds         v2: one line per earlier turn and what it did.
    get_reasoning       v2: one earlier turn's reasoning, a part at a time.
    search_reasoning    v2: grep the reasoning of every earlier turn.

Every tool but `submit` is read-only and free. The model's calls arrive as the XML the chat template asks for:

    <tool_call>
    <function=submit>
    <parameter=code>
    #include <bits/stdc++.h>
    ...
    </parameter>
    </function>
    </tool_call>

The template renders the schemas below into the system message and states that
format itself, so nothing here repeats it.
"""
import json
import re


# The model may not spend a whole turn firing tools; four is well past what any
# legitimate turn needs and bounds the cost of a turn that goes wrong.
MAX_CALLS_PER_TURN = 4

TOOLS = [
    {"type": "function", "function": {
        "name": "submit",
        "description": (
            "Submit a complete C++17 program to the judge. This is the only action that "
            "counts as a submission and the only way to solve the problem. The judge "
            "replies with the bare verdict -- AC, WA, TLE, RTE or CE -- and tells you "
            "nothing about which test failed or how many passed. The program is kept and "
            "can be read back later with get_submission."),
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string", "description": (
                "The complete program, from the first #include to the closing brace of "
                "main. Not a diff and not a fragment: whatever you send is compiled on "
                "its own.")},
            "approach": {"type": "string", "description": (
                "One or two sentences naming the algorithmic idea this program "
                "implements, clearly enough to tell it apart from your other attempts. "
                "You will be shown this line in list_submissions long after the "
                "reasoning behind it has left your context, so write it for that "
                "reader: the idea, not the syntax.")},
        }, "required": ["code", "approach"]}}},

    {"type": "function", "function": {
        "name": "list_submissions",
        "description": (
            "The index of every submission you have made on this problem: id, verdict, "
            "when it was submitted, its length, a short hash of its source and the "
            "approach you recorded for it. Two rows with the same hash are the same "
            "program. Free -- it does not cost a submission."),
        "parameters": {"type": "object", "properties": {}}}},

    {"type": "function", "function": {
        "name": "get_submission",
        "description": (
            "Read one of your earlier submissions back in full: its verdict, the "
            "approach you recorded and its complete source. Free -- it does not cost a "
            "submission."),
        "parameters": {"type": "object", "properties": {
            "id": {"type": "integer", "description": "The submission id, as shown by list_submissions."},
        }, "required": ["id"]}}},

    {"type": "function", "function": {
        "name": "diff_submissions",
        "description": (
            "A unified diff between the sources of two earlier submissions, for checking "
            "what a change actually changed. Free -- it does not cost a submission."),
        "parameters": {"type": "object", "properties": {
            "a": {"type": "integer", "description": "Id of the earlier submission."},
            "b": {"type": "integer", "description": "Id of the later submission."},
        }, "required": ["a", "b"]}}},

    {"type": "function", "function": {
        "name": "search_submissions",
        "description": (
            "Search every program you have submitted, and the approach lines you wrote "
            "for them, with a regular expression. Use it to check whether you have "
            "already tried something. Free -- it does not cost a submission."),
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "A Python regular expression."},
        }, "required": ["pattern"]}}},
]

# Reasoning is stripped from every turn the window keeps, so without these the
# model's own thinking is gone the moment a turn ends; see trace_store.py.
REASONING_TOOLS = [
    {"type": "function", "function": {
        "name": "list_rounds",
        "description": (
            "The index of your earlier turns: for each, when it ended, how many tokens "
            "it produced, how many parts its reasoning has and what it did (what it "
            "submitted and the verdict, or which tool it called). Your reasoning from "
            "earlier turns is not in this conversation, but every turn's is saved word "
            "for word; this tells you where to look. Free -- it does not cost a "
            "submission."),
        "parameters": {"type": "object", "properties": {}}}},

    {"type": "function", "function": {
        "name": "get_reasoning",
        "description": (
            "Read back the reasoning you wrote in one earlier turn, word for word. "
            "Long reasoning comes in parts of about 12,000 characters; the reply says "
            "how many parts there are, and the last part is where you decided what to "
            "do. Use it to recover an argument, a case you had already ruled out, or a "
            "line of thought a turn was cut off before finishing. Free -- it does not "
            "cost a submission."),
        "parameters": {"type": "object", "properties": {
            "round": {"type": "integer", "description": "The turn, as numbered by list_rounds."},
            "part": {"type": "integer", "description": "Which part, from 1. Defaults to 1."},
        }, "required": ["round"]}}},

    {"type": "function", "function": {
        "name": "search_reasoning",
        "description": (
            "Search the reasoning of all your earlier turns with a regular expression, "
            "case-insensitive. Each match gives the turn and the part it is in, for "
            "get_reasoning. Use it to find where you worked something out or why you "
            "dropped an idea. Free -- it does not cost a submission."),
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "A Python regular expression."},
            "round": {"type": "integer", "description": "Only search this turn. Optional."},
        }, "required": ["pattern"]}}},
]

SAMPLE_TOOLS = [
    {"type": "function", "function": {
        "name": "run_samples",
        "description": (
            "Compile a complete C++17 program exactly as submit does and run it on this "
            "problem's sample inputs -- the ones printed in the statement, and no others. "
            "Shows the compiler's first errors, or for every sample your output next to "
            "the expected output, whether it is judged correct, the running time and the "
            "end of your stderr. Free: it is not a submission and cannot solve the problem, "
            "and passing the samples does not mean the secret tests will pass."),
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string", "description": (
                "The complete program, from the first #include to the closing brace of "
                "main, as you would submit it. Debugging output may go to stderr.")},
        }, "required": ["code"]}}},
]

TOOLSETS = {"v1": TOOLS, "v2": TOOLS + REASONING_TOOLS, "v3": TOOLS + REASONING_TOOLS + SAMPLE_TOOLS}

def schema_of(tools: list[dict]) -> dict:
    """name -> parameters, for one toolset. Parsing is always against the
    toolset the run was given: a v1 run that calls get_reasoning is told
    there is no such tool, exactly as for any other name it made up."""
    return {t["function"]["name"]: t["function"]["parameters"] for t in tools}

# A program in a fenced block is not a tool call, but it is unmistakably an
# attempt to submit one: this model is heavily post-trained on competitive
# programming, where the answer *is* a ```cpp block, and that reflex wins over
# the call format often enough that a harness which ignores it measures format
# compliance rather than the thing the arm is about. The baseline reads exactly
# this shape, with the same "last block wins" rule, so accepting it also keeps
# a submission in one arm the same event as a submission in the other. Every
# call records which form it arrived in, so the rate stays measurable and the
# fallback can be switched off for an ablation.
# The language tag is whatever the model felt like writing. `\w*` looked
# right and silently dropped every ```c++ block, which is the tag this
# model reaches for about as often as ```cpp.
_CODE_FENCE_RE = re.compile(r"```([^\s`]*)[ \t]*\r?\n(.*?)```", re.DOTALL)
_APPROACH_RE = re.compile(r"^[ \t*_]*Approach[ \t*_]*:[ \t]*(.+?)[ \t*_]*$", re.M | re.I)

_TOOL_CALL_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
_FUNCTION_RE = re.compile(r"<function=([^>\s]+)\s*>(.*?)</function>", re.DOTALL)
_PARAM_RE = re.compile(r"<parameter=([^>\s]+)\s*>(.*?)</parameter>", re.DOTALL)


def split_think(text: str) -> tuple[str, str]:
    """(reasoning, visible).

    Generation starts inside the think block -- the template's generation
    prompt already emitted the opening `<think>` -- so what comes back has a
    closing tag and no opening one. No closing tag means the model never left
    its reasoning: all of it is reasoning and there is nothing visible to act
    on. That is usually a truncated turn; the one exception, a finished turn
    whose reasoning ends on a call, is calls_left_in_think's.
    """
    if "</think>" in text:
        head, _, tail = text.rpartition("</think>")
        return head.removeprefix("<think>").strip(), tail.strip()
    return text.strip(), ""


def calls_left_in_think(reasoning: str) -> tuple[str, str]:
    """(reasoning, calls) for a turn that ended without closing its think block.

    Both models often call a tool from inside their reasoning: the turn runs
    to the end of generation without a `</think>`, its last act a complete
    `<tool_call>` block. split_think files all of it as reasoning, so the call
    was discarded and the turn counted as one without a call -- two of those
    in a row end the contest. Measured on the transcripts, 258 of Qwen's 342
    no-call turns were this (177 of them submits), and 14 of its 22 unsolved
    no-insight runs ended on it; Nemotron's runs have the same pattern.

    Only `<tool_call>` blocks at the very end are taken, after the last of
    them nothing but whitespace: that is the model ending its turn on the
    call. A block followed by more reasoning is a draft the model went on
    thinking past -- Nemotron writes those -- and stays reasoning, as does
    anything short of the full wrapper. The caller applies this only to a turn
    that stopped on its own, never to one cut off by the token budget.
    """
    blocks = list(_TOOL_CALL_RE.finditer(reasoning))
    end = start = len(reasoning.rstrip())
    for m in reversed(blocks):
        if reasoning[m.end():end].strip():
            break
        start = end = m.start()
    if start == len(reasoning.rstrip()):
        return reasoning, ""
    return reasoning[:start].strip(), reasoning[start:].strip()


def strip_code_fences(text: str) -> str:
    """The visible text with fenced blocks removed.

    Used when a fenced block has been read as a submit call: the program is
    already in the call's arguments, and leaving the block in the content too
    would put it into the prompt a second time and undo the elision.
    """
    return _CODE_FENCE_RE.sub("", text).strip()


def strip_tool_calls(text: str) -> str:
    """The visible text with the call XML removed.

    History is replayed through the template's own `tool_calls` field, which
    re-renders the XML from the parsed arguments. Leaving the raw XML in the
    content as well would put every call into the prompt twice.
    """
    return _TOOL_CALL_RE.sub("", _FUNCTION_RE.sub("", text)).strip()


# Parameters that are required of the model but not of the harness. `approach`
# is a note to its future self, not part of the task: rejecting a submission
# that omits it would spend a whole generation on a formatting round trip and
# charge the agent arm for something that has nothing to do with solving the
# problem. `code` has no default -- there is nothing to compile without it.
_SOFT_DEFAULTS = {"submit": {"approach": ""}}


def _json_objects(text: str):
    """Every balanced `{...}` in the text that parses and carries a "name".

    The model sometimes answers with the JSON call shape from some other
    harness -- `{"name": "submit", "arguments": {"code": "..."}}` -- instead of
    the XML this template asks for. Nothing else in the turn carries the
    program: it is a JSON-escaped string, so there is no fenced block for the
    code-block fallback to find, and before this the whole turn was discarded
    and the contest often ended two rounds later having submitted nothing.

    Scanning for balanced braces rather than running a regex over the text is
    what makes this safe: a C++ program inside the JSON string is full of
    braces and quotes, and only a scanner that knows it is inside a string can
    find the end of the object. Starting the walk at the `{` before each
    "name" also accepts the nested `{"function": {"name": ...}}` shape.
    """
    out, i = [], 0
    while (i := text.find('"name"', i)) != -1:
        start = text.rfind("{", 0, i)
        if start == -1:
            i += 6
            continue
        depth, j, in_str, esc = 0, start, False, False
        while j < len(text):
            ch = text[j]
            if in_str:
                # A backslash consumes the next character whatever it is, so an
                # escaped quote does not end the string. Getting this wrong lets
                # the braces inside a C++ program leak into the depth count, and
                # every program that prints a quote has one.
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        else:
            i += 6
            continue
        try:
            obj = json.loads(text[start:j + 1])
        except ValueError:
            i += 6
            continue
        if isinstance(obj, dict) and isinstance(obj.get("name"), str):
            out.append(obj)
            i = j + 1
        else:
            i += 6
    return out


def _stringify(v):
    """JSON gives typed values; _coerce works on the strings the XML yields."""
    if isinstance(v, str):
        return v
    return json.dumps(v) if isinstance(v, (dict, list)) else str(v)


def _coerce(name: str, args: dict[str, str], schema: dict) -> tuple[dict, str | None]:
    """Parameter strings -> the types the schema declares."""
    props = schema[name].get("properties", {})
    out = {}
    for key, raw in args.items():
        if key not in props:
            return {}, (f"{name} has no parameter `{key}`. It takes: "
                        f"{', '.join(props) or '(none)'}.")
        if props[key].get("type") == "integer":
            try:
                out[key] = int(raw.strip())
            except ValueError:
                return {}, f"`{key}` must be an integer, got `{raw.strip()[:40]}`."
        else:
            out[key] = raw
    for key, default in _SOFT_DEFAULTS.get(name, {}).items():
        out.setdefault(key, default)
    missing = [k for k in schema[name].get("required", []) if k not in out]
    if missing:
        return out, f"{name} is missing required parameter(s): {', '.join(missing)}."
    return out, None


def _repair_name(called: str, param_names: set[str], schema: dict) -> str | None:
    """The tool a misnamed call meant, for the one mistake worth repairing.

    Observed in a real run: the model produced well-formed call XML but wrote
    the parameter's name where the function's belongs -- `<function=code>` over
    `<parameter=code>` holding a complete program. That is unmistakably a
    submit, and rejecting it costs a whole generation, which on this model runs
    to seventy thousand tokens and four minutes of a two-hour contest.

    Repairing anything looser than that is worse than not repairing at all. A
    first version keyed on the parameters alone, and the next run showed why:
    the model asked for `stateful_python` -- a sandbox from its own training,
    which does not exist here -- passing Python in a `code` parameter, and the
    rule handed that to the judge as a C++ submission. It cost a submission and
    returned a compile error, and the model was never told the tool it wanted
    was not there.

    So the name itself has to be the evidence: it must be a parameter of
    exactly one tool, and the parameters given must belong to that same tool.
    `code` is submit's and nothing else's; `stateful_python` is no tool's
    parameter, so it is reported as the unknown tool it is. In v2 `pattern`
    and `round` each belong to two tools, so neither is ever repaired.
    """
    owners = {name for name, sch in schema.items() if called in sch.get("properties", {})}
    if len(owners) != 1:
        return None
    name = owners.pop()
    props = set(schema[name].get("properties", {}))
    return name if param_names and param_names <= props else None


def _parse_function_block(name: str, body: str, strict: bool, schema: dict) -> dict:
    call = {"name": name, "arguments": {}, "error": None, "format": "strict" if strict else "lenient"}
    raw = {k: v.strip("\n") for k, v in _PARAM_RE.findall(body)}
    if name not in schema:
        repaired = _repair_name(name, set(raw), schema)
        if repaired is None:
            # agentv2's wording says there is no sandbox; a v3 run has the sample runner.
            sandbox = (
                "`run_samples` compiles a program and runs it on the statement's samples "
                "only, and `submit` sends a program to the judge and comes back with the "
                "verdict on the secret tests: there is no shell or interpreter beyond them."
                if "run_samples" in schema else
                "There is no way to compile, run or test a program here and no sandbox to "
                "work in: `submit` sends a program to the judge and comes back with the "
                "verdict, and that is the only way to find out whether it is right.")
            call["error"] = (f"There is no tool called `{name}`. The tools are: "
                             f"{', '.join(schema)}. {sandbox}")
            return call
        call["name"] = name = repaired
        call["format"] = "repaired"
    args, err = _coerce(name, raw, schema)
    call["arguments"], call["error"] = args, err
    return call


def parse_tool_calls(visible: str, accept_code_block: bool = True,
                     tools: list[dict] = TOOLS) -> list[dict]:
    """The calls in one turn's visible text.

    Well-formed calls are `<function=...>` nested in `<tool_call>`, which is
    what the template asks for. A bare `<function=...>` block with the wrapper
    left off is accepted too and marked `lenient`: it is unambiguous, rejecting
    it would spend a whole generation on a formatting round trip, and the mark
    keeps the format-adherence rate measurable from the transcript afterwards.

    Failing both, a JSON object naming a tool is read as that call and marked
    `json`, and failing that a bare fenced code block is read as a `submit` --
    see the notes on _json_objects and _CODE_FENCE_RE -- and marked
    `code_block`.

    `tools` is the run's toolset: a name outside it is an unknown tool.
    """
    schema = schema_of(tools)
    calls = []
    for block in _TOOL_CALL_RE.findall(visible):
        for name, body in _FUNCTION_RE.findall(block):
            calls.append(_parse_function_block(name, body, True, schema))
    if not calls:
        for name, body in _FUNCTION_RE.findall(visible):
            calls.append(_parse_function_block(name, body, False, schema))
    if not calls:
        for obj in _json_objects(visible):
            name = obj["name"]
            raw = {k: _stringify(v) for k, v in (obj.get("arguments") or {}).items()
                   if isinstance(k, str)}
            call = {"name": name, "arguments": {}, "error": None, "format": "json"}
            if name not in schema:
                repaired = _repair_name(name, set(raw), schema)
                if repaired is None:
                    continue          # some other JSON in the prose, not a call
                call["name"] = name = repaired
            call["arguments"], call["error"] = _coerce(name, raw, schema)
            calls.append(call)
    if not calls and accept_code_block:
        blocks = _CODE_FENCE_RE.findall(visible)
        if blocks:
            m = _APPROACH_RE.search(visible)
            calls.append({"name": "submit", "error": None, "format": "code_block",
                          "arguments": {"code": blocks[-1][1].strip(),
                                        "approach": m.group(1).strip()[:300] if m else ""}})
    return calls


def execute(call: dict, store, submit_cb, traces=None,
            current_round: int | None = None, samples_cb=None) -> tuple[bool, str]:
    """Run one parsed call. -> (ok, what the model is told).

    `submit_cb(code, approach) -> str` is the judge, held by the caller: it
    owns the clock, the submission counter and the transcript, and it is the
    only path in this module that changes anything. `samples_cb(code) -> str`
    is the sample runner of a v3 run. `traces` is the ReasoningStore of a v2
    or v3 run; parse_tool_calls has already turned a tool outside the run's
    toolset into an unknown-tool error.
    """
    if call["error"]:
        return False, call["error"]
    name, args = call["name"], call["arguments"]
    if name == "submit":
        return True, submit_cb(args["code"], args.get("approach", ""))
    if name == "run_samples" and samples_cb is not None:
        return True, samples_cb(args["code"])
    if name == "list_submissions":
        return True, store.render_list()
    if name == "get_submission":
        out = store.render_get(args["id"])
        sub = store._find(args["id"])
        if traces is not None and sub is not None:
            out += "\n\n" + traces.pointer_for(sub["round"])
        return True, out.rstrip()
    if name == "diff_submissions":
        return True, store.render_diff(args["a"], args["b"])
    if name == "search_submissions":
        return True, store.render_search(args["pattern"])
    if traces is not None:
        if name == "list_rounds":
            return True, traces.render_list()
        if name == "get_reasoning":
            return True, traces.render_get(args["round"], args.get("part"), current_round)
        if name == "search_reasoning":
            return True, traces.render_search(args["pattern"], args.get("round"))
    return False, f"There is no tool called `{name}`."
