"""Paths, model and limits of ReasoningGraph Ver2. Standard library only."""
import os
from pathlib import Path

VER2_DIR = Path(__file__).resolve().parent
REPO = VER2_DIR.parent
# The solver harness: its agent_prompt builds the problem message the solver sees, its judge runs the tests.
SOLVER = REPO / "Solver"
# The ICPC WF archive (per problem: statement, data/, solution.tex, solution.cpp; _verify/judging.json), the
# corrected statements the agent runs were made from. WF_ARCHIVE overrides (see env.example.sh).
ICPC_ARCHIVE = Path(os.environ.get("WF_ARCHIVE") or REPO / "data" / "ICPC_WF")
GRAPHS_DIR = VER2_DIR / "graph" / "graphs"
GRADE_DIR = VER2_DIR / "grade" / "runs"
REPORTS_DIR = VER2_DIR / "validate" / "reports"
PROBLEMS = VER2_DIR / "problems.txt"

API_MODEL = "gpt-6-astra"
GEN_EFFORT = "high"        # the builder (build.py)
AUDIT_EFFORT = "high"      # the reviewer, the editorial integrator and the revisers
GRADE_EFFORT = "high"      # the window and program probes

# --- the graph (graph/rules.py). What is left are the rules that keep a graph valid (ids in order, routes to
# earlier nodes only, distinct END routes, every node on a derivation of END, a node derived from the statement)
# and the text limits the probes rely on. The counts of nodes, routes, prerequisites, END routes, hazards and
# anchors are not capped, and the anchor checks only warn (limits removed 2026-10-30 at the user's request).
MIN_NODES, MAX_NODES = 5, 20    # only the old editorial-based build.py
WORDS = {"name": 8, "statement": 50, "accept": 80, "hazard": 40, "hazard_check": 60}
KINDS = ("modeling", "reformulation", "key_property", "algorithm", "construction")
SOURCES = ("statement", "editorial", "reference code", "editorial and code", "exploration")
ANSWER_NUMBERS = 8      # distinct integers absent from the statement that make a statement an answer table
MAX_FIXES = 3           # submissions sent back for breaking a rule, in a row
MAX_REVISIONS = 3       # review rounds with a revision after each, at most
QUOTE_CHARS = 300
CLAIM_CHARS = 300
JOBS = 4                # problems built at once

# --- exploration (graph/explore.py): the explorer sees the statement only; a path is added when its program is accepted
EXPLORE_EFFORT = "high"
MAX_PATHS = 20              # accepted paths per problem, at most: a backstop, the explorer is meant to stop by itself (12 until 2026-11-03: hit by 2021/G and 2025/L once slow approaches were submitted too)
MAX_PATH_ATTEMPTS = 4       # judged submissions of one approach before it is abandoned
MAX_SUBMISSIONS = 60        # submit_path calls in one exploration, at most (40 until 2026-11-03)
JUDGE_SNIPPET_CHARS = 1500  # of a failing test's input shown to the explorer

# --- grading (grade/)
UNIT_CHARS = 6000       # a unit ends at a paragraph or line break near this size
WINDOW_CHARS = 24000    # one probe call reads one window of consecutive units of one round
MIN_ROUND_CHARS = 5000  # a substantive round: at least this much written by the solver
PROGRAMS_PER_RUN = 3    # programs of a run the program probe reads
ATTEMPTS = 3            # answers sent back for failing the checks, per request
OFF_GRAPH_PER_WINDOW = 5  # off-graph claims a window probe may report
ADJUDICATE = True       # a node left wrong by the windows gets a second reading over its whole trail (grade.py --no-adjudicate)
ADJ_BEFORE = 1200       # characters of the solver's text shown before a trail passage
ADJ_AFTER = 2000        # and after it
ADJ_FINAL_CHARS = 8000  # the end of the solver's last window shown to the adjudicator (its final write-up and code)
GRADE_BLIND = True      # the probes see neither the judge's feedback nor any verdict (grade.py --sighted turns it off)
API_RETRIES = 8         # waits on rate limits, timeouts and server errors, per request
WORKERS = 8             # probes at once
