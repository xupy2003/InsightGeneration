# Reasoning graph · Hand of the Free Marked (2021/E-hand-of-the-free-marked)

status **accepted** · version `ccf37f7991dae64f` · 15 nodes · 4 END route(s) · 3 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 3 review round(s)

**Route.** P1: Model successful hands as a matching between k-card subsets and observable ordered rows together with the hidden card's mark. P2: Keep the matching characterization, but avoid enumerating complete mark-count vectors. P3: Use an adaptive recursion instead of enumerating every complete vector or joining two halves. P4: Compute the weighted distribution of the additive score with a sparse dynamic program over marks and selected-card counts.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Successful hands form an observation matching | statement |
| N2 | 2 | reformulation | Observations separate mark-count vectors | N1 |
| N3 | 3 | key_property | Count hands and marked observations | N2 |
| N4 | 3 | key_property | Uniform degrees within each hidden mark | N2 |
| N5 | 4 | key_property | Each vector matches its smaller side | N3 + N4 |
| N6 | 5 | algorithm | Enumerate and sum optimal hand counts | N1 + N2 + N3 + N5 |
| N7 | 5 | reformulation | Factor contributions across two mark groups | N3 + N5 |
| N8 | 6 | key_property | Aggregate partners by a score threshold | N7 |
| N9 | 7 | algorithm | Meet-in-the-middle probability with weighted queries | N1 + N2 + N7 + N8 |
| N10 | 6 | key_property | Suffix weight and score moment recurrence | N7 |
| N11 | 7 | key_property | Extremal suffix scores by card count | N10 |
| N12 | 8 | key_property | Collapse uniformly linear or saturated suffixes | N7 + N10 + N11 |
| N13 | 9 | algorithm | Adaptive suffix aggregation outputs the probability | N1 + N2 + N7 + N10 + N11 + N12 |
| N14 | 6 | key_property | Saturated partial scores are absorbing | N7 |
| N15 | 7 | algorithm | Sparse capped-score distribution dynamic program | N1 + N2 + N7 + N14 |
| END | | | complete solution | N1 + N2 + N3 + N4 + N5 + N6 \| N1 + N2 + N3 + N4 + N5 + N7 + N8 + N9 \| N1 + N2 + N3 + N4 + N5 + N7 + N10 + N11 + N12 + N13 \| N1 + N2 + N3 + N4 + N5 + N7 + N14 + N15 |

## N1 · Successful hands form an observation matching

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** Create a bipartite graph between k-card hands and observations consisting of an ordered visible row and the hidden card's mark. Edges represent possible displays. The optimal success probability equals the maximum matching size divided by binomial(n,k).

**Anchors.** selected cards · face-down card · marking · probability

**Accept.** Each observation and announced identity determine at most one successful hand, so successful hands admit distinct observations. Conversely, a matching supplies an assistant's display and magician's answer for every matched hand. Randomization cannot improve the best deterministic strategy.

**Review.** all checks passed

## N2 · Observations separate mark-count vectors

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** An observation determines the complete hand's mark-count vector a: count the visible marks and add one for the hidden mark. Thus the matching graph separates into independent subgraphs indexed by vectors with sum a_j=k and 0<=a_j<=n_j.

**Anchors.** marking · selected cards · visible cards

**Accept.** The visible identities determine their marks. No observation can connect hands having different mark multiplicities, so maximum matching sizes can be added over the vectors.

**Review.** all checks passed

## N3 · Count hands and marked observations

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** For a feasible vector a, the hand count is L=product_j binomial(n_j,a_j). With F=(k-1)!, the observation count hiding mark j is R_j=F*binomial(n_j,a_j-1)*product_{i!=j} binomial(n_i,a_i) when a_j>0, and zero otherwise.

**Anchors.** marking · ordered visible cards · hands

**Accept.** Choose the identities separately within each mark to count hands. For observations hiding mark j, instead choose a_j-1 identities of that mark and order all k-1 visible cards. Equivalently, R_j/L=F*a_j/(n_j-a_j+1). The observation parts for different hidden marks are disjoint.

**Review.** failed: atomic — Counting hands and counting observations are independently recognizable achievements: a solver can obtain the product of binomial coefficients without correctly counting hidden-mark observations and visible orders. Split these into a hand-count claim and an observation-count claim.

## N4 · Uniform degrees within each hidden mark

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** Within a fixed feasible mark-count vector, each hand has a_j*(k-1)! adjacent observations hiding mark j. Every such observation has exactly n_j-a_j+1 adjacent hands.

**Anchors.** face-down card · rearrange · marking

**Accept.** For the hand-side degree, choose one of its a_j cards to hide and permute the others. For the observation-side degree, complete the visible cards with any card of the hidden mark except the a_j-1 already visible cards.

**Review.** failed: atomic — The hand-side degree and observation-side degree require different counts; a solver can know how many displays a hand permits without recognizing how many hands complete an observation. Separate the two degree claims.

## N5 · Each vector matches its smaller side

*key_property · depth 4 · source: exploration · routes: N3 + N4*

**Statement.** For every feasible mark-count vector, the maximum matching size is min(L,R), where R=sum_j R_j is its total observation count.

**Anchors.** matching · mark-count vector · hands · observations

**Accept.** Weight every edge hiding mark j by 1/(n_j-a_j+1). Each observation receives weight one and each hand receives R/L. If R<=L this saturates all observations; otherwise scale by L/R to saturate all hands. Bipartite matching integrality gives a matching attaining the smaller-side upper bound.

**Review.** all checks passed

## N6 · Enumerate and sum optimal hand counts

*algorithm · depth 5 · source: exploration · routes: N1 + N2 + N3 + N5*

**Statement.** Output sum_a min(L(a),sum_j R_j(a))/binomial(n,k), enumerating integer vectors with sum a_j=k and 0<=a_j<=n_j. Equivalently, each vector contributes L(a)*min(1,(k-1)!*sum_j a_j/(n_j-a_j+1)) to the numerator.

**Anchors.** highest possible probability · mark-count vector · binomial coefficients

**Accept.** Precompute binomial(n_j,t) for 0<=t<=k by a multiplicative recurrence, enumerate compositions of k, and accumulate the stated numerator using floating-point arithmetic. There are at most binomial(19,9)=92,378 vectors, so O(m*binomial(k+m-1,m-1)+mk) arithmetic operations suffice.

**Review.** all checks passed

## N7 · Factor contributions across two mark groups

*reformulation · depth 5 · source: exploration · routes: N3 + N5*

**Statement.** Split the marks into two groups. A partial selection has count t, weight w=product_j binomial(n_j,a_j), and score s=(k-1)!*sum_j a_j/(n_j-a_j+1). Pairing records whose counts total k contributes w_L*w_R*min(1,s_L+s_R) successful hands.

**Anchors.** marking · mark-count vector · successful hands

**Accept.** Each partial record's count, product, and sum range over its own group of marks. The full hand count factors as the product of the two partial weights, while R/L is the sum of their scores. Each full mark-count vector corresponds uniquely to one compatible pair of partial records.

**Review.** all checks passed

## N8 · Aggregate partners by a score threshold

*key_property · depth 6 · source: exploration · routes: N7*

**Statement.** For a left record with weight w and score x, partition compatible right records at score y=1-x. Let W_< and Y_< sum weights and weighted scores below that threshold, and W_>= sum remaining weights. The combined successful-hand contribution is w*(x*W_<+Y_<+W_>=).

**Anchors.** partial selections · successful hands · score threshold

**Accept.** Below the threshold, min(1,x+y)=x+y; at or above it, the value is one. The identity does not require sorting. One evaluation method sorts right records and uses weight and weighted-score prefix sums, suffix weights, and a binary search. Records at equality may be placed on either side.

**Review.** all checks passed

## N9 · Meet-in-the-middle probability with weighted queries

*algorithm · depth 7 · source: exploration · routes: N1 + N2 + N7 + N8*

**Statement.** Partition marks into two groups and enumerate partial-selection records by selected-card count. For each record, aggregate opposite-group records using the weighted threshold formula, restricted to complementary card counts totaling k. Sum these contributions and divide by binomial(n,k) to obtain the optimal probability.

**Anchors.** highest possible probability · marking · partial selections · weighted threshold queries

**Accept.** Each compatible pair contributes exactly once, but pairs need not be enumerated. Weighted threshold aggregates can be evaluated by sorted prefix sums and binary searches, an offline sweep, or an ordered aggregate structure. A balanced partition gives at most binomial(k+ceil(m/2),ceil(m/2))<=3003 records per side; sorting and logarithmic queries readily fit the limits.

**Review.** all checks passed

## N10 · Suffix weight and score moment recurrence

*key_property · depth 6 · source: exploration · routes: N7*

**Statement.** For suffix marks, let W_j(r) sum r-card selection weights and M_j(r) sum weight times score. Set c_j(a)=binomial(n_j,a), d_j(a)=(k-1)!*a/(n_j-a+1). Then W_j(r)=sum_a c_j(a)W_{j+1}(r-a) and M_j(r)=sum_a c_j(a)[M_{j+1}(r-a)+d_j(a)W_{j+1}(r-a)].

**Anchors.** marking · partial selections · binomial weights · additive score

**Accept.** Index marks from zero. Use W_m(0)=1 and M_m(0)=0 for the empty suffix, with zero mass at other counts. Sum only valid counts a. Weight multiplication yields the W recurrence; score addition yields the extra d_j(a)W term in the M recurrence. Also W_j(r)=binomial(sum_{i>=j} n_i,r).

**Review.** failed: atomic — The suffix mass and the weighted score moment are separate quantities with separate derivations; knowing W, even through its closed-form binomial expression, does not establish the additional d_j(a)W term in M. Split the suffix-weight claim from the score-moment recurrence.

## N11 · Extremal suffix scores by card count

*key_property · depth 7 · source: exploration · routes: N10*

**Statement.** Let lo_j(r) and hi_j(r) be the minimum and maximum scores attainable by selecting r cards from suffix marks. Over counts a admitting a completion, lo_j(r)=min_a[d_j(a)+lo_{j+1}(r-a)], with the corresponding maximum recurrence for hi_j(r).

**Anchors.** marking · remaining cards · minimum score · maximum score

**Accept.** The empty suffix has score zero only at count zero. Impossible counts are excluded, or represented by positive/negative infinity. Enumerating the next mark's count proves both extrema recurrences; all suffix tables take O(mk^2) operations.

**Review.** all checks passed

## N12 · Collapse uniformly linear or saturated suffixes

*key_property · depth 8 · source: exploration · routes: N7 + N10 + N11*

**Statement.** Given accumulated score x and r remaining cards, a suffix contributes W_j(r) if x+lo_j(r)>=1. If x+hi_j(r)<=1, it contributes x*W_j(r)+M_j(r). These contributions exclude the already-selected marks' multiplicative weight.

**Anchors.** successful hands · remaining cards · score threshold · suffix weights

**Accept.** In the first case every completion is saturated, so summing its weight gives W_j(r). In the second case every completion is in the linear part of min(1,score), so summing weight times x plus suffix score gives xW_j(r)+M_j(r). Equality permits either formula.

**Review.** failed: atomic — The all-saturated collapse uses only total weight and a lower bound, whereas the all-linear collapse uses the score moment and an upper bound. A solver can establish the former without the latter, so expose them as separate collapse claims.

## N13 · Adaptive suffix aggregation outputs the probability

*algorithm · depth 9 · source: exploration · routes: N1 + N2 + N7 + N10 + N11 + N12*

**Statement.** Starting with score zero, recursively assign mark counts totaling k. Return zero for impossible remaining counts and collapse subtrees using the suffix formulas whenever applicable. Otherwise sum child results multiplied by binomial(n_j,a_j). Output the root result divided by binomial(n,k).

**Anchors.** highest possible probability · mark-count vector · suffix aggregation

**Accept.** Precompute suffix weights, moments and extrema. At an ambiguous state, branch over the next mark's count and add its score. A terminal state is always collapsible. This evaluates precisely the sum of optimal composition contributions, with at most the composition-recursion tree and O(mk^2) preprocessing.

**Review.** all checks passed

## N14 · Saturated partial scores are absorbing

*key_property · depth 6 · source: exploration · routes: N7*

**Statement.** Observation-to-hand score increments are nonnegative. Therefore a partial score may be capped at one without changing any completion's success factor: min(1,x+y)=min(1,min(1,x)+y) for x,y>=0.

**Anchors.** partial selections · additive score · successful hands

**Accept.** If x<1, capping changes nothing. If x>=1, every nonnegative future increment leaves the final success factor equal to one. Applying this identity repeatedly permits capping after every processed mark.

**Review.** failed: separable — This is an immediate consequence of N7's nonnegative additive scores and clipped success factor, rather than a substantial additional inference. Fold the saturation identity into N15's invariant or acceptance explanation.

## N15 · Sparse capped-score distribution dynamic program

*algorithm · depth 7 · source: exploration · routes: N1 + N2 + N7 + N14*

**Statement.** Initialize D_0(0,0)=1. For each mark j and allowed count a, add D_j(t,s)*binomial(n_j,a) into D_{j+1}(t+a,min(1,s+d_j(a))), where d_j(a)=(k-1)!*a/(n_j-a+1), retaining t+a<=k. Output sum_s s*D_m(k,s)/binomial(n,k).

**Anchors.** highest possible probability · marking · selected-card count · score distribution

**Accept.** D_j(t,s) sums binomial weights after the first j marks. Equal count-and-score states can be merged because they admit identical future choices and success factors. Use a sparse score-to-weight dictionary per count. Layer j has at most binomial(k+j,j)<=184,756 states, so ordered dictionaries suffice. Maintain sufficient precision for scores, weights, and the final weighted sum.

**Review.** all checks passed

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 + N5 + N6 \| N1 + N2 + N3 + N4 + N5 + N7 + N8 + N9 \| N1 + N2 + N3 + N4 + N5 + N7 + N10 + N11 + N12 + N13 \| N1 + N2 + N3 + N4 + N5 + N7 + N14 + N15

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N6 \| N9 \| N13 \| N15

## Hazards (END → program)

- **H1** Hand and observation counts can exceed all standard integer types: binomial(n,k) can be about 10^83. Intermediate products must not overflow integer arithmetic. *Check:* Use floating-point binomial recurrences and floating-point products, or arbitrary-precision integers. Cast before multiplication if integer operands could overflow.
- **H2** Vectors selecting more cards of a mark than exist are invalid; the ratio formula is only evaluated on feasible vectors. *Check:* Bound each selected count by its mark's population, or explicitly skip invalid vectors before using n_j-a_j+1 as a denominator.
- **H3** The printed probability must have absolute error at most 10^-9, including accumulation and formatting error. *Check:* Use sufficient floating-point precision and print enough decimal places; avoid integer division and severe cancellation.

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4, N5, N6

Model successful hands as a matching between k-card subsets and observable ordered rows together with the hidden card's mark. The graph separates by the numbers of cards of each mark; within each part, regular incidence counts give a fractional matching saturating the smaller side, hence an integral matching of that size. Enumerating all at most 92,378 mark-count vectors and summing their optimal contributions gives the answer.

New nodes: N1, N2, N3, N4, N5, N6 · judge: AC on 66 tests, slowest 0.014s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N2, N3, N4, N5, N7, N8, N9

Keep the matching characterization, but avoid enumerating complete mark-count vectors. Split the marks into two halves and represent each partial selection by its card count, binomial weight, and additive observation-to-hand score. Sorted weighted-prefix queries combine all compatible records from the other half at once, evaluating the same optimal probability in a meet-in-the-middle algorithm.

New nodes: N7, N8, N9 · judge: AC on 66 tests, slowest 0.011s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N2, N3, N4, N5, N7, N10, N11, N12, N13

Use an adaptive recursion instead of enumerating every complete vector or joining two halves. A small suffix dynamic program computes binomial weight sums, weighted score sums, and minimum/maximum attainable scores for every remaining card count. Any subtree entirely in the linear or saturated part of min(1,score) is evaluated in constant time; only subtrees straddling the threshold are expanded, so the worst case remains the small composition enumeration.

New nodes: N10, N11, N12, N13 · judge: AC on 66 tests, slowest 0.013s · program: `paths/P3.cpp` · None submission(s)
### P4 · N1, N2, N3, N4, N5, N7, N14, N15

Compute the weighted distribution of the additive score with a sparse dynamic program over marks and selected-card counts. Since all score increments are nonnegative, a partial score can be capped at one without changing any eventual success contribution, and states sharing a count and capped score can be merged. The state count is bounded by the number of partial count vectors, at most 184,756, so dictionary-based transitions fit easily.

New nodes: N14, N15 · judge: AC on 66 tests, slowest 0.028s · program: `paths/P4.cpp` · None submission(s)

## Exploration

Finished: True · 5 submissions · reason: Four accepted paths cover direct composition enumeration, meet-in-the-middle weighted threshold queries, adaptive suffix-moment aggregation, and sparse capped-score dynamic programming. I have no further genuinely different approach that I believe meets the limits; remaining ideas either reproduce existing claims, are implementation variations, or lack the required guarantees.

Ideas the explorer considered and dropped:

- Explicit maximum matching or maximum flow on individual hands and observations: the graph can contain about 10^83 hands, so it cannot be constructed.
- Hall-theorem and symmetry-based proofs of the smaller-side matching property: these are alternative proofs of N5, not new approaches.
- Generating functions for the complete weighted score distribution: their sparse convolution is the capped-score dynamic program already submitted.
- Grouping equal-sized mark classes, changing enumeration order, or using exact rational arithmetic: these are optimizations or numeric implementation changes rather than distinct solution paths.
- Replacing the composition-dependent minimum by a single global hand/observation ratio: different mark-count subgraphs cannot share observations, so excess capacity in one cannot compensate for a shortage in another.
- Monte Carlo estimation or discretizing scores coarsely: neither provides the required 10^-9 absolute-error guarantee within the limits.

## Review

END ok: True — All four routes specify a complete output computation with sufficient counting and optimality claims. The enumeration, weighted complementary-count join, adaptive suffix aggregation, and sparse score-distribution DP all fit the stated limits; none requires constructing the enormous matching explicitly.

Hazards ok: True — The hazards cover oversized combinatorial intermediates, infeasible mark counts and denominator validity, and the required numerical/output accuracy. Their checks permit floating-point or arbitrary-precision implementations without imposing an unnecessary arithmetic representation.

**Advisories.**

- N3 (bundles claims a solver can have separately; split it): Counting hands and counting observations are independently recognizable achievements: a solver can obtain the product of binomial coefficients without correctly counting hidden-mark observations and visible orders. Split these into a hand-count claim and an observation-count claim.
- N4 (bundles claims a solver can have separately; split it): The hand-side degree and observation-side degree require different counts; a solver can know how many displays a hand permits without recognizing how many hands complete an observation. Separate the two degree claims.
- N10 (bundles claims a solver can have separately; split it): The suffix mass and the weighted score moment are separate quantities with separate derivations; knowing W, even through its closed-form binomial expression, does not establish the additional d_j(a)W term in M. Split the suffix-weight claim from the score-moment recurrence.
- N12 (bundles claims a solver can have separately; split it): The all-saturated collapse uses only total weight and a lower bound, whereas the all-linear collapse uses the score moment and an upper bound. A solver can establish the former without the latter, so expose them as separate collapse claims.
- N14 (comes with its prerequisite; merge it): This is an immediate consequence of N7's nonnegative additive scores and clipped success factor, rather than a substantial additional inference. Fold the saturation identity into N15's invariant or acceptance explanation.
- order: For finer trace localization, split N3 into hand and observation counts, N4 into the two side-degree claims, N10 into suffix mass and score moment, and N12 into saturated and linear collapse rules. Fold N14 into N15's acceptance explanation. The dependency order and key-node choices otherwise work.

**Builder's notes.** N9 now states only the complementary-count weighted threshold join. Sorting, prefixes, balancing, and alternative query implementations appear only as acceptance examples. All node and hazard IDs are preserved, with no changes to routes or END routes.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `ba38c143bf442e29` | 2 | 6 | revise |
| 2 | `4572fdef2eb8a6d8` | 1 | 5 | revise |
| 3 | `ccf37f7991dae64f` | 0 | 6 | accept |
