"""Offline checks of the exploration loop with a scripted fake API and a fake judge: rules, judge verdicts,
accepted paths, the attempt cap, the path limit, the review with wording-only revisions, the files."""
import contextlib
import io
import json
import logging
import re
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from graph import explore as X  # noqa: E402
from graph import build as B  # noqa: E402
from tests.test_build import FakeContext  # noqa: E402


def node(i, routes, kind="construction", statement=None):
    return {"id": f"N{i}", "name": f"Cup level claim {i}", "kind": kind,
            "statement": statement or f"Claim {i} about the cups and the tower height.", "routes": routes,
            "accept": "States or uses it.", "anchors": ["cups"]}


def path(nodes, end_route, program, approach="Sort the cups and stack them greedily. It is O(n).", hazards=(),
         key_node=None):
    return {"approach": approach, "nodes": nodes, "end_route": end_route, "key_node": key_node or end_route[-1],
            "hazards": list(hazards), "program": program, "notes": ""}


def review(doc, bad=(), editorial_found=True):
    return {"nodes": [{"id": n["id"], **{f: n["id"] not in bad for f in B.NODE_FLAGS},
                       "note": "vague" if n["id"] in bad else ""} for n in doc["nodes"]],
            "end_ok": True, "end_note": "", "hazards_ok": True, "hazards_note": "", "missing": [],
            "editorial_found": editorial_found, "editorial_note": "" if editorial_found else "the editorial uses a DP",
            "order": "", "verdict": "accept" if not bad else "revise"}


def fake_judge(problem, code, workdir=None):
    if "// AC" in code:
        return {"verdict": "AC", "accepted": True, "tests_run": 10, "n_tests": 10, "failing_test": None,
                "failing_input": None, "failing_answer": None, "max_time_s": 0.1, "time_limit_s": 2.0,
                "compile_error": None}
    return {"verdict": "WA", "accepted": False, "tests_run": 3, "n_tests": 10, "failing_test": "secret-003",
            "failing_input": "4 9", "failing_answer": "7 3 5 1", "max_time_s": 0.1, "time_limit_s": 2.0,
            "compile_error": None}


class ScriptedClient:
    """responses.create returns the next scripted (tool, arguments); the tool must be one the request offers."""

    def __init__(self, script):
        self.script, self.calls, self.responses = list(script), [], self

    def create(self, **kw):
        offered = [t["name"] for t in kw["tools"]]
        name, result = self.script.pop(0)
        assert name in offered, f"{name} not offered; offered {offered}"
        first = kw["input"][0]
        self.calls.append((name, first.get("output") or first.get("content") or ""))
        usage = SimpleNamespace(input_tokens=100, output_tokens=10, input_tokens_details=None, output_tokens_details=None)
        call = SimpleNamespace(type="function_call", name=name, arguments=json.dumps(result),
                               call_id=f"c{len(self.calls)}", model_dump=lambda: {"type": "function_call"})
        return SimpleNamespace(id=f"r{len(self.calls)}", status="completed", usage=usage, output=[call])


def args(**kw):
    base = dict(effort="high", audit_effort="high", max_paths=C.MAX_PATHS, max_revisions=3, no_review=False,
                editorial="never", editorial_only=False, revise_from=None)
    base.update(kw)
    return SimpleNamespace(**base)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for p in (unittest.mock.patch.object(C, "GRAPHS_DIR", self.root / "graphs"),
                  unittest.mock.patch.object(X, "ProblemContext", FakeContext)):
            p.start()
            self.addCleanup(p.stop)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

class ExploreTests(Base):
    def test_full_loop(self):
        p1 = path([node(1, [[]], "modeling"), node(2, [["N1"]])], ["N1", "N2"], "// WA\nint main(){}")
        p1_fixed = dict(p1, program="// AC\nint main(){}")
        dup = path([], ["N1", "N2"], "// AC")
        p2 = path([node(3, [["N1"]], "algorithm")], ["N1", "N3"], "// AC\nint main(){return 0;}",
                  hazards=[{"id": "H1", "statement": "n squared reaches 4e10, beyond 32 bits.",
                            "check": "wide enough integer types for n*n."}])
        script = [("submit_path", p1), ("submit_path", p1_fixed), ("submit_path", dup), ("submit_path", p2),
                  ("finish_exploration", {"reason": "no other approach", "considered": ["DP over cups: too slow"]})]
        client = ScriptedClient(script + [("submit_review", None)])   # the review answer is filled in below
        reviewed = {}

        def create(**kw):          # the review needs the graph, which exists only once exploration ended
            if client.script and client.script[0][0] == "submit_review":
                doc = B.load_json(C.GRAPHS_DIR / "2025_J-stacking-cups" / "graph.json")
                client.script[0] = ("submit_review", review(doc, editorial_found=False))
            return ScriptedClient.create(client, **kw)
        client.responses = SimpleNamespace(create=create)
        with contextlib.redirect_stdout(io.StringIO()):
            doc = X.explore_problem(client, "wf2025/J-stacking-cups", args(), judge=fake_judge)
        self.assertEqual(doc["status"], "accepted")
        self.assertEqual([p["id"] for p in doc["paths"]], ["P1", "P2"])
        self.assertEqual(doc["end"]["routes"], [["N1", "N2"], ["N1", "N3"]])
        self.assertEqual([n["source"] for n in doc["nodes"]], ["exploration"] * 3)
        self.assertEqual([n["path"] for n in doc["nodes"]], ["P1", "P1", "P2"])
        self.assertEqual(doc["hazards"][0]["id"], "H1")
        self.assertEqual(doc["exploration"]["submissions"], 4)
        self.assertTrue(doc["exploration"]["finished"])
        self.assertEqual(doc["exploration"]["considered"], ["DP over cups: too slow"])
        self.assertTrue(any("editorial" in a for a in doc["advisories"]))
        out = C.GRAPHS_DIR / "2025_J-stacking-cups"
        self.assertTrue((out / "paths" / "P1.cpp").exists() and (out / "paths" / "P2.cpp").exists())
        self.assertEqual(len((out / "judged.jsonl").read_text().splitlines()), 3)      # the duplicate was not judged
        self.assertIn("## Paths", (out / "graph.md").read_text())
        self.assertTrue((out / "history" / f"graph_{doc['version']}.json").exists())
        # what the explorer was told
        self.assertIn("Verdict: WA", client.calls[1][1])
        self.assertIn("Accepted: P1", client.calls[2][1])
        self.assertIn("not a genuinely different approach", client.calls[3][1])
        self.assertIn("New node ids continue at N3", client.calls[3][1] + client.calls[2][1])
        self.assertEqual(doc["provenance"]["review_rounds"], 1)

    def test_review_blocking_revises_texts_only(self):
        p1 = path([node(1, [[]], "modeling"), node(2, [["N1"]])], ["N1", "N2"], "// AC")
        script = [("submit_path", p1), ("finish_exploration", {"reason": "done", "considered": []})]
        client = ScriptedClient(script + [("submit_review", None), ("revise_nodes", None), ("submit_review", None)])

        def create(**kw):
            if client.script and client.script[0][1] is None:
                name = client.script[0][0]
                doc = B.load_json(C.GRAPHS_DIR / "2025_J-stacking-cups" / "graph.json")
                if name == "submit_review":
                    done = any(c[0] == "revise_nodes" for c in client.calls)
                    client.script[0] = ("submit_review", review(doc, bad=() if done else ("N2",)))
                else:
                    nodes = [{k: n[k] for k in ("id", "name", "kind", "statement", "accept", "anchors")} for n in doc["nodes"]]
                    nodes[1]["statement"] = "Claim 2, restated precisely, about the cups."
                    client.script[0] = ("revise_nodes", {"nodes": nodes, "hazards": [], "notes": "restated N2"})
            return ScriptedClient.create(client, **kw)
        client.responses = SimpleNamespace(create=create)
        with contextlib.redirect_stdout(io.StringIO()):
            doc = X.explore_problem(client, "2025/J-stacking-cups", args(), judge=fake_judge)
        self.assertEqual(doc["status"], "accepted")
        self.assertEqual(doc["nodes"][1]["statement"], "Claim 2, restated precisely, about the cups.")
        self.assertEqual(doc["nodes"][1]["routes"], [["N1"]])
        self.assertEqual(doc["provenance"]["review_rounds"], 2)
        self.assertEqual(doc["builder_notes"], "restated N2")
        self.assertIn("Blocking", client.calls[3][1])                 # the findings went into the explorer's session

    def test_attempt_cap_and_path_limit(self):
        bad = path([node(1, [[]], "construction")], ["N1"], "// WA")      # a key node must be an output rule
        good = path([node(1, [[]], "modeling"), node(2, [["N1"]])], ["N1", "N2"], "// AC")
        script = [("submit_path", bad), ("submit_path", bad), ("submit_path", good),
                  ("finish_exploration", {"reason": "limit", "considered": []})]
        client = ScriptedClient(script)
        with unittest.mock.patch.object(C, "MAX_PATH_ATTEMPTS", 2), contextlib.redirect_stdout(io.StringIO()):
            doc = X.explore_problem(client, "2025/J-stacking-cups",
                                    args(max_paths=1, no_review=True), judge=fake_judge)
        self.assertIn("Abandon it", client.calls[2][1])
        self.assertEqual(len(doc["rejected"]), 1)
        self.assertEqual(doc["rejected"][0]["attempts"], 2)
        self.assertEqual(len(doc["paths"]), 1)
        self.assertIn("limit of 1 paths", client.calls[3][1])
        self.assertEqual(doc["status"], "unreviewed")

    def test_try_path_rules(self):
        ctx = FakeContext("2025/J-stacking-cups")
        state = {"nodes": [], "end_routes": [], "hazards": [], "paths": [], "rejected": [], "considered": [],
                 "finished": False, "reason": "", "submissions": 0}
        kind, problems = X.try_path(state, path([node(1, [[]]), node(2, [["N1"]])], ["N1"], "// AC"), ctx,
                                    self.root / "g", 1, judge=fake_judge)
        self.assertEqual(kind, "rules")
        self.assertTrue(any("N2" in p and "no derivation" in p for p in problems))
        kind, problems = X.try_path(state, path([node(1, [["N7"]])], ["N1"], "// AC"), ctx, self.root / "g", 1,
                                    judge=fake_judge)
        self.assertEqual(kind, "rules")
        kind, _ = X.try_path(state, path([node(1, [[]])], ["N1"], ""), ctx, self.root / "g", 1, judge=fake_judge)
        self.assertEqual(kind, "rules")
        kind, problems = X.try_path(state, path([node(1, [[]]), node(2, [["N1"]])], ["N1", "N2"], "// AC", key_node="N1"),
                                    ctx, self.root / "g", 1, judge=fake_judge)
        self.assertEqual(kind, "rules")                      # N2 is in end_route but the key node N1 does not depend on it
        self.assertTrue(any("does not depend" in p for p in problems))
        kind, p = X.try_path(state, path([node(1, [[]])], ["N1"], "// AC"), ctx, self.root / "g", 1, judge=fake_judge)
        self.assertEqual((kind, p["id"], p["key_node"], state["nodes"][0]["depth"]), ("accepted", "P1", "N1", 1))
        self.assertEqual(state["end_keys"], ["N1"])
        kind, problems = X.try_path(state, path([node(2, [["N1"]])], ["N1", "N2"], "// AC", key_node="N1"), ctx,
                                    self.root / "g", 2, judge=fake_judge)
        self.assertTrue(any("already the key node" in p for p in problems))


def editorial_path(nodes, end_route):
    return {"approach": "Scan the boundary b of the increasing block and build a fixed-cardinality subset; the first "
                        "feasible b contains b.", "nodes": nodes, "end_route": end_route, "key_node": end_route[-1],
            "hazards": [], "notes": ""}


class EditorialTests(Base):
    """The editorial step: added as a path (source editorial) when the reviewer does not find it, skipped when
    found, covered when the integrator says so, and runnable alone on an existing graph."""

    def _client(self, script, review_found, integrator_calls, revise=False):
        client = ScriptedClient(script)

        def create(**kw):
            if client.script and client.script[0][1] is None and client.script[0][0] == "submit_review":
                # the graph under review is in the request (after the editorial step it is newer than graph.json)
                ids = re.findall(r"^(N\d+) ·", kw["input"][0].get("content", ""), re.M)
                doc = {"nodes": [{"id": i} for i in ids]}
                client.script[0] = ("submit_review", review(doc, editorial_found=review_found))
            return ScriptedClient.create(client, **kw)
        client.responses = SimpleNamespace(create=create)
        return client

    def _explore_then(self, after, **kw):
        p1 = path([node(1, [[]], "modeling"), node(2, [["N1"]])], ["N1", "N2"], "// AC")
        script = [("submit_path", p1), ("finish_exploration", {"reason": "done", "considered": []}),
                  ("submit_review", None)] + after
        client = self._client(script, review_found=kw.pop("review_found", False), integrator_calls=after)
        with contextlib.redirect_stdout(io.StringIO()):
            doc = X.explore_problem(client, "2025/J-stacking-cups", args(editorial="missing", **kw),
                                    judge=fake_judge)
        return doc, client

    def test_added_when_missing(self):
        ed = editorial_path([node(3, [["N1"]], "algorithm")], ["N1", "N3"])
        doc, client = self._explore_then([("submit_path", ed), ("submit_review", None)])
        self.assertFalse(doc["editorial"]["covered"])
        self.assertEqual(doc["editorial"]["path"], "P2")
        self.assertEqual([p.get("source") for p in doc["paths"]], [None, "editorial"])   # provenance only
        self.assertEqual(doc["nodes"][2]["source"], "exploration")                     # nodes are not marked
        self.assertEqual(doc["nodes"][2]["path"], "P2")
        self.assertEqual(doc["end"]["routes"], [["N1", "N2"], ["N1", "N3"]])
        self.assertEqual(doc["paths"][1]["judge"]["verdict"], "WA")        # the fake judge; recorded, not required
        self.assertEqual(doc["provenance"]["review_rounds"], 2)
        self.assertEqual(doc["status"], "accepted")
        out = C.GRAPHS_DIR / "2025_J-stacking-cups"
        self.assertEqual((out / "paths" / "P2.cpp").read_text(), FakeContext("x").reference)
        self.assertIn("### P2 ·", (out / "graph.md").read_text())
        dot = (out / "graph.dot").read_text()
        self.assertIn('label="P2"', dot)
        self.assertNotIn("editorial", dot)
        self.assertIn("<graph>", client.calls[3][1])                         # the integrator saw the graph
        self.assertIn("<editorial>", client.calls[3][1])

    def test_covered_or_found(self):
        doc, _ = self._explore_then([("editorial_covered", {"route": ["N1", "N2"], "note": "same construction"})])
        self.assertTrue(doc["editorial"]["covered"])
        self.assertEqual(len(doc["paths"]), 1)
        self.assertEqual(doc["provenance"]["review_rounds"], 1)
        doc, _ = self._explore_then([], review_found=True)
        self.assertTrue(doc["editorial"]["covered"])
        self.assertIn("reviewer", doc["editorial"]["note"])

    def test_editorial_only_on_existing_graph(self):
        doc, _ = self._explore_then([], review_found=True)
        ed = editorial_path([node(3, [["N1"]], "algorithm")], ["N1", "N3"])
        client = self._client([("submit_path", ed), ("submit_review", None)], review_found=True, integrator_calls=[])
        with contextlib.redirect_stdout(io.StringIO()):
            new = X.editorial_problem(client, "wf2025/J-stacking-cups", args(), judge=fake_judge)
        self.assertEqual(new["editorial"]["path"], "P2")
        self.assertEqual(len(new["paths"]), 2)
        self.assertEqual(new["provenance"]["review_rounds"], 2)
        self.assertIn("editorial_step", new["provenance"])
        self.assertNotEqual(new["version"], doc["version"])


if __name__ == "__main__":
    unittest.main()
