"""What the insight should contain for this model, this round (plan.md §2 step 3). Pure Python.

The insight is a cut of the graph: from the nodes the model holds by itself (profile.held) to the key
node of one END route. Round 1 chooses the route whose missing nodes cost least (a missing node costs
1 + its wrong rate: a node the model gets wrong needs its misconception corrected, not just the
conclusion stated).

Two modes (config.MODE). "step", the default: the insight grows one node at a time. Round 1 states only
the first missing node of the route; after each round the route's frontier is the first node that
some run of the round does not hold (a node passes only at 3/3; a run holds a hinted node when its own text
established it or the hint gave it and the run never left it wrong). When the frontier is the hinted node, its item was not taken
up and goes up one level (statement -> negation of the model's own misreading -> rule -> rule with an
example); when the frontier lies further along (the hinted node passed and the model carried itself as
far as it could), the frontier node gets a level-1 item. "cut": every missing node is written at level 1
in round 1 and a node item whose node is where failed runs stop (stuck/root) goes up one level.

In both modes: a node item the grader did not find stated (given) in most runs is restated; a tripped
hazard becomes a hazard item; a route node the final programs contradict (code_gap) escalates its item
with the programs' evidence; stalled or no-submission runs, or runs with the idea but a wrong program,
bring the behavior item. A frontier item at C.MOVE_ON_LEVEL or above whose node the failed runs mostly work
past (they stop later on the route: its contradictions are slips on the way to a later obstacle) is kept as it
is and the later node is hinted. A node that resists at the top level with the runs stopping at it blocks its
route: the cheapest route avoiding it is chosen instead. Phase 2 (compaction) gets its candidate groups from here too: in step mode
every node item was added because the model did not pass its node, so only the earlier items (which
later ones may have made redundant), level downgrades, hazards and behavior are tried.
"""
from collections import Counter

import config as C
import graph as G
import profile as P

ITEM_KINDS = ("behavior", "node", "hazard")


def item_id(kind: str, ref: str | None = None) -> str:
    return kind if kind == "behavior" else f"{kind}:{ref}"


def node_item(nid: str, level: int, reason: str) -> dict:
    return {"id": item_id("node", nid), "kind": "node", "node": nid, "level": level, "text": None, "tokens": None,
            "reason": reason, "history": []}


def hazard_item(hid: str, level: int, reason: str) -> dict:
    return {"id": item_id("hazard", hid), "kind": "hazard", "hazard": hid, "level": level, "text": None,
            "tokens": None, "reason": reason, "history": []}


def behavior_item(level: int, reason: str) -> dict:
    return {"id": "behavior", "kind": "behavior", "level": level, "text": None, "tokens": None, "reason": reason,
            "history": []}


# --- the route

def route_cost(route: dict, held: set, nodes_profile: dict) -> tuple:
    missing = [n for n in route["nodes"] if n not in held]
    cost = sum(1.0 + (nodes_profile.get(n) or {}).get("wrong_rate", 0.0) for n in missing)
    return cost, missing


def choose_route(graph: dict, profile: dict, blocked=(), must_contain: str | None = None) -> dict | None:
    """The END route with the cheapest missing set (ties: fewer nodes, routes the model's own accepted runs
    took, then graph order), among routes containing no blocked node (and the node must_contain, if given).
    None when no route qualifies."""
    held = P.held_set(profile)
    ac_routes = (profile.get("summary") or {}).get("ac_routes") or {}
    best = None
    for route in G.end_routes(graph):
        if set(route["nodes"]) & set(blocked):
            continue
        if must_contain and must_contain not in route["nodes"]:
            continue
        cost, missing = route_cost(route, held, profile["nodes"])
        taken = ac_routes.get(str(route["index"]), ac_routes.get(route["index"], 0))
        key = (cost, len(route["nodes"]), -taken, route["index"])
        if best is None or key < best[0]:
            best = (key, {**route, "cost": round(cost, 2), "missing": missing, "held": [n for n in route["nodes"] if n in held]})
    return best[1] if best else None


def route_table(graph: dict, profile: dict) -> list:
    held = P.held_set(profile)
    out = []
    for route in G.end_routes(graph):
        cost, missing = route_cost(route, held, profile["nodes"])
        out.append({"index": route["index"], "key": route["key"], "nodes": route["nodes"], "source": route.get("source"),
                    "missing": missing, "cost": round(cost, 2)})
    return out


# --- round 1

def initial_items(graph: dict, profile: dict, route: dict, mode: str | None = None) -> dict:
    """Step mode: a level-1 item for the first missing node of the route; cut mode: one per missing node, in
    graph order. Plus, from the no-hint runs that had the idea but failed, the hazards they tripped, and the
    behavior item when the failures are behavior-type (stalled / no submission / END+fail/other in at least
    the configured share)."""
    mode = mode or C.MODE
    items = {}
    for nid in (route["missing"] if mode == "cut" else route["missing"][:1]):
        row = profile["nodes"].get(nid) or {}
        reason = (f"missing: held {row.get('established', 0)}/{row.get('runs', 0)}, wrong {row.get('wrong', 0)}, "
                  f"stuck {row.get('stuck', 0)}")
        items[item_id("node", nid)] = node_item(nid, 1, reason)
    s = profile.get("summary") or {}
    for hid, k in (s.get("hazards_tripped") or {}).items():
        items[item_id("hazard", hid)] = hazard_item(hid, 1, f"tripped in {k} no-hint run(s)")
    n_fail = s.get("failed") or 0
    if n_fail and ((s.get("stalled", 0) / n_fail >= C.BEHAVIOR_SHARE) or (s.get("end_fail_other", 0) / n_fail >= C.IMPL_SHARE)):
        items["behavior"] = behavior_item(1, f"{s.get('stalled', 0)} stalled / no-submission and "
                                             f"{s.get('end_fail_other', 0)} END+fail/other of {n_fail} failed no-hint runs")
    return items


# --- after an evaluated round

def pass_min(n_runs: int) -> int:
    """A node passes only when every run of the round holds it (the user's rule, 2026-11-03: 3/3)."""
    return n_runs


def holds(record: dict, nid: str) -> bool:
    """A run holds a node when its own text established it, or the hint gave it and the run's text never
    left it wrong (the solver took the hint and went on; the grader's stuck node is then further along).
    A given node the run contradicts is not held, so the hinted item escalates."""
    if nid in (record.get("established") or []):
        return True
    final = ((record.get("results") or {}).get(nid) or {}).get("final")
    return nid in (record.get("given") or []) and final != "wrong"


def held_counts(records: list, route_nodes: list) -> dict:
    """nid -> how many of the runs hold the node (see holds)."""
    return {nid: sum(holds(r, nid) for r in records) for nid in route_nodes}


def initial_passed(route: dict, passed=()) -> list:
    """The route's leading nodes that count as passed before any round on it: the profile-held prefix up to the
    first missing node, plus nodes passed in earlier rounds (after a route switch). Profile-held nodes beyond
    that prefix are checked by the 3/3 rule when the frontier reaches them (the hint can change what the
    model does there)."""
    ok = set(passed) | set(route.get("held") or [])
    out = []
    for nid in route["nodes"]:
        if nid not in ok:
            break
        out.append(nid)
    return out


def _final(record: dict, nid: str) -> str:
    return ((record.get("results") or {}).get(nid) or {}).get("final", "absent")


def passed_depth(records: list, route_nodes: list, passed=()) -> int:
    """The step-mode progress measure: the leading route nodes passed. A node not passed before passes when
    every run holds it (3/3). A node passed before (profile prefix or an earlier round) stays passed unless a
    majority of the runs contradict it: one run that merely does not restate a node the model normally has
    is noise, not a regression (2024/G Nemotron r4: one run left N1 working while the hinted N4 was held by
    all three, and the old all-nodes-3/3 rule scored the round as passed 0 and stopped the loop)."""
    counts, need, n = held_counts(records, route_nodes), pass_min(len(records)), len(records)
    depth = 0
    for nid in route_nodes:
        if nid in passed:
            if 2 * sum(_final(r, nid) == "wrong" for r in records) > n:
                break
        elif counts[nid] < need:
            break
        depth += 1
    return depth


def majority_min(n_runs: int) -> int:
    """Runs that make a majority (3 -> 2, 5 -> 3)."""
    return n_runs // 2 + 1


def majority_frontier(records: list, route_nodes: list, depth: int) -> str | None:
    """From the passed prefix on, the first route node fewer than a majority of the runs hold; None when a
    majority holds every remaining node."""
    counts, need = held_counts(records, route_nodes), majority_min(len(records))
    return next((nid for nid in route_nodes[depth:] if counts[nid] < need), None)


def past_frontier(fails: list, route_nodes: list, depth: int) -> tuple:
    """(node, k): the route node after the frontier (route_nodes[depth]) where most of the failed runs stop
    (the grader's stuck node) and how many failed runs stop past the frontier, when they are a majority of
    the failed runs; (None, 0) otherwise. Runs that stop later worked past the frontier: what they left wrong
    at it are slips (2023/J Nemotron r4: N2 at level 4 wrong in 2/3 runs, every run stuck at N4)."""
    later = set(route_nodes[depth + 1:])
    stuck = Counter(r.get("stuck") for r in fails if r.get("stuck") in later)
    k = sum(stuck.values())
    if not fails or 2 * k <= len(fails):
        return None, 0
    return stuck.most_common(1)[0][0], k


def frontier(records: list, route_nodes: list, passed=()) -> str | None:
    """The first route node not passed (see passed_depth); None when the whole route passed."""
    d = passed_depth(records, route_nodes, passed)
    return route_nodes[d] if d < len(route_nodes) else None


def uptake(records: list, nid: str) -> dict:
    """What the hinted runs did with a node: given by the hint, established in their own text, wrong, absent."""
    n = len(records)
    finals = [((r.get("results") or {}).get(nid) or {}).get("final", "absent") for r in records]
    return {"runs": n, "given": sum(nid in (r.get("given") or []) for r in records),
            "established": finals.count("established"), "wrong": finals.count("wrong"),
            "working": finals.count("working"), "absent": finals.count("absent")}


def update(graph: dict, profile: dict, route: dict, items: dict, records: list, mode: str | None = None,
           passed=(), recent: list | None = None) -> dict:
    """The next round's items from the hinted runs' records: {items, changes, blocked, off_route,
    summary, uptake, frontier, passed, passed_nodes, jump}; passed = the route nodes passed before this round (see
    passed_depth); recent = the records of the last scored rounds, this round's first, for the jump rule.
    Items not implicated keep their text; a changed item has text
    None (to be written) and its old version appended to its history by the caller."""
    mode = mode or C.MODE
    items = {k: dict(v) for k, v in items.items()}
    fails = [r for r in records if r.get("solved") is False]
    changes, blocked = [], []
    summ = P.summary(records)
    uptakes = {it["node"]: uptake(records, it["node"]) for it in items.values() if it["kind"] == "node"}
    counts, need = held_counts(records, route["nodes"]), pass_min(len(records))
    depth = passed_depth(records, route["nodes"], passed)
    front = route["nodes"][depth] if depth < len(route["nodes"]) else None
    passed_nodes = list(route["nodes"][:depth])
    for it in items.values():
        if it["kind"] == "node":
            it["passed"] = it["node"] in passed_nodes
    if not fails:
        return {"items": items, "changes": changes, "blocked": blocked, "off_route": Counter(), "summary": summ,
                "uptake": uptakes, "frontier": front, "passed": depth, "passed_nodes": passed_nodes}
    on_route = set(route["nodes"])
    stuck = Counter(r.get("stuck") for r in fails if r.get("stuck"))
    off_route = Counter({nid: k for nid, k in stuck.items() if nid not in on_route})
    end_fail = [r for r in fails if r.get("reached_end")]

    def mark(item, change, why):
        item["text"], item["tokens"] = None, None
        item["reason"] = why
        changes.append({"item": item["id"], "change": change, "why": why})

    def escalate_or_add(nid, why):
        iid = item_id("node", nid)
        if iid in items:
            it = items[iid]
            if it["level"] < max(C.LEVELS):
                it["level"] += 1
                mark(it, "escalate", why + f" -> level {it['level']}")
            else:
                blocked.append(nid)
                changes.append({"item": iid, "change": "blocked", "why": why + " at the top level"})
        else:
            claims = P.distinct_claims(fails, nid)
            items[iid] = node_item(nid, 2 if claims else 1, why + (" (the model had it wrong)" if claims else ""))
            changes.append({"item": iid, "change": "add", "why": items[iid]["reason"]})

    # 1. the node to work on
    maj, past = None, None
    if mode == "step":
        # the frontier: the first route node not passed (every run holds it). A frontier node a majority of
        # the runs hold is taken provisionally: its item stays as it is and the next node the majority lacks
        # is hinted, so one dissenting run does not keep the loop on a node most runs already use (the
        # user's rule, 2026-11-04). A node the majority does not hold is escalated; an earlier, passed node
        # comes back as the frontier only when a majority contradicted it. A frontier whose item is at
        # C.MOVE_ON_LEVEL or above (the rule with an example did not fix it) escalates or blocks only when the
        # failed runs stop at it (or before it): when most of them stop later on the route, its
        # contradictions are slips on the way to a later obstacle, so its item stays and the first later
        # node the majority lacks is hinted (2023/J Nemotron r4); the user's rule, 2026-11-04
        if front is not None:
            n = len(records)
            maj = majority_frontier(records, route["nodes"], depth)
            iid = item_id("node", front)
            settled = iid in items and items[iid]["level"] >= C.MOVE_ON_LEVEL
            if settled and (maj is None or maj == front):
                past, k = past_frontier(fails, route["nodes"], depth)
            if maj is not None and maj != front:
                escalate_or_add(maj, f"frontier {front} held in {counts[front]}/{n} runs (passes at {need}); "
                                     f"the next node {maj} is held in {counts[maj]}/{n}")
            elif past is not None:
                target = next((nid for nid in route["nodes"][depth + 1:] if counts[nid] < majority_min(n)), past)
                why = (f"frontier {front} resists at level {items[iid]['level']} (held in {counts[front]}/{n} runs) while "
                       f"{k}/{len(fails)} failed runs stop later at {past}")
                changes.append({"item": iid, "change": "kept", "why": why})
                escalate_or_add(target, why + f"; the next node the majority lacks is {target} (held in {counts[target]}/{n})")
            else:
                escalate_or_add(front, f"frontier: held in {counts[front]}/{n} runs (needs {need}) after {depth} passed nodes")
        else:
            # every route node is held by every run and some still fail without reaching END: there is no
            # frontier to hint, so the route node where most of those runs stop (the grader's stuck node;
            # ties -> the earliest on the route, as the grader breaks them) escalates, one node per round as
            # in cut mode, instead of re-running the same text until the stall rule stops the loop
            # (2024/G Nemotron r6: 1/3 with all five nodes given, the failed runs working on N4 and N5)
            idle = Counter(r.get("stuck") for r in fails if not r.get("reached_end") and r.get("stuck") in on_route)
            if idle:
                k, nid = max(((k, nid) for nid, k in idle.items()), key=lambda t: (t[0], -route["nodes"].index(t[1])))
                escalate_or_add(nid, f"every route node is held in all {len(records)} runs; {k}/{len(fails)} failed runs stop at {nid}")
    else:
        for nid, k in stuck.most_common():       # where the failed runs stop
            if nid in on_route:
                escalate_or_add(nid, f"stuck point of {k}/{len(fails)} failed runs")
    # 1b. jump: a node the model keeps getting wrong by itself, beyond the frontier on the route or on a
    # parallel route, is hinted now instead of when the step order reaches it (the user's rule, 2026-11-05).
    # Signal: wrong in at least C.JUMP_WRONG_SHARE of the runs, solved runs included, in each of the last
    # C.JUMP_ROUNDS scored rounds (recent: their records, this round's first). 2023/F Qwen r3-r9 contradicted
    # N9 (the target must itself be corner-packed) in 3/3 runs every round, the runs the official tests
    # accepted included, while the loop hinted N2..N6 of a 10-node route and never reached its algorithm
    # nodes. One node per round, the most wrong one (ties: on the route first, then graph order), from
    # level 1; its item escalates while the signal persists and stays at the top level without blocking
    # (it is not the frontier, so it never stops the loop or switches the route).
    jump = None
    windows = [rs for rs in recent or [] if rs][:C.JUMP_ROUNDS]
    if len(windows) >= C.JUMP_ROUNDS:
        changed = {c["item"] for c in changes}
        order = [n["id"] for n in graph.get("nodes") or []]
        cands = {}
        for nid in order:
            if nid in passed_nodes or nid == front or item_id("node", nid) in changed:
                continue
            shares = [sum(_final(r, nid) == "wrong" for r in rs) / len(rs) for rs in windows]
            if min(shares) >= C.JUMP_WRONG_SHARE:
                cands[nid] = shares
        if cands:
            nid = min(cands, key=lambda x: (-cands[x][0], x not in on_route, order.index(x)))
            iid, shares = item_id("node", nid), cands[nid]
            why = (f"jump: {nid} ({'on a parallel route' if nid not in on_route else 'beyond the frontier'}) is wrong in "
                   f"{'/'.join(str(round(s * len(rs))) for s, rs in zip(shares, windows))} of "
                   f"{'/'.join(str(len(rs)) for rs in windows)} runs of the last {len(windows)} rounds")
            if iid in items:
                it = items[iid]
                if it["level"] < max(C.LEVELS):
                    it["level"] += 1
                    mark(it, "escalate", why + f" -> level {it['level']}")
                    changes[-1]["rule"] = it["rule"] = "jump"
                else:
                    changes.append({"item": iid, "change": "kept", "why": why + "; at the top level already", "rule": "jump"})
            else:
                items[iid] = dict(node_item(nid, min(C.LEVELS), why), rule="jump")
                changes.append({"item": iid, "change": "add", "why": why, "rule": "jump"})
            jump = nid
    # 2. items the grader did not find in the hint
    for it in list(items.values()):
        if it["kind"] != "node" or it["text"] is None:
            continue
        u = uptakes[it["node"]]
        if u["runs"] and u["given"] / u["runs"] < C.MIN_GIVEN:
            mark(it, "restate", f"the grader found the node stated in the hint in only {u['given']}/{u['runs']} runs")
    # 3. the final programs: hazards and contradicted route nodes
    for hid, k in Counter(h for r in end_fail for h in r.get("hazards_tripped") or []).most_common():
        iid = item_id("hazard", hid)
        why = f"tripped in {k} run(s) that had the idea"
        if iid in items:
            if items[iid]["level"] < 2:
                items[iid]["level"] = 2
                mark(items[iid], "escalate", why + " again -> level 2")
        else:
            items[iid] = hazard_item(hid, 1, why)
            changes.append({"item": iid, "change": "add", "why": why})
    for nid, k in Counter(x for r in end_fail for x in r.get("code_gap") or []).most_common():
        iid = item_id("node", nid)
        if nid in on_route and iid in items and items[iid]["text"] is not None:
            it = items[iid]
            why = f"the final program contradicts it in {k} run(s) that had the idea"
            if it["level"] < max(C.LEVELS):
                it["level"] += 1
                mark(it, "escalate", why + f" -> level {it['level']}")
            else:
                mark(it, "restate", why)
            changes[-1]["rule"] = "code_gap"     # the loop keeps the node's passed version when the stronger one was worse
    # 4. behavior
    stalled = sum(str(r.get("class")).endswith("stalled") or r.get("submissions") == 0 for r in fails)
    impl = sum(str(r.get("class")) == "END+fail/other" for r in fails)
    if stalled / len(fails) >= C.BEHAVIOR_SHARE or impl / len(fails) >= C.IMPL_SHARE:
        why = f"{stalled} stalled / no-submission and {impl} END+fail/other of {len(fails)} failed runs"
        if "behavior" in items:
            if items["behavior"]["level"] < 2:
                items["behavior"]["level"] = 2
                mark(items["behavior"], "escalate", why + " -> procedure")
        else:
            items["behavior"] = behavior_item(1, why)
            changes.append({"item": "behavior", "change": "add", "why": why})
    return {"items": items, "changes": changes, "blocked": blocked, "off_route": off_route, "summary": summ,
            "uptake": uptakes, "frontier": front, "passed": depth, "passed_nodes": passed_nodes,
            "majority_frontier": maj, "past_frontier": past, "jump": jump}


def switch_route(graph: dict, profile: dict, items: dict, new_route: dict, mode: str | None = None) -> dict:
    """Items for a new route: node items of nodes on it are kept (text and level), others dropped; missing
    nodes without an item are added at level 1 (cut mode: all of them; step mode: the first one); hazard
    and behavior items are kept."""
    mode = mode or C.MODE
    out = {}
    for iid, it in items.items():
        if it["kind"] != "node" or it["node"] in new_route["nodes"]:
            out[iid] = dict(it)
    for nid in new_route["missing"]:
        if item_id("node", nid) in out:
            continue
        out[item_id("node", nid)] = node_item(nid, 1, "missing on the new route")
        if mode == "step":
            break
    return out


def wants_switch(update_result: dict, n_fail: int) -> str | None:
    """The off-route node most failed runs stop at, when at least half of them stop off the route."""
    off = update_result.get("off_route") or Counter()
    if not off or not n_fail:
        return None
    nid, k = off.most_common(1)[0]
    return nid if sum(off.values()) / n_fail >= 0.5 else None


# --- phase 2: what to try removing

def ablation_groups(graph: dict, items: dict, profile: dict, mode: str | None = None) -> list:
    """Candidate removals in the order to try them. Cut mode: node items the model nearly holds (highest
    held rate first), hazard items, the behavior item, level downgrades of escalated node items, then the
    remaining node items one by one (deepest first: a late step is more often recovered by the model
    itself). Step mode: hazards, behavior, level downgrades, then the node items one by one in route order
    except the last one added (the round before it was added is the evidence that it is needed); an
    earlier item may have become redundant once the later ones were there. Last, in both modes, "shorten":
    every remaining item rewritten at its level in fewer tokens (the loop repeats it while it is accepted,
    halves it like any group when it is not)."""
    mode = mode or C.MODE
    nodes = [it for it in items.values() if it["kind"] == "node"]
    rate = lambda it: (profile["nodes"].get(it["node"]) or {}).get("held_rate", 0.0)
    depth = lambda it: (profile["nodes"].get(it["node"]) or {}).get("depth", 0)
    groups = []
    if mode == "cut":
        nearly = sorted([it for it in nodes if rate(it) > 0], key=lambda it: -rate(it))
        if nearly:
            groups.append({"name": "nodes the model sometimes holds", "op": "drop", "members": [it["id"] for it in nearly]})
    hz = [it["id"] for it in items.values() if it["kind"] == "hazard"]
    if hz:
        groups.append({"name": "hazards", "op": "drop", "members": hz})
    if "behavior" in items:
        groups.append({"name": "behavior", "op": "drop", "members": ["behavior"]})
    esc = [it["id"] for it in nodes if it["level"] > 1]
    if esc:
        groups.append({"name": "escalated items back to level 1", "op": "level1", "members": esc})
    if mode == "cut":
        rest = sorted([it for it in nodes if rate(it) == 0], key=lambda it: -depth(it))
    else:
        rest = sorted(nodes[:-1], key=depth)      # insertion order = the order they were added; the last stays
    for it in rest:
        groups.append({"name": f"node {it['node']}", "op": "drop", "members": [it["id"]]})
    wordy = [it["id"] for it in items.values() if it["kind"] != "behavior" and it.get("text")]
    if wordy:
        groups.append({"name": "shorter wording", "op": "shorten", "members": wordy})
    return groups
