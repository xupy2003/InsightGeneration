"""Offline checks of the graph rules, derived fields, version and text."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from graph import rules as R  # noqa: E402

STATEMENT = ("There are n cups with diameters 1..n placed in some order; the tower height h is the top of the "
             "highest cup. Print an order with height h or impossible.")
REFERENCE = "#include <bits/stdc++.h>\nint main() { long long n, h; std::cin >> n >> h; return 0; }\n"


def node(i, routes, kind="key_property", **kw):
    d = {"id": f"N{i}", "name": f"Cup level claim {i}", "kind": kind,
         "statement": f"Claim {i} about the cups and the tower height.", "routes": routes,
         "accept": "States or uses it.", "anchors": ["cups"], "source": "editorial"}
    d.update(kw)
    return d


def toy():
    return {"solution_outline": "Model the cups, then bound the heights, then construct the order.",
            "nodes": [node(1, [[]], "modeling"), node(2, [["N1"]]), node(3, [["N1"]]), node(4, [["N2"]]),
                      node(5, [["N2", "N3"], ["N4"]], "construction")],
            "end": {"statement": "Holding N5 the order is written by routine coding.", "routes": [["N5"]]},
            "hazards": [{"id": "H1", "statement": "n squared reaches 4e10, beyond 32 bits.",
                         "check": "64-bit types for h and n*n."}],
            "notes": ""}


class RuleTests(unittest.TestCase):
    def test_toy_passes(self):
        self.assertEqual(R.check_graph(toy(), STATEMENT), [])
        self.assertEqual(R.warnings_of(toy(), STATEMENT), [])

    def test_depths_and_reachability(self):
        self.assertEqual(R.depths(toy()), {"N1": 1, "N2": 2, "N3": 2, "N4": 3, "N5": 3})
        self.assertEqual(R.reachable(toy()), {"N1", "N2", "N3", "N4", "N5"})
        d = R.derive(toy())
        self.assertEqual([n["depth"] for n in d["nodes"]], [1, 2, 2, 3, 3])
        self.assertEqual(d["nodes"][0]["traps"], [])

    def test_unreachable_and_later_routes(self):
        g = toy()
        g["nodes"].append(node(6, [["N1"]]))
        self.assertTrue(any("N6" in p and "no derivation of END" in p for p in R.check_graph(g, STATEMENT)))
        g = toy()
        g["nodes"][1]["routes"] = [["N3"]]
        self.assertTrue(any("not earlier nodes" in p for p in R.check_graph(g, STATEMENT)))

    def test_redundant_and_empty_routes(self):
        g = toy()
        g["nodes"][4]["routes"] = [["N2", "N3"], ["N2"]]
        self.assertTrue(any("subset" in p for p in R.check_graph(g, STATEMENT)))
        g = toy()
        g["nodes"][1]["routes"] = [[], ["N1"]]
        self.assertTrue(any("statement alone" in p for p in R.check_graph(g, STATEMENT)))
        g = toy()
        g["end"]["routes"] = [[]]
        self.assertTrue(any("END route" in p and "empty" in p for p in R.check_graph(g, STATEMENT)))
        g = toy()
        for n in g["nodes"]:
            n["routes"] = [["N1"]] if n["id"] != "N1" else [["N2"]]
        self.assertTrue(any("not earlier" in p for p in R.check_graph(g, STATEMENT)))

    def test_names_code_and_numbers(self):
        g = toy()
        g["nodes"][0]["name"] = "Implementation"
        self.assertTrue(any("fits any problem" in p for p in R.check_graph(g, STATEMENT)))
        g = toy()
        g["nodes"][0]["statement"] = "The cups give 11 13 17 19 23 29 31 37 as answers."
        self.assertTrue(any("precomputed answers" in p for p in R.check_graph(g, STATEMENT)))
        g = toy()
        g["nodes"][0]["anchors"] = ["zebra"]                      # anchors only warn
        self.assertEqual(R.check_graph(g, STATEMENT), [])
        self.assertTrue(any("occurs in the statement" in w for w in R.warnings_of(g, STATEMENT)))
        g["nodes"][0]["anchors"] = []
        self.assertEqual(R.check_graph(g, STATEMENT), [])
        self.assertTrue(any("no anchors" in w for w in R.warnings_of(g, STATEMENT)))

    def test_counts_and_hazards(self):
        g = toy()
        g["nodes"] = g["nodes"][:4]
        g["end"]["routes"] = [["N4"], ["N3"]]
        self.assertEqual(R.check_graph(g, STATEMENT), [])                      # no cap unless asked
        self.assertTrue(any(f"at least {C.MIN_NODES} nodes" in p
                            for p in R.check_graph(g, STATEMENT, C.MIN_NODES, C.MAX_NODES)))
        self.assertTrue(any("at most 3 nodes" in p for p in R.check_graph(g, STATEMENT, max_nodes=3)))
        g = toy()
        g["hazards"][0]["id"] = "H7"
        self.assertTrue(any("must have id H1" in p for p in R.check_graph(g, STATEMENT)))
        g = toy()
        g["hazards"] = [dict(g["hazards"][0], id=f"H{i}") for i in range(1, 10)]   # any number of hazards
        self.assertEqual(R.check_graph(g, STATEMENT), [])
        g = toy()
        g["nodes"][4]["routes"] = [["N1", "N3", "N4"], ["N2"]]                    # any route size and count
        g["nodes"].append(dict(g["nodes"][4], id="N6", routes=[["N5"], ["N4"], ["N3"], ["N2"]]))
        g["end"]["routes"] = [["N5"], ["N6"], ["N4"], ["N3"], ["N2"]]
        self.assertEqual(R.check_graph(g, STATEMENT), [])

    def test_key_nodes(self):
        g = R.derive(toy())
        self.assertEqual(R.ancestors(g, "N5"), {"N1", "N2", "N3", "N4"})
        self.assertEqual(R.key_nodes(g, ["N1", "N2", "N3", "N5"]), ["N5"])     # a route written out in full
        self.assertEqual(R.key_nodes(g, ["N5"]), ["N5"])                       # or as its terminal node alone
        self.assertEqual(R.key_nodes(g, ["N2", "N3"]), ["N2", "N3"])           # independent claims: both key
        g["end"]["routes"] = [["N1", "N2", "N3", "N5"], ["N4"]]
        self.assertEqual(R.end_key_routes(g), [["N5"], ["N4"]])            # terminal nodes when no keys are declared
        g["end"]["keys"] = ["N5", "N4"]
        self.assertEqual(R.end_key_routes(g), [["N5"], ["N4"]])
        self.assertEqual(R.check_path(g, [], ["N1", "N2", "N5"], "N5", []), [])
        # the key node is the output rule: kind algorithm or construction, never a complexity claim
        self.assertTrue(any("has kind 'key_property'" in p for p in R.check_path(g, [], ["N1", "N2"], "N2", [])))
        g2 = R.derive(toy())
        g2["nodes"][4]["statement"] = "The construction runs in O(n log n) and fits the limits."
        self.assertTrue(any("complexity or feasibility" in p for p in R.check_path(g2, [], ["N1", "N2", "N5"], "N5", [])))
        self.assertTrue(any("efficiency claim" in w for w in R.warnings_of(g2, STATEMENT)))
        self.assertIsNone(R.complexity_claim("Append the largest cup last to realize the height."))
        self.assertEqual(R.complexity_claim("Pairwise testing is fast enough here."), "fast enough")
        self.assertTrue(any("does not depend" in p for p in R.check_path(g, [], ["N1", "N2", "N5"], "N2", [])))
        self.assertTrue(any("already the key node" in p for p in R.check_path(g, [], ["N5"], "N5", ["N5"])))
        self.assertTrue(any("must be one of end_route" in p for p in R.check_path(g, [], ["N1"], "N5", [])))

    def test_version_ignores_traps_and_depth(self):
        a = R.derive(toy())
        b = R.derive(toy())
        b["nodes"][0]["traps"] = ["the cup rests on the previous cup only"]
        b["nodes"][0]["depth"] = 9
        self.assertEqual(R.version_of(a), R.version_of(b))
        b["nodes"][0]["statement"] += " changed"
        self.assertNotEqual(R.version_of(a), R.version_of(b))

    def test_text(self):
        text = R.graph_text(R.derive(toy()))
        for part in ("N1 ·", "routes: statement", "N2+N3 | N4", "END [routes: N5]", "H1:"):
            self.assertIn(part, text)
        self.assertEqual([n["id"] for n in R.probe_nodes(toy())], ["N1", "N2", "N3", "N4", "N5"])


if __name__ == "__main__":
    unittest.main()
