# Reasoning graph · Tilting Tiles (2023/F-tilting-tiles)

status **accepted** · version `be7c696185544a59` · 18 nodes · 4 END route(s) · 6 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 2 review round(s)

**Route.** P1: After the first two perpendicular tilts, occupied cells form a corner-packed Ferrers diagram. P2: Use the same Ferrers-diagram and cyclic-permutation reduction, but combine rotation constraints without factoring their moduli. P3: There is an algebraic square root of the four-tilt permutation: reverse every occupied row, then every occupied column. P4: Again reduce each canonical seed to cycle rotation congruences, but explicitly construct the common exponent class using incremental generalized CRT and arbitrary-precision integers.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Tilts are stable line compression | statement |
| N2 | 2 | key_property | Perpendicular tilts create corner Ferrers diagrams | N1 |
| N3 | 2 | key_property | Perpendicular prefixes cover both-axis sequences | N1 |
| N4 | 3 | key_property | Corner changes have inverse tilts | N2 |
| N5 | 4 | reformulation | Aligned reachability is one revolution orbit | N4 |
| N6 | 5 | key_property | Repeated colors determine all matching exponents | N5 |
| N7 | 6 | key_property | Prime powers synchronize tile-cycle rotations | N6 |
| N8 | 7 | algorithm | Test aligned orbit by prime-power compatibility | N5 + N6 + N7 |
| N9 | 8 | algorithm | Decide using prefixes and aligned revolution orbits | N1 + N2 + N3 + N8 |
| N10 | 6 | key_property | Pairwise gcd synchronizes revolution counts | N6 |
| N11 | 6 | key_property | Distinct color periods have bounded total | N6 |
| N12 | 7 | algorithm | Decide reachability by pairwise period compatibility | N1 + N2 + N3 + N5 + N6 + N10 + N11 |
| N13 | 3 | key_property | Four tilts square two line reversals | N2 |
| N14 | 6 | reformulation | Reversal-product rotations require an even exponent | N5 + N6 + N13 |
| N15 | 7 | algorithm | Decide using even line-reversal powers | N1 + N2 + N3 + N7 + N14 |
| N16 | 6 | algorithm | Intersect tile-cycle exponent classes incrementally | N6 |
| N17 | 7 | key_property | Whole-board color repetition period | N11 |
| N18 | 8 | algorithm | Decide by exact incremental CRT | N1 + N2 + N3 + N16 + N17 |
| END | | | complete solution | N1 + N2 + N3 + N4 + N5 + N6 + N7 + N8 + N9 \| N1 + N2 + N3 + N4 + N5 + N6 + N10 + N11 + N12 \| N1 + N2 + N3 + N4 + N5 + N6 + N7 + N13 + N14 + N15 \| N1 + N2 + N3 + N4 + N5 + N6 + N11 + N16 + N17 + N18 |

## N1 · Tilts are stable line compression

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** A tilt packs each row or column against the chosen boundary while preserving tile order within that line. Consecutive tilts along one axis are equivalent to their last tilt.

**Anchors.** tilt · rows · columns · tile order

**Accept.** Recognizes that gaps disappear and tiles never pass within an affected line. Packing toward either end preserves that line's color sequence, so any uninterrupted run of horizontal or vertical tilts can be replaced by its final tilt.

**Review.** all checks passed

## N2 · Perpendicular tilts create corner Ferrers diagrams

*key_property · depth 2 · source: exploration · routes: N1*

**Statement.** Two perpendicular tilts produce a corner-packed Ferrers occupied-cell set, stable under the corresponding horizontal and vertical tilts. Further tilts preserve its row-length multiset and only change the occupied set's corner anchoring. Conversely, stability under one horizontal and one vertical tilt characterizes such corner packing.

**Anchors.** occupied cells · perpendicular tilts · corner · row lengths

**Accept.** After horizontal compression, column populations are nested; vertical compression makes them monotone and corner-aligned. The vertical-first argument is symmetric. Subsequent tilts change the occupied set's anchoring without changing its Ferrers shape, although tile colors can be permuted by a sequence of corner changes.

**Review.** all checks passed

## N3 · Perpendicular prefixes cover both-axis sequences

*key_property · depth 2 · source: exploration · routes: N1*

**Statement.** Every outcome reachable using both axes is reachable from one of the eight perpendicular two-tilt prefixes of the starting arrangement. Any reachable representative family from which all eight prefix outcomes are reachable is equally sufficient.

**Anchors.** starting arrangement · sequence of tilts · perpendicular prefixes · representative family

**Accept.** Collapse the initial same-axis run and retain its final tilt followed by the first perpendicular tilt. Trying all eight ordered prefixes suffices. Alternatively, four seeds suffice: first tilt in any direction, then up after a horizontal tilt or left after a vertical tilt. An additional opposite second-axis tilt recovers the other prefix outcome.

**Review.** all checks passed

## N4 · Corner changes have inverse tilts

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** For corner-packed Ferrers arrangements, changing horizontal or vertical anchoring is reversed by the opposite tilt, restoring every tile. The corner transitions form a four-vertex square whose reverse edges act as inverse bijections.

**Anchors.** corner · tiles · opposite tilt

**Accept.** Row or column order is preserved and the inverse tilt restores all original occupied positions. Boundary-degenerate diagrams may have coincident corner placements, but the corresponding transitions are identities; the four anchoring choices can still be treated as the vertices of a square.

**Review.** all checks passed

## N5 · Aligned reachability is one revolution orbit

*reformulation · depth 4 · source: exploration · routes: N4*

**Statement.** For a fixed Ferrers shape, align two arrangements' corner phases using reversible tilts. They are mutually reachable exactly when their aligned colorings differ by a power of the permutation induced by one complete revolution through the four corners.

**Anchors.** Ferrers shape · corner phases · complete revolution · permutation orbit

**Accept.** Cancel inverse transitions on the corner square; closed reduced walks are full revolutions. One realization normalizes by up then left and uses right, down, left, up. Any reference corner, inverse revolution, or enumeration of partial-turn anchors with target colors pulled back to reference labels is equivalent. Negative powers are reachable because the permutation is finite.

**Review.** all checks passed

## N6 · Repeated colors determine all matching exponents

*key_property · depth 5 · source: exploration · routes: N5*

**Statement.** On a cycle of the board's revolution permutation, the exponents matching the target colors are either empty or one residue class modulo the cycle's least cyclic color period, which can be smaller than its length.

**Anchors.** permutation cycle · target colors · matching exponents · least cyclic color period

**Accept.** A matching exponent exists precisely when the target cycle string is a rotation of the initial string. Once one rotation matches, every other matching shift differs from it by the least color period dividing the cycle length. Uses a consistent cycle orientation and preserves all shifts allowed by indistinguishable colors.

**Review.** all checks passed

## N7 · Prime powers synchronize tile-cycle rotations

*key_property · depth 6 · source: exploration · routes: N6*

**Statement.** A common number of board revolutions satisfies all tile-color cycle constraints exactly when, for each prime, every pair of imposed residues agrees modulo the smaller power of that prime dividing their least cyclic color periods.

**Anchors.** board revolutions · tile-color cycle constraints · color periods · prime powers

**Accept.** Decompose the color-period constraints into prime-power components. Constraints for distinct primes combine independently; constraints for one prime must agree on their shared modulus. Factoring periods and retaining only the strongest constraint for each prime is one implementation, not a required representation.

**Review.** all checks passed

## N8 · Test aligned orbit by prime-power compatibility

*algorithm · depth 7 · source: exploration · routes: N5 + N6 + N7*

**Statement.** For equal-shape arrangements with aligned corner phases, derive the revolution permutation's cycles, determine each cycle's allowable color-matching exponents, and test compatibility of their prime-power constraints. The arrangements are reachable exactly when every cycle matches and all constraints are compatible.

**Anchors.** revolution permutation · color-matching exponents · prime-power compatibility · aligned arrangements

**Accept.** The permutation may be obtained by labeled tilts or an equivalent mapping, using either revolution orientation. KMP on doubled cycle strings and prefix-function period extraction are examples; other sufficiently efficient rotation and period methods count. A smallest-prime-factor sieve supports compatibility checks. With n tiles, O(hw+n log n) time and O(hw+n) storage suffice without enumerating the permutation order.

**Review.** all checks passed

## N9 · Decide using prefixes and aligned revolution orbits

*algorithm · depth 8 · source: exploration · routes: N1 + N2 + N3 + N8*

**Statement.** Return yes for unchanged or single-tilt outcomes. Otherwise return yes exactly when the target is corner-packed and some perpendicular-prefix representative of the same Ferrers shape passes the revolution-orbit test after accounting for the target's corner phase.

**Anchors.** starting arrangement · ending arrangement · perpendicular prefixes · corner phases · yes · no

**Accept.** Include zero-tilt and one-axis outcomes. For the remaining cases, try all eight perpendicular prefixes or a covering representative family. Four seeds normalized by up then left are one realization; explicit partial-turn anchors are another. Compare shapes and use the prime-power orbit test. A constant number of O(hw+n log n) computations suffices.

**Review.** all checks passed

## N10 · Pairwise gcd synchronizes revolution counts

*key_property · depth 6 · source: exploration · routes: N6*

**Statement.** Let k count complete corner revolutions, with k≡r_i modulo p_i required to match target colors on cycle i, where p_i is its least cyclic color period. One board-wide k exists exactly when every pair satisfies r_i≡r_j modulo gcd(p_i,p_j).

**Anchors.** corner revolutions · target colors · least cyclic color periods · common repetition count · gcd

**Accept.** Applies generalized CRT to the repetition count shared by all tile cycles. Necessity follows by subtracting two color-matching congruences. Sufficiency follows from consistency of their prime-power components, without requiring the program to factor the color periods.

**Review.** all checks passed

## N11 · Distinct color periods have bounded total

*key_property · depth 6 · source: exploration · routes: N6*

**Statement.** If n tiles occupy the permutation cycles, the sum of their distinct color periods is at most n. Consequently, the number D of distinct periods satisfies D(D+1)/2 at most n.

**Anchors.** tiles · permutation cycles · distinct periods

**Accept.** Choose one cycle for each distinct period. Its period is at most its length, and chosen cycles are disjoint. The smallest possible sum of D distinct positive periods is D(D+1)/2.

**Review.** all checks passed

## N12 · Decide reachability by pairwise period compatibility

*algorithm · depth 7 · source: exploration · routes: N1 + N2 + N3 + N5 + N6 + N10 + N11*

**Statement.** Include zero-tilt and one-axis outcomes. Otherwise cover perpendicular prefixes and corner phases, rejecting shape mismatches or missing cycle rotations. Accept exactly when some candidate's color-period residues agree within equal-period groups and between distinct groups modulo the gcd of their periods.

**Anchors.** starting arrangement · ending arrangement · prefix and phase candidates · color-period residues · pairwise gcd

**Accept.** Eight prefixes with partial-turn anchors or four top-left-normalized seeds provide coverage. KMP is one sufficiently efficient rotation/period extractor. Reject conflicting residues for repeated periods, then compare the D distinct-period constraints using O(D²) gcd checks. Since their periods sum to at most n tiles, total time O(hw+n log n) and storage O(hw+n) suffice.

**Review.** all checks passed

## N13 · Four tilts square two line reversals

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** On a top-left Ferrers diagram, let A reverse the tiles within each occupied row and B reverse them within each occupied column. The permutation induced by right, down, left, up equals (BA) squared, where BA applies A followed by B.

**Anchors.** Ferrers diagram · occupied rows · occupied columns · four tilts · line reversals

**Accept.** Reflect each intermediate corner placement geometrically back to top-left. A horizontal corner change then acts as A and a vertical change as B. After four changes the geometric reflections cancel, leaving A,B,A,B. Reversal lengths are the occupied row lengths and column heights.

**Review.** all checks passed

## N14 · Reversal-product rotations require an even exponent

*reformulation · depth 6 · source: exploration · routes: N5 + N6 + N13*

**Statement.** Let A reverse occupied rows and B occupied columns of a top-left Ferrers diagram. Two colorings are mutually reachable exactly when their cycle rotation constraints for BA admit a common even exponent, with moduli given by least cyclic color periods.

**Anchors.** top-left Ferrers diagram · row and column reversals · BA cycles · even exponent · color periods

**Accept.** BA applies A followed by B. Powers of the physical four-tilt permutation are exactly even powers of BA. Apply the colored-cycle rotation characterization to BA and include the congruence exponent equal to zero modulo two. This handles even cycles split by squaring and color periods smaller than cycle lengths.

**Review.** all checks passed

## N15 · Decide using even line-reversal powers

*algorithm · depth 7 · source: exploration · routes: N1 + N2 + N3 + N7 + N14*

**Statement.** Include zero-tilt and one-axis outcomes. For the remaining prefix and corner-phase candidates with matching Ferrers shapes, test the row/column-reversal product. Accept exactly when some candidate has color-matching cycle residues whose prime-power constraints admit a common even exponent.

**Anchors.** prefix and phase candidates · row lengths · column heights · BA permutation · even exponent

**Accept.** Four seeds aligned to top-left are one candidate-handling realization; equivalent prefix and phase coverage also counts. At top-left, BA's source for cell (r,c) is (s,rowlength[s]-1-c), with s=columnheight[c]-1-r. Extract rotations and periods efficiently, for example with KMP, and include residue zero modulo two in the prime-power test. O(hw+n log n) time and O(hw+n) memory suffice.

**Review.** all checks passed

## N16 · Intersect tile-cycle exponent classes incrementally

*algorithm · depth 6 · source: exploration · routes: N6*

**Statement.** While processing the board's revolution cycles, maintain the exact arithmetic progression of repetition counts satisfying all processed tile-color constraints. Intersect it with each new cycle's residue class; reject precisely when the intersection is empty. Otherwise the updated class represents all remaining possible repetition counts.

**Anchors.** board revolution cycles · tile-color constraints · repetition counts · exact class intersection

**Accept.** One update stores k≡a modulo M and adds k≡b modulo p. With g=gcd(M,p), reject unless g divides b-a; otherwise solve (M/g)t≡(b-a)/g modulo p/g and obtain k≡a+Mt modulo Mp/g. Extended Euclid supplies the inverse when p/g>1. Any equivalent exact intersection of the cycle-exponent classes counts.

**Review.** all checks passed

## N17 · Whole-board color repetition period

*key_property · depth 7 · source: exploration · routes: N11*

**Statement.** For a fixed Ferrers shape and revolution permutation, the least positive revolution count restoring all tile colors is the least common multiple of the cycles' least cyclic color periods. Compatible target exponents therefore form one class modulo this whole-board color period.

**Anchors.** revolution permutation · tile colors · least cyclic color periods · whole-board return period · least common multiple

**Accept.** A revolution count restores the board exactly when it is divisible by every cycle's color period. Repeated periods do not change the lcm. If one exponent reaches the target, all other such exponents differ by a whole-board color-return count. The empty set of cycle periods has lcm one.

**Review.** all checks passed

## N18 · Decide by exact incremental CRT

*algorithm · depth 8 · source: exploration · routes: N1 + N2 + N3 + N16 + N17*

**Statement.** Include zero-tilt and one-axis outcomes. Otherwise cover perpendicular prefixes and target corner phases, rejecting shape mismatches or cycles with no matching rotation. Return yes exactly when some candidate's tile-color exponent classes have a nonempty intersection computed by exact incremental CRT.

**Anchors.** starting arrangement · ending arrangement · prefix and phase candidates · tile-color exponent classes · exact CRT

**Accept.** One realization uses four normalized seeds, KMP, duplicate-period merging, and arbitrary-precision CRT; eight prefixes with partial-turn anchors also suffice. For n tiles, D distinct periods satisfy D(D+1)/2≤n. Their lcm is at most n^D, using O(1+sqrt(n) log(n+1)) bits and fewer than 13000 bits under the limits. O(D) small-modulus CRT merges plus O(hw+n) rotation extraction fit the limits.

**Review.** all checks passed

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 + N5 + N6 + N7 + N8 + N9 \| N1 + N2 + N3 + N4 + N5 + N6 + N10 + N11 + N12 \| N1 + N2 + N3 + N4 + N5 + N6 + N7 + N13 + N14 + N15 \| N1 + N2 + N3 + N4 + N5 + N6 + N11 + N16 + N17 + N18

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N9 \| N12 \| N15 \| N18

## Hazards (END → program)

- **H1** Zero-tilt and one-axis outcomes must be included, even when the ending arrangement is not corner-packed. *Check:* Accept the unchanged board and every matching single-tilt board, directly or through equivalent candidate coverage. Do not exclude these outcomes solely because they fail the shape condition that applies after perpendicular tilts.
- **H2** Same-colored tiles are indistinguishable; fixing tile identities or retaining only one matching shift modulo a full cycle length can incorrectly reject reachable arrangements. *Check:* Preserve every color-matching cyclic shift, using least-period congruences or an equivalent representation. Permanent identities assigned for motion analysis must not impose extra restrictions on tiles of the same color.
- **H3** The revolution order and combined cycle-period modulus need not fit machine integers, and enumerating all powers may be infeasible. *Check:* Use overflow-safe compatibility tests or exact arbitrary-precision CRT. Storing the lcm is valid when exact and affordable. Runtime must not depend on enumerating the potentially enormous full permutation order.
- **H4** Single-row, single-column, full, and empty boards may have coincident corner placements and identity permutation cycles. *Check:* Handle identity cycles and period one normally; do not assume all corner placements are distinct or any tile exists.
- **H5** Each tilt must preserve tile order within every affected line, preserve all colors, and leave exactly the corresponding packed occupied cells. *Check:* Verify stable, lossless compaction. A fresh destination grid, temporary line buffer, or safe in-place scan all qualify; no unread tile may be overwritten and no tile may be duplicated or dropped.
- **H6** When explicit CRT arithmetic is used, residue–inverse products can exceed 32-bit range, and accumulated exponent classes can exceed machine-word range. *Check:* Use exact overflow-safe arithmetic for CRT products and any stored accumulated values. A 64-bit intermediate suffices for products of residues below 250000; arbitrary precision is one valid way to store the combined exponent and modulus.

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4, N5, N6, N7, N8, N9

After the first two perpendicular tilts, occupied cells form a corner-packed Ferrers diagram. Subsequent tilts are reversible corner changes, so after normalization to the top-left, reachability reduces to powers of one four-tilt permutation; only four initial seeds need consideration. On each permutation cycle, linear string matching gives a congruence for the number of repetitions, and prime-power compatibility combines these congruences without constructing a huge least common multiple.

New nodes: N1, N2, N3, N4, N5, N6, N7, N8, N9 · judge: AC on 55 tests, slowest 0.037s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N2, N3, N4, N5, N6, N10, N11, N12

Use the same Ferrers-diagram and cyclic-permutation reduction, but combine rotation constraints without factoring their moduli. Merge equal periods and check generalized-CRT compatibility for every pair of distinct periods. The sum of those distinct periods is at most the number of tiles, so there are only O(sqrt(n)) of them and all pairwise gcd checks take O(n log n) time.

New nodes: N10, N11, N12 · judge: AC on 55 tests, slowest 0.034s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N2, N3, N4, N5, N6, N7, N13, N14, N15

There is an algebraic square root of the four-tilt permutation: reverse every occupied row, then every occupied column. Two applications of this product equal a complete right-down-left-up revolution. Thus canonical reachability can instead be tested on the cycles of this row/column-reversal product, provided the common exponent is constrained to be even; linear string matching and prime-power compatibility keep the computation near-linear.

New nodes: N13, N14, N15 · judge: AC on 55 tests, slowest 0.034s · program: `paths/P3.cpp` · None submission(s)
### P4 · N1, N2, N3, N4, N5, N6, N11, N16, N17, N18

Again reduce each canonical seed to cycle rotation congruences, but explicitly construct the common exponent class using incremental generalized CRT and arbitrary-precision integers. Equal periods are merged first. There are only O(sqrt(n)) distinct periods and their product has O(sqrt(n) log n) bits, so exact large-integer CRT is comfortably small and avoids both factorization and all-pairs compatibility checks.

New nodes: N16, N17, N18 · judge: AC on 55 tests, slowest 0.035s · program: `paths/P4.cpp` · None submission(s)

## Exploration

Finished: True · 4 submissions · reason: Four accepted paths cover the cyclic Ferrers-diagram reduction with prime-power compatibility, bounded pairwise-gcd compatibility, explicit arbitrary-precision CRT, and the row/column-reversal square-root characterization with an even-exponent constraint. I have no further genuinely different approach that I can justify as correct and fast enough.

Ideas the explorer considered and dropped:

- Breadth-first search over colored arrangements or direct enumeration of all four-tilt powers: the reachable orbit can have an enormous permutation order, so neither has an adequate worst-case bound.
- Checking only color counts and Ferrers shape: these are necessary but miss preserved cyclic orders and synchronization constraints between permutation cycles.
- Assigning permanent identities to same-colored tiles: this can reject valid transformations; cyclic color periods are necessary to represent indistinguishability.
- Replacing KMP with Z-functions, suffix-based matching, or canonical necklace rotations: these merely implement the already-established rotation-and-period subproblem differently rather than giving a new reasoning path.
- Reflecting each corner to top-left and describing arbitrary moves by a dihedral action: its row and column involutions reduce to the square-root permutation and parity characterization already represented by the third path.
- Fixed-width incremental CRT: the accumulated modulus can overflow; the accepted arbitrary-precision path supplies a rigorous size bound instead.

## Review

END ok: True — All four routes cover zero-tilt and one-axis outcomes, both-axis seed coverage, shape and corner-phase handling, and efficient colored-permutation orbit testing. P3 correctly replaces revolution powers with even powers of the reversal product; P4 supplies exact CRT intersection and a sufficient bound on its arithmetic size.

Hazards ok: True — The hazards cover stable lossless tilts, indistinguishable colors, trivial outcomes outside the corner-packed regime, degenerate and empty boards, and potentially enormous permutation orders and CRT moduli. H6 is appropriately conditional on explicit CRT arithmetic; no essential additional implementation constraint is missing.

**Builder's notes.** Generalized prefix and phase coverage so the existing paths also recognize eight-prefix/partial-anchor implementations. Fixed ids and routes prevent literally deleting N17 or splitting N6 into additional nodes. N17 now states the intrinsic whole-board color-return period; its former storage bound is folded into N18.accept. N6 is focused on the complete set of matching exponents, with the rotation test explained in accept. Zero-tilt handling was removed from N1 and retained in the decision rules and H1.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `d2385a30cc93cccb` | 12 | 4 | revise |
| 2 | `be7c696185544a59` | 0 | 0 | accept |
