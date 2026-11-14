# Reasoning graph · Bridging the Gap (2023/J-bridging-the-gap)

status **accepted** · version `99253eadd1c82ba4` · 15 nodes · 3 END route(s) · 2 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 4 review round(s)

**Route.** P1: Normalize a schedule into batches: one crossing carries a prefix of the fastest remaining walkers, who return one at a time while enabling slow-only crossings. P2: Separate empty replenishment batches from batches that carry permanent passengers: empty batches commute to the beginning and form an independent unbounded knapsack. P3: Sort the walkers and represent permanent transfers as largest blocks of a shrinking prefix, charging each crossing together with its fastest helpers’ eventual individual returns.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Sorted crossing-time model | statement |
| N2 | 2 | key_property | Batch normal form with fastest returners | N1 |
| N3 | 3 | reformulation | Current-set batch costs and credits | N2 |
| N4 | 4 | key_property | Largest groups and residual prefix normalization | N2 + N3 |
| N5 | 5 | algorithm | DP with prepaid slow-only crossings | N3 + N4 |
| N6 | 6 | algorithm | Minimize prepaid groups and finishing cost | N1 + N4 + N5 |
| N7 | 6 | reformulation | Empty batches separate from passenger batches | N3 + N4 + N5 |
| N8 | 7 | algorithm | Empty replenishment is unbounded knapsack | N3 + N7 |
| N9 | 7 | key_property | Passenger counts determine mixed credits | N5 + N7 |
| N10 | 8 | algorithm | Cardinality partition of passenger batches | N3 + N7 + N9 |
| N11 | 9 | algorithm | Combine knapsack with cardinality partitions | N1 + N4 + N8 + N10 |
| N12 | 5 | key_property | Unified prefix order for permanent transfers | N2 + N3 + N4 |
| N13 | 8 | reformulation | Realizability of completed credit plans | N12 + N7 + N8 |
| N14 | 9 | key_property | Bounded return-balance range | N12 + N13 + N8 |
| N15 | 10 | algorithm | Permanent-progress signed-balance dynamic program | N1 + N8 + N12 + N13 + N14 |
| END | | | complete solution | N1 + N2 + N3 + N4 + N5 + N6 \| N1 + N2 + N3 + N4 + N5 + N7 + N8 + N9 + N10 + N11 \| N1 + N2 + N3 + N4 + N5 + N7 + N8 + N12 + N13 + N14 + N15 |

## N1 · Sorted crossing-time model

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** A crossing costs its participants’ maximum time, and successive torch trips alternate direction, ending forward. Walker identities do not otherwise affect feasibility or cost, so the walkers may be indexed by sorted crossing times t1<=...<=tn.

**Anchors.** walkers · torch · crossing times

**Accept.** Establishes both the trip-cost model and invariance under relabeling walkers. Sorting is justified by interchangeable identities, not by an assumption that chronological crossings must follow sorted order. Equal-time walkers may be ordered arbitrarily.

**Review.** failed: atomic — The crossing/torch mechanics and the justification for sorting are independently establishable claims. Separate the trip model from invariance under relabeling and sorted indexing.

## N2 · Batch normal form with fastest returners

*key_property · depth 2 · source: exploration · routes: N1*

**Statement.** Some optimum consists of batches followed by one final crossing. A batch sends the k fastest remaining walkers and at most c-k permanent passengers forward, then returns those k walkers individually, interleaving k-1 groups of permanent passengers. Each interleaved group has at most c walkers.

**Anchors.** fastest remaining walkers · crosses back · bridge capacity · torch

**Accept.** Must establish the full batch normal form, not merely single-person returns. Exchange arguments justify individual returns, regrouping overlapping excursions into batches, and choosing the fastest currently remaining returners. Each batch leaves its returners on the original bank and its permanent passengers across the river, allowing concatenation.

**Review.** failed: atomic — Single-person returns, regrouping excursions into batches, and choosing the fastest remaining returners are distinct normalization steps; a solver can establish the first without the others. Split these exchange lemmas so a partial normalization argument has its own location.

## N3 · Current-set batch costs and credits

*reformulation · depth 3 · source: exploration · routes: N2*

**Statement.** With remaining times u1<=...<=um, a k-returner batch uses k-1 slow-only crossings. Excluding those crossings, its cost is sum_{r=1}^k ur plus the maximum time in its preparatory crossing; without preparatory permanent passengers, that maximum is uk.

**Anchors.** fastest remaining walkers · preparatory crossing · slow-only crossings · crosses back

**Accept.** Charges each of the k returners once and charges the preparatory crossing once; slow-only crossing costs are separate. If preparatory passengers exist, their largest time determines its maximum. These are current-set times: replacing ur by globally sorted tr requires establishing that the original fastest k walkers are still available.

**Review.** failed: separable — The k-1 interleaved crossings are already specified in N2, and the stated charge follows immediately from N1's crossing cost and N2's individual returns. Fold this accounting into the batch-normal-form acceptance criteria or the batch-cost definitions used by the DP.

## N4 · Largest groups and residual prefix normalization

*key_property · depth 4 · source: exploration · routes: N2 + N3*

**Statement.** Some optimum reserves the largest walkers for slow-only groups in blocks of c, except possibly the last; a partial last group leaves at most c others. Preparatory passengers are removed from the largest end of the complementary sorted prefix, and passenger-carrying preparatory crossings are full.

**Anchors.** bridge capacity · slow-only groups · sorted crossing times · preparatory passengers

**Accept.** Uses passenger exchanges and fullness normalization. The residual prefix excludes all reserved slow-only groups, including those not yet physically transported. At subsequent batch boundaries this prefix only shortens from its largest end; reserved walkers are slower. Thus k returners chosen from this prefix have original times t1,...,tk, and their return cost is Sk=sum_{r=1}^k tr. Slack is confined to a possible last slow-only group or the final crossing; empty preparatory crossings remain allowed.

**Review.** failed: atomic — Assigning the largest walkers to capacity-sized slow-only blocks and normalizing preparatory crossings to full crossings of a residual prefix require distinct exchanges. Separate the slow-only allocation lemma from preparatory fullness/prefix normalization, placing availability of the original fastest helpers with the latter.

## N5 · DP with prepaid slow-only crossings

*algorithm · depth 5 · source: exploration · routes: N3 + N4*

**Statement.** F(i,j) minimizes the additional cost of finishing the residual prefix of i walkers while serving j prepaid slow-only crossings. Finish directly when i<=c,j=0. An empty k-returner batch reduces j by k-1; for i>c, a full preparatory crossing also removes the c-k largest prefix walkers.

**Anchors.** residual prefix · prepaid slow-only crossings · minimum total time

**Accept.** With Sk=sum_{r=1}^k tr, use F(i,0)=ti for i<=c; empty transitions Sk+tk+F(i,j-k+1), 2<=k<=min(c,i,j+1); and passenger-carrying transitions ti+Sk+F(i-c+k,j-k+1), i>c, 1<=k<=min(c-1,j+1). Empty means no preparatory permanent passengers. Infeasible choices are excluded. These minima admit acyclic evaluation, for example by increasing i and then j.

**Review.** all checks passed

## N6 · Minimize prepaid groups and finishing cost

*algorithm · depth 6 · source: exploration · routes: N1 + N4 + N5*

**Statement.** Minimize the sum of slow-only group maxima plus F(i,j), including j=0,i=n. For j>0 take j-1 full largest groups and one nonempty group of at most c walkers; its remaining prefix i must equal n-jc or satisfy i<=c. Output this minimum.

**Anchors.** minimum total time · bridge capacity · entire group

**Accept.** Enumerates j<=ceil((n-2)/c); group maxima sum to t_n+t_(n-c)+...+t_(n-(j-1)c). Full groups leave i=n-jc; a partial last group leaves n-jc<i<=min(c,n-(j-1)c-1). States above c need only satisfy i+cj<=n. O(n^2) transition work and O(n^2/c+n) storage suffice. For n<=c, the result is tn.

**Review.** all checks passed

## N7 · Empty batches separate from passenger batches

*reformulation · depth 6 · source: exploration · routes: N3 + N4 + N5*

**Statement.** Batches without preparatory passengers can precede all other batches at unchanged cost. Thus F(i,j)=min_{0<=e<=j}(K_min(i,c)(e)+M(i,j-e)), where K_L(e) minimizes the cost of e credits from such batches using at most L returners, and M permits only passenger-carrying batches and the final crossing.

**Anchors.** fastest walkers · slow-only crossings · preparatory crossing · residual prefix

**Accept.** An empty preparatory batch removes nobody from the residual prefix, and its reserved slow-only groups are disjoint from other batches’ groups. Moving it earlier preserves returner availability. Conversely, executing an empty-batch plan and then a passenger-carrying plan realizes each candidate in the minimum. Credits count the slow-only crossings served.

**Review.** all checks passed

## N8 · Empty replenishment is unbounded knapsack

*algorithm · depth 7 · source: exploration · routes: N3 + N7*

**Statement.** With Sk=sum_{r=1}^k tr, K_L(0)=0. For e>0, K_L(e)=min_{2<=k<=min(L,e+1)}(K_L(e-k+1)+Sk+tk). Each empty preparatory batch is therefore an unlimited knapsack item of credit weight k-1 and cost Sk+tk.

**Anchors.** fastest walkers · return credits · empty preparatory crossing · minimum total time

**Accept.** Establishes these minima for the needed limits L and credit totals, with unattainable totals excluded. Equivalent unbounded-knapsack computations count, including memoized recurrences or bottom-up methods. One implementation introduces items by increasing L and relaxes credit totals increasingly. Only totals through ceil((n-2)/c) are needed; prefix-limit answers can be consumed before retaining the final K_c array.

**Review.** all checks passed

## N9 · Passenger counts determine mixed credits

*key_property · depth 7 · source: exploration · routes: N5 + N7*

**Statement.** For i>c, if M(i,b) ends with m walkers and uses q passenger-carrying preparatory crossings, then i=m+q(c-1)-b and 2<=m<=c. Fixing m and q therefore determines the starting residual prefix i from the mixed-batch credit total b.

**Anchors.** bridge capacity · permanent passengers · final crossing · residual prefix

**Accept.** A full k-returner preparatory crossing removes c-k permanent walkers and supplies k-1 credits; their sum is c-1. Summing over q crossings gives the identity. The last passenger-carrying preparatory crossing starts with a prefix larger than c and leaves at least two walkers.

**Review.** all checks passed

## N10 · Cardinality partition of passenger batches

*algorithm · depth 8 · source: exploration · routes: N3 + N7 + N9*

**Statement.** For each final prefix m, set A(0,0)=tm. For q>=1 and b>=0, let i=m+q(c-1)-b>c. Then A(q,b)=ti+min_k(Sk+A(q-1,b-k+1)), where 1<=k<=min(c-1,b+1). Impossible states are excluded.

**Anchors.** fastest walkers · preparatory crossing · return credits · minimum total time

**Accept.** A(q,b) minimizes the mixed-only cost with q preparatory crossings, b credits, and final prefix m. Retaining q+b<=floor((n-m)/(c-1)) and b<=ceil((n-2)/c) suffices: these bounds are necessary to fit the reserved slow-only groups within n walkers. The recurrence can use only the previous q row. Across m, its transitions take O(n^2) time.

**Review.** all checks passed

## N11 · Combine knapsack with cardinality partitions

*algorithm · depth 9 · source: exploration · routes: N1 + N4 + N8 + N10*

**Statement.** For n>c, let Pp=sum_{h=0}^{p-1}t_(n-hc). Minimize Pp+A(q,b)+Kc(p-b) over states with i=m+q(c-1)-b>c, integral p=(n-i)/c, and p>=b. Also minimize Pp+ti+Ki(p) for 2<=i<=c, p=ceil((n-i)/c). For n<=c, output tn.

**Anchors.** minimum total time · entire group · bridge capacity

**Accept.** The first minimum covers full slow-only groups together with passenger-carrying batches and independent empty preparatory batches. The second covers plans with no preparatory passengers, including a partial last slow-only group. The all-shuttle solution appears with p=b=0. Prefix sums, one knapsack array, and two partition rows provide an O(n)-space realization.

**Review.** all checks passed

## N12 · Unified prefix order for permanent transfers

*key_property · depth 5 · source: exploration · routes: N2 + N3 + N4*

**Statement.** Some optimum has a representation in which permanent transfers are consecutive largest blocks of a shrinking globally sorted prefix. Each such crossing also carries fastest helpers, filling the bridge or including the entire remaining prefix; crossings without permanent transfers are separate replenishment batches.

**Anchors.** sorted crossing times · permanent passengers · fastest walkers · bridge capacity

**Accept.** With m remaining and s permanent passengers, 1<=s<=min(c,m), there are h=min(c,m)-s helpers with times t1,...,th. The crossing and their eventual returns cost tm+Sh. This is an accounting decomposition, not chronological removal. Exchanges from batch normal form must justify combining slow-only groups and passenger-carrying crossings into this single prefix order.

**Review.** failed: atomic — Putting all permanent transfers into one largest-block accounting order and obtaining the fastest-helper/fullness normal form are separately establishable transformations, particularly around a partial slow-only block. Split the ordering claim from helper allocation and charging.

## N13 · Realizability of completed credit plans

*reformulation · depth 8 · source: exploration · routes: N12 + N7 + N8*

**Statement.** Complete normalized prefix-transfer plans, supplemented by empty replenishment batches to supply the required returns, can be reordered into legal torch schedules without changing their charged costs. Thus negative balances in accounting order do not make an otherwise completed plan infeasible.

**Anchors.** torch · crosses back · return credits · empty preparatory crossing

**Accept.** Define balance as charged individual returns minus forward crossings. A productive h-helper crossing contributes h-1. An empty k-returner batch contributes k-1 and costs tk+Sk: all k participants return. A terminal productive balance a<=-1 is completed to balance -1 for Kc(-1-a), using N8. Establish realizability by batch reordering; negative accounting prefixes need not be executable, and representations need not be unique.

**Review.** all checks passed

## N14 · Bounded return-balance range

*key_property · depth 9 · source: exploration · routes: N12 + N13 + N8*

**Statement.** Let d be the number of walkers permanently transferred and a the signed return balance. Some optimal prefix-accounting plan satisfies -floor(d/c)-[d=n] <= a <= ceil((n-d)/c)-1 at every state, so balances outside this interval may be omitted without losing the optimum.

**Anchors.** permanent passengers · return credits · bridge capacity · remaining walkers

**Accept.** Establish the lower bound from fullness of nonterminal prefix transfers and the possible final partial transfer. Establish the upper bound by normalizing away return capacity beyond what remaining capacity-sized groups need. The upper bound need not hold for arbitrary feasible schedules. Equivalent shifted credit conventions count if they preserve this admissible state set or establish another sufficient range with the required complexity.

**Review.** failed: atomic — The lower bound is fullness-based accounting, whereas the upper bound requires an independent optimality-preserving surplus-return normalization. Move the elementary lower-bound accounting alongside the prefix-transfer definitions and retain the upper-bound normalization separately, or split the two bounds.

## N15 · Permanent-progress signed-balance dynamic program

*algorithm · depth 10 · source: exploration · routes: N1 + N8 + N12 + N13 + N14*

**Statement.** Minimize charged crossing costs over permanent-progress and signed-return-balance states using largest-block transfers with fastest helpers. After all walkers have permanent transfers, add the cheapest independent replenishment that leaves one unreturned final forward crossing. The minimum completed cost is the answer.

**Anchors.** minimum total time · entire group · return credits · crossing times

**Accept.** Initialize D(0,0)=0. For m=n-d, r=min(c,m), choose 1<=s<=r, set h=r-s, and relax D(d+s,a+h-1) with D(d,a)+tm+Sh within N14’s range. Output min_{a<=-1}(D(n,a)+Kc(-1-a)); when c>=n, output tn. Optionally discard a>ℓ if D(d,a)>=D(d,ℓ)+Kc(a-ℓ), where ℓ is that row’s lower bound. Prefix sums and knapsack give O(n²) time and O(n²/c+n) space.

**Review.** all checks passed

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 + N5 + N6 \| N1 + N2 + N3 + N4 + N5 + N7 + N8 + N9 + N10 + N11 \| N1 + N2 + N3 + N4 + N5 + N7 + N8 + N12 + N13 + N14 + N15

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N6 \| N11 \| N15

## Hazards (END → program)

- **H1** Accumulated crossing costs can exceed 32-bit range. Arithmetic involving unreachable states must not overflow or produce values that incorrectly improve a feasible answer. *Check:* Verify sufficient range for accumulated costs, sums, and transition arithmetic, for example 64-bit integers. Individual times may remain 32-bit. Unreachable states may be omitted, guarded, or represented by safe sentinels whose arithmetic cannot corrupt the minima.
- **H2** When c>=n, the answer is the largest crossing time. In general, infeasible configurations must not contribute to the reported optimum. *Check:* Verify the maximum-time answer for c>=n, whether obtained directly or through the general algorithm. Feasibility may be enforced through state definitions, transitions, or final settlement. An explicit early return or infinity initialization is unnecessary; signed intermediate credit deficits are legitimate if the final represented schedule is feasible.

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4, N5, N6

Normalize a schedule into batches: one crossing carries a prefix of the fastest remaining walkers, who return one at a time while enabling slow-only crossings. After sorting, slow-only crossings can receive the largest walkers first; a two-dimensional DP matches these crossings with batches that supply their returners. The DP has O(n^2) total transition work and O(n^2/c+n) storage, uses 64-bit costs, and directly handles c>=n.

New nodes: N1, N2, N3, N4, N5, N6 · judge: AC on 104 tests, slowest 0.12s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N2, N3, N4, N5, N7, N8, N9, N10, N11

Separate empty replenishment batches from batches that carry permanent passengers: empty batches commute to the beginning and form an independent unbounded knapsack. For the remaining batches, fixing the final prefix and number of preparatory crossings makes the current prefix size a function of the accumulated return credits, permitting a rolling cardinality-partition DP. Combining these two optimizations with the largest slow-only groups gives O(n^2) time and O(n) auxiliary space.

New nodes: N7, N8, N9, N10, N11 · judge: AC on 104 tests, slowest 0.081s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N2, N3, N4, N5, N7, N8, N12, N13, N14, N15

Sort the walkers and represent permanent transfers as largest blocks of a shrinking prefix, charging each crossing together with its fastest helpers’ eventual individual returns. Use a DP over permanent progress and signed return balance, then settle its terminal deficit with the existing unbounded knapsack for empty replenishment batches. Batch reordering justifies this accounting representation, while bounded balance ranges give O(n²) time and O(n²/c+n) space.

New nodes: N12, N13, N14, N15 · judge: AC on 104 tests, slowest 0.2s · program: `paths/P3.cpp` · None submission(s)

## Exploration

Finished: True · 2 submissions · reason: Two accepted approaches cover the direct prepaid-crossing DP and a structurally different factorization into empty-batch knapsack and rolling cardinality partitions. I do not have another genuinely different characterization with a correct implementation that fits the limits.

Ideas the explorer considered and dropped:

- A one-dimensional recurrence assigning consecutive slow walkers to each entire batch is not correct: slow-only groups and preparatory groups from different batches may need to interleave in sorted order. For c=3 and times 10,10,15,15,15,100,100,100,100,100,100, two mixed batches achieve 285, while the contiguous-batch restriction misses that arrangement.
- Dijkstra over the exact subset of walkers on each bank models the mechanics directly but requires exponentially many states for n up to 10000.
- Always using one fastest walker as the sole returner is suboptimal even on Sample 1; multiple returners must be represented.
- Greedy selection or a convex-penalty optimization of empty batches is unjustified: their credit costs are an unbounded knapsack and need not be convex. With three unit-time returners, minimum costs for zero through three credits are 0,3,4,7.
- Monge or min-plus optimizations of the existing partition recurrence might improve performance, but they would optimize an already established algorithm rather than provide another independently developed output characterization.

## Review

END ok: True — All three routes supply their optimization recurrences, terminal output rules, feasible domains, and sufficient bounds for an implementation within the limits. P3's transitions and settlement agree with the reference solution.

Hazards ok: True — H1 covers accumulated-cost range and unreachable-state arithmetic. H2 covers the c>=n boundary and final feasibility without incorrectly forbidding signed intermediate deficits or requiring a particular implementation.

**Advisories.**

- N1 (bundles claims a solver can have separately; split it): The crossing/torch mechanics and the justification for sorting are independently establishable claims. Separate the trip model from invariance under relabeling and sorted indexing.
- N2 (bundles claims a solver can have separately; split it): Single-person returns, regrouping excursions into batches, and choosing the fastest remaining returners are distinct normalization steps; a solver can establish the first without the others. Split these exchange lemmas so a partial normalization argument has its own location.
- N3 (comes with its prerequisite; merge it): The k-1 interleaved crossings are already specified in N2, and the stated charge follows immediately from N1's crossing cost and N2's individual returns. Fold this accounting into the batch-normal-form acceptance criteria or the batch-cost definitions used by the DP.
- N4 (bundles claims a solver can have separately; split it): Assigning the largest walkers to capacity-sized slow-only blocks and normalizing preparatory crossings to full crossings of a residual prefix require distinct exchanges. Separate the slow-only allocation lemma from preparatory fullness/prefix normalization, placing availability of the original fastest helpers with the latter.
- N12 (bundles claims a solver can have separately; split it): Putting all permanent transfers into one largest-block accounting order and obtaining the fastest-helper/fullness normal form are separately establishable transformations, particularly around a partial slow-only block. Split the ordering claim from helper allocation and charging.
- N14 (bundles claims a solver can have separately; split it): The lower bound is fullness-based accounting, whereas the upper bound requires an independent optimality-preserving surplus-return normalization. Move the elementary lower-bound accounting alongside the prefix-transfer definitions and retain the upper-bound normalization separately, or split the two bounds.
- the editorial's approach is not among the paths: P3 matches the reference algorithm, but there is no END route a direct editorial solver would establish: P3 unnecessarily requires the alternative F recurrence in N5 and the F/M factorization in N7, as well as the segregated batch-development chain. Add a direct route through individual-return/fast-helper normalization, unified prefix accounting, replenishment knapsack, realizability, balance bounds, and N15. Separately, the supplied editorial's package formula omits one t_(h+1): N8 correctly uses t_k+S_k for k-1 credits, matching the reference's t[helpers]+fast_prefix[helpers+1].
- order: Split the independent normalization claims in N1, N2, N4, and N12; fold N3's immediate accounting into the relevant batch definitions. Separate N14's elementary lower-bound bookkeeping from its substantive upper-bound normalization. Give the reference/editorial DP a direct derivation and END route that does not require constructing the alternative F and M dynamic programs.

**Builder's notes.** N14 now states only the optimality-preserving balance-range lemma; the optional same-progress dominance test has moved to N15's acceptance criteria. N13 now focuses on realizability, with elementary balance accounting in its acceptance criteria. The suggested node splits, merges, and direct editorial END route require structural changes forbidden in this text-only revision, so they have not been performed. P3 therefore retains its indirect dependency chain through the alternative batch-DP claims. The corrected empty-package cost tk+Sk for k-1 net credits is retained.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `620faf963e869d4c` | 3 | 5 | revise |
| 2 | `5a1ac020f0903ec7` | 0 | 6 | accept |
| 3 | `4c8de99ee27a49d1` | 1 | 7 | revise |
| 4 | `99253eadd1c82ba4` | 0 | 8 | revise |
