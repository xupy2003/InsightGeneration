# Reasoning graph · Crystal Crosswind (2021/A-crystal-crosswind)

status **accepted** · version `c87e7fca21f66ea8` · 11 nodes · 3 END route(s) · 4 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 1 review round(s)

**Route.** P1: Represent every cell by a Boolean occupancy variable. P2: Contract the cell implication graph into strongly connected components: all cells in one component must share their occupancy. P3: For each wind, decompose the grid into exact-displacement chains.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Exact Boolean meaning of a boundary | statement |
| N2 | 2 | key_property | Forced occupied and empty cells | N1 |
| N3 | 3 | reformulation | Crystal constraints form implication closure | N1 + N2 |
| N4 | 4 | key_property | Least crystal is positive reachability | N3 |
| N5 | 4 | key_property | Greatest crystal excludes negative ancestors | N3 |
| N6 | 5 | algorithm | Output the two implication closures | N4 + N5 |
| N7 | 4 | key_property | Strong components share molecule occupancy | N3 |
| N8 | 5 | algorithm | Component DAG occupancy dynamic programs | N7 |
| N9 | 2 | reformulation | Wind chains identify occupied run starts | N1 |
| N10 | 3 | key_property | Boundary blocks admit precisely nonempty prefixes | N9 |
| N11 | 4 | algorithm | Propagate wind-block prefix frontiers | N10 |
| END | | | complete solution | N1 + N2 + N3 + N4 + N5 + N6 \| N1 + N2 + N3 + N7 + N8 \| N1 + N9 + N10 + N11 |

## N1 · Exact Boolean meaning of a boundary

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** For each wind w and in-grid location p, membership in its observed boundary set is equivalent to occupied(p) AND NOT occupied(p-w). Every location outside the specified rectangle is unoccupied.

**Anchors.** wind · boundary · molecule · specified dimensions

**Accept.** Uses the exact supplied wind vector, including nonprimitive vectors. Both directions of the equivalence matter: observed boundaries must exist, and unobserved boundaries must not appear.

**Review.** all checks passed

## N2 · Forced occupied and empty cells

*key_property · depth 2 · source: exploration · routes: N1*

**Statement.** Let P contain every observed boundary location. Let F contain every in-grid predecessor of an observed boundary, and every unobserved location whose predecessor for some wind is outside. Every consistent structure contains P and avoids F.

**Anchors.** observed boundaries · predecessor · outside

**Accept.** For each listed boundary p, force p present and p-w absent when in bounds. For each wind, a location not listed with p-w outside must be absent. Overlapping constraints are compatible by the consistency guarantee.

**Review.** failed: atomic — Boundary-induced fixed values and exterior-induced absence are separately recognizable: a solver can correctly handle listed boundaries yet miss non-boundaries whose predecessors are outside. Split that exterior-seeding rule from the fixed values supplied by listed boundaries.

## N3 · Crystal constraints form implication closure

*reformulation · depth 3 · source: exploration · routes: N1 + N2*

**Statement.** Create an arc p→p-w whenever p is not an observed boundary for that wind and p-w is in-grid. A set of occupied cells is consistent exactly when it contains P, avoids F, and is closed under these arcs.

**Anchors.** occupied cells · observed boundary · implication arcs · P · F

**Accept.** Checks listed boundaries through the fixed cells, and unlisted boundaries through either an implication arc or an exterior forced absence. Boundary positions do not create an implication for that wind.

**Review.** all checks passed

## N4 · Least crystal is positive reachability

*key_property · depth 4 · source: exploration · routes: N3*

**Statement.** The cells reachable from P along implication arcs form the unique inclusion-minimal consistent crystal. Every consistent crystal contains this reachability closure; consistency guarantees that it avoids F.

**Anchors.** minimal structure · P · implication arcs

**Accept.** Reachability includes its starting vertices. Shows closure, satisfaction of fixed constraints, and containment in every solution, establishing unique minimum cardinality as well.

**Review.** all checks passed

## N5 · Greatest crystal excludes negative ancestors

*key_property · depth 4 · source: exploration · routes: N3*

**Statement.** The cells from which F is reachable along implication arcs must be empty. Their complement is the unique inclusion-maximal consistent crystal: it contains P, avoids F, and is closed under all implication arcs.

**Anchors.** maximal structure · F · reversed arcs

**Accept.** Equivalently propagates forced absence along reversed arcs. If an allowed cell implied a forbidden cell, it would itself be forbidden. Every consistent solution avoids the resulting forbidden set.

**Review.** all checks passed

## N6 · Output the two implication closures

*algorithm · depth 5 · source: exploration · routes: N4 + N5*

**Statement.** Search forward from P and backward from F in the implication graph. Output the forward-reachable cells as the minimum crystal, then the complement of backward-reachable cells as the maximum crystal. Generate neighbors using the winds and their boundary-membership sets.

**Anchors.** minimum crystal · maximum crystal · winds · boundary-membership sets

**Accept.** An implicit-graph BFS or DFS processes each cell at most once per search and tests k winds per cell, taking O(k·dx·dy + sum b) time. A reversed arc from u reaches q=u+w only when q is in-grid and q is not that wind's boundary.

**Review.** failed: separable, atomic — The two output constructions are independently understandable and already stated by N4 and N5; given those nodes and N3's arc definition, this is routine integration rather than another substantive bottleneck. Retain it as a combined output-rule summary, or narrow the preceding nodes so it contributes a genuinely new claim.

## N7 · Strong components share molecule occupancy

*key_property · depth 4 · source: exploration · routes: N3*

**Statement.** Every strongly connected component of the implication graph is entirely occupied or entirely empty in any consistent crystal. Contracting components gives a DAG whose implication constraints and aggregated forced-presence and forced-absence constraints preserve exactly the consistent structures.

**Anchors.** implication graph · occupied cells · strongly connected components · P · F

**Accept.** Mutual reachability forces equality of occupancy. Components containing P or F inherit the corresponding fixed value. Edges between distinct components retain their implication meaning, and the quotient is acyclic.

**Review.** all checks passed

## N8 · Component DAG occupancy dynamic programs

*algorithm · depth 5 · source: exploration · routes: N7*

**Statement.** In topological component order, minimum occupancy is forced-presence OR any occupied predecessor component. In reverse topological order, maximum occupancy is NOT forced-absence AND every successor component occupied. Expand component values to cells and output the minimum and maximum structures.

**Anchors.** component DAG · minimum occupancy · maximum occupancy · structures

**Accept.** Predecessor and successor refer to arcs of the condensation DAG, excluding edges within a component. Empty OR is false and empty AND is true. Consistency makes both assignments respect all fixed values. SCC decomposition and both sweeps can inspect O(k·dx·dy) implicit arcs.

**Review.** failed: atomic — The forward minimum DP and reverse maximum DP are separate constructions: knowing the first does not establish the second. Give them separate diagnostic nodes while retaining their combined output rule as the path summary.

## N9 · Wind chains identify occupied run starts

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** For each wind w, in-grid locations partition into chains p,p+w,... beginning where p-w is outside. Its observed boundaries are exactly the first occupied locations of the nonempty occupied runs on those chains.

**Anchors.** wind · locations · observed boundaries · occupied runs

**Accept.** Follows the actual displacement rather than the primitive direction. A nonzero wind gives finite chains with unique predecessors and successors; boundaries are precisely the empty-to-occupied transitions, including transitions from outside the grid.

**Review.** all checks passed

## N10 · Boundary blocks admit precisely nonempty prefixes

*key_property · depth 3 · source: exploration · routes: N9*

**Statement.** Each observed boundary's permitted block extends forward along its wind chain, ending two steps before the next boundary or at the chain's end. A one-wind solution chooses a nonempty prefix of every block and leaves all other locations empty.

**Anchors.** observed boundary · wind chain · permitted block · occupied prefix

**Accept.** The predecessor of the next boundary must be empty. Before the first boundary nothing may be occupied. After a run ends, occupancy cannot restart before another listed boundary. Consistency ensures consecutive listed boundaries leave room for a nonempty block.

**Review.** all checks passed

## N11 · Propagate wind-block prefix frontiers

*algorithm · depth 4 · source: exploration · routes: N10*

**Statement.** Build the permitted wind-chain blocks. For the minimum, start from all boundaries and extend block prefixes through occupied cells. For the maximum, forbid cells missing a block for any wind and truncate block prefixes before forbidden cells. Propagate changes to stabilization and output both resulting grids.

**Anchors.** minimum structure · maximum structure · block prefixes · wind-chain blocks

**Accept.** Maintain growing lower and shrinking upper prefix lengths per block. Queue each newly occupied or forbidden cell once and visit its k containing blocks. Each block position is traversed at most once per bound, giving O(k·dx·dy + sum b) time. Every update is mandatory in all consistent crystals; stabilization satisfies the prefix characterization for every wind, proving both extrema.

**Review.** failed: atomic — Growing mandatory prefixes and shrinking permitted prefixes are independently discoverable algorithms, with different initialization and propagation rules. Split their diagnostic claims into minimum-extension and maximum-truncation nodes, retaining the combined construction as the path's output summary.

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 + N5 + N6 \| N1 + N2 + N3 + N7 + N8 \| N1 + N9 + N10 + N11

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N6 \| N8 \| N11

## Hazards (END → program)

- **H1** The supplied wind displacement must not be normalized: wx and wy need not be relatively prime. *Check:* All predecessor and successor calculations use the original wx and wy, not a primitive direction or intervening lattice points.
- **H2** A predecessor or successor is outside whenever either coordinate leaves its permitted range; flattened indices alone do not detect row wrapping. *Check:* Validate x and y independently before accessing a cell or boundary-membership array.
- **H3** Print the minimum structure first, then one empty line, then the maximum; rows run from y=1 to dy and columns from x=1 to dx. *Check:* Each grid has exactly dy lines of dx characters. The top-left output character represents (1,1); do not reverse the vertical axis.
- **H4** Implication paths can contain a number of cells proportional to the entire grid size; graph traversals must not overflow the call stack. *Check:* Use iterative DFS/BFS, or otherwise provide sufficient stack space. A recursion depth proportional to dx·dy is not safe on a typical default C++ stack.

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4, N5, N6

Represent every cell by a Boolean occupancy variable. Listed boundaries fix a cell present and its predecessor absent; every unlisted boundary position gives an implication from that cell to its predecessor. The minimum structure is the implication closure of forced-present cells, while the maximum is the complement of the reverse implication closure of forced-absent cells; both searches take O(k·dx·dy + sum b) time.

New nodes: N1, N2, N3, N4, N5, N6 · judge: AC on 29 tests, slowest 0.16s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N2, N3, N7, N8

Contract the cell implication graph into strongly connected components: all cells in one component must share their occupancy. The condensation is a DAG, so minimum occupancy is computed by a forward Boolean dynamic program and maximum occupancy by a backward Boolean dynamic program. Iterative Kosaraju traversal and implicit wind-generated edges keep the total work O(k·dx·dy + sum b).

New nodes: N7, N8 · judge: AC on 29 tests, slowest 0.33s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N9, N10, N11

For each wind, decompose the grid into exact-displacement chains. Every observed boundary begins an occupied run, so it owns a permitted block ending before the mandatory empty predecessor of the next boundary; a valid crystal chooses a nonempty prefix of each block. Compute the smallest compatible prefixes by extension and the largest by truncation, propagating only newly occupied or newly forbidden cells; monotone block frontiers give O(k·dx·dy + sum b) total work.

New nodes: N9, N10, N11 · judge: AC on 29 tests, slowest 0.274s · program: `paths/P3.cpp` · None submission(s)

## Exploration

Finished: True · 3 submissions · reason: Three genuinely different accepted paths are established: cell-level implication reachability, strongly connected component DAG dynamic programming, and wind-chain block prefix propagation. I do not have another distinct approach that is both justified and fast enough for the full limits.

Ideas the explorer considered and dropped:

- Intersecting the individual winds' maximum structures is insufficient: the intersection can introduce an unobserved boundary for another wind, so cross-wind propagation remains necessary.
- Repeated whole-grid Boolean or morphological fixed-point sweeps are correct with suitable updates, but their convergence can require too many full-grid passes; the accepted worklist algorithms avoid this problem.
- A generic 2-SAT formulation reduces to the same implication and component reasoning already represented. A zero-capacity-cut formulation likewise recovers the existing two reachability closures rather than a genuinely new algorithm.
- Weighted minimum-cut formulations can optimize molecule count, but introduce a much heavier flow computation without a sufficiently convincing five-second worst-case performance argument here.
- Enumerating occupied subsets or combinations of run endpoints is exponential. Treating implications as undirected connectivity, or merely deleting unforced zero-indegree cells, is incorrect because implications are directional and optional cycles can remain.

## Review

END ok: True — All three END routes provide complete constructions. The implication route supplies both seed sets and propagation directions; the SCC route supplies the quotient constraints and both DP recurrences; the chain route supplies the exact permitted blocks and monotone prefix propagation. Their accepts describe implementations with sufficient time and memory bounds.

Hazards ok: True — The hazards cover exact nonprimitive displacements, two-dimensional bounds and row wrapping, output order and orientation, and traversal-stack safety. No additional essential overflow or precision constraint is needed at the stated coordinate and grid limits.

**Advisories.**

- N2 (bundles claims a solver can have separately; split it): Boundary-induced fixed values and exterior-induced absence are separately recognizable: a solver can correctly handle listed boundaries yet miss non-boundaries whose predecessors are outside. Split that exterior-seeding rule from the fixed values supplied by listed boundaries.
- N6 (comes with its prerequisite; merge it; bundles claims a solver can have separately; split it): The two output constructions are independently understandable and already stated by N4 and N5; given those nodes and N3's arc definition, this is routine integration rather than another substantive bottleneck. Retain it as a combined output-rule summary, or narrow the preceding nodes so it contributes a genuinely new claim.
- N8 (bundles claims a solver can have separately; split it): The forward minimum DP and reverse maximum DP are separate constructions: knowing the first does not establish the second. Give them separate diagnostic nodes while retaining their combined output rule as the path summary.
- N11 (bundles claims a solver can have separately; split it): Growing mandatory prefixes and shrinking permitted prefixes are independently discoverable algorithms, with different initialization and propagation rules. Split their diagnostic claims into minimum-extension and maximum-truncation nodes, retaining the combined construction as the path's output summary.
- order: Improve diagnostic granularity by separating N2's exterior non-boundary seeding rule and separating the minimum and maximum constructions within N8 and N11. N6 repeats the substantive constructions in N4 and N5, so treat it as output integration rather than an additional reasoning barrier, or narrow N4/N5 to distinct supporting proof obligations.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `c87e7fca21f66ea8` | 0 | 5 | accept |
