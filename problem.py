"""The World Finals archive: one problem, loaded.

The archive is not in Kattis package format -- statements are plain text, the
tests sit in a flat data/ directory, and the limits are printed in the
statement rather than declared in a config file. WFProblem supplies the same
attributes judge.py expects, so the judge needs no archive-specific code.

4 of the 24 problems cannot be graded by comparing output: 3 accept more than
one correct answer and 1 is interactive. Their checkers and interactors live
under <archive>/_verify/ and are named in _verify/judging.json; `mode` carries
that through to the judge.

ARCHIVE_ROOT defaults to data/problems beside this file. _verify/ sits inside
it, so that one variable relocates the whole archive; set WF_ARCHIVE to use
another copy.
"""
import json
import os
import re
from pathlib import Path
from judge import DEFAULT_MEMORY_MB


REPO_ROOT = Path(__file__).resolve().parent
ARCHIVE_ROOT = Path(os.environ.get("WF_ARCHIVE", REPO_ROOT / "data" / "problems"))
VERIFY_ROOT = ARCHIVE_ROOT / "_verify"
CONFIG_PATH = VERIFY_ROOT / "judging.json"
REFERENCE = "solution.cpp"
FALLBACK_TIME_LIMIT = 10.0

_TL_RE = re.compile(r"Time\s+limit:\s*([0-9]+(?:\.[0-9]+)?)\s*second", re.I)

_TOL_RE = re.compile(
    r"((?:absolute|relative)[^.]{0,80}?error)[^.]{0,40}?"
    r"10\s*(?:[-−–]|\^?\{?-)\s*([0-9]+)",
    re.I | re.S,
)

def parse_time_limit(statement: str):
    m = _TL_RE.search(statement)
    return float(m.group(1)) if m else None

def parse_float_tolerance(statement: str):
    """-> (flag_name, 1e-k) if the statement grants an error tolerance, else None.

    Getting this wrong is silent and total: judged as an exact diff, every
    correct answer to a geometry problem is scored wrong. The kind matters too
    -- a statement that promises only an *absolute* tolerance is not judged
    leniently on large answers, so it is read off the same sentence rather than
    assumed.
    """
    m = _TOL_RE.search(statement)
    if not m:
        return None
    phrase = m.group(1).lower()
    tol = float(f"1e-{m.group(2)}")
    has_abs, has_rel = "absolute" in phrase, "relative" in phrase
    if has_abs and has_rel:
        return "float_tolerance", tol
    if has_rel:
        return "float_relative_tolerance", tol
    return "float_absolute_tolerance", tol

def _natural_key(path: Path):
    """secret-2 before secret-10, and samples before secret."""
    stem = path.stem
    group = 0 if stem.startswith("sample") else 1
    parts = [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", stem)]
    return (group, parts)

class WFProblem:
    """Duck-types icpc_eval.Problem over the flat World Finals layout.

    icpc_eval's runner reads `.dir`, `.contest`, `.name`, `.title`, `.mode`,
    `.interactive`, `.custom`, `.validator_dir`, `.validator_flags`,
    `.time_limit`, `.memory_mb`, `.yaml` and `.tests()`; that is the whole
    contract, so nothing in the shared runner needs to change.
    """

    def __init__(self, path, config=None):
        self.dir = Path(path).resolve()
        if not self.dir.is_dir():
            raise FileNotFoundError(f"no such problem dir: {self.dir}")
        self.year = self.dir.parent.name
        self.contest = f"wf{self.year}"
        self.name = self.dir.name
        self.letter = self.name.split("-", 1)[0]
        self.key = f"{self.year}/{self.letter}"
        self.yaml = {}

        meta_path = self.dir / "meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
        self.title = meta.get("title") or self.name

        statement_path = self.dir / "statement.txt"
        statement = statement_path.read_text(errors="replace") if statement_path.is_file() else ""

        cfg = (config or {}).get(self.key, {})
        self.config = cfg

        self.time_limit = float(cfg.get("time_limit_s")
                                or parse_time_limit(statement)
                                or FALLBACK_TIME_LIMIT)
        self.memory_mb = int(cfg.get("memory_mb") or DEFAULT_MEMORY_MB)

        parsed_tol = parse_float_tolerance(statement)

        mode = cfg.get("mode")
        if mode is None:
            mode = "float" if parsed_tol else "exact"
        self.judging_mode = mode
        self.interactive = (mode == "interactive")

        # Validator flags only matter for the built-in comparator. A custom
        # checker or an interactor gets its own argv and ignores them.
        if cfg.get("tolerance") is not None:
            tol_flag = cfg.get("tolerance_kind", "float_tolerance")
            tol = float(cfg["tolerance"])
        elif mode == "float":
            tol_flag, tol = parsed_tol or ("float_tolerance", 1e-6)
        else:
            tol_flag, tol = None, None
        self.tolerance = tol
        self.validator_flags = f"{tol_flag} {tol:g}" if tol else None

        self.validator_dir = self._judge_dir()
        self.custom = self.validator_dir is not None and not self.interactive
        # A problem that needs a judge and has none is a hard error at run time,
        # never silently demoted to a comparison: an interactive problem judged
        # that way would "pass" a submission by diffing its query stream against
        # the answer file.
        self.missing_judge = (mode in ("custom", "interactive")
                              and self.validator_dir is None)

        if self.missing_judge:
            self.mode = f"{self.judging_mode}!NOJUDGE"
        elif self.interactive:
            self.mode = "interactive"
        elif self.custom:
            self.mode = "custom"
        elif tol:
            self.mode = f"{tol_flag.replace('float_', '').replace('tolerance', 'tol')}({tol:g})"
        else:
            self.mode = "exact"

    def _judge_dir(self):
        """`_verify/{checkers,interactors}/<year>/<L>-<slug>/`, if it exists."""
        kind = "interactors" if self.interactive else "checkers"
        for base in (VERIFY_ROOT / kind / self.year / self.name,
                     VERIFY_ROOT / kind / self.year / self.letter):
            if base.is_dir() and any(p.is_file() for p in base.iterdir()):
                return base
        return None

    def tests(self, which="secret"):
        """[(input, answer_or_None)] in judging order.

        A flat data/ dir, so `which` selects on the filename prefix rather than
        on a subdirectory. Interactive problems legitimately ship inputs with
        no .ans -- the interactor holds the answer -- so a missing .ans is only
        an error for a problem judged by comparison, and evaluate() raises
        there rather than here.
        """
        data = self.dir / "data"
        if not data.is_dir():
            return []
        out = []
        for tin in sorted(data.glob("*.in"), key=_natural_key):
            # "._secret-03.in" and friends are macOS AppleDouble stubs that rode
            # along with the 2021 B and D data. They are resource forks, not
            # tests: judging one is an instant WA on a correct solution.
            if tin.name.startswith("._"):
                continue
            if which == "sample" and not tin.stem.startswith("sample"):
                continue
            if which == "secret" and tin.stem.startswith("sample"):
                continue
            ans = tin.with_suffix(".ans")
            out.append((tin, ans if ans.is_file() else None))
        return out

    def reference(self):
        src = self.dir / REFERENCE
        return src if src.is_file() else None

    def __repr__(self):
        return f"<WF {self.year}/{self.name} tl={self.time_limit} mode={self.mode}>"

def load_config(path=None):
    """The judging modes the statement text cannot express.

    A missing config is a hard error, not an empty default. It is what marks
    the problems that accept more than one correct answer and the interactive
    ones; without it they fall back to `exact` and get compared against a
    single answer file, which rejects correct submissions and looks exactly
    like the model getting the problem wrong. There is no reading of a missing
    config under which the remaining problems are still graded correctly.
    """
    p = Path(path or CONFIG_PATH)
    if not p.is_file():
        raise FileNotFoundError(
            f"no judging config at {p}. It ships with the problems; if the archive "
            f"was moved, point WF_ARCHIVE at the directory that holds _verify/.")
    d = json.loads(p.read_text())
    return d.get("problems", d)

def load_problem(ref, root=None, config=None):
    """`ref` is `<year>/<L>-<slug>`, `<year>/<L>`, or a path to the problem dir."""
    config = config if config is not None else load_config()
    p = Path(ref)
    if p.is_dir():
        return WFProblem(p, config)
    root = Path(root or ARCHIVE_ROOT)
    direct = root / ref
    if direct.is_dir():
        return WFProblem(direct, config)
    # <year>/<letter>
    parts = str(ref).strip("/").split("/")
    if len(parts) == 2:
        year, letter = parts
        matches = [q for q in (root / year).glob(f"{letter.upper()}-*") if q.is_dir()]
        if len(matches) == 1:
            return WFProblem(matches[0], config)
        if len(matches) > 1:
            raise FileNotFoundError(f"{ref} is ambiguous: {[m.name for m in matches]}")
    raise FileNotFoundError(f"no such problem: {ref}")
