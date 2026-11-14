"""Text lengths in a solver model's own tokens (GPTv3/PricedGuidance/tokens.py, adapted).

The engine's Python has no transformers, so the solver's tokenizer runs in the solver's conda env, in one
worker process per model that stays up for the whole run: starting one costs about ten seconds, and the
writers' length checks count every answer they get back. An insight's length is counted this way because
formulas take about two tokens a word and a word count would be gamed by dense notation.
"""
import json
import os
import subprocess

import config as C

WORKER = r'''
import json, sys
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(sys.argv[1])
for line in sys.stdin:
    texts = json.loads(line)
    print("COUNTS " + json.dumps([len(tok(t, add_special_tokens=False)["input_ids"]) if t else 0 for t in texts]),
          flush=True)
'''
_workers, _cache = {}, {}


def _worker(model):
    w = _workers.get(model)
    if w is None or w.poll() is not None:
        spec = C.SOLVERS[model]
        # -I and cwd=/: the worker must not see this directory on its import path (profile.py, tokens.py and
        # the others shadow modules transformers' imports reach for; the import then fails)
        w = _workers[model] = subprocess.Popen(
            [str(C.CONDA_ENVS / spec["conda_env"] / "bin" / "python"), "-I", "-c", WORKER, str(spec["path"])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd="/",
            env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    return w


def counts(model, texts):
    """[the length of each text in the model's tokens], without special tokens."""
    todo = sorted({t for t in texts if (model, t) not in _cache})
    if todo:
        w = _worker(model)
        w.stdin.write(json.dumps(todo) + "\n")
        w.stdin.flush()
        while True:   # anything else the tokenizer prints is not an answer
            line = w.stdout.readline()
            if not line:
                raise RuntimeError(f"the {model} tokenizer worker exited")
            if line.startswith("COUNTS "):
                break
        for t, n in zip(todo, json.loads(line[len("COUNTS "):])):
            _cache[(model, t)] = n
    return [_cache[(model, t)] for t in texts]


def count(model, text):
    return counts(model, [text])[0]


def counter(model):
    """count(text) for one model; tests pass their own (a word count)."""
    return lambda text: count(model, text)


def stop():
    for w in _workers.values():
        if w.poll() is None:
            w.stdin.close()
            w.terminate()
    _workers.clear()
