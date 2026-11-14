"""Offline end-to-end tests of the loop with a fake solver, a fake grader and a fake writer: phase 1 to
5/5 with keep-best, the gate (the entry confirmation of a clean sweep), phase 2 compaction on
confirmation-sized rounds with and without the split, the confirmation of an insight that never swept,
the route switch, the stop on a resisting node, the control arm, and resuming from state.json."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
import graph as G  # noqa: E402
import loop as L  # noqa: E402
from tests.fixtures import baseline_records, graph, record  # noqa: E402

WORDS = lambda t: len(t.split())


class FakeProblem:
    def __init__(self, problem):
        self.problem, self.slug, self.title = problem, problem.replace("/", "_"), "Toy"
        self.statement, self.editorial, self.reference = "The toy problem statement.", "editorial", "int main(){}"


class FakeWriter:
    """Deterministic item texts; records what it was asked."""

    def __init__(self, loop):
        self.calls = []
        self.codes = []
        self.shortened = []

    def node_item(self, node, level, route, items, held, mistakes, wording, previous=None, shorten=None, **kw):
        self.calls.append(("node", node["id"], level, len(mistakes), len(previous or [])))
        if shorten:                                   # the words that fit (the count is WORDS)
            self.shortened.append((node["id"], shorten["limit"]))
            return " ".join(shorten["from"].split()[:shorten["limit"]])
        return f"{node['id']} level {level}: {node['statement']}" + (" (v2)" if previous else "")

    def hazard_item(self, hazard, level, evidence, previous=None, shorten=None, **kw):
        self.calls.append(("hazard", hazard["id"], level))
        if shorten:
            self.shortened.append((hazard["id"], shorten["limit"]))
            return " ".join(shorten["from"].split()[:shorten["limit"]])
        return f"{hazard['id']} level {level}: {hazard['statement']}"


class FakeSolver:
    """Runs are decided by a script: condition -> list of solved flags (per seed)."""

    def __init__(self, script):
        self.script, self.launched = script, []

    def launch(self, problem, model, runs_dir, condition, insight_path=None, seeds=range(1, 6)):
        self.launched.append((condition, list(seeds), insight_path and Path(insight_path).read_text()))
        return [f"job-{condition}-{s}" for s in seeds]

    def wait(self, jobs, what=""):
        return []

    def collect(self, runs_dir, slug, seeds=range(1, 6)):
        cond = Path(runs_dir).parent.name
        flags = self.script[cond]
        return [{"seed": s, "solved": flags[k], "submissions": 3, "stop_reason": "solved" if flags[k] else "time",
                 "elapsed_s": 100, "rounds": 3, "output_tokens": 1000 * (k + 1), "tokens_to_first_submit": 100, "insight": True,
                 "trace": f"{runs_dir}/{slug}_run{s}_transcript.jsonl"} for k, s in enumerate(seeds)]   # by position: confirm seeds start at 101


def make_grader(script):
    """script: condition -> list of (solved, states, stuck, reached_end, extras) per seed."""
    def grader(problem, traces, out_dir, cache_dir=None, workers=None, log_path=None):   # the real signature
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        cond = out_dir.parent.name
        records = []
        for i, t in enumerate(traces, 1):
            solved, states, stuck, end, extra = script[cond][i - 1]
            records.append(record(f"x/qwen/{cond}/run{i}", "qwen", solved, states, stuck=stuck, reached_end=end,
                                  insight=True, run=i, trace=t, **extra))
        (out_dir / "runs.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")
        return records
    return grader


def pilot_grader(problem, traces, out_dir, cache_dir=None, log_path=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    recs = baseline_records()
    (out_dir / "runs.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    return recs


def make_loop(tmp, solver, grader, g=None, **kw):
    g = g or graph()
    for n in g["nodes"]:
        n["depth"] = G.depths(g)[n["id"]]
    loop = L.Loop("2099/X-toy", "qwen", runs_root=Path(tmp), solver=solver, grader=grader,
                  writer_factory=lambda lp: FakeWriter(lp), count=WORDS, problem_loader=FakeProblem,
                  graph_loader=lambda p: g, rounds1=kw.pop("rounds1", 4), rounds2=kw.pop("rounds2", 4),
                  mode=kw.pop("mode", "cut"), runs_per_round=kw.pop("runs_per_round", 5),
                  confirm_runs=kw.pop("confirm_runs", 5), **kw)
    return loop


def chain_graph():
    g = graph()
    g["end"] = {"statement": "...", "routes": [["N1", "N2", "N3"]], "keys": ["N3"]}
    g["paths"] = [g["paths"][0]]
    return g


def hinted(solved, states, stuck=None, end=False, **extra):
    return (solved, states, stuck, end, extra)


EST = {"N1": "established", "N4": "established"}
WRONG4 = {"N1": "established", "N4": "wrong"}


class TestLoop(unittest.TestCase):
    def test_phase1_phase2_confirm(self):
        tmp = tempfile.mkdtemp()
        # r1: 2/5 (N4 L1), r2: 5/5 (N4 L2) -> the gate g1 reproduces it 5/5 -> phase 2: groups = [level1 N4]
        # then [drop N4]; c1 (N4 back to L1): 5/5 accepted; c2 (drop N4): 1/5 rejected, which ends phase 2.
        # Nothing is confirmed afterwards: g1 and c1 were confirmation-sized themselves.
        solved = {"r1": [True, True, False, False, False], "r2": [True] * 5, "g1": [True] * 5, "c1": [True] * 5,
                  "c2": [True, False, False, False, False]}
        grades = {"r1": [hinted(True, EST, end=True, given=["N4"])] * 2 + [hinted(False, WRONG4, "N4", given=["N4"])] * 3,
                  "r2": [hinted(True, EST, end=True, given=["N4"])] * 5,
                  "g1": [hinted(True, EST, end=True, given=["N4"])] * 5,
                  "c1": [hinted(True, EST, end=True, given=["N4"])] * 5,
                  "c2": [hinted(True, EST, end=True)] + [hinted(False, WRONG4, "N4")] * 4}
        solver = FakeSolver(solved)
        loop = make_loop(tmp, solver, make_grader(grades))
        # round 0 comes from a graded pilot? none here: the grader is used on RunPool/baseline traces
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        state = loop.drive()
        conds = [r["condition"] for r in state["rounds"]]
        self.assertEqual(conds, ["r1", "r2", "g1", "c1", "c2"])
        self.assertEqual(state["route"]["index"], 2)
        r1, r2, g1, c1, c2 = state["rounds"]
        self.assertTrue(r1["accepted"] and r2["accepted"])
        self.assertEqual(r1["plan"]["changes"][0]["change"], "escalate")
        self.assertEqual(r2["items_snapshot"]["node:N4"]["level"], 2)
        self.assertIn("(v2)", r2["insight"])
        self.assertEqual(c1["group"]["op"], "level1")
        self.assertTrue(c1["accepted"])
        self.assertEqual(c1["items_snapshot"]["node:N4"]["level"], 1)
        self.assertFalse(c2["accepted"])
        self.assertEqual(state["best"]["condition"], "c1")
        self.assertTrue(state["stop_reason"].startswith("confirmed on c1"))
        self.assertIn("first compaction the insight does not survive", state["stop_reason"])
        self.assertEqual(state["confirmations"], [])                  # the gate and c1 replace the confirmation round
        self.assertEqual([{k: v for k, v in g.items() if k != "sha"} for g in state["gates"]],
                         [{"round": 3, "condition": "g1", "ok": True, "solved": 5, "runs": 5, "want": 4, "of": 2}])
        self.assertEqual(g1["insight"], r2["insight"])                # the gate reruns the round's own text
        self.assertEqual(solver.launched[2][1], list(range(101, 106)))   # on seeds the round did not use
        # the insight files and the grades are where the report expects them
        self.assertTrue((Path(tmp) / "2099_X-toy" / "qwen" / "c1" / "insight.txt").exists())
        self.assertTrue((Path(tmp) / "2099_X-toy" / "qwen" / "r1" / "grade" / "runs.jsonl").exists())
        # resuming a finished loop changes nothing
        again = make_loop(tmp, solver, make_grader(grades))
        self.assertEqual(len(again.drive()["rounds"]), 5)
        self.assertEqual(len(solver.launched), 5)

    def test_reject_restores_best_and_writer_sees_worse(self):
        tmp = tempfile.mkdtemp()
        # r1: 3/5 accepted; r2 (N4 L2): 1/5 rejected -> items restored to r1's text, history has the worse L2 version;
        # r3: escalation jumps to L3 (L2 was tried and worse); 3/5 again (tie: accepted); budget 3 -> confirm.
        solved = {"r1": [True, True, True, False, False], "r2": [True, False, False, False, False],
                  "r3": [True, True, True, False, False], "f1": [True, True, True, False, False]}
        ok = hinted(True, EST, end=True, given=["N4"])
        bad = hinted(False, WRONG4, "N4", given=["N4"])
        grades = {"r1": [ok] * 3 + [bad] * 2, "r2": [ok] + [bad] * 4, "r3": [ok] * 3 + [bad] * 2, "f1": [ok] * 3 + [bad] * 2}
        loop = make_loop(tmp, FakeSolver(solved), make_grader(grades), rounds1=3, rounds2=2, phase2_min=5)
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        state = loop.drive()
        r1, r2, r3 = state["rounds"][:3]
        self.assertTrue(r1["accepted"])
        self.assertFalse(r2["accepted"])
        self.assertEqual(r3["items_snapshot"]["node:N4"]["level"], 3)
        hist = r3["items_snapshot"]["node:N4"]["history"]
        self.assertIn("worse", [h["verdict"] for h in hist])
        self.assertEqual(state["best"]["condition"], "r3")
        self.assertEqual(state["rounds"][3]["condition"], "f1")      # no phase 2 below 5/5; a confirmation round
        self.assertEqual(state["stop_reason"], "confirmed")           # the best round's 3/5 was reproduced
        self.assertEqual(state["confirmations"], [{"round": 4, "condition": "f1", "ok": True, "solved": 3, "runs": 5, "want": 3, "of": 3}])

    def test_route_switch_when_blocked(self):
        tmp = tempfile.mkdtemp()
        # N4 at the top level still the stuck node -> blocked -> switch to route 1 (N2, N3 items)
        solved = {"r1": [False] * 5, "r2": [False] * 5, "r3": [False] * 5, "r4": [False] * 5, "r5": [False] * 5,
                  "r6": [True] * 5, "g1": [True] * 5}
        bad = hinted(False, WRONG4, "N4", given=["N4"])
        good1 = hinted(True, {"N1": "established", "N2": "established", "N3": "established"}, end=True, given=["N2", "N3"])
        grades = {"r1": [bad] * 5, "r2": [bad] * 5, "r3": [bad] * 5, "r4": [bad] * 5, "r5": [bad] * 5, "r6": [good1] * 5,
                  "g1": [good1] * 5}
        loop = make_loop(tmp, FakeSolver(solved), make_grader(grades), rounds1=7, rounds2=0)
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        state = loop.drive()
        levels = [r["items_snapshot"].get("node:N4", {}).get("level") for r in state["rounds"][:5]]
        self.assertEqual(levels, [1, 2, 3, 4, 5])
        self.assertEqual(state["route"]["index"], 1)
        self.assertEqual(set(state["rounds"][5]["items_snapshot"]), {"node:N2", "node:N3"})
        self.assertEqual(state["route_history"][-1]["index"], 1)
        self.assertEqual(state["best"]["score"]["solved"], 5)
        # rounds2=0: nothing to compact, so the gate is the whole confirmation
        self.assertEqual([r["condition"] for r in state["rounds"]][-1], "g1")
        self.assertTrue(state["stop_reason"].startswith("confirmed on g1"))

    def test_step_mode_grows_escalates_and_compacts(self):
        tmp = tempfile.mkdtemp()
        # route N1 -> N2 -> N3, N1 held. r1: N2 L1 held by 1/5 -> frontier N2 -> r2: N2 L2, held 5/5 -> frontier N3
        # -> r3: + N3 L1 -> 5/5 -> the gate g1 reproduces it -> phase 2: c1 (N2 back to L1) 5/5 accepted,
        # c2 (drop N2) 2/5 rejected, which ends phase 2 on the confirmed c1.
        n1, n12, n123 = {"N1": "established"}, {"N1": "established", "N2": "established"}, \
            {"N1": "established", "N2": "established", "N3": "established"}
        wrong2 = {"N1": "established", "N2": "wrong"}
        solved = {"r1": [False] * 5, "r2": [False] * 5, "r3": [True] * 5, "g1": [True] * 5, "c1": [True] * 5,
                  "c2": [True, True, False, False, False]}
        grades = {"r1": [hinted(False, n12, "N3", given=["N2"])] + [hinted(False, wrong2, "N2", given=["N2"])] * 4,
                  "r2": [hinted(False, n12, "N3", given=["N2"])] * 5,
                  "r3": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5,
                  "g1": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5,
                  "c1": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5,
                  "c2": [hinted(True, n123, end=True, given=["N3"])] * 2 + [hinted(False, wrong2, "N2", given=["N3"])] * 3}
        solver = FakeSolver(solved)
        loop = make_loop(tmp, solver, make_grader(grades), g=chain_graph(), mode="step", rounds1=6, rounds2=4)
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        state = loop.drive()
        self.assertEqual(state["mode"], "step")
        self.assertEqual([r["condition"] for r in state["rounds"]], ["r1", "r2", "r3", "g1", "c1", "c2"])
        r1, r2, r3, g1, c1, c2 = state["rounds"]
        self.assertEqual(list(r1["items_snapshot"]), ["node:N2"])
        self.assertEqual(r1["score"]["passed"], 1)
        self.assertEqual([(c["item"], c["change"]) for c in r1["plan"]["changes"]], [("node:N2", "escalate")])
        self.assertEqual(r2["items_snapshot"]["node:N2"]["level"], 2)
        self.assertIn("(v2)", r2["insight"])
        self.assertTrue(r2["accepted"])                                  # passed 1 -> 2
        self.assertEqual((r2["plan"]["passed"], r2["plan"]["frontier"]), (2, "N3"))
        self.assertEqual([(c["item"], c["change"]) for c in r2["plan"]["changes"]], [("node:N3", "add")])
        self.assertEqual(list(r3["items_snapshot"]), ["node:N2", "node:N3"])
        self.assertEqual(r3["items_snapshot"]["node:N3"]["level"], 1)
        self.assertEqual(c1["group"]["op"], "level1")
        self.assertTrue(c1["accepted"])
        self.assertEqual(c1["items_snapshot"]["node:N2"]["level"], 1)
        self.assertEqual(c2["group"]["members"], ["node:N2"])
        self.assertFalse(c2["accepted"])
        self.assertEqual(state["best"]["condition"], "c1")
        self.assertTrue(state["stop_reason"].startswith("confirmed on c1"))
        # the gate writes nothing: it reruns the round's own items. The writer wrote N2 twice (L1, L2) and N3
        # once; nothing was rewritten for passed nodes
        calls = [c for c in loop._writer.calls if c[0] == "node"]
        self.assertEqual([(c[1], c[2]) for c in calls], [("N2", 1), ("N2", 2), ("N3", 1)])

    def test_step_mode_rejected_round_retries_the_added_node_higher(self):
        tmp = tempfile.mkdtemp()
        # r1: N2 passes 5/5 (frontier N3) accepted; r2 adds N3 L1 but the runs regress (N2 held 2/5): rejected,
        # N3's L1 text is "worse" -> r3 re-adds N3 at L2; r3 5/5.
        n12 = {"N1": "established", "N2": "established"}
        n123 = {"N1": "established", "N2": "established", "N3": "established"}
        wrong2 = {"N1": "established", "N2": "wrong"}
        solved = {"r1": [False] * 5, "r2": [False] * 5, "r3": [True] * 5, "g1": [True] * 5}
        grades = {"r1": [hinted(False, n12, "N3", given=["N2"])] * 5,
                  "r2": [hinted(False, n12, "N3", given=["N2", "N3"])] * 2 + [hinted(False, wrong2, "N2", given=["N2", "N3"])] * 3,
                  "r3": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5,
                  "g1": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5}
        loop = make_loop(tmp, FakeSolver(solved), make_grader(grades), g=chain_graph(), mode="step", rounds1=6, rounds2=0)
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        state = loop.drive()
        r1, r2, r3 = state["rounds"][:3]
        self.assertTrue(r1["accepted"])
        self.assertFalse(r2["accepted"])
        self.assertEqual(r3["items_snapshot"]["node:N3"]["level"], 2)
        self.assertEqual([h["verdict"] for h in r3["items_snapshot"]["node:N3"]["history"]], ["worse"])
        self.assertEqual(r3["items_snapshot"]["node:N2"]["text"], r1["items_snapshot"]["node:N2"]["text"])
        self.assertEqual(state["best"]["condition"], "r3")


    def test_rejected_rounds_accumulate_the_added_nodes_worse_versions(self):
        tmp = tempfile.mkdtemp()
        # r1 accepted (frontier N3); r2 adds N3 L1 and regresses: rejected; r3 re-adds N3 at L2 and regresses
        # again: rejected; r4 re-adds N3 at L3 and its history carries both worse versions (r2 L1, r3 L2),
        # merged from the rejected round's own item, not only the latest rejected text.
        n12 = {"N1": "established", "N2": "established"}
        n123 = {"N1": "established", "N2": "established", "N3": "established"}
        wrong2 = {"N1": "established", "N2": "wrong"}
        solved = {"r1": [False] * 5, "r2": [False] * 5, "r3": [False] * 5, "r4": [True] * 5, "g1": [True] * 5}
        regress = [hinted(False, n12, "N3", given=["N2", "N3"])] * 2 + [hinted(False, wrong2, "N2", given=["N2", "N3"])] * 3
        grades = {"r1": [hinted(False, n12, "N3", given=["N2"])] * 5, "r2": regress, "r3": regress,
                  "r4": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5,
                  "g1": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5}
        loop = make_loop(tmp, FakeSolver(solved), make_grader(grades), g=chain_graph(), mode="step", rounds1=6, rounds2=0)
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        state = loop.drive()
        r2, r3, r4 = state["rounds"][1:4]
        self.assertFalse(r2["accepted"])
        self.assertFalse(r3["accepted"])
        self.assertEqual(r3["items_snapshot"]["node:N3"]["level"], 2)
        self.assertEqual(r4["items_snapshot"]["node:N3"]["level"], 3)
        self.assertEqual([(h["round"], h["level"]) for h in r4["items_snapshot"]["node:N3"]["history"] if h["verdict"] == "worse"],
                         [("r2", 1), ("r3", 2)])
        self.assertEqual(state["best"]["condition"], "r4")


    def test_a_passed_nodes_code_gap_escalation_found_worse_is_kept_not_blocked(self):
        tmp = tempfile.mkdtemp()
        # r1 (accepted): every run holds N1 and N2 (passed), four stop at N3 and one reaches END with a final
        # program contradicting N2 (code gap): N3 is added and N2 escalated one level. r2 regresses (every run
        # stops at N2, wrong): rejected; the plan from r1's records asks for the same code-gap escalation, but
        # N2's stronger level was tried and worse and there is none above it (the top is 2 here): N2 keeps the
        # version that passed and the loop goes on instead of stopping on "N2 resists at the top level"
        # (2023/J Nemotron r8, 2026-11-05).
        n12 = {"N1": "established", "N2": "established"}
        n123 = {"N1": "established", "N2": "established", "N3": "established"}
        wrong2 = {"N1": "established", "N2": "wrong"}
        solved = {"r1": [False] * 5, "r2": [False] * 5, "r3": [True] * 5, "g1": [True] * 5}
        grades = {"r1": [hinted(False, n12, "N3", given=["N2"])] * 4
                        + [hinted(False, n12, None, end=True, given=["N2"], code_gap=["N2"])],
                  "r2": [hinted(False, wrong2, "N2", given=["N2", "N3"])] * 5,
                  "r3": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5,
                  "g1": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5}
        loop = make_loop(tmp, FakeSolver(solved), make_grader(grades), g=chain_graph(), mode="step", rounds1=6, rounds2=0)
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        levels = C.LEVELS
        C.LEVELS = (1, 2)
        try:
            state = loop.drive()
        finally:
            C.LEVELS = levels
        r1, r2, r3 = state["rounds"][:3]
        self.assertEqual([(c["item"], c["change"]) for c in r1["plan"]["changes"]], [("node:N3", "add"), ("node:N2", "escalate")])
        self.assertEqual(r2["items_snapshot"]["node:N2"]["level"], 2)
        self.assertFalse(r2["accepted"])
        self.assertEqual([(c["item"], c["change"]) for c in r2["plan"]["changes"]], [("node:N3", "add"), ("node:N2", "kept")])
        self.assertEqual((r2["plan"]["blocked"], state["blocked"], state["stopped"]), ([], [], True))
        self.assertEqual({k: v["level"] for k, v in r3["items_snapshot"].items()}, {"node:N2": 1, "node:N3": 2})
        self.assertEqual(r3["items_snapshot"]["node:N2"]["text"], r1["items_snapshot"]["node:N2"]["text"])
        self.assertEqual([(h["round"], h["level"]) for h in r3["items_snapshot"]["node:N2"]["history"] if h["verdict"] == "worse"],
                         [("r2", 2)])
        self.assertTrue(state["stop_reason"].startswith("confirmed on g1"))

    def test_jump_hints_a_later_node_the_runs_keep_getting_wrong(self):
        tmp = tempfile.mkdtemp()
        # Step mode on the chain N1 -> N2 -> N3: every run holds N1 and stops at N2 (wrong), so the frontier N2
        # escalates every round. N3, beyond the frontier, is working in r1 and wrong in every run of r2 and
        # r3: the jump rule wants the signal in two consecutive scored rounds, so r2's plan only escalates N2
        # and r3's plan adds N3 at level 1 beside the frontier (the user's rule, 2026-11-05). r4 with both
        # items solves.
        working3 = {"N1": "established", "N2": "wrong", "N3": "working"}
        wrong3 = {"N1": "established", "N2": "wrong", "N3": "wrong"}
        n123 = {"N1": "established", "N2": "established", "N3": "established"}
        solved = {"r1": [False] * 5, "r2": [False] * 5, "r3": [False] * 5, "r4": [True] * 5, "g1": [True] * 5}
        grades = {"r1": [hinted(False, working3, "N2", given=["N2"])] * 5,
                  "r2": [hinted(False, wrong3, "N2", given=["N2"])] * 5,
                  "r3": [hinted(False, wrong3, "N2", given=["N2"])] * 5,
                  "r4": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5,
                  "g1": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5}
        loop = make_loop(tmp, FakeSolver(solved), make_grader(grades), g=chain_graph(), mode="step", rounds1=6, rounds2=0)
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        state = loop.drive()
        r1, r2, r3, r4 = state["rounds"][:4]
        self.assertEqual([(c["item"], c["change"]) for c in r1["plan"]["changes"]], [("node:N2", "escalate")])
        self.assertEqual([(c["item"], c["change"]) for c in r2["plan"]["changes"]], [("node:N2", "escalate")])
        self.assertIsNone(r2["plan"]["jump"])
        self.assertEqual([(c["item"], c["change"], c.get("rule")) for c in r3["plan"]["changes"]],
                         [("node:N2", "escalate", None), ("node:N3", "add", "jump")])
        self.assertEqual(r3["plan"]["jump"], "N3")
        self.assertEqual({k: v["level"] for k, v in r4["items_snapshot"].items()}, {"node:N2": 4, "node:N3": 1})
        self.assertEqual(r4["items_snapshot"]["node:N3"]["rule"], "jump")
        self.assertIn("beyond the frontier", r4["items_snapshot"]["node:N3"]["reason"])
        self.assertEqual(state["blocked"], [])
        self.assertTrue(state["stop_reason"].startswith("confirmed on g1"))

    def test_jump_picks_a_parallel_route_node_the_runs_contradict(self):
        # diagnose.update alone, route 1 (N1+N2+N3) with N2 hinted: every run holds N1, stops at N2 and
        # contradicts N4, the parallel route's algorithm node, in this round and the one before: the jump adds
        # N4 at level 1 ("on a parallel route") beside the frontier escalation, never blocks, and does not fire
        # when the earlier round had N4 merely working. A jump item at the top level is kept, not blocked.
        import diagnose as D
        from tests.fixtures import record
        g = graph()
        route = {"index": 1, "nodes": ["N1", "N2", "N3"], "key": "N3", "held": ["N1"], "missing": ["N2", "N3"]}
        wrong4 = {"N1": "established", "N2": "wrong", "N4": "wrong"}
        work4 = {"N1": "established", "N2": "wrong", "N4": "working"}
        runs = lambda states, cond, given=("N2",): [record(f"x/qwen/{cond}/run{i}", "qwen", False, states, stuck="N2",
                                                           given=list(given), insight=True, run=i) for i in (1, 2, 3)]
        items = {"node:N2": dict(D.node_item("N2", 1, "frontier"), text="N2 level 1")}
        upd = D.update(g, {}, route, items, runs(wrong4, "r2"), "step", passed=["N1"],
                       recent=[runs(wrong4, "r2"), runs(wrong4, "r1")])
        self.assertEqual([(c["item"], c["change"], c.get("rule")) for c in upd["changes"]],
                         [("node:N2", "escalate", None), ("node:N4", "add", "jump")])
        self.assertEqual((upd["jump"], upd["blocked"], upd["items"]["node:N4"]["level"]), ("N4", [], 1))
        self.assertIn("on a parallel route", upd["items"]["node:N4"]["reason"])
        upd = D.update(g, {}, route, items, runs(wrong4, "r2"), "step", passed=["N1"],
                       recent=[runs(wrong4, "r2"), runs(work4, "r1")])
        self.assertEqual([(c["item"], c["change"]) for c in upd["changes"]], [("node:N2", "escalate")])
        self.assertIsNone(upd["jump"])
        top = dict(items, **{"node:N4": dict(D.node_item("N4", max(C.LEVELS), "jump"), text="N4 top", rule="jump")})
        upd = D.update(g, {}, route, top, runs(wrong4, "r3", ("N2", "N4")), "step", passed=["N1"],
                       recent=[runs(wrong4, "r3", ("N2", "N4")), runs(wrong4, "r2", ("N2", "N4"))])
        self.assertEqual([(c["item"], c["change"]) for c in upd["changes"]], [("node:N2", "escalate"), ("node:N4", "kept")])
        self.assertEqual((upd["jump"], upd["blocked"]), ("N4", []))

    def test_reopen_continues_a_stopped_loop_under_the_current_rules(self):
        tmp = tempfile.mkdtemp()
        # N2 wrong in 3/5 runs at every level while every run works past it and stops at N3 (working there, so
        # the jump rule stays quiet). With the move-on rule switched off the loop escalates N2 to the top level
        # and stops (no other route); reopen under the current rules plans again from the same records: N2's
        # item stays, N3 is hinted, the loop goes on.
        past = {"N1": "established", "N2": "wrong", "N3": "working"}
        slip = {"N1": "established", "N2": "working", "N3": "working"}
        n123 = {"N1": "established", "N2": "established", "N3": "established"}
        fail = [hinted(False, past, "N3", given=["N2"])] * 3 + [hinted(False, slip, "N3", given=["N2"])] * 2
        solved = {f"r{i}": [False] * 5 for i in range(1, 6)}
        solved.update({"r6": [True] * 5, "g1": [True] * 5})
        grades = {f"r{i}": fail for i in range(1, 6)}
        grades.update({"r6": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5,
                       "g1": [hinted(True, n123, end=True, given=["N2", "N3"])] * 5})
        loop = make_loop(tmp, FakeSolver(solved), make_grader(grades), g=chain_graph(), mode="step", rounds1=8, rounds2=0)
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        move_on = C.MOVE_ON_LEVEL
        C.MOVE_ON_LEVEL = 99
        try:
            state = loop.drive()
        finally:
            C.MOVE_ON_LEVEL = move_on
        self.assertTrue(state["stopped"])
        self.assertIn("resist at the top level", state["stop_reason"])
        self.assertEqual([r["items_snapshot"]["node:N2"]["level"] for r in state["rounds"]], [1, 2, 3, 4, 5])
        self.assertEqual(state["blocked"], ["N2"])
        loop.reopen()
        self.assertFalse(loop.state["stopped"])
        r5 = loop.state["rounds"][4]
        self.assertEqual([(c["item"], c["change"]) for c in r5["plan"]["changes"]], [("node:N2", "kept"), ("node:N3", "add")])
        self.assertEqual((r5["plan"]["blocked"], loop.state["blocked"], r5["plan"]["past_frontier"]), ([], [], "N3"))
        state = loop.drive()
        self.assertEqual([r["condition"] for r in state["rounds"]], ["r1", "r2", "r3", "r4", "r5", "r6", "g1"])
        r6 = state["rounds"][5]
        self.assertEqual({k: v["level"] for k, v in r6["items_snapshot"].items()}, {"node:N2": 5, "node:N3": 1})
        self.assertEqual(r6["items_snapshot"]["node:N2"]["text"], r5["items_snapshot"]["node:N2"]["text"])
        self.assertTrue(state["stop_reason"].startswith("confirmed on g1"))
        with self.assertRaises(L.Stop):                                 # only a phase-1 stop can be reopened
            loop.reopen()
        self.assertTrue(loop.state["stopped"])

    def test_three_run_rounds_five_run_gate_then_five_run_compaction(self):
        tmp = tempfile.mkdtemp()
        # rounds of 3 runs (a node passes at 3/3); r1: N2 held 3/3 -> + N3; r2: 3/3 -> the gate g1 reruns r2's own
        # text on 5 fresh seeds: 4/5, within the tolerance of 1, so compaction starts. c1 (drop N2) runs 5 times
        # too and is accepted at 4/5, so nothing needs confirming afterwards; the queue empties and the loop stops.
        n12 = {"N1": "established", "N2": "established"}
        n123 = {"N1": "established", "N2": "established", "N3": "established"}
        wrong2 = {"N1": "established", "N2": "wrong"}
        solved = {"r1": [False] * 3, "r2": [True] * 3, "g1": [True, True, True, True, False],
                  "c1": [True, True, True, True, False]}
        grades = {"r1": [hinted(False, n12, "N3", given=["N2"])] * 3,
                  "r2": [hinted(True, n123, end=True, given=["N2", "N3"])] * 3,
                  "g1": [hinted(True, n123, end=True, given=["N2", "N3"])] * 4
                        + [hinted(False, wrong2, "N2", given=["N2", "N3"])],
                  "c1": [hinted(True, n123, end=True, given=["N3"])] * 4 + [hinted(False, wrong2, "N2", given=["N3"])]}
        solver = FakeSolver(solved)
        loop = make_loop(tmp, solver, make_grader(grades), g=chain_graph(), mode="step", runs_per_round=3, confirm_runs=5)
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        state = loop.drive()
        r1, r2, g1, c1 = state["rounds"]
        self.assertEqual([len(x[1]) for x in solver.launched], [3, 3, 5, 5])
        self.assertEqual(solver.launched[2][1], list(range(101, 106)))      # the gate never replays the round's seeds
        self.assertEqual(solver.launched[3][1], list(range(1, 6)))          # a compaction is a new text: plain seeds
        self.assertEqual(solver.launched[2][2], solver.launched[1][2])      # and it reruns exactly r2's insight
        self.assertEqual((r1["score"]["runs"], r1["score"]["passed"]), (3, 2))
        self.assertEqual(r2["score"]["solved"], 3)
        self.assertEqual((g1["score"]["runs"], g1["score"]["solved"], g1["accepted"]), (5, 4, True))
        self.assertEqual([{k: v for k, v in g.items() if k != "sha"} for g in state["gates"]],
                         [{"round": 3, "condition": "g1", "ok": True, "solved": 4, "runs": 5, "want": 4, "of": 2}])
        self.assertEqual((c1["score"]["runs"], c1["accepted"]), (5, True))
        self.assertEqual(state["confirmations"], [])
        self.assertEqual(state["confirmed_by"], "c1")
        self.assertTrue(state["stop_reason"].startswith("confirmed on c1"))
        self.assertEqual(list(state["best"]["items"]), ["node:N3"])

    def test_a_failed_gate_sends_the_loop_back_to_phase_1(self):
        tmp = tempfile.mkdtemp()
        # r1: N2 held 3/3 -> + N3; r2: 3/3, but the gate g1 reproduces it only 2/5 (needs 4): no compaction. The
        # loop returns to phase 1 and plans from the gate's own five records, which stop at N3; r3 escalates N3
        # and sweeps again, and its own gate g2 holds. (2025/J Nemotron, 2026-11-06: r2 was 3/3 and then 3/5.)
        n12 = {"N1": "established", "N2": "established"}
        n123 = {"N1": "established", "N2": "established", "N3": "established"}
        wrong3 = {"N1": "established", "N2": "established", "N3": "wrong"}
        working3 = {"N1": "established", "N2": "established", "N3": "working"}
        solved = {"r1": [False] * 3, "r2": [True] * 3, "g1": [True, True, False, False, False],
                  "r3": [True] * 3, "g2": [True] * 5}
        ok = hinted(True, n123, end=True, given=["N2", "N3"])
        grades = {"r1": [hinted(False, n12, "N3", given=["N2"])] * 3,
                  # one run neither establishes N3 nor is credited with the hint, so N3 is not passed and
                  # stays the frontier even though the round solved every run
                  "r2": [ok] * 2 + [hinted(True, working3, end=True, given=["N2"])],
                  "g1": [ok] * 2 + [hinted(False, wrong3, "N3", given=["N2", "N3"])] * 3,
                  "r3": [ok] * 3, "g2": [ok] * 5}
        solver = FakeSolver(solved)
        loop = make_loop(tmp, solver, make_grader(grades), g=chain_graph(), mode="step", runs_per_round=3,
                         confirm_runs=5, rounds2=0)
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        state = loop.drive()
        self.assertEqual([r["condition"] for r in state["rounds"]], ["r1", "r2", "g1", "r3", "g2"])
        g1, r3, g2 = state["rounds"][2], state["rounds"][3], state["rounds"][4]
        self.assertEqual((g1["score"]["solved"], g1["accepted"]), (2, False))
        self.assertEqual([(g["condition"], g["ok"]) for g in state["gates"]], [("g1", False), ("g2", True)])
        # the failed gate is what the next round is planned from, and it does not count as a phase-1 attempt
        self.assertEqual([(c["item"], c["change"]) for c in g1["plan"]["changes"]], [("node:N3", "escalate")])
        self.assertEqual(r3["items_snapshot"]["node:N3"]["level"], 2)
        self.assertEqual(state["best"]["condition"], "r3")
        self.assertTrue(state["stop_reason"].startswith("confirmed on g2"))

    def test_phase2_shortens_when_dropping_fails(self):
        tmp = tempfile.mkdtemp()
        # step mode, 3-run rounds, with PHASE2_STOP_ON_FAIL off so the half-split search is exercised.
        # r1: N2 passes -> + N3; r2: 3/3 -> the gate g1 5/5 -> phase 2 on 5-run rounds: c1 drop N2 1/5 rejected
        # (one member: no split); c2 shorten [N2, N3] 5/5 accepted -> pass 2 queued: c3 0/5 rejected -> halves:
        # c4 shorten [N2] 5/5 accepted; the budget (4) is used, and c4 ran five times, so nothing is confirmed
        # afterwards.
        n12 = {"N1": "established", "N2": "established"}
        n123 = {"N1": "established", "N2": "established", "N3": "established"}
        wrong2 = {"N1": "established", "N2": "wrong"}
        ok3 = [hinted(True, n123, end=True, given=["N2", "N3"])] * 3
        ok5 = [hinted(True, n123, end=True, given=["N2", "N3"])] * 5
        solved = {"r1": [False] * 3, "r2": [True] * 3, "g1": [True] * 5, "c1": [True] + [False] * 4,
                  "c2": [True] * 5, "c3": [False] * 5, "c4": [True] * 5}
        grades = {"r1": [hinted(False, n12, "N3", given=["N2"])] * 3, "r2": ok3, "g1": ok5,
                  "c1": [hinted(True, n123, end=True, given=["N3"])] + [hinted(False, wrong2, "N2", given=["N3"])] * 4,
                  "c2": ok5, "c3": [hinted(False, wrong2, "N2", given=["N2", "N3"])] * 5, "c4": ok5}
        solver = FakeSolver(solved)
        loop = make_loop(tmp, solver, make_grader(grades), g=chain_graph(), mode="step", runs_per_round=3, confirm_runs=5,
                         rounds2=4)
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        floor, stop_on_fail = C.SHORTEN_MIN, C.PHASE2_STOP_ON_FAIL
        C.SHORTEN_MIN = 2                 # the fixture texts are a few words long
        C.PHASE2_STOP_ON_FAIL = False     # the knob that keeps the older search over the remaining groups
        try:
            state = loop.drive()
        finally:
            C.SHORTEN_MIN, C.PHASE2_STOP_ON_FAIL = floor, stop_on_fail
        self.assertEqual([r["condition"] for r in state["rounds"]], ["r1", "r2", "g1", "c1", "c2", "c3", "c4"])
        r1, r2, g1, c1, c2, c3, c4 = state["rounds"]
        self.assertEqual((c1["group"]["op"], c1["group"]["members"], c1["accepted"]), ("drop", ["node:N2"], False))
        self.assertEqual((c2["group"]["op"], c2["group"]["members"], c2["accepted"]), ("shorten", ["node:N2", "node:N3"], True))
        self.assertLess(c2["insight_tokens"], r2["insight_tokens"])
        self.assertEqual([h["verdict"] for h in c2["items_snapshot"]["node:N2"]["history"]], ["shortened"])
        self.assertEqual(c2["items_snapshot"]["node:N2"]["level"], 1)
        self.assertNotIn("shorten", c2["items_snapshot"]["node:N2"])
        self.assertEqual((c3["group"]["op"], c3["group"].get("pass"), c3["accepted"]), ("shorten", 2, False))
        self.assertLess(c3["insight_tokens"], c2["insight_tokens"])
        self.assertEqual((c4["group"]["op"], c4["group"]["members"], c4["accepted"]), ("shorten", ["node:N2"], True))
        self.assertEqual(state["best"]["condition"], "c4")
        self.assertEqual([r["score"]["runs"] for r in (g1, c1, c2, c3, c4)], [5] * 5)
        self.assertEqual(state["confirmed_by"], "c4")
        self.assertTrue(state["stop_reason"].startswith("confirmed on c4"))
        self.assertIn("budget", state["stop_reason"])
        limits = [lim for _, lim in loop._writer.shortened]
        self.assertTrue(all(lim >= 2 for lim in limits) and len(limits) == 5)     # N2+N3, N2+N3 again, N2
        # every compaction round is confirmation-sized, so no confirmation round follows phase 2
        self.assertEqual([r for r in state["rounds"] if r["phase"] == "confirm"], [])
        self.assertEqual(state["confirmations"], [])

    def test_control_keynode(self):
        tmp = tempfile.mkdtemp()
        solved = {"ctl_keynode": [True, False, False, False, False]}
        grades = {"ctl_keynode": [hinted(True, EST, end=True)] + [hinted(False, WRONG4, "N4")] * 4}
        loop = make_loop(tmp, FakeSolver(solved), make_grader(grades))
        loop.grader = lambda *a, **k: (make_grader(grades)(*a, **k) if Path(a[2]).parent.name != "r0" else pilot_grader(*a, **k))
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        loop.control("keynode")
        ctl = loop.state["controls"]["keynode"]
        self.assertEqual(ctl["score"]["solved"], 1)
        self.assertIn("knapsack DP", ctl["insight"])

    def test_write_only_and_baseline_solves(self):
        tmp = tempfile.mkdtemp()
        loop = make_loop(tmp, FakeSolver({}), pilot_grader)
        L.runpool_traces = lambda *a, **k: ["t1", "t2", "t3", "t4", "t5"]
        state = loop.drive(write_only=True)
        self.assertEqual(state["rounds"][0]["status"], "written")
        self.assertIn("N4 level 1", state["rounds"][0]["insight"])
        # a model that solves every profiled run stops at round 0
        tmp2 = tempfile.mkdtemp()
        def ac_grader(problem, traces, out_dir, cache_dir=None, log_path=None):
            recs = [record(f"pool/qwen/baseline/run{i}", "qwen", True, EST, reached_end=True, run=i) for i in range(1, 6)]
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            (Path(out_dir) / "runs.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
            return recs
        loop2 = make_loop(tmp2, FakeSolver({}), ac_grader)
        state2 = loop2.drive()
        self.assertTrue(state2["stopped"])
        self.assertIn("without a hint", state2["stop_reason"])

class TestPrimary(unittest.TestCase):
    def test_solved_first_then_end_ac_before_noend_ac(self):
        # 2023/F Qwen: r6 (2/3 solved, both noEND+AC) outranks r4 (0/3, one END+fail run) and r3 (1 noEND+AC);
        # among equally solved rounds an END+AC run ranks above a noEND+AC one, then END count, passed nodes
        def sc(solved, ends, passed, reached, wrong, classes):
            return {"solved": solved, "ends": ends, "passed": passed, "reached": reached, "wrong": wrong,
                    "per_run": [{"class": c} for c in classes]}
        r3 = sc(1, 0, 1, 3.0, 3.0, ["noEND+AC", "noEND+fail/stuck:N5", "noEND+fail/stuck:N2"])
        r4 = sc(0, 1, 3, 4.3, 0.7, ["END+fail/other", "noEND+fail/stuck:N6", "noEND+fail/stuck:N16"])
        r6 = sc(2, 0, 5, 6.3, 1.3, ["noEND+AC", "noEND+AC", "noEND+fail/stuck:N16"])
        self.assertEqual(L.primary(r3), [1, 0, 0, 1, 3.0, -3.0])
        self.assertGreater(L.primary(r6), L.primary(r3))
        self.assertGreater(L.primary(r3), L.primary(r4))
        ac = sc(1, 1, 1, 3.0, 3.0, ["END+AC", "noEND+fail/stuck:N5", "noEND+fail/stuck:N2"])
        self.assertGreater(L.primary(ac), L.primary(r3))                      # END+AC above noEND+AC
        more_end = sc(0, 2, 3, 4.3, 0.7, ["END+fail/other", "END+fail/other", "noEND+fail/stuck:N16"])
        self.assertGreater(L.primary(more_end), L.primary(r4))               # then END count, then passed
        self.assertGreater(L.primary(r4), L.primary(sc(0, 1, 2, 4.3, 0.7, ["END+fail/other", "noEND+fail/stuck:N6", "noEND+fail/stuck:N16"])))



if __name__ == "__main__":
    unittest.main()
