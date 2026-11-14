"""Offline checks of the validation metrics, suggestions, agreement and files."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from graph import rules as R  # noqa: E402
from grade import closure as Cl  # noqa: E402
from validate import validate as V  # noqa: E402
from tests.test_closure import cp  # noqa: E402
from tests.test_rules import toy  # noqa: E402

GRAPH = {**R.derive(toy()), "problem": "2025/J-stacking-cups", "title": "Stacking Cups", "version": "v1"}


def record(label, model, condition, solved, checkpoints, given=(), tripped=(), insight=False):
    s = Cl.summarize(GRAPH, checkpoints, list(given), solved, list(tripped))
    return {"label": label, "model": model, "condition": condition, "solved": solved, "insight": insight,
            "graph_version": "v1", "programs": [{"id": 1, "role": "final"}], **s}


def cohort():
    held_all = {"N1": "established", "N2": "established", "N3": "established", "N5": "established"}
    runs = [record(f"ac{i}", "qwen", "baseline", True, [cp("W", held_all)]) for i in range(3)]
    runs.append(record("ac_noend", "qwen", "baseline", True,
                       [cp("W", {"N1": "established", "N2": "established", "N3": "established"})]))
    for i in range(3):
        claims = {"N1": "established", "N2": "wrong", "N3": "established"}
        r = record(f"fail{i}", "qwen", "baseline", False, [cp("W", claims)])
        r["results"]["N2"]["claims"][0]["claim"] = f"belief {i % 2}"       # two distinct mistaken beliefs
        runs.append(r)
    runs.append(record("fail_end", "nemotron", "baseline", False, [cp("W", held_all)]))
    runs.append(record("fail_hazard", "nemotron", "baseline", False, [cp("W", held_all)], tripped=["H1"]))
    runs.append(record("stalled", "nemotron", "baseline", False, [cp("W", {})]))
    return runs


class ValidateTests(unittest.TestCase):
    def test_metrics(self):
        m = V.metrics(cohort())
        self.assertEqual((m["ac"], m["fail"]), (4, 6))
        self.assertEqual(m["soundness"], 0.75)
        self.assertEqual(m["unsound_runs"], ["ac_noend"])
        self.assertEqual(m["discrimination"], round(5 / 6, 3))
        self.assertEqual(m["residual_runs"], ["fail_end"])
        self.assertEqual(m["localization"]["qwen/baseline"]["top"], "N2")
        self.assertEqual(m["localization"]["qwen/baseline"]["top_share"], 1.0)
        self.assertEqual(m["localization"]["nemotron/baseline"]["stalled"], 3)

    def test_node_stats_and_suggestions(self):
        runs = cohort()
        stats = V.node_stats(runs, GRAPH)
        self.assertEqual(stats["N2"]["stuck_runs"], 3)
        self.assertEqual(stats["N2"]["distinct_claims"], 2)
        self.assertEqual(stats["N3"]["held_ac"], 4)
        self.assertEqual(stats["N4"]["held_ac"], 0)
        blocking, advisory, traps, off = V.suggestions(runs, GRAPH, stats)
        self.assertEqual(off, [])
        self.assertEqual(len(blocking), 1)
        self.assertIn("ac_noend", blocking[0])
        self.assertTrue(any(a.startswith("split N2") for a in advisory))
        self.assertTrue(any("N4" in a and "nobody walks" in a for a in advisory))
        self.assertTrue(any(a.startswith("merge N3") for a in advisory))   # always held with N1, never stuck
        self.assertEqual(sorted(traps["N2"]), ["belief 0", "belief 1"])

    def test_agreement_and_files(self):
        runs = cohort()
        self.assertEqual(V.agreement(runs, runs, GRAPH)["node_states"], 1.0)
        other = json.loads(json.dumps(runs))
        other[0]["stuck"] = "N4"
        other[0]["results"]["N1"]["final"] = "absent"
        a = V.agreement(runs, other, GRAPH)
        self.assertLess(a["node_states"], 1.0)
        self.assertEqual(a["stuck"], 0.9)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "graph.json").write_text(json.dumps(GRAPH))
            (root / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in runs))
            with contextlib.redirect_stdout(io.StringIO()):
                code = V.main(["--graph", str(root / "graph.json"), "--runs", str(root / "runs.jsonl"),
                               "--out", str(root / "rep"), "--compare", str(root / "runs.jsonl"), "--apply-traps"])
            self.assertEqual(code, 0)
            fb = json.loads((root / "rep" / "feedback.json").read_text())
            self.assertEqual(fb["graph_version"], "v1")
            self.assertEqual(len(fb["blocking"]), 1)
            text = (root / "rep" / "report.md").read_text()
            self.assertIn("soundness", text)
            self.assertIn("Grader agreement", text)
            doc = json.loads((root / "graph.json").read_text())
            self.assertEqual(sorted(doc["nodes"][1]["traps"]), ["belief 0", "belief 1"])


if __name__ == "__main__":
    unittest.main()
