"""agentv3's sample runner: it runs the statement's samples and nothing else, judges them as the judge
would, and reaches the model through the v3 toolset and prompt.

    cd Solver && WF_ARCHIVE=... python3 -m pytest -q tests/
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
os.environ.setdefault("WF_ARCHIVE", str(HERE.parent / "data" / "ICPC_WF"))
sys.path.insert(0, str(HERE))

import agent_prompt as AP  # noqa: E402
import check_samples as CS  # noqa: E402
import judge as J          # noqa: E402
import problem as PB       # noqa: E402
import tools as T          # noqa: E402

ARCHIVE = Path(os.environ["WF_ARCHIVE"])
FLOAT = "2016/H-polygonal-puzzle"        # real-valued output with a tolerance
CHECKER = "2025/B-blackboard-game"      # any winning first move is accepted: a custom checker


def write(code):
    f = tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False)
    f.write(code)
    f.close()
    return f.name


class SampleRunner(unittest.TestCase):
    def test_reference_passes_its_samples(self):
        for ref in (FLOAT, CHECKER):
            pb = PB.load_problem(ref, root=ARCHIVE)
            res = J.run_samples(pb, pb.reference())
            self.assertIsNone(res["compile_error"], ref)
            self.assertTrue(res["samples"] and all(r["ok"] for r in res["samples"]), (ref, res))
            self.assertTrue(all(r["name"].startswith("sample") for r in res["samples"]))

    def test_a_wrong_program_shows_its_output_and_stderr(self):
        pb = PB.load_problem(FLOAT, root=ARCHIVE)
        src = write('#include <cstdio>\nint main(){ fprintf(stderr, "debug line\\n"); printf("0\\n"); }\n')
        res = J.run_samples(pb, src)
        rows = res["samples"]
        self.assertTrue(rows and not any(r["ok"] for r in rows))
        self.assertEqual(rows[0]["output"].strip(), "0")
        self.assertIn("debug line", rows[0]["stderr"])
        shown = AP.render_samples(res)
        self.assertIn("0/", shown)
        self.assertIn("Expected output:", shown)
        self.assertIn("debug line", shown)

    def test_only_samples_are_ever_read(self):
        pb = PB.load_problem(FLOAT, root=ARCHIVE)
        asked = []
        real = pb.tests

        def tests(which="secret"):
            asked.append(which)
            return real(which)

        pb.tests = tests
        J.run_samples(pb, pb.reference())
        self.assertEqual(asked, ["sample"])

    def test_compile_errors_show_the_first_error(self):
        pb = PB.load_problem(FLOAT, root=ARCHIVE)
        src = write("#include <vector>\nint main(){ undefined_name(1); std::vector<int> v; v.push_back(\"x\"); }\n")
        res = J.run_samples(pb, src)
        self.assertIsNotNone(res["compile_error"])
        shown = AP.render_samples(res)
        self.assertIn("undefined_name", shown.splitlines()[2] + shown.splitlines()[1])   # the first error, near the top
        self.assertLessEqual(len(shown.splitlines()), J.EXCERPT_LINES + 2)


class EngineCheck(unittest.TestCase):
    """check_samples.py, the insight engine's sample check of a failed program."""

    def test_compiled_like_a_submission(self):
        pb = PB.load_problem(FLOAT, root=ARCHIVE)
        res = CS.check(FLOAT, pb.reference().read_text())
        self.assertTrue(res["samples"] and all(r["ok"] for r in res["samples"]))
        # no includes and no namespace: run.py's prelude is added, as for a submission
        res = CS.check(FLOAT, 'int main(){ vector<int> v{1}; cout << v[0] << endl; }\n')
        self.assertIsNone(res["compile_error"])
        self.assertTrue(res["samples"] and not any(r["ok"] for r in res["samples"]))


class Toolset(unittest.TestCase):
    def test_v3_has_run_samples_and_v2_does_not(self):
        self.assertIn("run_samples", T.schema_of(T.TOOLSETS["v3"]))
        self.assertNotIn("run_samples", T.schema_of(T.TOOLSETS["v2"]))
        call = {"name": "run_samples", "arguments": {"code": "int main(){}"}, "error": None}
        ok, reply = T.execute(call, store=None, submit_cb=None, samples_cb=lambda code: f"ran {len(code)}")
        self.assertTrue(ok)
        self.assertEqual(reply, "ran 12")
        ok, reply = T.execute(call, store=None, submit_cb=None)          # a v2 run has no sample runner
        self.assertFalse(ok)

    def test_an_unknown_tool_is_answered_with_the_runs_own_tools(self):
        call = '<tool_call><function=bash><parameter=cmd>ls</parameter></function></tool_call>'
        v3 = T.parse_tool_calls(call, tools=T.TOOLSETS["v3"])[0]["error"]
        v2 = T.parse_tool_calls(call, tools=T.TOOLSETS["v2"])[0]["error"]
        self.assertIn("run_samples", v3)
        self.assertNotIn("no sandbox", v3)
        self.assertIn("no sandbox", v2)

    def test_prompts(self):
        v2, v3 = AP.system_for("v2"), AP.system_for("v3")
        self.assertIn("no compiler you can reach", v2)
        self.assertNotIn("no compiler you can reach", v3)
        self.assertIn("run_samples", v3)
        self.assertIn("debug output to standard output", v3)


if __name__ == "__main__":
    unittest.main()
