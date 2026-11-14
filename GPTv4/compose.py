"""The insight text from its items (plan.md §2 step 5): the behavior item first, then the node items in
graph order (a route is a progression, so earlier conclusions come first), then the hazard items; items
separated by a blank line, plain ASCII. The length is counted in the solver's own tokens. No model calls.
"""
import config as C
import graph as G
from write import PROGRAM, ascii, copied

ORDER = {"behavior": 0, "node": 1, "hazard": 2}


def ordered(items: dict, graph: dict) -> list:
    def key(it):
        if it["kind"] == "node":
            return (ORDER["node"], G.index(graph, it["node"]))
        if it["kind"] == "hazard":
            hz = [h.get("id") for h in G.hazards(graph)]
            return (ORDER["hazard"], hz.index(it["hazard"]) if it["hazard"] in hz else len(hz))
        return (ORDER["behavior"], 0)
    return sorted((it for it in items.values() if it.get("text")), key=key)


def assemble(items: dict, graph: dict) -> str:
    return "\n\n".join(ascii(it["text"]).strip() for it in ordered(items, graph)).strip() + "\n"


def check_insight(text: str, codes=()) -> list:
    """Errors of the whole text: a complete program, or a copied run across item boundaries."""
    errors = []
    if PROGRAM.search(text):
        errors.append("the insight contains a complete program")
    for code in codes or ():
        run = copied(text, code)
        if run:
            errors.append(f"the insight copies a program's code: {run[:120]}")
            break
    return errors


def token_count(count, items: dict) -> int:
    return sum(count(it["text"]) for it in items.values() if it.get("text"))


def describe(items: dict, graph: dict) -> str:
    """One line per item for the log."""
    out = []
    for it in ordered(items, graph):
        what = it["kind"] if it["kind"] == "behavior" else f"{it['kind']} {it.get('node') or it.get('hazard')}"
        out.append(f"- {what} L{it['level']} ({it.get('tokens') or '?'} tok): {(it.get('text') or '')[:90]!r}")
    return "\n".join(out)
