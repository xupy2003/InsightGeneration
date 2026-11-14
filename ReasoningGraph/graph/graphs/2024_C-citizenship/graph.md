# Reasoning graph · Citizenship (2024/C-citizenship)

status **accepted** · version `100d025f426a9eb9` · 21 nodes · 7 END route(s) · 3 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 4 review round(s)

**Route.** P1: Encode dates as integer days and mark each 365-day window invalid when it contains more than 365-d absent days. P2: After the final trip, feasibility is monotone if the application date is advanced by exactly one year: one old block is discarded and an entirely present block is added. P3: For a fixed month/day, only the most recent invalid annual block matters: after the final trip, every later application with that month/day includes this block until it becomes more than y years old. P4: Compress the invalid 365-day window endpoints into maximal intervals. P5: Treat each of the y annual absence counts as a piecewise-affine function of the application date. P6: Represent invalid annual-window endpoints as a bitset. P7: An annual window is invalid precisely when it contains a group of 366-d consecutive absent days in the chronologically sorted absence list.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Application-relative annual residency blocks | statement |
| N2 | 2 | reformulation | Invalid individual annual window | N1 |
| N3 | 2 | key_property | Finite application search horizon | N1 |
| N4 | 3 | key_property | Aligned annual-block validity summaries | N2 |
| N5 | 4 | algorithm | Minimum qualifying aligned endpoint | N3 + N4 |
| N6 | 2 | key_property | Yearly monotonicity after final trip | N1 |
| N7 | 3 | algorithm | Binary search each calendar position | N2 + N3 + N6 |
| N8 | 3 | key_property | Latest invalid window determines eligibility | N2 + N6 |
| N9 | 4 | algorithm | Direct thresholds for calendar positions | N8 |
| N10 | 3 | key_property | Sparse annual absence slope changes | N2 |
| N11 | 4 | key_property | Few invalid endpoint intervals | N10 |
| N12 | 5 | reformulation | Shifted intervals forbid application dates | N11 |
| N13 | 6 | algorithm | Forbidden-interval coverage scan | N3 + N12 |
| N14 | 4 | key_property | Shared event partition for annual counts | N10 |
| N15 | 5 | reformulation | Three affine feasibility envelopes | N14 |
| N16 | 6 | algorithm | Sweep affine date segments | N3 + N15 |
| N17 | 3 | key_property | Concatenating annual-block rejection sets | N2 |
| N18 | 4 | algorithm | Doubling annual-block rejection sets | N3 + N17 |
| N19 | 3 | reformulation | Consecutive absence witnesses | N2 |
| N20 | 4 | key_property | Residue maxima over absence witnesses | N19 |
| N21 | 5 | algorithm | Absence-witness threshold construction | N8 + N20 |
| END | | | complete solution | N1 + N2 + N3 + N4 + N5 \| N1 + N2 + N3 + N6 + N7 \| N1 + N2 + N6 + N8 + N9 \| N1 + N2 + N3 + N10 + N11 + N12 + N13 \| N1 + N2 + N3 + N10 + N14 + N15 + N16 \| N1 + N2 + N3 + N17 + N18 \| N1 + N2 + N6 + N8 + N19 + N20 + N21 |

## N1 · Application-relative annual residency blocks

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** Using fixed-calendar serial days, applying on T tests exactly y disjoint blocks [T-365k,T-365(k-1)-1], k=1,...,y. Presence in each block is the number of its days outside the union of inclusive travel intervals; each block must contain at least d present days.

**Anchors.** application date · 12-month periods · out of the country · d days

**Accept.** Use any consistent serial-day encoding with the supplied month lengths and 365 days per year. Trips mark both endpoints absent; unlisted days, including the past before the first trip, are present. The application day is excluded, and annual boundaries are spaced exactly 365 days apart.

**Review.** all checks passed

## N2 · Invalid individual annual window

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** Let P(t) count listed absent days strictly before t. A 365-day block ending immediately before T is invalid exactly when P(T)-P(T-365)>365-d.

**Anchors.** d days · absent days · 365-day block

**Accept.** Equivalently, compute a rolling 365-day absence count and compare it to the allowed 365-d absences. Equality is valid because the requirement is at least d days present. Prefix counts are zero before the earliest listed absence, regardless of the chosen day origin.

**Review.** all checks passed

## N3 · Finite application search horizon

*key_property · depth 2 · source: exploration · routes: N1*

**Statement.** If L is the final absent day, the earliest qualifying application after L lies in [L+1,L+1+365y]. At the upper endpoint all y required annual blocks lie strictly after L and therefore contain only present days.

**Anchors.** last date of the input · earliest date · y consecutive years

**Accept.** Any sufficient inclusive horizon derived from the absence-free future is acceptable. The displayed bound is 365y days after L+1, or 365y+1 days after L; its maximum increment from L is 365001 days. The extra day cannot generally be omitted when d=365.

**Review.** all checks passed

## N4 · Aligned annual-block validity summaries

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** For each residue modulo 365, annual windows form an ordered sequence. A date qualifies exactly when its last y windows are valid, equivalently when its consecutive-valid suffix has length at least y. Sliding invalid counts or consecutive-valid run lengths maintain this condition incrementally.

**Anchors.** y consecutive years · aligned annual windows · invalid-window counts · consecutive valid blocks

**Accept.** Let B(T) indicate an invalid window. Maintain F(T)=F(T-365)+B(T)-B(T-365y) and test F(T)=0; alternatively, set R(T)=0 on an invalid window and R(T)=min(y,R(T-365)+1) otherwise, testing R(T)=y. These are distinct summaries of the same aligned suffix. Initialize pre-travel history as valid: B=F=0 and R=y, or scan enough preceding valid blocks.

**Review.** all checks passed

## N5 · Minimum qualifying aligned endpoint

*algorithm · depth 4 · source: exploration · routes: N3 + N4*

**Statement.** Evaluate the aligned annual-window summaries through a guaranteed qualifying horizon. Output the minimum endpoint T>L whose last y annual windows are all valid, converted to a calendar date.

**Anchors.** earliest date · aligned annual windows · calendar date

**Accept.** Prefix or rolling absence counts supply window validity. Update invalid-window counts or consecutive-good runs, either chronologically or independently along each residue chain, and minimize eligible endpoints. Any consistent day origin is allowed. For example, origin 0000-01-01 gives fewer than 2.2 million endpoints through L+1+365y; linear time and space in this span fit. Initialize each chain far enough back, or treat pre-travel blocks as valid.

**Review.** all checks passed

## N6 · Yearly monotonicity after final trip

*key_property · depth 2 · source: exploration · routes: N1*

**Statement.** Let L be the final absent day. For T>L, advancing from T to T+365 removes the oldest tested block and adds [T,T+364], which is entirely present. Feasibility is therefore monotone along each residue class modulo 365 after the final trip.

**Anchors.** last date of the input · 12-month periods · application date

**Accept.** Recognize that monotonicity holds for one-year jumps, not necessarily for consecutive days. All retained blocks are identical, and the new block has 365 present days because it starts after L.

**Review.** all checks passed

## N7 · Binary search each calendar position

*algorithm · depth 3 · source: exploration · routes: N2 + N3 + N6*

**Statement.** For each residue modulo 365, take its first date T>L and binary-search the smallest k in [0,y] such that T+365k has no invalid required block. Output the minimum resulting date over all residues.

**Anchors.** earliest date · residue modulo 365 · y consecutive years

**Accept.** Use absence prefix differences to check each of the y annual blocks. Each residue's feasibility predicate is monotone, and k=y is feasible because every required day is after L. With origin 0000-01-01, O(L+365y log(y+1)) time and O(L) space fit the limits; translated encodings are equivalent.

**Review.** all checks passed

## N8 · Latest invalid window determines eligibility

*key_property · depth 3 · source: exploration · routes: N2 + N6*

**Statement.** For residue r modulo 365, let b_r be its latest invalid annual-window endpoint, if one exists. An application T>L with residue r qualifies exactly when b_r does not exist or T>=b_r+365y.

**Anchors.** latest invalid annual window · y consecutive years · application date

**Accept.** No annual window ending after L+365 can be invalid. For T>L, every later endpoint with the same residue is valid, so b_r<=T. This latest bad endpoint lies among the y required endpoints exactly when T<b_r+365y; earlier bad endpoints cannot impose a stronger restriction.

**Review.** all checks passed

## N9 · Direct thresholds for calendar positions

*algorithm · depth 4 · source: exploration · routes: N8*

**Statement.** Find b_r for every residue by evaluating annual-window absence counts through L+365. Let t_r be the first day after L with residue r. Output the minimum over r of t_r if b_r is absent, otherwise max(t_r,b_r+365y).

**Anchors.** earliest date · calendar positions · latest invalid endpoints

**Accept.** Prefix sums or rolling annual absence counts locate the latest invalid endpoint of each residue. The threshold and t_r share the same residue, so their maximum is the first qualifying date of that residue. With origin 0000-01-01, O(L+365) time suffices, independently of y; equivalent shifted encodings are allowed.

**Review.** all checks passed

## N10 · Sparse annual absence slope changes

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** The annual absence count W(T)=P(T)-P(T-365) is affine on integer segments separated only by trip starts, days after trip ends, and their 365-day shifts.

**Anchors.** trip starts · trip ends · annual absence count · slope changes

**Accept.** With A(t) the absence indicator, moving the window gives W(T+1)-W(T)=A(T)-A(T-365). The two indicators change only at inclusive trip boundaries and their one-year shifts. This identity proves the sparse piecewise-affine structure; merely updating a rolling count does not by itself establish that structure.

**Review.** all checks passed

## N11 · Few invalid endpoint intervals

*key_property · depth 4 · source: exploration · routes: N10*

**Statement.** The invalid annual-window endpoints form O(n) maximal integer intervals: the annual absence count is affine between its O(n) slope changes, and an affine segment crosses the invalidity threshold at most once.

**Anchors.** invalid annual-window endpoints · trip boundaries · 365-d

**Accept.** There are at most 4n boundary events before merging equal dates. On each resulting segment, the absence count is constant or monotone, so its comparison with 365-d changes at most once. Scanning daily counts or solving threshold crossings analytically both obtain these intervals.

**Review.** all checks passed

## N12 · Shifted intervals forbid application dates

*reformulation · depth 5 · source: exploration · routes: N11*

**Statement.** An invalid annual-window endpoint interval [a,b] forbids application dates in [a+365j,b+365j] for j=0,...,y-1. The union of these shifted intervals over all maximal invalid endpoint intervals is exactly the set of nonqualifying application dates.

**Anchors.** application dates · invalid endpoint intervals · y consecutive years

**Accept.** An application T uses endpoints T-365j. Thus one required block is invalid exactly when T belongs to a shifted invalid interval. Union coverage, rather than interval lengths or summed absence across different years, determines rejection.

**Review.** all checks passed

## N13 · Forbidden-interval coverage scan

*algorithm · depth 6 · source: exploration · routes: N3 + N12*

**Statement.** Compute maximal invalid endpoint intervals, shift each by 365j for j=0,...,y-1, and restrict them to [L+1,L+1+365y]. Output the first date in this range not covered by any shifted interval.

**Anchors.** earliest date · forbidden intervals · coverage

**Accept.** Daily prefix counts can generate the invalid intervals through L+365. Range additions into a difference array followed by a prefix scan find the first uncovered date in O(L+ny+365y) time and O(L+365y) space with origin 0000-01-01. Sorting and merging forbidden intervals, or using translated day coordinates, are also valid.

**Review.** all checks passed

## N14 · Shared event partition for annual counts

*key_property · depth 4 · source: exploration · routes: N10*

**Statement.** All y annual absence counts for application T are simultaneously affine between consecutive dates obtained by shifting trip boundaries by 365j, j=0,...,y. There are O(ny) such dates; each count has slope -1, 0, or 1 on every resulting segment.

**Anchors.** annual blocks · trip boundaries · application date · shared event dates · three possible slopes

**Accept.** Write W_j(T)=P(T-365j)-P(T-365(j+1)) for j=0,...,y-1. A trip [a,b] changes its incoming slope at a+365j and b+1+365j, and its outgoing slope at a+365(j+1) and b+1+365(j+1). Their union gives a shared event partition. Each slope is A(T-365j)-A(T-365(j+1)), a difference of binary indicators, and therefore belongs to {-1,0,1}.

**Review.** failed: atomic — The common shifted-boundary event partition and the restriction to three possible slopes are separately recognizable claims. Move the slope restriction into N10, where it follows directly from the indicator-difference identity, or separate it from the shared-partition claim.

## N15 · Three affine feasibility envelopes

*reformulation · depth 5 · source: exploration · routes: N14*

**Statement.** Between shared event dates, write each annual absence count as W_j(T)=s_jT+c_j. Let M_s=max c_j among slope-s blocks. With K=365-d, every block qualifies exactly when M_0<=K and M_-1-K<=T<=K-M_1, omitting conditions for empty groups.

**Anchors.** 365-d · annual absence counts · feasible dates

**Accept.** For slope zero, the largest count must not exceed K. Slope -1 imposes a lower date bound, and slope +1 imposes an upper date bound. Taking each group's maximum intercept simultaneously enforces every annual block's inequality.

**Review.** all checks passed

## N16 · Sweep affine date segments

*algorithm · depth 6 · source: exploration · routes: N3 + N15*

**Statement.** Sweep shifted trip-boundary events after L, maintaining intercept maxima for all three slope groups. In each event-free integer-date segment within [L+1,L+1+365y], intersect its dates with the bounds imposed by these maxima. Output the first date in the first nonempty intersection.

**Anchors.** earliest date · slope events · feasible date segments

**Accept.** Initialize counts and slopes at L+1. At each event, preserve affected counts while changing slopes and intercepts. Ordered sets can maintain the three maxima. Process simultaneous changes consistently; segments may end one day before the next event. With origin 0000-01-01, O(L+ny log(ny+1)) time and O(L+ny) space suffice. Translated coordinates and equivalent maximum-maintenance structures are allowed.

**Review.** all checks passed

## N17 · Concatenating annual-block rejection sets

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** Let D_k(T) mean that some endpoint among T,T-365,...,T-365(k-1) is invalid, with D_0(T)=false. Then D_{a+b}(T)=D_a(T) OR D_b(T-365a). Thus rejection sets for longer sequences of annual blocks can be composed by shifting and union.

**Anchors.** y consecutive years · invalid endpoints · rejection sets

**Accept.** Split a+b required annual windows into the newest a and the remaining b. The second part rejects exactly the dates in a 365a-day translation of the b-block rejection set. Equal-length composition doubles the number of tested annual blocks. A left shift realizes the translation in a day-indexed bitset.

**Review.** all checks passed

## N18 · Doubling annual-block rejection sets

*algorithm · depth 4 · source: exploration · routes: N3 + N17*

**Statement.** Construct the rejection set for y annual blocks by binary doubling and composition: combine a-block rejection dates with a 365a-day translation of b-block rejection dates. Output the earliest date in [L+1,L+1+365y] outside the resulting set.

**Anchors.** earliest date · rejection sets · binary doubling

**Accept.** A bitset is one representation: union is bitwise OR and translation is a left shift. Build power-of-two block lengths and compose the binary expansion of y. With origin 0000-01-01, negative-day rejection bits are zero; truncate beyond the horizon. Daily initialization, word-parallel composition, and a linear final search take O(L+365y+(L+365y)log(y+1)/64) time and O(L+365y) space.

**Review.** all checks passed

## N19 · Consecutive absence witnesses

*reformulation · depth 3 · source: exploration · routes: N2*

**Statement.** Let p_0<p_1<... be all absent days and K=365-d. An annual-window endpoint T is invalid exactly when some group of K+1 consecutive absent days satisfies p_{i+K}+1<=T<=p_i+365. An interval with reversed endpoints contributes nothing.

**Anchors.** absent days · annual-window endpoints · 365-d

**Accept.** More than K absences in [T-365,T-1] contain K+1 consecutive entries of the global absence list. Conversely, the two inequalities put the entire group inside that annual window. The strict upper-day exclusion accounts for p_{i+K}+1.

**Review.** all checks passed

## N20 · Residue maxima over absence witnesses

*key_property · depth 4 · source: exploration · routes: N19*

**Statement.** For each residue r, an interval [a,b] contributes z=b-((b-r) mod 365) when z>=a. The latest invalid annual-window endpoint with residue r is the maximum such contribution over all consecutive-absence witness intervals; if there is no contribution, no such endpoint exists.

**Anchors.** witness intervals · latest invalid endpoints · residue modulo 365 · maximum contribution

**Accept.** Use least-nonnegative remainders. Witness intervals have increasing right endpoints, so reverse traversal is one efficient method: the first interval containing an unassigned residue supplies its maximum contribution. No earlier right endpoint can yield a larger same-residue date. Each witness interval spans at most 365 dates, hence at most two residue ranges. Other efficient maximum-extraction methods are equivalent.

**Review.** all checks passed

## N21 · Absence-witness threshold construction

*algorithm · depth 5 · source: exploration · routes: N8 + N20*

**Statement.** Find each residue's latest invalid annual-window endpoint b_r from the nonempty consecutive-absence witness intervals. For each residue, take its first date T>L satisfying T>=b_r+365y, omitting the bound when no such endpoint exists. Output the minimum resulting date.

**Anchors.** earliest date · absence witnesses · latest invalid endpoints

**Accept.** One efficient realization scans witness intervals in decreasing right-endpoint order, maintaining an ordered set of unassigned residues. Split each interval into at most two residue ranges and assign each residue once. With M absent days, this takes O(M log 365) time and O(M+365) space. Other efficient methods extracting the same latest endpoints also establish this construction.

**Review.** all checks passed

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 + N5 \| N1 + N2 + N3 + N6 + N7 \| N1 + N2 + N6 + N8 + N9 \| N1 + N2 + N3 + N10 + N11 + N12 + N13 \| N1 + N2 + N3 + N10 + N14 + N15 + N16 \| N1 + N2 + N3 + N17 + N18 \| N1 + N2 + N6 + N8 + N19 + N20 + N21

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N5 \| N7 \| N9 \| N13 \| N16 \| N18 \| N21

## Hazards (END → program)

- **H1** February always has 28 days: ordinary Gregorian leap-year rules must not be used. *Check:* Date encoding and decoding use exactly the supplied month lengths and 365 days per year.
- **H2** Trip endpoints are both absent, residency blocks exclude the application day, and the answer must be strictly after the final input date. *Check:* Mark [a,b] inclusively, count [T-365k,T-365(k-1)-1], and only accept T greater than the last input endpoint.
- **H3** The answer can be beyond year 5000, and required blocks can extend before year 0000, where there are no listed absences. Output must use YYYY-MM-DD. *Check:* Support possible answers through L+1+365y and treat pre-0000 days as having no listed absences. Print exactly four zero-padded year digits, two zero-padded month digits, and two zero-padded day digits, separated by hyphens.

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4, N5

Encode dates as integer days and mark each 365-day window invalid when it contains more than 365-d absent days. The number of invalid windows among an application's y annual blocks has a constant-time recurrence along each residue class modulo 365, so a chronological scan finds the first valid application in O(L+365y) time, where L is the last input day. The scan is bounded because applying 365y days after the first day following the final trip always succeeds.

New nodes: N1, N2, N3, N4, N5 · judge: AC on 40 tests, slowest 0.018s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N2, N3, N6, N7

After the final trip, feasibility is monotone if the application date is advanced by exactly one year: one old block is discarded and an entirely present block is added. For each of the 365 month/day positions, binary-search the first feasible year using direct prefix-sum checks of the y blocks, then choose the earliest of those dates. This costs O(L+365y log(y+1)) time.

New nodes: N6, N7 · judge: AC on 40 tests, slowest 0.019s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N2, N6, N8, N9

For a fixed month/day, only the most recent invalid annual block matters: after the final trip, every later application with that month/day includes this block until it becomes more than y years old. Scan all possibly invalid annual-window endpoints and retain their latest endpoint for each residue modulo 365. Each residue then gives its earliest application directly, without binary search or maintaining a y-window count.

New nodes: N8, N9 · judge: AC on 40 tests, slowest 0.016s · program: `paths/P3.cpp` · None submission(s)
### P4 · N1, N2, N3, N10, N11, N12, N13

Compress the invalid 365-day window endpoints into maximal intervals. Each invalid interval forbids y shifted intervals of application dates, so range-add these forbidden intervals and return the first uncovered date after the final trip. There are only O(n) invalid intervals because the annual absence count changes slope only at travel boundaries and their one-year shifts, giving O(L+ny+365y) time.

New nodes: N10, N11, N12, N13 · judge: AC on 40 tests, slowest 0.015s · program: `paths/P4.cpp` · None submission(s)
### P5 · N1, N2, N3, N10, N14, N15, N16

Treat each of the y annual absence counts as a piecewise-affine function of the application date. Its slope is always -1, 0, or 1, and changes only at shifted travel boundaries; between events, the maximum intercept in each slope group gives a simple interval of feasible dates. Sweeping O(ny) events with ordered sets finds the earliest feasible segment in O(L+ny log(ny)) time.

New nodes: N14, N15, N16 · judge: AC on 40 tests, slowest 0.293s · program: `paths/P5.cpp` · None submission(s)
### P6 · N1, N2, N3, N17, N18

Represent invalid annual-window endpoints as a bitset. The set of dates rejected by a+b consecutive annual blocks is the union of the dates rejected by the first a blocks and a 365a-day shift of the dates rejected by b blocks. Binary doubling and bitset OR/shift operations therefore construct all rejected application dates in O(L+(L+365y) log(y+1)/64) time, after which the first unmarked permitted date is the answer.

New nodes: N17, N18 · judge: AC on 40 tests, slowest 0.017s · program: `paths/P6.cpp` · None submission(s)
### P7 · N1, N2, N6, N8, N19, N20, N21

An annual window is invalid precisely when it contains a group of 366-d consecutive absent days in the chronologically sorted absence list. Each such group gives an interval of invalid window endpoints; processing these intervals by decreasing right endpoint determines the latest invalid endpoint for each calendar position. Apply the previously established latest-invalid threshold to obtain the answer, using an ordered set to assign each of the 365 residues only once.

New nodes: N19, N20, N21 · judge: AC on 40 tests, slowest 0.013s · program: `paths/P7.cpp` · None submission(s)

## Exploration

Finished: True · 9 submissions · reason: Seven genuinely different approaches have been accepted: annual-residue rolling counts, per-calendar-position binary search, latest-invalid thresholds, forbidden-interval coverage, affine event sweeping, bitset doubling, and consecutive-absence witnesses. I do not have another distinct approach that I believe both correct and fast enough; the remaining variants reuse claims already represented in the graph.

Ideas the explorer considered and dropped:

- Directly testing every annual block on every candidate date, maintaining consecutive valid-year runs, or using residue queues re-evaluates the existing chronological scan or latest-invalid characterization without adding a distinct intermediate claim.
- Generating invalid endpoint intervals analytically at slope changes instead of scanning daily counts uses the already established slope-change and interval-union nodes; it is an alternative implementation of the same path.
- Jumping past a currently violated interval is another way to traverse the existing union of forbidden application intervals, rather than a new characterization.
- Binary search over all chronological dates is invalid: feasibility can become false again on a later day, despite being monotone under 365-day advances after the final trip.
- Checking total presence over all y years, or validating trips independently, loses the separate per-year requirement and the accumulation of multiple trips within one annual block.
- FFT-style convolution could evaluate annual rejection counts, but adds substantial implementation and runtime overhead compared with the accepted recurrence and bitset composition, without a useful new structural characterization.

## Review

END ok: True — All seven END routes supply the residency model, the necessary rejection or eligibility characterization, and a sufficiently efficient output algorithm. Initialization before the recorded history, finite bounds where needed, and efficient event or witness processing are covered by the nodes and their acceptance criteria.

Hazards ok: True — H1–H3 cover the fixed calendar, inclusive trip endpoints, exclusion of the application day, strict post-trip eligibility, pre-0000 history, extended answer range, and output formatting. The bounded day indices and counts fit signed 32-bit arithmetic; no additional essential numerical hazard is missing.

**Advisories.**

- N14 (bundles claims a solver can have separately; split it): The common shifted-boundary event partition and the restriction to three possible slopes are separately recognizable claims. Move the slope restriction into N10, where it follows directly from the indicator-difference identity, or separate it from the shared-partition claim.
- order: Minor, nonblocking cut improvement: separate N14's common event partition from its three-slope restriction, or fold the slope restriction into N10. The remaining dependency order is sound.

**Builder's notes.** N20 now states the order-independent maximum over witness intervals. Reverse traversal and first-hit assignment appear only as efficient examples in accept, so neither N20 nor N21 requires those bookkeeping choices. All node IDs, routes, END routes, and hazards are retained as required; the remaining nonblocking split/merge suggestions would change that fixed topology.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `6204b6631fa2b0a4` | 4 | 6 | revise |
| 2 | `d8f9d7b4a974644d` | 1 | 4 | revise |
| 3 | `7e36e66d0d3f71b7` | 1 | 4 | revise |
| 4 | `100d025f426a9eb9` | 0 | 2 | accept |
