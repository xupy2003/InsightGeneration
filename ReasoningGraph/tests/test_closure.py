"""Offline checks of the closure: node states over checkpoints, END, unsupported, frontier, stuck, roots, class."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from graph import rules as R  # noqa: E402
from grade import closure as Cl  # noqa: E402
from tests.test_rules import toy  # noqa: E402

GRAPH = R.derive(toy())
# The same graph with its END route written out in full (the explorer lists every node a path rests on).
FULL = {**GRAPH, "end": {"statement": "", "routes": [["N1", "N2", "N3", "N5"]], "keys": ["N5"]}}


def cp(cid, states, kind="window", rounds=(2,)):
    rows = [{"node_id": nid, "state": st, "quote": f"q {nid}" if st != "absent" else None,
             "solver_claim": f"belief {nid} {st}" if st != "absent" else None, "unit_id": None, "where": cid}
            for nid, st in states.items()]
    return {"id": cid, "kind": kind, "rounds": list(rounds), "rows": rows}


class ClosureTests(unittest.TestCase):
    def test_states_last_non_absent_and_rank(self):
        cps = [cp("A", {"N1": "working", "N2": "absent"}), cp("B", {"N1": "established", "N2": "wrong"}),
               cp("C", {"N1": "absent", "N2": "working"})]
        res = Cl.node_states(GRAPH, cps)
        self.assertEqual(res["N1"]["trajectory"], "~+.")
        self.assertEqual(res["N1"]["final"], "established")
        self.assertEqual(res["N2"]["trajectory"], ".x~")
        self.assertEqual(res["N2"]["final"], "working")
        self.assertEqual(res["N2"]["wrong"], 1)
        self.assertEqual(res["N2"]["claims"][0]["claim"], "belief N2 wrong")
        both = [{**cp("D", {"N1": "established"})["rows"][0]}, {**cp("D", {"N1": "wrong"})["rows"][0]}]
        res = Cl.node_states(GRAPH, [{"id": "D", "kind": "window", "rounds": [1], "rows": both}])
        self.assertEqual(res["N1"]["final"], "wrong")

    def test_end_unsupported_frontier(self):
        held = {"N1", "N2", "N3"}
        self.assertEqual(Cl.end_routes_satisfied(GRAPH, held), [])
        self.assertEqual(Cl.frontier(GRAPH, held), ["N4", "N5"])
        self.assertEqual(Cl.unsupported(GRAPH, held), [])
        held = {"N1", "N2", "N4", "N5"}
        self.assertEqual(Cl.end_routes_satisfied(GRAPH, held), [1])
        full = {**GRAPH, "end": {"statement": "", "routes": [["N1", "N2", "N3", "N5"]]}}   # written out in full
        self.assertEqual(Cl.end_routes_satisfied(full, {"N5"}), [1])            # the key node N5 is enough
        self.assertEqual(Cl.end_routes_satisfied(full, {"N1", "N2", "N3"}), [])
        self.assertEqual(Cl.unsupported(GRAPH, held), [])
        self.assertEqual(Cl.unsupported(GRAPH, {"N5"}), ["N5"])
        self.assertEqual(Cl.unsupported(GRAPH, {"N5"}, given={"N5"}), [])
        self.assertEqual(Cl.frontier(GRAPH, set()), ["N1"])

    def test_stuck_roots_and_class(self):
        cps = [cp("A", {"N1": "established", "N2": "wrong", "N3": "working"})]
        res = Cl.node_states(GRAPH, cps)
        held = {"N1"}
        self.assertEqual(Cl.frontier(GRAPH, held), ["N2", "N3"])
        self.assertEqual(Cl.stuck_node(GRAPH, res, held), ("N2", "frontier"))
        self.assertEqual(Cl.roots(GRAPH, res), ["N2"])
        self.assertEqual(Cl.root_node(GRAPH, res), "N2")
        # a wrong node whose prerequisite is wrong is not a root
        cps = [cp("A", {"N1": "wrong", "N2": "wrong"})]
        res = Cl.node_states(GRAPH, cps)
        self.assertEqual(Cl.roots(GRAPH, res), ["N1"])
        self.assertEqual(Cl.stuck_node(GRAPH, Cl.node_states(GRAPH, [cp("A", {})]), set()), (None, None))
        self.assertEqual(Cl.classify(True, True, [], None), "END+AC")
        self.assertEqual(Cl.classify(False, True, ["H1"], None), "END+fail/hazard:H1")
        self.assertEqual(Cl.classify(False, True, [], None), "END+fail/other")
        self.assertEqual(Cl.classify(True, False, [], None), "noEND+AC")
        self.assertEqual(Cl.classify(False, False, [], "N2"), "noEND+fail/stuck:N2")
        self.assertEqual(Cl.classify(False, False, [], None), "noEND+fail/stalled")
        self.assertEqual(Cl.classify(False, False, [], None, off_graph=True), "noEND+fail/off_graph")

    def test_apply_adjudications(self):
        cps = [cp("A", {"N1": "established", "N2": "established", "N3": "established", "N5": "established"}),
               cp("B", {"N2": "wrong"})]
        # the windows leave N2 wrong: END blocked on the full route
        s = Cl.summarize(FULL, cps, given=[], solved=True, tripped=[])
        self.assertFalse(s["reached_end"])
        self.assertEqual(s["class"], "noEND+AC")
        # the adjudication reads B as a slip: N2 established, END reached, the slip marked on the claim
        adj = {"N2": {"final": "established", "basis": "A", "reason": "A summary slip.",
                      "slips": [{"where": "B", "why": "Its own code contradicts it."}]}}
        s = Cl.summarize(FULL, cps, given=[], solved=True, tripped=[], adjudications=adj)
        self.assertTrue(s["reached_end"])
        self.assertEqual(s["class"], "END+AC")
        self.assertEqual(s["results"]["N2"]["window_final"], "wrong")
        self.assertEqual(s["results"]["N2"]["final"], "established")
        self.assertEqual(s["results"]["N2"]["trajectory"], "+x")              # the windows' states are kept
        self.assertEqual(s["results"]["N2"]["claims"][0]["slip"], "Its own code contradicts it.")
        self.assertEqual(s["adjudicated"], {"N2": "established"})
        self.assertEqual(s["roots"], [])
        # an adjudication that keeps wrong changes nothing but records itself
        adj = {"N2": {"final": "wrong", "basis": "B", "reason": "It decides on it.", "slips": []}}
        s = Cl.summarize(FULL, cps, given=[], solved=True, tripped=[], adjudications=adj)
        self.assertFalse(s["reached_end"])
        self.assertEqual(s["adjudicated"], {"N2": "wrong"})
        # unknown nodes and malformed answers are ignored
        s = Cl.summarize(FULL, cps, given=[], solved=True, tripped=[], adjudications={"N9": {"final": "established"},
                                                                                       "N2": {"final": "maybe"}})
        self.assertEqual(s["adjudicated"], {})

    def test_summarize_text_only_given_and_programs(self):
        # the program's holds do not establish nodes: N5 held in code only is not held (2026-11-03)
        cps = [cp("R2W01", {"N1": "established"}),
               cp("P2", {"N1": "established", "N5": "established"}, kind="program")]
        s = Cl.summarize(GRAPH, cps, given=["N2"], solved=True, tripped=[])
        self.assertEqual(s["established"], ["N1"])
        self.assertEqual(s["given"], ["N2"])
        self.assertFalse(s["reached_end"])
        self.assertEqual(s["class"], "noEND+AC")
        self.assertEqual(s["implemented"]["N5"]["status"], "holds")
        self.assertEqual(s["implemented"]["N4"]["status"], "not_needed")
        self.assertEqual(s["results"]["N1"]["trajectory"], "+")        # windows only
        # the text holds the key node on given prerequisites: END, not unsupported, not derived
        s = Cl.summarize(FULL, [cp("R2W01", {"N5": "established"})], given=["N1", "N2", "N3"], solved=True,
                         tripped=[])
        self.assertTrue(s["reached_end"])
        self.assertFalse(s["derived_end"])
        self.assertEqual(s["unsupported"], [])
        self.assertEqual(s["class"], "END+AC")
        # the whole route in the text: derived
        s = Cl.summarize(FULL, [cp("R2W01", {"N1": "established", "N2": "established", "N3": "established",
                                              "N5": "established"})], given=[], solved=True, tripped=[])
        self.assertTrue(s["derived_end"])
        self.assertEqual(s["end_routes"][0]["nodes"], ["N1", "N2", "N3", "N5"])
        # the hint states the key node; the run never establishes it itself: no END, stuck at the given node
        # it gets wrong (on the frontier: given prerequisites support it)
        s = Cl.summarize(GRAPH, [cp("R2W01", {"N1": "established", "N5": "wrong"})],
                         given=["N1", "N2", "N3", "N5"], solved=False, tripped=[])
        self.assertFalse(s["reached_end"])
        self.assertEqual(s["frontier"], ["N2", "N3", "N4", "N5"])
        self.assertEqual((s["stuck"], s["stuck_source"]), ("N5", "frontier"))
        self.assertEqual(s["class"], "noEND+fail/stuck:N5")

    def test_wrong_on_route_blocks_end(self):
        # key held, but a step of the route left wrong: not END (a skipped step would be fine)
        s = Cl.summarize(FULL, [cp("R2W01", {"N1": "wrong", "N5": "established"})], given=[], solved=True,
                         tripped=[])
        self.assertFalse(s["reached_end"])
        self.assertEqual(s["end_routes"][0]["wrong"], ["N1"])
        self.assertEqual(s["class"], "noEND+AC")
        s = Cl.summarize(FULL, [cp("R2W01", {"N5": "established"})], given=[], solved=True, tripped=[])
        self.assertTrue(s["reached_end"])                # skipped steps are fine
        self.assertEqual(s["unsupported"], ["N5"])      # N5 held without N4 or N3
        # a wrong node off the route does not block (another path's step)
        s = Cl.summarize(GRAPH, [cp("R2W01", {"N1": "wrong", "N5": "established"})], given=[], solved=True,
                         tripped=[])
        self.assertTrue(s["reached_end"])                # the route of GRAPH is [N5] alone
        # a right idea with code contradicting a route node: END+fail/other, code_gap names the node
        cps = [cp("R2W01", {"N1": "established", "N2": "established", "N3": "established", "N5": "established"}),
               cp("P1", {"N3": "wrong"}, kind="program")]
        s = Cl.summarize(FULL, cps, given=[], solved=False, tripped=[])
        self.assertEqual(s["class"], "END+fail/other")
        self.assertEqual(s["code_gap"], ["N3"])
        self.assertEqual(s["implemented"]["N3"]["status"], "contradicts")

    def test_stuck_root_fallback_and_off_graph(self):
        # the frontier has no evidence, but a deeper node is wrong: stuck at the root, not stalled
        cps = [cp("R2W01", {"N1": "established", "N5": "wrong"})]
        s = Cl.summarize(GRAPH, cps, given=[], solved=False, tripped=[])
        self.assertEqual(s["frontier"], ["N2", "N3"])
        self.assertEqual((s["stuck"], s["stuck_source"]), ("N5", "root"))
        self.assertEqual(s["class"], "noEND+fail/stuck:N5")
        # nothing on the graph at all: stalled, unless the run stated wrong claims no node covers
        s = Cl.summarize(GRAPH, [cp("R2W01", {})], given=[], solved=False, tripped=[])
        self.assertEqual(s["class"], "noEND+fail/stalled")
        off = [{"claim": "The answer is always n.", "quote": "always n", "unit_id": "U1", "wrong": True}]
        s = Cl.summarize(GRAPH, [cp("R2W01", {})], given=[], solved=False, tripped=[], off_graph=off)
        self.assertEqual(s["class"], "noEND+fail/off_graph")
        self.assertEqual(s["off_graph"], off)
        s = Cl.summarize(GRAPH, [cp("R2W01", {"N1": "established", "N2": "wrong"})], given=[], solved=False,
                         tripped=[])
        self.assertEqual(s["class"], "noEND+fail/stuck:N2")
        self.assertEqual(s["root"], "N2")
        s = Cl.summarize(GRAPH, [cp("R2W01", {"N5": "established"})], given=[], solved=False, tripped=["H1"])
        self.assertEqual(s["class"], "END+fail/hazard:H1")

if __name__ == "__main__":
    unittest.main()
