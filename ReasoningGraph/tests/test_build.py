"""Offline checks of the old editorial-based builder loop with a scripted fake API: rules send a graph back,
the reviewer's blocking findings cause a revision, the files are written."""
import contextlib
import io
import json
import logging
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from graph import build as B  # noqa: E402
from graph import rules as R  # noqa: E402
from tests.test_rules import toy, STATEMENT, REFERENCE  # noqa: E402


class FakeContext:
    def __init__(self, problem):
        self.problem, self.title = problem, "Stacking Cups"
        self.statement, self.editorial, self.reference = STATEMENT, "Model, bound, construct.", REFERENCE

    def message(self):
        return (f"<problem>\n{self.statement}\n</problem>\n\n<editorial>\n{self.editorial}\n</editorial>\n\n"
                f"<reference_solution>\n```cpp\n{self.reference.rstrip()}\n```\n</reference_solution>")

    def hashes(self):
        return {"statement": "s", "editorial": "e", "reference": "r"}


def review_answer(nodes, bad=(), alternatives=None, missing=()):
    return {"nodes": [{"id": n["id"], **{f: n["id"] not in bad for f in B.NODE_FLAGS},
                       "note": "wrong route" if n["id"] in bad else ""} for n in nodes],
            "end_ok": True, "end_note": "", "hazards_ok": True, "hazards_note": "", "missing": list(missing),
            "alternatives": alternatives or [{"approach": "Greedy from the largest cup.", "correct_and_fast": True,
                                              "representable": True, "note": "goes through N4"}],
            "order": "", "verdict": "accept" if not bad and not missing else "revise"}


class ScriptedClient:
    """responses.create returns the next scripted answer for the requested tool."""

    def __init__(self, script):
        self.script, self.calls, self.responses = {k: list(v) for k, v in script.items()}, [], self

    def create(self, **kw):
        name = kw["tools"][0]["name"]
        first = kw["input"][0]
        self.calls.append((name, kw.get("previous_response_id"), first.get("type", "message"),
                           first.get("output") or first.get("content") or ""))
        result = self.script[name].pop(0)
        usage = SimpleNamespace(input_tokens=100, output_tokens=10, input_tokens_details=None, output_tokens_details=None)
        call = SimpleNamespace(type="function_call", name=name, arguments=json.dumps(result), call_id=f"c{len(self.calls)}",
                               model_dump=lambda: {"type": "function_call"})
        return SimpleNamespace(id=f"r{len(self.calls)}", status="completed", usage=usage, output=[call])


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patches = [unittest.mock.patch.object(C, "GRAPHS_DIR", self.root / "graphs"),
                   unittest.mock.patch.object(B, "ProblemContext", FakeContext)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def test_classify(self):
        g = R.derive(toy())
        blocking, advisory = B.classify(review_answer(g["nodes"], bad=("N2",)), g)
        self.assertEqual(len(blocking), 1)
        self.assertIn("N2 (", blocking[0])
        rev = review_answer(g["nodes"], alternatives=[{"approach": "DP over cups", "correct_and_fast": True,
                                                       "representable": False, "note": "lacks the DP claim"}])
        blocking, advisory = B.classify(rev, g)
        self.assertTrue(blocking and blocking[0].startswith("missing route"))
        rev["alternatives"][0]["correct_and_fast"] = False
        self.assertEqual(B.classify(rev, g)[0], [])

    def test_build_loop(self):
        good = toy()
        short = toy()
        short["nodes"] = short["nodes"][:3]           # breaks the node count rule: sent back by the rules
        short["end"]["routes"] = [["N3"]]
        g = R.derive(good)
        client = ScriptedClient({
            "submit_graph": [short, good, good],
            "submit_review": [review_answer(g["nodes"], bad=("N2",)), review_answer(g["nodes"])]})
        args = SimpleNamespace(gen_effort="high", audit_effort="high", max_revisions=3, max_nodes=None)
        with contextlib.redirect_stdout(io.StringIO()):
            doc = B.build_problem(client, "wf2025/J-stacking-cups", args)
        self.assertEqual(doc["status"], "accepted")
        self.assertEqual(doc["problem"], "2025/J-stacking-cups")
        self.assertEqual(doc["provenance"]["builder_submissions"], 3)
        self.assertEqual(doc["provenance"]["review_rounds"], 2)
        out = C.GRAPHS_DIR / "2025_J-stacking-cups"
        for name in ("graph.json", "review.json", "graph.md", "graph.dot", "sessions.jsonl"):
            self.assertTrue((out / name).exists(), name)
        self.assertTrue((out / "history" / f"graph_{doc['version']}.json").exists())
        kinds = [c[0] for c in client.calls]
        self.assertEqual(kinds[:2], ["submit_graph", "submit_graph"])          # rules sent the short graph back
        self.assertEqual(client.calls[1][2], "function_call_output")
        self.assertIn("Not accepted", client.calls[1][3])
        md = (out / "graph.md").read_text()
        self.assertIn("END", md)
        self.assertIn("H1", md)

    def test_revise_from_feedback(self):
        good = toy()
        g = R.derive(good)
        client = ScriptedClient({"submit_graph": [good], "submit_review": [review_answer(g["nodes"])]})
        args = SimpleNamespace(gen_effort="high", audit_effort="high", max_revisions=3, max_nodes=None)
        with contextlib.redirect_stdout(io.StringIO()):
            B.build_problem(client, "2025/J-stacking-cups", args)
        out = C.GRAPHS_DIR / "2025_J-stacking-cups"
        doc = json.loads((out / "graph.json").read_text())
        doc["nodes"][1]["traps"] = ["the cup rests on the previous cup only"]
        (out / "graph.json").write_text(json.dumps(doc))
        fb = self.root / "feedback.json"
        fb.write_text(json.dumps({"graph_version": doc["version"], "blocking": ["accepted run x reaches no END route"],
                                  "advisory": ["merge N3"]}))
        client = ScriptedClient({"submit_graph": [good], "submit_review": [review_answer(g["nodes"])]})
        args.revise_from = fb
        with contextlib.redirect_stdout(io.StringIO()):
            new = B.revise_problem(client, "2025/J-stacking-cups", args)
        self.assertEqual(new["status"], "accepted")
        self.assertEqual(new["provenance"]["revised_from"]["graph_version"], doc["version"])
        self.assertEqual(new["nodes"][1]["traps"], ["the cup rests on the previous cup only"])   # traps kept
        self.assertEqual(len(json.loads((out / "review.json").read_text())), 2)
        self.assertIn("<findings>", client.calls[0][3])


if __name__ == "__main__":
    unittest.main()
