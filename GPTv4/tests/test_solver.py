"""The Slurm adapter's command and the reading of a run, without Slurm."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from adapters import solver_agentv3 as S  # noqa: E402


class TestSolver(unittest.TestCase):
    def test_sbatch_command(self):
        cmd = S.sbatch_command("g4_qwen_2024_G_r1_s1", "80G", {"PROBLEM": "2024/G-kindergarten", "RUN": "1"}, dry=True)
        self.assertEqual(cmd[:2], ["sbatch", "--test-only"])
        self.assertIn("--export=ALL,PROBLEM=2024/G-kindergarten,RUN=1", cmd)
        self.assertEqual(cmd[-1], "contest.sh")
        self.assertIn(f"--partition={C.PARTITION}", cmd)

    def test_read_run(self):
        tmp = Path(tempfile.mkdtemp())
        slug = "2024_G-kindergarten"
        p = S.run_paths(tmp, slug, 2)
        p["summary"].write_text(json.dumps({"solved": True, "num_submissions": 2, "stop_reason": "solved",
                                            "elapsed_seconds": 500.0, "insight": True}))
        rows = [{"round": 0, "prompt": "..."},
                {"round": 1, "completion_tokens": 1000, "tool_calls": [{"name": "run_samples"}]},
                {"round": 2, "completion_tokens": 2500, "tool_calls": [{"name": "submit"}]}]
        p["transcript"].write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        run = S.read_run(tmp, slug, 2)
        self.assertEqual((run["solved"], run["output_tokens"], run["rounds"], run["tokens_to_first_submit"]),
                         (True, 3500, 2, 3500))
        self.assertEqual(S.collect(tmp, slug, range(1, 4))[0]["seed"], 2)
        self.assertEqual(S.done_seeds(tmp, slug, range(1, 4)), [2])
        self.assertEqual(S.job_name("qwen", slug, "r1", 3), "g4_qwen_2024_G_r1_s3")


if __name__ == "__main__":
    unittest.main()
