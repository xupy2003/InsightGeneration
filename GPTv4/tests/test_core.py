"""Offline tests of the engine's pure parts: profile, route choice and items, the update rules, the
writer's checks and the composition."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compose as CP  # noqa: E402
import config as C  # noqa: E402
import diagnose as D  # noqa: E402
import graph as G  # noqa: E402
import grading as GR  # noqa: E402
import profile as P  # noqa: E402
import write as W  # noqa: E402
from tests.fixtures import baseline_records, graph, record  # noqa: E402

WORDS = lambda t: len(t.split())


class TestGraph(unittest.TestCase):
    def test_routes_and_depths(self):
        g = graph()
        d = G.depths(g)
        self.assertEqual(d, {"N1": 1, "N2": 2, "N3": 3, "N4": 2})
        routes = G.end_routes(g)
        self.assertEqual([r["key"] for r in routes], ["N3", "N4"])
        self.assertEqual(routes[1]["source"], "editorial")
        self.assertEqual(G.ancestors(g, "N3"), {"N1", "N2"})


class TestProfile(unittest.TestCase):
    def test_held_and_claims(self):
        g = graph()
        for n in g["nodes"]:
            n["depth"] = G.depths(g)[n["id"]]
        prof = P.build(g, baseline_records(), "qwen")
        self.assertEqual(prof["held"], ["N1"])
        self.assertEqual(prof["nodes"]["N2"]["wrong"], 5)
        self.assertEqual(prof["summary"]["stuck"], {"N2": 5})
        self.assertEqual(len(prof["nodes"]["N2"]["claims"]), 1)       # the same claim text in every run
        self.assertEqual(prof["nodes"]["N2"]["claims"][0]["runs"], 5)
        self.assertEqual(prof["nodes"]["N1"]["wording"][0]["state"], "established")

    def test_held_needs_low_wrong_rate(self):
        g = graph()
        recs = baseline_records()
        recs[0]["results"]["N1"]["final"] = "wrong"
        recs[1]["results"]["N1"]["final"] = "wrong"
        prof = P.build(g, recs, "qwen")
        self.assertEqual(prof["held"], [])


class TestDiagnose(unittest.TestCase):
    def setUp(self):
        self.g = graph()
        for n in self.g["nodes"]:
            n["depth"] = G.depths(self.g)[n["id"]]
        self.prof = P.build(self.g, baseline_records(), "qwen")

    def test_route_and_items(self):
        route = D.choose_route(self.g, self.prof)
        # route 2 (N1+N4) misses one node at cost 1; route 1 misses N2 (wrong in every run: 2.0) and N3
        self.assertEqual(route["index"], 2)
        self.assertEqual(route["missing"], ["N4"])
        items = D.initial_items(self.g, self.prof, route, "cut")
        self.assertEqual(list(items), ["node:N4"])
        self.assertEqual(items["node:N4"]["level"], 1)
        blocked = D.choose_route(self.g, self.prof, blocked=["N4"])
        self.assertEqual(blocked["index"], 1)
        self.assertIsNone(D.choose_route(self.g, self.prof, blocked=["N1"]))
        self.assertEqual(D.choose_route(self.g, self.prof, must_contain="N3")["index"], 1)

    def test_update_escalates_stuck_and_adds_hazard(self):
        route = D.choose_route(self.g, self.prof)
        items = D.initial_items(self.g, self.prof, route, "cut")
        items["node:N4"]["text"] = "a level-1 item"
        hinted = [record(f"x/qwen/r1/run{i}", "qwen", False, {"N1": "established", "N4": "wrong"}, stuck="N4",
                         given=["N4"], insight=True, run=i) for i in range(1, 4)]
        hinted += [record("x/qwen/r1/run4", "qwen", False, {"N1": "established", "N4": "established"}, reached_end=True,
                          given=["N4"], insight=True, hazards=["H1"], run=4)]
        hinted += [record("x/qwen/r1/run5", "qwen", True, {"N1": "established", "N4": "established"}, reached_end=True,
                          given=["N4"], insight=True, run=5)]
        upd = D.update(self.g, self.prof, route, items, hinted, "cut")
        self.assertEqual(upd["items"]["node:N4"]["level"], 2)
        self.assertIsNone(upd["items"]["node:N4"]["text"])
        self.assertIn("hazard:H1", upd["items"])
        kinds = {(c["item"], c["change"]) for c in upd["changes"]}
        self.assertIn(("node:N4", "escalate"), kinds)
        self.assertIn(("hazard:H1", "add"), kinds)
        self.assertEqual(upd["uptake"]["N4"]["established"], 2)

    def test_update_restates_unrecognized_and_blocks_at_top(self):
        route = D.choose_route(self.g, self.prof)
        items = D.initial_items(self.g, self.prof, route, "cut")
        items["node:N4"].update(text="t", level=max(C.LEVELS))
        hinted = [record(f"x/qwen/r1/run{i}", "qwen", False, {"N1": "established", "N4": "wrong"}, stuck="N4",
                         given=[], insight=True, run=i) for i in range(1, 6)]
        upd = D.update(self.g, self.prof, route, items, hinted, "cut")
        self.assertEqual(upd["blocked"], ["N4"])
        self.assertEqual([c["change"] for c in upd["changes"] if c["item"] == "node:N4"], ["blocked", "restate"])

    def test_update_behavior_and_off_route(self):
        route = D.choose_route(self.g, self.prof)
        items = D.initial_items(self.g, self.prof, route, "cut")
        items["node:N4"]["text"] = "t"
        hinted = [record(f"x/qwen/r1/run{i}", "qwen", False, {"N1": "established"}, given=["N4"], insight=True, run=i,
                         submissions=0) for i in range(1, 4)]
        hinted += [record(f"x/qwen/r1/run{i}", "qwen", False, {"N1": "established", "N2": "wrong"}, stuck="N2",
                          given=["N4"], insight=True, run=i) for i in range(4, 6)]
        upd = D.update(self.g, self.prof, route, items, hinted, "cut")
        self.assertIn("behavior", upd["items"])
        self.assertEqual(dict(upd["off_route"]), {"N2": 2})
        self.assertIsNone(D.wants_switch(upd, 5))          # 2 of 5 off route: below half
        upd["off_route"]["N2"] = 3
        self.assertEqual(D.wants_switch(upd, 5), "N2")
        new_route = D.choose_route(self.g, self.prof, must_contain="N2")
        switched = D.switch_route(self.g, self.prof, upd["items"], new_route, "cut")
        self.assertNotIn("node:N4", switched)
        self.assertEqual({k for k in switched}, {"node:N2", "node:N3", "behavior"})

    def test_ablation_groups(self):
        items = {"node:N1": D.node_item("N1", 2, ""), "node:N4": D.node_item("N4", 1, ""),
                 "hazard:H1": D.hazard_item("H1", 1, ""), "behavior": D.behavior_item(1, "")}
        groups = D.ablation_groups(self.g, items, self.prof, "cut")
        self.assertEqual([g["name"] for g in groups][:4],
                         ["nodes the model sometimes holds", "hazards", "behavior", "escalated items back to level 1"])
        self.assertEqual(groups[0]["members"], ["node:N1"])
        self.assertEqual(groups[-1], {"name": "node N4", "op": "drop", "members": ["node:N4"]})


class TestWriteChecks(unittest.TestCase):
    def test_ascii_and_checks(self):
        self.assertEqual(W.ascii("a ≤ b → c²"), "a <= b -> c^2")
        self.assertEqual(W.check_text("The bound holds.", 10, WORDS, "statement"), [])
        errs = W.check_text("one\n\ntwo " * 3, 3, WORDS, "")
        self.assertTrue(any("blank" in e for e in errs) and any("tokens" in e for e in errs))
        self.assertTrue(any("program" in e for e in W.check_text("#include <x>\nint main(){}", 99, WORDS, "")))
        self.assertTrue(any("ids" in e for e in W.check_text("use N3 here", 99, WORDS, "")))
        numbers = " ".join(str(1000 + i) for i in range(8))
        self.assertTrue(any("precomputed" in e for e in W.check_text(numbers, 99, WORDS, "")))
        code = "for (int i = 0; i < n; i++) { s += a[i] * b[i]; if (s > m) s -= m; }"
        self.assertTrue(any("copies" in e for e in W.check_text(code, 99, WORDS, "", [code])))
        self.assertEqual(W.check_text("s = s + a*b mod m", 99, WORDS, "", [code]), [])

    def test_copied(self):
        code = "x = a + b; y = x * 2; z = y - a; w = z / 3; v = w + 1; u = v * v; t = u - 7;"
        self.assertTrue(W.copied(code[:60], code, k=8))
        self.assertEqual(W.copied("x = a + b", code, k=8), "")


class TestCompose(unittest.TestCase):
    def test_order_and_tokens(self):
        g = graph()
        items = {"node:N3": D.node_item("N3", 1, ""), "node:N1": D.node_item("N1", 1, ""),
                 "hazard:H1": D.hazard_item("H1", 1, ""), "behavior": D.behavior_item(1, "")}
        for k, v in items.items():
            v["text"] = f"text of {k} ≤"
        text = CP.assemble(items, g)
        self.assertEqual(text.split("\n\n"), ["text of behavior <=", "text of node:N1 <=", "text of node:N3 <=",
                                              "text of hazard:H1 <=\n"])
        self.assertEqual(CP.token_count(WORDS, items), 16)
        self.assertEqual(CP.check_insight(text), [])


class TestGrading(unittest.TestCase):
    def test_route_progress(self):
        r = record("x/qwen/r1/run1", "qwen", False, {"N1": "established", "N2": "wrong", "N3": "established"}, stuck="N2")
        p = GR.route_progress(r, ["N1", "N2", "N3"])
        self.assertEqual((p["reached"], p["held"], p["wrong"], p["end"]), (1, ["N1", "N3"], ["N2"], False))
        r = record("x/qwen/r1/run2", "qwen", True, {"N1": "established", "N3": "established"}, reached_end=True)
        self.assertEqual(GR.route_progress(r, ["N1", "N2", "N3"])["reached"], 2)

    def test_fix_trace(self):
        self.assertEqual(GR.fix_trace("/nowhere/codebase/agentv3/x.jsonl"), "/nowhere/codebase/agentv3/x.jsonl")


def chain_graph():
    """The toy graph with a single END route N1 -> N2 -> N3 (key N3)."""
    g = graph()
    g["end"] = {"statement": "...", "routes": [["N1", "N2", "N3"]], "keys": ["N3"]}
    g["paths"] = [g["paths"][0]]
    for n in g["nodes"]:
        n["depth"] = G.depths(g)[n["id"]]
    return g


class TestStepMode(unittest.TestCase):
    """One node per round: the frontier decides, items grow, compaction tries the earlier items."""

    def setUp(self):
        self.g = chain_graph()
        self.prof = P.build(self.g, baseline_records(), "qwen")      # N1 held, stuck at N2
        self.route = D.choose_route(self.g, self.prof)

    def hinted(self, i, states, stuck=None, solved=False, end=False, given=("N2",), **kw):
        return record(f"x/qwen/r1/run{i}", "qwen", solved, states, stuck=stuck, reached_end=end, given=list(given),
                      insight=True, run=i, **kw)

    def test_round_1_is_the_first_missing_node(self):
        self.assertEqual(self.route["missing"], ["N2", "N3"])
        self.assertEqual(list(D.initial_items(self.g, self.prof, self.route, "step")), ["node:N2"])
        self.assertEqual(list(D.initial_items(self.g, self.prof, self.route, "cut")), ["node:N2", "node:N3"])

    def test_passed_frontier_adds_the_next_node(self):
        items = D.initial_items(self.g, self.prof, self.route, "step")
        items["node:N2"]["text"] = "t"
        recs = [self.hinted(i, {"N1": "established", "N2": "established"}, stuck="N3") for i in range(1, 6)]
        self.assertEqual(D.passed_depth(recs, self.route["nodes"]), 2)
        self.assertEqual(D.frontier(recs, self.route["nodes"]), "N3")
        # one run short of all of them: not passed
        short = recs[:4] + [self.hinted(5, {"N1": "established", "N2": "wrong"}, stuck="N2")]
        self.assertEqual((D.passed_depth(short, self.route["nodes"]), D.frontier(short, self.route["nodes"])), (1, "N2"))
        upd = D.update(self.g, self.prof, self.route, items, recs, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd["changes"]], [("node:N3", "add")])
        self.assertEqual(upd["items"]["node:N3"]["level"], 1)
        self.assertEqual(upd["items"]["node:N2"]["text"], "t")          # the passed item is untouched
        self.assertTrue(upd["items"]["node:N2"]["passed"])
        self.assertEqual((upd["passed"], upd["frontier"]), (2, "N3"))

    def test_given_node_the_runs_do_not_contradict_is_passed(self):
        # 2024/G round 1: N3 given by the hint, absent from the runs' own text, every run wrong at N4 ->
        # N3 passed, the frontier is N4 (the grader's stuck node), not an escalation of N3
        items = D.initial_items(self.g, self.prof, self.route, "step")
        items["node:N2"]["text"] = "t"
        recs = [self.hinted(i, {"N1": "established", "N3": "wrong"}, stuck="N3") for i in range(1, 6)]
        self.assertTrue(all(D.holds(r, "N2") for r in recs))
        self.assertEqual((D.passed_depth(recs, self.route["nodes"]), D.frontier(recs, self.route["nodes"])), (2, "N3"))
        upd = D.update(self.g, self.prof, self.route, items, recs, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd["changes"]], [("node:N3", "add")])
        self.assertEqual(upd["items"]["node:N3"]["level"], 2)          # the model had N3 wrong
        self.assertTrue(upd["items"]["node:N2"]["passed"])
        # a run that takes the hint but leaves the node wrong does not hold it: N2 is not passed (4/5), but a
        # majority holds it, so the next node is hinted and N2's item stays as it is
        mixed = recs[:4] + [self.hinted(5, {"N1": "established", "N2": "wrong"}, stuck="N2")]
        self.assertFalse(D.holds(mixed[4], "N2"))
        self.assertEqual(D.frontier(mixed, self.route["nodes"]), "N2")
        self.assertEqual(D.majority_frontier(mixed, self.route["nodes"], 1), "N3")
        upd2 = D.update(self.g, self.prof, self.route, items, mixed, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd2["changes"]], [("node:N3", "add")])
        self.assertEqual((upd2["items"]["node:N2"]["text"], upd2["items"]["node:N2"]["level"]), ("t", 1))
        self.assertEqual((upd2["passed"], upd2["frontier"], upd2["majority_frontier"]), (1, "N2", "N3"))
        # a majority leaving it wrong escalates it
        most = recs[:2] + [self.hinted(i, {"N1": "established", "N2": "wrong"}, stuck="N2") for i in range(3, 6)]
        upd3 = D.update(self.g, self.prof, self.route, items, most, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd3["changes"]], [("node:N2", "escalate")])
        self.assertEqual(upd3["majority_frontier"], "N2")
        # 3-run rounds: 2 of 3 is a majority
        three = recs[:2] + [self.hinted(3, {"N1": "established", "N2": "wrong"}, stuck="N2")]
        upd4 = D.update(self.g, self.prof, self.route, items, three, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd4["changes"]], [("node:N3", "add")])

    def test_unpassed_frontier_escalates_the_hinted_node(self):
        items = D.initial_items(self.g, self.prof, self.route, "step")
        items["node:N2"]["text"] = "t"
        recs = [self.hinted(i, {"N1": "established", "N2": "wrong"}, stuck="N2") for i in range(1, 5)]
        recs += [self.hinted(5, {"N1": "established", "N2": "established"}, stuck="N3")]
        upd = D.update(self.g, self.prof, self.route, items, recs, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd["changes"]], [("node:N2", "escalate")])
        self.assertEqual(upd["items"]["node:N2"]["level"], 2)
        self.assertNotIn("node:N3", upd["items"])
        # a node the model got wrong without a hint enters at level 2 when it becomes the frontier
        items2 = {"node:N2": dict(items["node:N2"], text="t")}
        recs2 = [self.hinted(i, {"N1": "established", "N2": "established", "N3": "wrong"}, stuck="N3") for i in range(1, 6)]
        upd2 = D.update(self.g, self.prof, self.route, items2, recs2, "step")
        self.assertEqual(upd2["items"]["node:N3"]["level"], 2)

    def test_frontier_resisting_at_the_top_level_moves_on_when_the_runs_stop_later(self):
        # 2023/J Nemotron round 4: N2 at the top level still wrong in 2/3 runs, but every run worked past it
        # and stopped at a later node (slips at N2, the real obstacle later) -> N2's item stays, the later
        # node is hinted; the route blocks only when the runs stop at the frontier itself
        items = D.initial_items(self.g, self.prof, self.route, "step")
        items["node:N2"].update(text="t", level=max(C.LEVELS))
        recs = [self.hinted(1, {"N1": "established", "N2": "wrong", "N3": "wrong"}, stuck="N3"),
                self.hinted(2, {"N1": "established", "N2": "working", "N3": "wrong"}, stuck="N3"),
                self.hinted(3, {"N1": "established", "N2": "wrong", "N3": "wrong"}, stuck="N3")]
        self.assertEqual(D.past_frontier(recs, self.route["nodes"], 1), ("N3", 3))
        upd = D.update(self.g, self.prof, self.route, items, recs, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd["changes"]], [("node:N2", "kept"), ("node:N3", "add")])
        self.assertEqual(upd["blocked"], [])
        self.assertEqual((upd["items"]["node:N2"]["text"], upd["items"]["node:N2"]["level"]), ("t", max(C.LEVELS)))
        self.assertEqual(upd["items"]["node:N3"]["level"], 2)                      # the model had N3 wrong
        self.assertEqual((upd["passed"], upd["frontier"], upd["past_frontier"]), (1, "N2", "N3"))
        # the runs stop at the frontier itself: blocked as before
        same = [self.hinted(i, {"N1": "established", "N2": "wrong"}, stuck="N2") for i in range(1, 4)]
        self.assertEqual(D.past_frontier(same, self.route["nodes"], 1), (None, 0))
        upd2 = D.update(self.g, self.prof, self.route, items, same, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd2["changes"]], [("node:N2", "blocked")])
        self.assertEqual((upd2["blocked"], upd2["past_frontier"]), (["N2"], None))
        # only a minority of the failed runs stop later: blocked
        upd3 = D.update(self.g, self.prof, self.route, items, recs[:1] + same[1:], "step")
        self.assertEqual(upd3["blocked"], ["N2"])
        # below C.MOVE_ON_LEVEL the frontier escalates as before; from it on the rule applies
        items["node:N2"]["level"] = C.MOVE_ON_LEVEL - 1
        upd4 = D.update(self.g, self.prof, self.route, items, recs, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd4["changes"]], [("node:N2", "escalate")])
        self.assertEqual(upd4["items"]["node:N2"]["level"], C.MOVE_ON_LEVEL)
        items["node:N2"]["level"] = C.MOVE_ON_LEVEL
        upd5 = D.update(self.g, self.prof, self.route, items, recs, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd5["changes"]], [("node:N2", "kept"), ("node:N3", "add")])
        # the runs stopping at a frontier below the top level: it escalates to the top level first
        items["node:N2"]["level"] = C.MOVE_ON_LEVEL
        upd6 = D.update(self.g, self.prof, self.route, items, same, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd6["changes"]], [("node:N2", "escalate")])
        self.assertEqual(upd6["items"]["node:N2"]["level"], max(C.LEVELS))

    def test_whole_route_passed_leaves_nodes_alone(self):
        items = {"node:N2": dict(D.node_item("N2", 1, ""), text="t"), "node:N3": dict(D.node_item("N3", 1, ""), text="t")}
        recs = [self.hinted(i, {"N1": "established", "N2": "established", "N3": "established"}, end=True,
                            given=("N2", "N3"), hazards=["H1"]) for i in range(1, 6)]
        upd = D.update(self.g, self.prof, self.route, items, recs, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd["changes"]], [("hazard:H1", "add")])
        self.assertEqual((upd["passed"], upd["frontier"]), (3, None))

    def test_whole_route_held_but_runs_still_stuck_escalates_the_stuck_node(self):
        # 2024/G Nemotron round 6: every route node given and uncontradicted, 1/3 solved, the two failed runs
        # still working on N4 and N5 -> no frontier; the node most failed runs stop at escalates (ties: the
        # earliest on the route), one node per round, instead of re-running the same text
        items = {"node:N2": dict(D.node_item("N2", 1, ""), text="t"), "node:N3": dict(D.node_item("N3", 2, ""), text="t")}
        recs = [self.hinted(1, {"N1": "established", "N2": "established", "N3": "established"}, solved=True, end=True,
                            given=("N2", "N3")),
                self.hinted(2, {"N1": "established", "N2": "working", "N3": "working"}, stuck="N3", given=("N2", "N3")),
                self.hinted(3, {"N1": "established", "N2": "working", "N3": "working"}, stuck="N3", given=("N2", "N3"))]
        self.assertEqual((D.passed_depth(recs, self.route["nodes"]), D.frontier(recs, self.route["nodes"])), (3, None))
        upd = D.update(self.g, self.prof, self.route, items, recs, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd["changes"]], [("node:N3", "escalate")])
        self.assertEqual((upd["items"]["node:N3"]["level"], upd["items"]["node:N2"]["text"]), (3, "t"))
        self.assertEqual((upd["passed"], upd["frontier"]), (3, None))
        # a tie between two stuck nodes goes to the earlier one on the route
        tie = recs[:1] + [self.hinted(2, {"N1": "established", "N2": "working", "N3": "working"}, stuck="N2",
                                      given=("N2", "N3")), recs[2]]
        upd2 = D.update(self.g, self.prof, self.route, items, tie, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd2["changes"]], [("node:N2", "escalate")])
        # at the top level the stuck node blocks, as a resisting frontier does
        items["node:N3"]["level"] = max(C.LEVELS)
        upd3 = D.update(self.g, self.prof, self.route, items, recs, "step")
        self.assertEqual(([(c["item"], c["change"]) for c in upd3["changes"]], upd3["blocked"]),
                         ([("node:N3", "blocked")], ["N3"]))
        # failed runs that reached END are the hazards' business, not a stuck node's
        ended = recs[:1] + [self.hinted(i, {"N1": "established", "N2": "established", "N3": "established"}, end=True,
                                        stuck="N3", given=("N2", "N3"), hazards=["H1"]) for i in (2, 3)]
        upd4 = D.update(self.g, self.prof, self.route, items, ended, "step")
        self.assertEqual([(c["item"], c["change"]) for c in upd4["changes"]], [("hazard:H1", "add")])

    def test_passed_nodes_stay_passed_unless_a_majority_contradicts(self):
        # 2024/G Nemotron round 4: the hinted N4 held by every run, but one run only left the profile-held N1
        # "working" -> the all-nodes-3/3 rule scored passed 0, rejected the round and stopped the loop at L4.
        # Here N1 is the passed prefix, N2 the hinted node, N3 wrong in the runs' own text.
        self.assertEqual(D.initial_passed(self.route), ["N1"])
        items = D.initial_items(self.g, self.prof, self.route, "step")
        items["node:N2"]["text"] = "t"
        recs = [self.hinted(1, {"N1": "working", "N2": "established", "N3": "wrong"}, stuck="N1")]
        recs += [self.hinted(i, {"N1": "established", "N2": "established", "N3": "wrong"}, stuck="N3") for i in range(2, 6)]
        self.assertEqual(D.passed_depth(recs, self.route["nodes"]), 0)                   # the old rule
        self.assertEqual(D.passed_depth(recs, self.route["nodes"], ["N1"]), 2)           # N1 stays, N2 passed 5/5
        self.assertEqual(D.frontier(recs, self.route["nodes"], ["N1"]), "N3")
        upd = D.update(self.g, self.prof, self.route, items, recs, "step", passed=["N1"])
        self.assertEqual([(c["item"], c["change"]) for c in upd["changes"]], [("node:N3", "add")])
        self.assertEqual((upd["passed"], upd["frontier"], upd["passed_nodes"]), (2, "N3", ["N1", "N2"]))
        self.assertTrue(upd["items"]["node:N2"]["passed"])
        # a majority of the runs contradicting the passed N1 regresses the frontier to N1
        bad = [self.hinted(i, {"N1": "wrong", "N2": "established"}, stuck="N1") for i in range(1, 4)] + recs[3:]
        self.assertEqual((D.passed_depth(bad, self.route["nodes"], ["N1"]), D.frontier(bad, self.route["nodes"], ["N1"])), (0, "N1"))
        upd2 = D.update(self.g, self.prof, self.route, items, bad, "step", passed=["N1"])
        self.assertEqual([(c["item"], c["change"]) for c in upd2["changes"]], [("node:N1", "add")])
        self.assertEqual(upd2["passed_nodes"], [])
        # a minority (2 of 5) does not
        two = bad[:2] + recs[2:]
        self.assertEqual(D.passed_depth(two, self.route["nodes"], ["N1"]), 2)
        # after a route switch the nodes passed so far carry over as the new route's prefix
        self.assertEqual(D.initial_passed(dict(self.route, held=[]), ["N1", "N2"]), ["N1", "N2"])
        self.assertEqual(D.initial_passed(dict(self.route, held=["N3"]), ["N1"]), ["N1"])     # N3 beyond the gap is not pre-passed

    def test_switch_and_ablation_in_step_mode(self):
        new_route = dict(self.route, missing=["N2", "N3"])
        switched = D.switch_route(self.g, self.prof, {"hazard:H1": D.hazard_item("H1", 1, "")}, new_route, "step")
        self.assertEqual(list(switched), ["hazard:H1", "node:N2"])
        items = {"node:N2": D.node_item("N2", 2, ""), "node:N3": D.node_item("N3", 1, ""), "hazard:H1": D.hazard_item("H1", 1, "")}
        groups = D.ablation_groups(self.g, items, self.prof, "step")
        self.assertEqual([(g["name"], g["op"], g["members"]) for g in groups],
                         [("hazards", "drop", ["hazard:H1"]), ("escalated items back to level 1", "level1", ["node:N2"]),
                          ("node N2", "drop", ["node:N2"])])       # N3, the last added, is not a candidate
        # written items end with the "shorten" group: every item (the last added too), the behavior item aside
        written = {k: dict(v, text="t") for k, v in items.items()}
        written["behavior"] = dict(D.behavior_item(1, ""), text="b")
        self.assertEqual(D.ablation_groups(self.g, written, self.prof, "step")[-1],
                         {"name": "shorter wording", "op": "shorten", "members": ["node:N2", "node:N3", "hazard:H1"]})


if __name__ == "__main__":
    unittest.main()
