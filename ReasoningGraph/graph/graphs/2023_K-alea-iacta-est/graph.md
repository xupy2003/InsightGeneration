# Reasoning graph · Alea Iacta Est (2023/K-alea-iacta-est)

status **accepted** · version `9bd9e636889fa301` · 16 nodes · 3 END route(s) · 4 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 2 review round(s)

**Route.** P1: Model the visible faces as a finite stochastic shortest-path problem, with every anagram of a dictionary word absorbing. P2: A label-setting algorithm avoids numerical value iteration altogether. P3: Use policy iteration rather than repeatedly minimizing at every numerical update.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Successful outcomes and reachability | statement |
| N2 | 2 | key_property | Target-following completion-time bound | N1 |
| N3 | 3 | reformulation | Optimal continuation Bellman equations | N1 + N2 |
| N4 | 4 | modeling | Uniform completions of retained faces | N3 |
| N5 | 5 | algorithm | Lattice computation of best reroll expectations | N4 |
| N6 | 4 | key_property | Lower Bellman residual certifies accuracy | N2 + N3 |
| N7 | 6 | algorithm | Certified lattice value iteration output | N5 + N6 |
| N8 | 5 | key_property | An action bounds all its outcomes | N3 + N4 |
| N9 | 5 | reformulation | Repeat until a settled outcome | N4 |
| N10 | 6 | key_property | Smallest repeat value finalizes outcomes | N2 + N8 + N9 |
| N11 | 7 | algorithm | Label-setting initial-roll expectation | N10 |
| N12 | 5 | algorithm | Monotone evaluation of a reroll policy | N4 |
| N13 | 6 | key_property | Greedy retained-face policies finish in expectation | N3 + N12 |
| N14 | 4 | construction | Target mismatches initialize an upper bound | N1 + N3 |
| N15 | 7 | key_property | Upper Bellman residual certifies accuracy | N2 + N3 + N13 |
| N16 | 8 | algorithm | Certified policy iteration output | N5 + N12 + N13 + N14 + N15 |
| END | | | complete solution | N1 + N2 + N3 + N4 + N5 + N6 + N7 \| N1 + N2 + N3 + N4 + N8 + N9 + N10 + N11 \| N1 + N2 + N3 + N4 + N5 + N12 + N13 + N14 + N15 + N16 |

## N1 · Successful outcomes and reachability

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** A complete outcome specifies one face for each labeled die and is successful exactly when its symbol multiset equals a dictionary word's multiset. Success is reachable if and only if at least one complete outcome is successful.

**Anchors.** dice · faces · valid words · successful outcomes

**Accept.** Recognize successful outcomes by comparing symbol multisets, for example by sorting both words and outcomes while preserving multiplicities. Every complete face-index outcome has positive probability on a full roll, so existence also characterizes feasibility. An explicit feasibility precheck is not required.

**Review.** all checks passed

## N2 · Target-following completion-time bound

*key_property · depth 2 · source: exploration · routes: N1*

**Statement.** If a successful complete outcome exists, every state admits a strategy taking at most B=6d expected additional rolls: fix that outcome, retain matching dice, and reroll unmatched dice until they show their designated faces.

**Anchors.** successful outcome · matching dice · expected number of rolls

**Accept.** Each unmatched die reaches its designated face in expected six trials. The number of simultaneous rounds is bounded by the sum of these trial counts. Matching dice need no trials, and encountering any other successful outcome can only shorten the strategy.

**Review.** all checks passed

## N3 · Optimal continuation Bellman equations

*reformulation · depth 3 · source: exploration · routes: N1 + N2*

**Statement.** Let V(s) be the optimal expected additional rolls from a complete outcome s. It is zero on successful states; otherwise V(s)=1+min_R E[V(s after rerolling R)], where R is a nonempty subset of labeled dice rerolled independently.

**Anchors.** optimal strategy · reroll subset · continuation value · V

**Accept.** First-step optimality minimizes over retained-face choices, with independent uniform face outcomes and one unit of cost per simultaneous reroll. Including the empty reroll subset as an artificial waiting action is equivalent: it costs one without changing the state and cannot improve the optimum.

**Review.** all checks passed

## N4 · Uniform completions of retained faces

*modeling · depth 4 · source: exploration · routes: N3*

**Statement.** A partial assignment fixes retained faces and wildcards rerolled dice. Selecting it from a compatible complete outcome is free; rolling its wildcards costs one roll and produces independent, uniform faces. With k wildcards, its 6^k face-index completions are equiprobable.

**Anchors.** retained dice · rerolled dice · partial assignment · wildcard

**Accept.** Establish the retained-face/wildcard interpretation and the uniform completion distribution. This may be represented as a complete-state action or as a partial state with zero-cost selection followed by one-roll completion. Settled-completion counts and sums establish this node without computing a full-lattice averaging transform.

**Review.** all checks passed

## N5 · Lattice computation of best reroll expectations

*algorithm · depth 5 · source: exploration · routes: N4*

**Statement.** Given complete-state continuation values, compute each state's minimum expected continuation over retained-face restrictions by averaging uniform completions of partial assignments and taking restriction minima. These operations on at most 7^d partial assignments evaluate all reroll choices without enumerating their transition distributions.

**Anchors.** continuation values · partial-assignment averages · retained faces · restriction minima

**Accept.** A wildcard expectation is the average of the six entries replacing that wildcard. After computing these averages, coordinate-wise minimum-with-wildcard updates obtain every state's restriction minimum. Dependency-ordered lattice dynamic programs are equivalent. Both stages together take O(d7^d) work and O(7^d) storage.

**Review.** all checks passed

## N6 · Lower Bellman residual certifies accuracy

*key_property · depth 4 · source: exploration · routes: N2 + N3*

**Statement.** Let U be a zero-initialized Bellman iterate and δ=max_s(TU(s)−U(s))<1. Then U≤V≤6d and 0≤V(s)−U(s)≤6dδ/(1−δ) for every state. The same error bound holds for the uniform average of continuation values.

**Anchors.** Bellman iterate · residual · expected completion · precision

**Accept.** Monotonicity gives 0≤U≤TU≤V. A TU-greedy policy satisfies U(s)≥1−δ+E[U(next)] until success, so its expected duration is at most U(s)/(1−δ). Comparing that duration with V proves the residual bound.

**Review.** all checks passed

## N7 · Certified lattice value iteration output

*algorithm · depth 6 · source: exploration · routes: N5 + N6*

**Statement.** If no successful state exists, output impossible. Otherwise repeatedly apply Bellman updates from zero using partial averages and restriction minima. These iterates converge to the optimal continuation values. Stop when the residual certifies accuracy, then output one plus the all-wildcard continuation average.

**Anchors.** impossible · expected number of rolls · all-wildcard average · Bellman updates

**Accept.** Monotone updates are bounded by 6d and converge to a Bellman fixed point; a greedy policy shows that this bounded nonnegative fixed point is V. Keep terminal values zero and use O(d7^d) work per sweep. The mandatory first roll contributes one. An average from the preceding iterate is valid when its measured residual certifies it.

**Review.** all checks passed

## N8 · An action bounds all its outcomes

*key_property · depth 5 · source: exploration · routes: N3 + N4*

**Statement.** Let Q(p)=1+E[V(s)] over complete outcomes extending retained-face assignment p. Every such outcome s satisfies V(s)≤Q(p), because it can reroll exactly p's wildcards. If p is optimal at a nonterminal state s, all its outcomes have value at most V(s).

**Anchors.** retained faces · optimal strategy · complete outcomes · Q

**Accept.** Every completion preserves p's retained faces, so the same action remains available there. Successful outcomes have value zero and also satisfy the inequality. This property permits label setting even though a reroll can return to its starting outcome.

**Review.** all checks passed

## N9 · Repeat until a settled outcome

*reformulation · depth 5 · source: exploration · routes: N4*

**Statement.** Suppose p has n equiprobable complete outcomes, of which c>0 are settled with optimal values summing to S. Retaining p and repeatedly rerolling its wildcards until a settled outcome appears, then continuing optimally, has expected cost (n+S)/c.

**Anchors.** partial assignment · settled outcomes · repeated rerolls · expected cost

**Accept.** All successful complete outcomes are settled initially. The repeat strategy satisfies x=1+S/n+(n−c)x/n. Face-index completions each have probability 1/n, including when symbols repeat. An assignment with c=0 offers no finite repeat-until-settled candidate. The same formula can label the retained-face partial state itself.

**Review.** all checks passed

## N10 · Smallest repeat value finalizes outcomes

*key_property · depth 6 · source: exploration · routes: N2 + N8 + N9*

**Statement.** With successful states initially settled at zero, let each partial assignment have n completions, c settled, whose values sum to S. Choose a minimum (n+S)/c among 0<c<n. Its unsettled completions all have that optimal value and can be settled together.

**Anchors.** settled states · smallest value · partial assignment · optimal action

**Accept.** Let m be the smallest unsettled optimal value. An optimal action there has no outcome above m, so its unsettled outcomes equal m and its repeat candidate equals m. Every candidate is an achievable upper bound for its unsettled completions, proving the rule. Explicit complete-outcome batches or equivalent zero-cost propagation through partial states count.

**Review.** all checks passed

## N11 · Label-setting initial-roll expectation

*algorithm · depth 7 · source: exploration · routes: N10*

**Statement.** Use label setting on successful outcomes and retained-face assignments to determine the expected cost of the initial all-dice roll. Output impossible if that start cannot reach success; otherwise output its finalized cost, equivalently one plus the uniform mean of optimal complete-state continuation values.

**Anchors.** label setting · initial all-dice roll · all-wildcard start · impossible

**Accept.** A partial-state implementation uses zero-cost selection or discarding and one-roll uniform completion, and may stop when the all-wildcard start is finalized. Alternatively, finalize complete outcomes and average their values. Settled counts, value sums, and a heap process O(12^d) completion incidences in O(12^d log(12^d)) time. Lazy stale-entry rejection or an indexed heap is valid.

**Review.** all checks passed

## N12 · Monotone evaluation of a reroll policy

*algorithm · depth 5 · source: exploration · routes: N4*

**Statement.** For a proper retained-face policy π, define TπU(s)=1+Eπ[U(next)] outside successful states and zero inside. Starting from nonnegative U≥TπU, repeated Tπ updates decrease to the policy's expected remaining rolls and preserve W≥TπW≥TW, where T minimizes over retained-face choices.

**Anchors.** retained-face policy · policy evaluation · uniform completions · supersolution invariant

**Accept.** Proper means finite expected completion time from every complete outcome. Policy equations then have a unique bounded solution, obtained by averaging uniform completions of each selected retained-face assignment. If W=TπU≤U, monotonicity gives TπW≤W; minimizing gives TW≤TπW. Thus stopping policy evaluation early still preserves the Bellman supersolution invariant.

**Review.** all checks passed

## N13 · Greedy retained-face policies finish in expectation

*key_property · depth 6 · source: exploration · routes: N3 + N12*

**Statement.** For the dice's retained-face Bellman operator T, a nonnegative array U with zero successful-state values and TU≤U makes every U-greedy reroll policy proper: its expected remaining rolls from state s are at most U(s), so U(s)≥V(s).

**Anchors.** retained faces · greedy reroll policy · expected remaining rolls · upper bound

**Accept.** At each unsuccessful outcome, select retained faces minimizing the uniform mean of U over their completions. Then U(s)≥1+E[U(next)]. Telescoping over successive rerolls bounds the expected number before success by U(s), proving finite expected completion and the upper bound on V. Preservation during subsequent evaluation is established separately by the policy-evaluation node.

**Review.** all checks passed

## N14 · Target mismatches initialize an upper bound

*construction · depth 4 · source: exploration · routes: N1 + N3*

**Statement.** Fix a successful face-index assignment and let m(s) count mismatching dice. Setting U(s)=0 on successful states and U(s)=6m(s) elsewhere gives TU≤U: rerolling all mismatches leaves at most 5m(s) expected continuation, so its total is at most 1+5m(s)≤6m(s).

**Anchors.** successful assignment · mismatching dice · upper bound

**Accept.** Every nonterminal state has at least one mismatch. Each rerolled mismatch remains mismatched with probability 5/6, so the expected assigned continuation is at most 5m. Additional successful outcomes only reduce it. Any designated successful face-index assignment works, including when different faces bear the same symbol.

**Review.** all checks passed

## N15 · Upper Bellman residual certifies accuracy

*key_property · depth 7 · source: exploration · routes: N2 + N3 + N13*

**Statement.** For a nonnegative Bellman supersolution U with terminal values zero, let δ=max_s(U(s)−TU(s)). Then 0≤U(s)−V(s)≤6dδ for every state.

**Anchors.** Bellman residual · supersolution · accuracy

**Accept.** Along an optimal reroll policy, U(s)≤1+δ+E[U(next)]. Telescoping until success yields U≤(1+δ)V, and V≤6d. The proper greedy-policy argument supplies U≥V. The initial-roll continuation average inherits the same error bound.

**Review.** all checks passed

## N16 · Certified policy iteration output

*algorithm · depth 8 · source: exploration · routes: N5 + N12 + N13 + N14 + N15*

**Statement.** If success is unreachable, output impossible. Otherwise initialize the mismatch supersolution, alternate greedy retained-face policy improvement and fixed-policy evaluation, and stop when the upper Bellman residual certifies accuracy. Output one plus the average continuation after rolling every die.

**Anchors.** policy iteration · initial roll · expected number of rolls · impossible

**Accept.** Recover minimizing retained-face assignments while computing restriction minima. Fixed-policy evaluation uses partial averages and the selected action per outcome; monotone inexact evaluation preserves the supersolution invariant. Arrays have at most 7^d entries, and each evaluation or improvement sweep takes O(d7^d) work. The added one counts the mandatory initial full roll.

**Review.** all checks passed

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 + N5 + N6 + N7 \| N1 + N2 + N3 + N4 + N8 + N9 + N10 + N11 \| N1 + N2 + N3 + N4 + N5 + N12 + N13 + N14 + N15 + N16

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N7 \| N11 \| N16

## Hazards (END → program)

- **H1** Repeated symbols on different faces contribute their full multiplicity to roll probabilities. *Check:* Use six equally weighted face indices per die, or weight merged symbols by their number of faces divided by six.
- **H2** Success depends on the multiset of symbols, not their order or merely their set. *Check:* Canonicalize both dictionary words and complete outcomes while preserving repeated symbols, for example by sorting all d symbols.
- **H3** Count the mandatory initial full roll, and report impossible exactly when no valid word can ever be formed. *Check:* Either precheck for successful face assignments or determine that the all-wildcard initial state is unreachable. Account for the initial roll within that state's cost, or add one to the mean continuation after the first full roll.
- **H4** Output must have absolute or relative error at most 10^-6. Numerical iteration needs a justified stopping rule; label setting still needs sufficiently accurate arithmetic. *Check:* Conditional examples: zero-start Bellman iteration has error at most 6dδ/(1−δ) from its residual δ<1; a supersolution has error at most 6dδ. Label-setting implementations can stop upon finalizing the initial cost without a residual test. Use enough arithmetic and printed precision in either case.

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4, N5, N6, N7

Model the visible faces as a finite stochastic shortest-path problem, with every anagram of a dictionary word absorbing. Bellman value iteration can evaluate all reroll choices using averages and minima on the lattice of partial dice assignments, requiring only about 7^d entries rather than explicit transition matrices. A reachable word supplies a uniform 6d bound on the remaining expectation, which also turns the Bellman residual into a rigorous stopping criterion.

New nodes: N1, N2, N3, N4, N5, N6, N7 · judge: AC on 27 tests, slowest 0.112s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N2, N3, N4, N8, N9, N10, N11

A label-setting algorithm avoids numerical value iteration altogether. After some complete outcomes have known optimal values, each retained-face assignment offers a repeat-until-known strategy with value (number of completions + sum of known continuation values)/(number of known completions). The smallest such value is exactly the smallest unsettled optimal value, so all unsettled outcomes compatible with that assignment can be finalized together; a priority queue and partial-assignment incidence updates implement this efficiently.

New nodes: N8, N9, N10, N11 · judge: AC on 27 tests, slowest 0.319s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N2, N3, N4, N5, N12, N13, N14, N15, N16

Use policy iteration rather than repeatedly minimizing at every numerical update. A designated successful face assignment supplies a simple Bellman supersolution; each greedy policy is therefore proper, and evaluating that fixed policy monotonically improves the upper bound. Partial-assignment averages evaluate policies efficiently, lattice minima perform policy improvement, and an upper Bellman-residual certificate determines when the initial-roll expectation is accurate enough.

New nodes: N12, N13, N14, N15, N16 · judge: AC on 27 tests, slowest 0.178s · program: `paths/P3.cpp` · None submission(s)

## Exploration

Finished: True · 3 submissions · reason: Three genuinely different approaches were implemented and accepted: certified Bellman value iteration, a non-iterative label-setting algorithm based on repeat-until-settled strategies, and certified policy iteration. I do not have another independent approach that is both correct and suitable for the limits.

Ideas the explorer considered and dropped:

- Fix one reachable word or face assignment and optimize only its collection: this gives a useful upper bound but is not generally optimal, because the best strategy can switch target words after observing rolls.
- Explicitly enumerate every action's transition distribution: the resulting transition incidence count can reach 42^d, making repeated full Bellman updates too expensive; the accepted lattice averaging approach already avoids this.
- Solve the full Bellman linear program or dense policy equations directly: tens of thousands of state variables and millions of action constraints make generic dense methods unsuitable, with no additional efficient specialized solver established beyond the accepted approaches.
- Use coordinate-wise Gauss–Seidel updates, remove self-loops algebraically, merge identical symbols, or compress symmetric dice: these are implementation improvements or state reductions for existing approaches, not independent solution paths.
- Compute the best probability of success separately for each roll deadline and sum failure probabilities: deadline-optimal policies need not agree across deadlines, so that does not generally produce the minimum expected stopping time.

## Review

END ok: True — All three routes supply the outcome model, an implementable evaluation algorithm, and the initial-roll output rule. The numerical routes also supply valid residual certificates; the label-setting route supplies the repeat-value formula and finalization argument.

Hazards ok: True — The hazards cover face multiplicities, multiset-based success, impossibility, initial-roll accounting, and numerical accuracy. No additional problem-wide overflow or degeneracy constraint is needed for the stated state-space sizes.

**Builder's notes.** Ids and routes were preserved. Shared partial-assignment semantics now occupy N4, while the averaging/minimum computation is confined to N5 on P1/P3. N11 accepts both complete-state averaging and partial-state all-wildcard finalization. N13 now concerns properness specifically for retained-face policies; evaluation-invariant preservation is in N12. Within the fixed node inventory, success/reachability remain in N1, the completion-time bound is isolated in N2, initial-roll accounting is in the output nodes, and convergence is in N7 rather than the residual-certificate node N6.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `21e8fc6b66da1bb9` | 4 | 6 | revise |
| 2 | `9bd9e636889fa301` | 0 | 0 | accept |
