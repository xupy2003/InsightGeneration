"""Offline end-to-end checks of the grader with a fake API: rounds, windows, probes, programs, hints,
fallback, cache and the written files."""
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from graph import rules as R  # noqa: E402
from grade import grade as G  # noqa: E402
from grade import probe as P  # noqa: E402
from grade import rounds as Rd  # noqa: E402
from grade import windows as W  # noqa: E402
from grade import programs as Pg  # noqa: E402
import config as C  # noqa: E402
from tests.test_rules import toy  # noqa: E402

GRAPH = {**R.derive(toy()), "problem": "2025/J-stacking-cups", "title": "Stacking Cups", "version": "v1"}
NIDS = [n["id"] for n in GRAPH["nodes"]]
MARKER = "Here are some key insights that can help you solve this problem."


class FakeClient:
    """responses.create answers from the request body: window states from the node ids named in the text
    ("N2 wrong"), hint states from the ids present, program statuses from "// Nk" comments."""

    def __init__(self, fail_with=None, bad_off_graph=False):
        self.responses = self
        self.calls = 0
        self.fail_with = fail_with
        self.bad_off_graph = bad_off_graph      # window answers carry an off_graph claim whose quote is not in the text

    def create(self, **kw):
        if self.fail_with:
            raise self.fail_with
        self.calls += 1
        message = kw["input"][0]["content"]
        name = kw["tools"][0]["name"]
        body, _ = json.JSONDecoder().raw_decode(message, message.index("{"))
        if name == "submit_adjudication":
            trail = body["trail"]
            wrong = [r for r in trail if r["state"] == "wrong"]
            est = [r for r in trail if r["state"] == "established"]
            if any("slip" in (r.get("context") or "") for r in wrong):
                result = {"final": "established" if est else "working",
                          "basis": (est or trail)[0]["where"],
                          "slips": [{"where": r["where"], "why": "The solver's own code contradicts it."} for r in wrong],
                          "reason": "A summary slip; the operative version is right."}
            else:
                result = {"final": "wrong", "basis": wrong[-1]["where"], "slips": [],
                          "reason": "The solver decides on the mistaken rule."}
        elif name == "submit_program":
            code = body["program"]["code"]
            result = {"nodes": [{"node_id": nid, "status": "holds" if f"// {nid}" in code else "not_needed",
                                 "quote": f"// {nid}" if f"// {nid}" in code else "", "reason": f"reason {nid}"}
                                for nid in NIDS],
                      "hazards": [{"hazard_id": h["id"], "status": "tripped" if "int32" in code else "ok",
                                   "quote": "int32" if "int32" in code else "", "reason": "r"}
                                  for h in body["hazards"]]}
        else:
            units = body["window"]["units"]
            hint = units[0]["kind"] == "insight"
            rows = []
            for nid in NIDS:
                state, unit, quote = "absent", None, None
                for u in units:
                    for st in (("established", "working") if hint else ("established", "wrong", "working")):
                        needle = nid if hint else f"{nid} {st}"
                        if needle in u["text"] and (not hint or st == "established"):
                            state, unit, quote = st, u["id"], needle
                            break
                    if state != "absent":
                        break
                rows.append({"node_id": nid, "state": state, "unit_id": unit, "quote": quote,
                             "solver_claim": f"belief about {nid}" if state != "absent" else None})
            result = {"focus": "Looks at the cups.", "nodes": rows}
            if self.bad_off_graph and not hint:
                result["off_graph"] = [
                    {"claim": "A claim the graph lacks.", "unit_id": units[0]["id"], "quote": "not in the text", "wrong": False},
                    {"claim": "A fine claim.", "unit_id": units[0]["id"], "quote": units[0]["text"][:20], "wrong": True}]
        usage = SimpleNamespace(input_tokens=100, output_tokens=10, input_tokens_details=None, output_tokens_details=None)
        call = SimpleNamespace(type="function_call", name=name, arguments=json.dumps(result), call_id="c")
        return SimpleNamespace(id="r", status="completed", usage=usage, output=[call])


class QuotaError(Exception):
    code = "insufficient_quota"


def write_run(root, model, condition, n, rounds_text, subs, solved, hint=None):
    d = root / "runs" / model / condition
    d.mkdir(parents=True, exist_ok=True)
    stem = d / f"2025_J-stacking-cups_run{n}"
    prompt = "# Problem: Stacking Cups\n..." + (f"\n{MARKER}\n{hint}\n" if hint else "")
    records = [{"round": 0, "problem": "wf2025/J-stacking-cups", "prompt": prompt, "insight": bool(hint)}]
    for i, text in enumerate(rounds_text, 1):
        subs_here = [s for s in subs if s["round"] == i]
        records.append({"round": i, "assistant_raw": text + "</think>\nSubmitting now.",
                        "tool_calls": [{"name": "submit"} for _ in subs_here],
                        "tool_results": [{"name": "submit", "ok": True, "content": s["verdict"]} for s in subs_here],
                        "finish_reason": "stop"})
    Path(f"{stem}_transcript.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    Path(f"{stem}_submissions.jsonl").write_text("".join(json.dumps(s) + "\n" for s in subs))
    Path(f"{stem}_summary.json").write_text(json.dumps(
        {"problem": "wf2025/J-stacking-cups", "solved": solved, "model": "Qwen3.6-35B-A3B" if model == "qwen"
         else "Nemotron-Cascade-2-30B-A3B", "insight": bool(hint), "num_submissions": len(subs),
         "stop_reason": "solved" if solved else "time_budget"}))
    return f"{stem}_transcript.jsonl"


def sub(i, rnd, verdict, code):
    return {"id": i, "round": rnd, "verdict": verdict, "accepted": verdict == "AC", "approach": "a", "code": code}


class GradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.graph_path = self.root / "graph.json"
        self.graph_path.write_text(json.dumps(GRAPH))
        long = " filler" * 30
        self.ac = write_run(self.root, "qwen", "baseline", 1,
                            [f"N1 wrong.{long}", f"N1 established. N2 established. N3 established. N5 established.{long}"],
                            [sub(1, 1, "WA", "// N1\nint main(){}"), sub(2, 2, "AC", "// N1 // N2 // N3 // N5\nint main(){}")],
                            True)
        self.fail_run = write_run(self.root, "qwen", "baseline", 2,
                              [f"N1 working.{long}", f"N1 established. N2 wrong.{long}"],
                              [sub(1, 2, "WA", "// N1\nint32 main(){}")], False)
        self.hint = write_run(self.root, "nemotron", "insight", 1, [f"N1 established.{long}"],
                              [sub(1, 1, "AC", "// N1 // N5\nint main(){}")], True, hint="Use N5 and N2.")
        self.fallback = write_run(self.root, "nemotron", "baseline", 3, [f"N1 wrong.{long}", f"nothing here{long}"],
                                  [], False)

    def test_rounds_windows_programs(self):
        rounds = Rd.read_rounds(self.ac)
        self.assertEqual([r["round"] for r in rounds], [1, 2])
        self.assertEqual(rounds[1]["submits"], 1)
        sel = Rd.select(rounds, first=True, min_chars=10)
        self.assertEqual((sel["last"], sel["first"], sel["fallback"], sel["tail"]), (2, 1, 1, []))
        self.assertEqual(Rd.select(rounds, first=False, min_chars=10)["first"], None)
        self.assertEqual(Rd.insight_text(self.ac), "")
        self.assertEqual(Rd.insight_text(self.hint), "Use N5 and N2.")
        wins = W.round_windows(self.ac, 2)
        self.assertEqual(len(wins), 1)
        self.assertEqual(wins[0]["rounds"], [2])
        self.assertTrue(wins[0]["id"].startswith("R2W"))
        self.assertTrue(all(u["round"] == 2 for u in wins[0]["units"]))
        subs = Pg.submissions(self.ac)
        picks = Pg.select(subs, {2})
        self.assertEqual([(p["id"], p["role"]) for p in picks], [(2, "final")])
        picks = Pg.select([sub(1, 1, "WA", "a"), sub(2, 2, "AC", "b"), sub(3, 3, "WA", "c")], {2})
        self.assertEqual([(p["id"], p["role"]) for p in picks], [(2, "accepted"), (3, "final")])

    def test_check_window_and_program(self):
        window = W.round_windows(self.fail_run, 2)[0]
        unit = window["units"][0]
        good = {"focus": "f", "nodes": [{"node_id": nid, "state": "absent", "unit_id": None, "quote": None,
                                          "solver_claim": None} for nid in NIDS]}
        good["nodes"][0].update(state="established", unit_id=unit["id"], quote="N1 established", solver_claim="c")
        self.assertEqual(P.check_window(good, window, NIDS), [])
        bad = json.loads(json.dumps(good))
        bad["nodes"][0]["quote"] = "not in the window"
        bad["nodes"][1]["quote"] = "x"
        self.assertTrue(any("copied exactly" in e for e in P.check_window(bad, window, NIDS)))
        self.assertTrue(any("absent node" in e for e in P.check_window(bad, window, NIDS)))
        self.assertTrue(any("missing nodes" in e for e in P.check_window({"focus": "f", "nodes": good["nodes"][:2]},
                                                                           window, NIDS)))
        self.assertTrue(any("one of" in e for e in P.check_window(good, window, NIDS, ("absent",))))
        # off_graph: quotes checked like node rows; a missing field means none
        withoff = json.loads(json.dumps(good))
        withoff["off_graph"] = [{"claim": "The cups always nest.", "unit_id": unit["id"], "quote": "N1 established",
                                 "wrong": True}]
        self.assertEqual(P.check_window(withoff, window, NIDS), [])
        withoff["off_graph"][0]["quote"] = "not there"
        self.assertTrue(any("off_graph 1: quote" in e for e in P.check_window(withoff, window, NIDS)))
        withoff["off_graph"] = [dict(withoff["off_graph"][0], quote="N1 established")] * (C.OFF_GRAPH_PER_WINDOW + 1)
        self.assertTrue(any("at most" in e for e in P.check_window(withoff, window, NIDS)))
        prog = {"id": 1, "code": "// N1\nint main(){}", "verdict": "WA"}
        ans = {"nodes": [{"node_id": nid, "status": "holds" if nid == "N1" else "not_needed",
                          "quote": "// N1" if nid == "N1" else "", "reason": "r"} for nid in NIDS],
               "hazards": [{"hazard_id": "H1", "status": "ok", "quote": "", "reason": "r"}]}
        self.assertEqual(P.check_program(ans, prog, NIDS, ["H1"]), [])
        ans["nodes"][0]["quote"] = "// N9"
        ans["hazards"][0]["status"] = "tripped"
        errors = P.check_program(ans, prog, NIDS, ["H1"])
        self.assertTrue(any("N1: the quote" in e for e in errors))
        self.assertTrue(any("H1: tripped needs a quote" in e for e in errors))

    def test_check_adjudication(self):
        trail = [{"where": "R2W01", "state": "established"}, {"where": "R2W02", "state": "wrong"},
                 {"where": "R2W03", "state": "wrong"}]
        ok = {"final": "established", "basis": "R2W01", "reason": "r.",
              "slips": [{"where": "R2W02", "why": "w."}, {"where": "R2W03", "why": "w."}]}
        self.assertEqual(P.check_adjudication(ok, trail), [])
        self.assertEqual(P.check_adjudication({"final": "wrong", "basis": "R2W03", "reason": "r.",
                                               "slips": [{"where": "R2W02", "why": "w."}]}, trail), [])
        self.assertEqual(P.check_adjudication({"final": "working", "basis": "R2W02", "reason": "r.",
                                               "slips": ok["slips"]}, trail), [])
        self.assertTrue(P.check_adjudication({**ok, "slips": ok["slips"][:1]}, trail))       # a standing wrong passage
        self.assertTrue(P.check_adjudication({**ok, "final": "wrong"}, trail))               # wrong needs one standing
        self.assertTrue(P.check_adjudication({**ok, "basis": "R2W02"}, trail))               # established basis
        self.assertTrue(P.check_adjudication({**ok, "basis": "R9W09"}, trail))               # unknown where
        self.assertTrue(P.check_adjudication({**ok, "slips": ok["slips"] + [{"where": "R2W01", "why": "w."}]}, trail))
        self.assertTrue(P.check_adjudication({**ok, "slips": ok["slips"] + ok["slips"][:1]}, trail))   # twice
        self.assertTrue(P.check_adjudication({**ok, "reason": ""}, trail))

    def test_adjudication(self):
        long = " filler" * 30
        # the last window states N2 wrong in a summary its own code contradicts (a slip to the fake adjudicator)
        write_run(self.root, "qwen", "baseline", 7,
                  ["N1 established" + long, "N1 established N5 established N2 wrong slip" + long],
                  [sub(1, 2, "AC", "int main(){} // N1 // N5")], True)
        # the last window decides on the wrong rule: stays wrong
        write_run(self.root, "qwen", "baseline", 8,
                  ["N1 established" + long, "N1 established N2 wrong" + long],
                  [sub(1, 2, "WA", "int main(){} // N1")], False)
        out = self.root / "adj"
        client = FakeClient()
        with contextlib.redirect_stdout(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs",
                           str(self.root / "runs" / "qwen" / "baseline" / "*_run[78]_transcript.jsonl"),
                           "--out", str(out), "--min-round-chars", "10"], client=client)
        self.assertEqual(code, 0)
        records = {r["label"]: r for r in map(json.loads, (out / "runs.jsonl").read_text().splitlines())}
        slip = records["runs/qwen/baseline/run7"]
        self.assertEqual(slip["results"]["N2"]["window_final"], "wrong")
        self.assertEqual(slip["results"]["N2"]["final"], "working")           # no passage judged established
        self.assertEqual(slip["results"]["N2"]["trajectory"], "x")
        self.assertEqual(slip["results"]["N2"]["claims"][0]["slip"], "The solver's own code contradicts it.")
        self.assertEqual(slip["adjudicated"], {"N2": "working"})
        self.assertNotIn("N2", slip["roots"])
        self.assertEqual(slip["class"], "END+AC")
        kept = records["runs/qwen/baseline/run8"]
        self.assertEqual(kept["results"]["N2"]["final"], "wrong")
        self.assertEqual(kept["adjudicated"], {"N2": "wrong"})
        self.assertEqual(kept["class"], "noEND+fail/stuck:N2")
        doc = json.loads((out / "grade.json").read_text())
        self.assertTrue(doc["adjudicate"])
        self.assertEqual(doc["adjudicated"], 2)
        self.assertEqual(doc["summary"]["adjudicated"], {"working": 1, "wrong": 1})
        report = (out / "report.md").read_text()
        self.assertIn("## Adjudicated nodes", report)
        self.assertIn("`x` ⇒ `~`", report)
        # cached: a second grading makes no request; --no-adjudicate leaves the window fold
        again = FakeClient(fail_with=QuotaError("insufficient_quota"))
        with contextlib.redirect_stdout(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs",
                           str(self.root / "runs" / "qwen" / "baseline" / "*_run[78]_transcript.jsonl"),
                           "--out", str(out), "--min-round-chars", "10"], client=again)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((out / "grade.json").read_text())["requests"], 0)
        with contextlib.redirect_stdout(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs",
                           str(self.root / "runs" / "qwen" / "baseline" / "*_run[78]_transcript.jsonl"),
                           "--out", str(self.root / "adj2"), "--cache", str(out / "cache"),
                           "--min-round-chars", "10", "--no-adjudicate"], client=again)
        self.assertEqual(code, 0)
        plain = {r["label"]: r for r in map(json.loads, (self.root / "adj2" / "runs.jsonl").read_text().splitlines())}
        self.assertEqual(plain["runs/qwen/baseline/run7"]["results"]["N2"]["final"], "wrong")
        self.assertEqual(plain["runs/qwen/baseline/run7"]["adjudicated"], {})

    def test_tail_round(self):
        # the key node N5 is wrong in the last substantive round and corrected in a short final round (the AC one)
        long = " filler" * 30
        trace = write_run(self.root, "qwen", "baseline", 9,
                          ["N1 established" + long, "N1 established N2 established N3 established N5 wrong" + long,
                           "N5 established"],
                          [sub(1, 3, "AC", "int main(){} // N1 // N2 // N3 // N5")], True)
        rounds = Rd.read_rounds(trace)
        sel = Rd.select(rounds, min_chars=100)
        self.assertEqual((sel["last"], sel["fallback"], sel["tail"]), (2, 1, [3]))
        plan = G.plan_run(trace, False, 100, blind=True)
        self.assertEqual(sorted(plan["windows"]), [2, 3])
        self.assertEqual(G.rounds_order(plan), [2, 3])
        self.assertEqual(G.plan_run(trace, False, 100, tail=False)["selection"]["tail"], [3])   # known, not read
        self.assertEqual(sorted(G.plan_run(trace, False, 100, tail=False)["windows"]), [2])
        # the run's end for the adjudicator spans the short last window and the end of the one before it
        w2, w3 = plan["windows"][2][0], plan["windows"][3][0]
        answers = {w["id"]: {"focus": "f", "nodes": [{"node_id": "N5", "state": st, "unit_id": w["units"][0]["id"],
                                                      "quote": q, "solver_claim": "c"}]}
                   for w, st, q in ((w2, "wrong", "N5 wrong"), (w3, "established", "N5 established"))}
        trail, wins, final = G.trail_of(plan, answers, [2, 3], "N5")
        self.assertEqual([(t["where"], t["state"]) for t in trail], [(w2["id"], "wrong"), (w3["id"], "established")])
        self.assertEqual(final["where"], f"{w2['id']}..{w3['id']}")
        self.assertTrue(final["text"].endswith("Submitting now."))
        self.assertIn("N5 wrong", final["text"])
        self.assertIn("N5 established", final["text"])
        out = self.root / "tail"
        with contextlib.redirect_stdout(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs", trace, "--out", str(out),
                           "--min-round-chars", "100"], client=FakeClient())
        self.assertEqual(code, 0)
        rec = json.loads((out / "runs.jsonl").read_text().splitlines()[0])
        self.assertEqual(rec["rounds_read"], [2, 3])
        self.assertEqual(rec["windows_read"], [w2["id"], w3["id"]])
        self.assertEqual(rec["results"]["N5"]["trajectory"], "x+")
        self.assertEqual(rec["results"]["N5"]["final"], "established")
        self.assertEqual(rec["adjudicated"], {})
        self.assertEqual(rec["class"], "END+AC")
        self.assertTrue(json.loads((out / "grade.json").read_text())["tail"])
        with contextlib.redirect_stdout(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs", trace, "--out", str(self.root / "notail"),
                           "--min-round-chars", "100", "--no-tail"], client=FakeClient())
        self.assertEqual(code, 0)
        rec = json.loads((self.root / "notail" / "runs.jsonl").read_text().splitlines()[0])
        self.assertEqual(rec["rounds_read"], [2])
        self.assertEqual(rec["results"]["N5"]["final"], "wrong")       # the fix in round 3 is not seen
        self.assertEqual(rec["adjudicated"], {"N5": "wrong"})
        self.assertEqual(rec["class"], "noEND+AC")

    def test_salvage_off_graph(self):
        window = W.round_windows(self.ac, 2)[0]
        unit = window["units"][0]
        rows = [{"node_id": nid, "state": "absent", "unit_id": None, "quote": None, "solver_claim": None} for nid in NIDS]
        fine = {"claim": "A fine claim.", "unit_id": unit["id"], "quote": unit["text"][:20], "wrong": False}
        bad = dict(fine, quote="not in the text")
        answer = {"focus": "f", "nodes": rows, "off_graph": [bad, fine, dict(bad, unit_id="nope")]}
        fixed = P.salvage_window(answer, window, NIDS)
        self.assertEqual(fixed["off_graph"], [fine])
        self.assertEqual(fixed["off_graph_dropped"], 2)
        self.assertEqual(P.check_window(fixed, window, NIDS), [])
        self.assertIs(P.salvage_window(dict(answer, off_graph=[fine]), window, NIDS)["off_graph"][0], fine)
        self.assertIsNone(P.salvage_window(dict(answer, focus=None), window, NIDS))      # a node-side fault: no salvage
        self.assertIsNone(P.salvage_window(dict(answer, nodes=rows[1:]), window, NIDS))
        # end to end: every window answer carries a bad off_graph quote; after ATTEMPTS answers the window is
        # kept without it instead of being discarded
        out = self.root / "salvage"
        client = FakeClient(bad_off_graph=True)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs", self.ac, "--out", str(out),
                           "--min-round-chars", "10"], client=client)
        self.assertEqual(code, 0)
        rec = json.loads((out / "runs.jsonl").read_text().splitlines()[0])
        self.assertEqual(rec["windows_read"], ["R2W01"])
        self.assertEqual(rec["windows_unread"], [])
        self.assertEqual(rec["windows_salvaged"], ["R2W01"])
        self.assertEqual([x["claim"] for x in rec["off_graph"]], ["A fine claim."])
        self.assertEqual(rec["class"], "END+AC")
        self.assertEqual(client.calls, C.ATTEMPTS + 1)                 # the window ATTEMPTS times, the program once
        doc = json.loads((out / "grade.json").read_text())
        self.assertTrue(any("off_graph claims whose quotes failed" in w for w in doc["warnings"]))
        # the salvaged answer is cached: a regrade asks nothing
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs", self.ac, "--out", str(out),
                           "--min-round-chars", "10"], client=FakeClient(fail_with=QuotaError("insufficient_quota")))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((out / "grade.json").read_text())["requests"], 0)

    def test_end_to_end(self):
        out = self.root / "out"
        client = FakeClient()
        with contextlib.redirect_stdout(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs", str(self.root / "runs" / "*" / "*" / "*_transcript.jsonl"),
                           "--out", str(out), "--min-round-chars", "10", "--first-round"], client=client)
        self.assertEqual(code, 0)
        records = {r["label"]: r for r in map(json.loads, (out / "runs.jsonl").read_text().splitlines())}
        ac = records["runs/qwen/baseline/run1"]
        self.assertEqual(ac["rounds_read"], [1, 2])
        self.assertEqual(ac["class"], "END+AC")
        self.assertEqual(ac["established"], ["N1", "N2", "N3", "N5"])
        self.assertEqual(ac["results"]["N1"]["trajectory"], "x+")      # round 1 window, round 2 window; no program column
        self.assertTrue(ac["derived_end"])
        self.assertEqual(ac["implemented"]["N5"]["status"], "holds")
        self.assertEqual(ac["implemented"]["N4"]["status"], "not_needed")
        self.assertEqual([c["kind"] for c in ac["checkpoints"]], ["window", "window"])
        self.assertEqual([p["role"] for p in ac["programs"]], ["final"])
        self.assertEqual(ac["model"], "qwen")
        fail = records["runs/qwen/baseline/run2"]
        self.assertEqual(fail["class"], "noEND+fail/stuck:N2")
        self.assertEqual(fail["root"], "N2")
        self.assertEqual(fail["frontier"], ["N2", "N3"])
        self.assertEqual(fail["hazards_tripped"], ["H1"])           # tripped, but END not reached: still stuck
        hint = records["runs/nemotron/insight/run1"]
        self.assertEqual(hint["given"], ["N2", "N5"])
        self.assertEqual(hint["class"], "noEND+AC")                   # the hint states N5, the text never does: hint-carried
        self.assertEqual(hint["established"], ["N1"])
        self.assertEqual(hint["unsupported"], [])
        self.assertTrue(hint["insight"])
        fb = records["runs/nemotron/baseline/run3"]
        self.assertEqual(fb["rounds_read"], [1, 2])                  # first round, then the last (no fallback: round 1 is first)
        self.assertEqual(fb["class"], "noEND+fail/stuck:N1")
        doc = json.loads((out / "grade.json").read_text())
        self.assertEqual(doc["summary"]["classes"]["END+AC"], 1)
        self.assertEqual(doc["summary"]["classes"]["noEND+AC"], 1)
        self.assertTrue(doc["blind"])                                   # blind is the default
        self.assertIn("## Runs", (out / "report.md").read_text())
        # a second grading uses the cache only
        again = FakeClient(fail_with=QuotaError("insufficient_quota"))
        with contextlib.redirect_stdout(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs", str(self.root / "runs" / "*" / "*" / "*_transcript.jsonl"),
                           "--out", str(out), "--min-round-chars", "10", "--first-round"], client=again)
        self.assertEqual(code, 0)
        doc = json.loads((out / "grade.json").read_text())
        self.assertEqual(doc["requests"], 0)
        self.assertGreater(doc["cache_hits"], 0)

    def test_blind(self):
        """--blind: no tool results in the windows, no verdict to the program probe, nothing about verdicts
        in the instructions; the requests never carry a verdict."""
        sighted = {u["kind"] for w in W.round_windows(self.ac, 2) for u in w["units"]}
        blind = {u["kind"] for w in W.round_windows(self.ac, 2, blind=True) for u in w["units"]}
        self.assertIn("tool_result", sighted)
        self.assertEqual(blind, {"reasoning", "reply"})
        prog = {"id": 1, "code": "x", "verdict": "WA", "round": 1}
        self.assertIn("verdict", P.program_payload(GRAPH, prog)["program"])
        self.assertNotIn("verdict", P.program_payload(GRAPH, prog, blind=True)["program"])
        self.assertNotIn("verdict", P.WINDOW_INSTRUCTIONS_BLIND)
        self.assertIn("withheld", P.PROGRAM_INSTRUCTIONS_BLIND)
        self.assertNotIn("not accepted, not where", P.PROGRAM_INSTRUCTIONS_BLIND)

        class Spy(FakeClient):
            def __init__(self):
                super().__init__()
                self.seen = []

            def create(self, **kw):
                self.seen.append(kw["instructions"] + kw["input"][0]["content"])
                return super().create(**kw)

        out, client = self.root / "out_blind", Spy()
        with contextlib.redirect_stdout(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs", self.ac, self.fail_run, "--out", str(out),
                           "--blind", "--min-round-chars", "10"], client=client)
        self.assertEqual(code, 0)
        self.assertTrue(client.seen)
        leaks = [m.group(0) for s in client.seen for m in re.finditer(r"\b(WA|AC)\b|not accepted, not where", s)]
        self.assertEqual(leaks, [])
        doc = json.loads((out / "grade.json").read_text())
        self.assertTrue(doc["blind"])
        recs = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines()]
        self.assertEqual([r["blind"] for r in recs], [True, True])
        self.assertEqual({r["label"]: r["class"] for r in recs},
                         {"runs/qwen/baseline/run1": "END+AC", "runs/qwen/baseline/run2": "noEND+fail/stuck:N2"})
        self.assertIn("Blind", (out / "report.md").read_text())

    def test_fallback_round(self):
        out = self.root / "out2"
        with contextlib.redirect_stdout(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs", self.fallback, "--out", str(out),
                           "--min-round-chars", "10"], client=FakeClient())
        self.assertEqual(code, 0)
        rec = json.loads((out / "runs.jsonl").read_text().splitlines()[0])
        self.assertEqual(rec["rounds_read"], [1, 2])                  # fallback round 1 read before the last
        self.assertEqual(rec["class"], "noEND+fail/stuck:N1")

    def test_dry_run_and_quota(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = G.main(["--graph", str(self.graph_path), "--runs", self.ac, "--dry-run", "--min-round-chars", "10"])
        self.assertEqual(code, 0)
        self.assertIn("probe calls", buf.getvalue())
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = G.main(["--graph", str(self.graph_path), "--runs", self.ac, "--out", str(self.root / "out3"),
                           "--min-round-chars", "10"], client=FakeClient(fail_with=QuotaError("insufficient_quota")))
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
