# Reasoning graph · Mosaic Browsing (2021/G-mosaic-browsing)

status **accepted** · version `6eca7330a54fb9ee` · 30 nodes · 13 END route(s) · 7 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 2 review round(s)

**Route.** P1: Represent each legal placement by the sum of squared color differences over the motif's nonempty squares; it matches exactly when this nonnegative score is zero. P2: The same integer squared-error correlations can be evaluated exactly with number-theoretic transforms instead of floating-point FFTs. P3: Directly enumerate every legal top-left position and compare the mosaic against the motif's nonempty cells, stopping at the first mismatch. P4: For every mosaic row and color, store a bitset of columns having that color. P5: Decompose each motif row into maximal contiguous nonempty runs. P6: Use the decomposition into nonempty horizontal runs, but verify each run in constant time with deterministic substring identifiers rather than scanning rows with KMP. P7: Use Aho–Corasick to find every nonempty motif run in the mosaic, and count the run constraints supported by each legal placement. P8: Count agreeing constrained cells instead of summing squared differences. P9: Represent colors by their seven binary bits and count bit disagreements only at nonempty motif cells. P10: Flatten the mosaic and insert wildcard gaps between motif rows so that the motif becomes one wildcard string with the same row stride. P11: The suffix-array/LCP version timed out because it issued a range-minimum query for every run at every placement. P12: Compute the equal-color agreement counts directly from sparse color-position lists instead of convolutions. P13: Use rolling hashes of nonempty horizontal runs as a fast rejection filter, then compare constrained cells exactly only for surviving placements.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Legal placements and wildcard constraints | statement |
| N2 | 2 | reformulation | Nonnegative mismatch score | N1 |
| N3 | 3 | reformulation | Score expansion and correlation alignment | N1 + N2 |
| N4 | 4 | algorithm | FFT scores enumerate every match | N1 + N2 + N3 |
| N5 | 3 | key_property | Bounded scores permit exact modular testing | N2 |
| N6 | 4 | algorithm | Exact NTT correlation enumeration | N1 + N3 + N5 |
| N7 | 2 | algorithm | Direct verification of every placement | N1 |
| N8 | 2 | reformulation | Shifted color sets characterize candidates | N1 |
| N9 | 3 | algorithm | Bitset intersection of color restrictions | N1 + N8 |
| N10 | 2 | reformulation | Solid horizontal runs suffice | N1 |
| N11 | 3 | algorithm | KMP run filtering | N1 + N10 |
| N12 | 3 | key_property | Joint exact substring identifiers | N10 |
| N13 | 4 | key_property | Two blocks decide run equality | N12 |
| N14 | 5 | algorithm | Canonical substring queries verify placements | N1 + N10 + N12 + N13 |
| N15 | 3 | key_property | Run occurrences vote for placements | N1 + N10 |
| N16 | 4 | algorithm | Aho–Corasick run occurrence voting | N1 + N10 + N15 |
| N17 | 2 | reformulation | Equal-color count characterizes matches | N1 |
| N18 | 3 | reformulation | Color indicators give agreement correlations | N1 + N17 |
| N19 | 4 | algorithm | One-hot convolution match enumeration | N1 + N17 + N18 |
| N20 | 2 | reformulation | Masked bit disagreements characterize matches | N1 |
| N21 | 3 | algorithm | Seven bit-plane correlations by NTT | N1 + N20 |
| N22 | 2 | reformulation | Wildcard string preserves motif offsets | N1 |
| N23 | 3 | key_property | Shift-And motif-prefix state invariant | N22 |
| N24 | 4 | algorithm | Streaming Shift-And reports completed motifs | N1 + N22 + N23 |
| N25 | 3 | key_property | Suffix LCP certifies a run match | N10 |
| N26 | 4 | key_property | Run matches form a suffix interval | N25 |
| N27 | 5 | algorithm | Suffix intervals verify motif placements | N1 + N10 + N25 + N26 |
| N28 | 3 | algorithm | Sparse equal-color pair voting | N1 + N17 |
| N29 | 3 | key_property | Run hashes safely reject mismatches | N10 |
| N30 | 4 | algorithm | Hash filtering with exact verification | N1 + N10 + N29 |
| END | | | complete solution | N1 + N2 + N3 + N4 \| N1 + N2 + N3 + N5 + N6 \| N1 + N7 \| N1 + N8 + N9 \| N1 + N10 + N11 \| N1 + N10 + N12 + N13 + N14 \| N1 + N10 + N15 + N16 \| N1 + N17 + N18 + N19 \| N1 + N20 + N21 \| N1 + N22 + N23 + N24 \| N1 + N10 + N25 + N26 + N27 \| N1 + N17 + N28 \| N1 + N10 + N29 + N30 |

## N1 · Legal placements and wildcard constraints

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** A placement is legal exactly when the motif's entire rectangle lies inside the mosaic. It matches exactly when every nonzero motif entry equals its corresponding mosaic entry; zero motif entries impose no color constraint.

**Anchors.** motif · mosaic · empty square · position

**Accept.** Enumerates top-left rows 0 through rq-rp and columns 0 through cq-cp, and ignores motif zeros when comparing colors. Oversized motifs have no legal placements. If all motif entries are zero, every legal placement matches.

**Review.** failed: atomic — Whole-rectangle legality and wildcard color semantics are independently learnable: a solver can compare all nonzero cells correctly yet incorrectly trim empty borders when deciding legal starts. Separate these two modeling claims.

## N2 · Nonnegative mismatch score

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** For motif colors P and corresponding mosaic colors Q at a legal placement, choose W=[P≠0] or W=P. The score S=∑W(P-Q)² is nonnegative and is zero exactly when the placement matches: empty cells contribute nothing, and every constrained mismatch contributes positively.

**Anchors.** motif colors · mosaic colors · empty squares · mismatch score

**Accept.** Either the unweighted score ∑[P≠0](P-Q)² or the weighted score ∑P(P-Q)² establishes this characterization. The proof uses positive weights at constrained cells and zero weights at empty cells. Correlation expansion is a separate step.

**Review.** all checks passed

## N3 · Score expansion and correlation alignment

*reformulation · depth 3 · source: exploration · routes: N1 + N2*

**Statement.** For W=[P≠0] or W=P, S=∑WP²+corr(W,Q²)-2corr(WP,Q), where each correlation aligns motif cells with their translated mosaic cells. Convolution coefficients yield these correlations when serialization, padding and reversal preserve that two-dimensional alignment.

**Anchors.** mismatch score · correlations · convolution alignment · motif offsets

**Accept.** One construction uses stride cq, motif length L=(rp-1)cq+cp, reversed motif operands, and coefficient L-1+r*cq+c for zero-based placements. Equivalent padding and reversal conventions count. For W=[P≠0], the constant is ∑P² and operands are W,P; for W=P, they are ∑P³ and P,P².

**Review.** failed: atomic — Expanding the squared-error score into correlations and realizing those 2D correlations as correctly indexed convolutions are separate obstacles. Split the algebraic expansion from the padding, reversal, and coefficient-alignment claim.

## N4 · FFT scores enumerate every match

*algorithm · depth 4 · source: exploration · routes: N1 + N2 + N3*

**Statement.** Evaluate the mismatch-score correlations using FFT convolution and make a numerically reliable decision whether each legal placement's score is zero. Output exactly those zero-score placements, sorted by row and then column.

**Anchors.** FFT · mismatch scores · zero-score decision · matches

**Accept.** Separate real convolutions or packed complex convolution count. An unweighted example convolves reversed (128M+2iP) with (Q²/128+iQ), then adds ∑P² to its real part. Weighted-score evaluation also counts. Nearest-integer recovery or a justified near-zero test is valid; inspected coefficients must be unaffected by aliasing.

**Review.** all checks passed

## N5 · Bounded scores permit exact modular testing

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** For either weighting W=[P≠0] or W=P, every legal score satisfies 0≤S≤9801∑W. For pairwise coprime moduli whose product exceeds this bound, S is zero exactly when its residue modulo every modulus is zero.

**Anchors.** mismatch score · weights · score bound · moduli

**Accept.** For t constrained cells, the unweighted bound is 9801t and the weighted bound is at most 980100t. A tighter bound sums W*max((P-1)²,(P-100)²). Use one sufficiently large modulus or enough coprime moduli; a smaller modulus alone does not exclude positive-score collisions.

**Review.** all checks passed

## N6 · Exact NTT correlation enumeration

*algorithm · depth 4 · source: exploration · routes: N1 + N3 + N5*

**Statement.** Evaluate the score correlations modulo NTT primes whose product exceeds the proven score bound. Add the constant ∑WP² modulo each prime, and output precisely the legal placements whose score residues are zero for every prime, sorted by row and column.

**Anchors.** NTT · score correlations · modular score · matches

**Accept.** Transform W, WP, Q and Q² with appropriate alignment, combine spectra as W*Q²-2(WP)*Q, and inverse-transform. W=[P≠0] gives the unweighted implementation; W=P gives the weighted version. Primes 998244353 and 1004535809 support the standard required lengths and their product exceeds both maximum score bounds.

**Review.** all checks passed

## N7 · Direct verification of every placement

*algorithm · depth 2 · source: exploration · routes: N1*

**Statement.** Enumerate all legal placements. At each placement compare every nonzero motif cell to its corresponding mosaic cell, rejecting on any unequal pair. Output exactly the unrejected placements in row-major order.

**Anchors.** legal placements · nonzero motif cells · direct comparison

**Accept.** Stores constrained cells or scans the motif directly. Checks may be ordered arbitrarily, including by increasing mosaic color frequency, and stop immediately on a mismatch. An all-empty motif accepts every legal placement.

**Review.** all checks passed

## N8 · Shifted color sets characterize candidates

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** Let B(s,v) contain the mosaic columns of color v in row s. For a fixed legal top row r, matching starting columns are exactly the legal columns intersected with every set B(r+i,P(i,j))-j for nonzero motif cells (i,j).

**Anchors.** mosaic rows · colors · starting columns · nonzero motif cells

**Accept.** A start c satisfies a constrained cell precisely when c+j belongs to the corresponding row's color set. Intersecting these necessary and sufficient restrictions handles all cells, while zeros contribute no restriction.

**Review.** all checks passed

## N9 · Bitset intersection of color restrictions

*algorithm · depth 3 · source: exploration · routes: N1 + N8*

**Statement.** Build bitsets B(s,v). For each legal top row, initialize all legal starting columns, then intersect with the appropriately shifted color bitset for each nonzero motif cell. Output the surviving set bits in row-major order.

**Anchors.** color bitsets · shift · intersection · surviving columns

**Accept.** Uses machine-word bitsets, either whole-bitset shifts or extraction of shifted words. Restrictions can be reordered and processing can stop when the candidate set is empty. An all-zero motif leaves every legal bit set.

**Review.** all checks passed

## N10 · Solid horizontal runs suffice

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** Partition the motif's nonzero cells into solid horizontal runs. A legal placement matches exactly when every run equals the mosaic substring starting at the placement plus that run's row and column offsets.

**Anchors.** motif rows · nonzero runs · mosaic substrings

**Accept.** Every constrained cell belongs to a run, and runs contain no empty cells. Maximal consecutive nonzero runs are one choice; subdividing them into shorter runs is equally valid. Equality of all prescribed substrings is necessary and sufficient.

**Review.** all checks passed

## N11 · KMP run filtering

*algorithm · depth 3 · source: exploration · routes: N1 + N10*

**Statement.** For each legal top row, initialize all legal starting columns. For every motif run, find its occurrences in the corresponding mosaic row with exact string matching, translate occurrences by the run's column offset, and intersect the candidates. Output the remaining placements in row-major order.

**Anchors.** KMP · run occurrences · candidate intersections · matches

**Accept.** Precompute each run's KMP failure function, or use an equivalent exact linear-time single-pattern matcher. A run occurrence starting at column s supports top-left column s minus the run's motif column. Stop when no candidate remains; no runs means all placements match.

**Review.** all checks passed

## N12 · Joint exact substring identifiers

*key_property · depth 3 · source: exploration · routes: N10*

**Statement.** Assign shared, collision-free identifiers to power-of-two-length substrings of both motif and mosaic by ranking pairs of half-block identifiers. Equal identifiers then mean equal strings, enabling exact comparisons of motif runs with their prescribed mosaic substrings.

**Anchors.** motif runs · mosaic substrings · shared identifiers · half-block pairs

**Accept.** Individual colors start with distinct shared identifiers. At each length, equal ordered pairs of half identifiers receive the same identifier, and unequal pairs receive different identifiers. Sorting, exact maps or equivalent canonical ranking count. Preprocessing may include padding, but actual run comparisons stay within their rows.

**Review.** all checks passed

## N13 · Two blocks decide run equality

*key_property · depth 4 · source: exploration · routes: N12*

**Statement.** A motif run of length l equals its prescribed mosaic substring exactly when their shared identifiers agree for both length-b prefixes and length-b suffixes, where b is the largest power of two not exceeding l. These blocks cover every run position.

**Anchors.** motif run · prescribed mosaic substring · prefix block · suffix block

**Accept.** Uses k=floor(log2(l)) and compares joint identifiers at offsets 0 and l-2^k. Overlap is harmless, including when the two blocks coincide for a power-of-two run length.

**Review.** all checks passed

## N14 · Canonical substring queries verify placements

*algorithm · depth 5 · source: exploration · routes: N1 + N10 + N12 + N13*

**Statement.** Build exact power-of-two substring identifiers for the motif and mosaic. Enumerate legal placements, checking each nonempty horizontal motif run against its prescribed mosaic substring with the two-block equality test. Output exactly the placements passing every run, in row-major order.

**Anchors.** substring index · legal placements · run comparisons · matches

**Accept.** Concatenation of both grids suffices if all actual queries stay within their respective rows. Pair ranking can use radix/counting sort. Runs may be checked in any order, with early rejection; preprocessing takes O((rp*cp+rq*cq)(1+log cp)) with linear-time ranking per level.

**Review.** all checks passed

## N15 · Run occurrences vote for placements

*key_property · depth 3 · source: exploration · routes: N1 + N10*

**Statement.** An occurrence of a motif run ending at mosaic position (s,t) supports the unique placement (s-i,t-j), where (i,j) is that run's zero-based motif end position. A legal placement matches exactly when its supported-run count equals the total number of motif runs.

**Anchors.** run occurrence · run endpoint · placement votes

**Accept.** Each particular run contributes at most once to any placement because its prescribed endpoint is fixed. Identical strings at different motif offsets are separate constraints. Coordinates in the translation formula are zero-based; equivalent one-based formulas count.

**Review.** all checks passed

## N16 · Aho–Corasick run occurrence voting

*algorithm · depth 4 · source: exploration · routes: N1 + N10 + N15*

**Statement.** Build a multi-pattern automaton containing all nonempty motif runs with their offsets. Scan the mosaic rows, report all within-row terminal and suffix-terminal occurrences, and increment the corresponding legal placement's vote count. Output placements with votes equal to the number of runs, in row-major order.

**Anchors.** Aho–Corasick · failure links · run offsets · vote counts

**Accept.** Use failure/output links for overlapping occurrences and terminal suffixes. Retain every motif offset at shared terminals. Offset lists can be indexed by row and column to avoid processing invalid placements. Prevent cross-row votes by resets, separators or boundary checks. With no runs, every legal placement has the required zero votes.

**Review.** all checks passed

## N17 · Equal-color count characterizes matches

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** Let t be the number of nonzero motif cells. At a legal placement, the total number of aligned equal-color pairs, summed over colors 1 through 100, is at most t and equals t exactly when the motif matches.

**Anchors.** colors · equal-color pairs · nonzero motif cells

**Accept.** Uses one-hot color indicators: sum over colors and motif positions of [P=v][Q=v]. Each constrained position contributes either zero or one; wildcard positions contribute zero.

**Review.** all checks passed

## N18 · Color indicators give agreement correlations

*reformulation · depth 3 · source: exploration · routes: N1 + N17*

**Statement.** For each nonzero color v, correlating motif indicator [P=v] with mosaic indicator [Q=v] counts aligned agreements of that color at every legal placement. Correctly aligned convolution coefficients yield these correlations; summing over colors gives the total agreement count.

**Anchors.** color indicators · correlation alignment · convolution · agreement count

**Accept.** For example, flatten with stride cq, reverse a padded motif indicator of length L=(rp-1)cq+cp, and inspect coefficient L-1+r*cq+c for zero-based placement (r,c). Other padding and reversal conventions count if each motif cell is paired with its translated mosaic cell. Wildcards have zero indicators.

**Review.** failed: atomic — A solver can express agreements as indicator correlations while still being unable to preserve the grid alignment in a convolution. Keep the agreement-correlation identity here and extract convolution alignment into a shared prerequisite with N3 and N21.

## N19 · One-hot convolution match enumeration

*algorithm · depth 4 · source: exploration · routes: N1 + N17 + N18*

**Statement.** Evaluate and sum the color-indicator convolutions. At every legal placement, reliably decide whether the agreement count equals the number of nonzero motif cells, and output exactly those placements in row-major order.

**Anchors.** one-hot convolution · agreement total · matches

**Accept.** FFT with accurate integer recovery or a justified comparison to the target count works, as does exact modular convolution with a modulus exceeding the count bound. Unused colors may be skipped. Packing the two real indicators per color into one complex transform and accumulating spectral products is one implementation.

**Review.** all checks passed

## N20 · Masked bit disagreements characterize matches

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** For each legal placement, let D=∑[P≠0]popcount(P XOR Q) over aligned motif and mosaic cells. With t nonzero motif cells, 0≤D≤7t, and D=0 exactly when the placement matches.

**Anchors.** color bits · empty squares · bit disagreements

**Accept.** Colors through 100 fit in seven bits. At each constrained cell, popcount(P XOR Q) is nonnegative and is zero exactly for equal colors. Empty motif cells contribute nothing. This establishes the mismatch characterization independently of its correlation expansion.

**Review.** all checks passed

## N21 · Seven bit-plane correlations by NTT

*algorithm · depth 3 · source: exploration · routes: N1 + N20*

**Statement.** Evaluate D=∑popcount(P)+∑_{b=0}^6 corr(M-2P_b,Q_b), where M=[P≠0] and P_b,Q_b are color bits, using correctly aligned NTT convolutions modulo a prime exceeding 7t, with t nonzero motif cells. Output legal placements with D≡0 in row-major order.

**Anchors.** bit planes · NTT · masked disagreement total · matches

**Accept.** The binary identity x XOR y=x+y-2xy gives the expansion. Modulus 998244353 exceeds 7t≤7,000,000. One layout reverses cq-stride-padded motif operands of length L=(rp-1)cq+cp and inspects coefficient L-1+r*cq+c. Equivalent layouts count. Spectral products may be summed before inversion; normalize negative coefficients and add the motif popcount constant.

**Review.** failed: atomic — The masked-XOR correlation expansion is a new algebraic insight, distinct from evaluating it with aligned NTTs and using a sufficiently large modulus to enumerate matches. Extract the expansion as a prerequisite, leaving this node as the output-determining NTT algorithm.

## N22 · Wildcard string preserves motif offsets

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** With a consistent row-stride serialization of both grids, motif cell offsets align with translated mosaic cells. Representing empty motif cells and intervening gaps as wildcards makes motif-string matching equivalent to the original constraints at every legal rectangular placement.

**Anchors.** serialized mosaic · motif offsets · wildcard gaps · legal placements

**Accept.** One construction flattens the mosaic row-major with stride cq, inserts cq-cp wildcards between motif rows, and trims the motif string to L=(rp-1)cq+cp. Then motif cell (i,j) has offset i*cq+j. Equivalent padding conventions count if offsets, inspected substrings and rectangular legality remain consistent.

**Review.** all checks passed

## N23 · Shift-And motif-prefix state invariant

*key_property · depth 3 · source: exploration · routes: N22*

**Statement.** While scanning the serialized mosaic, bit k of D marks a matching length-(k+1) prefix of the flattened motif from an admitted start. For color v, D=((D<<1)|s)&A_v, where A_v marks accepting motif positions and s admits the current start.

**Anchors.** flattened motif prefixes · mosaic scan · acceptance masks · Shift-And state

**Accept.** Initially D is zero. Shifting extends matching prefixes, s seeds a new prefix, and intersection enforces the current color. Admit all starts and filter completed hits for legality, or admit only legal starts. Multiword implementations propagate the preceding word's high bit.

**Review.** all checks passed

## N24 · Streaming Shift-And reports completed motifs

*algorithm · depth 4 · source: exploration · routes: N1 + N22 + N23*

**Statement.** Scan the serialized mosaic with the motif's Shift-And acceptance masks and prefix state. Report full-motif-prefix hits exactly when their starts correspond to legal rectangular placements. Convert these starts to grid coordinates and output all matches sorted by row and column.

**Anchors.** Shift-And · completed motif prefix · legal rectangles · placement coordinates

**Accept.** For motif-string length L and input end offset e, a full-prefix hit starts at e-L+1. Legality may be enforced during seeding or checked at completion. Machine-word state updates and active-word bounds are valid implementations. An all-zero motif must report every legal placement.

**Review.** all checks passed

## N25 · Suffix LCP certifies a run match

*key_property · depth 3 · source: exploration · routes: N10*

**Statement.** In a sequence containing the motif and mosaic, a motif run equals its prescribed mosaic substring exactly when the longest common prefix of the suffixes starting at those positions is at least the run's length.

**Anchors.** motif run · prescribed mosaic substring · starting suffixes · LCP threshold

**Accept.** The compared run and mosaic substring must fit within their respective rows. Concatenated-grid suffixes or a generalized suffix index work because only the required prefix length matters. This reduction does not require a particular method for obtaining longest-common-prefix values.

**Review.** all checks passed

## N26 · Run matches form a suffix interval

*key_property · depth 4 · source: exploration · routes: N25*

**Statement.** All suffixes beginning with a given motif run occupy a contiguous suffix-array interval containing that run's own suffix. Its endpoints are the farthest ranks on either side whose LCP with the run's suffix is at least the run length.

**Anchors.** motif run · suffix-array interval · interval endpoints

**Accept.** Lexicographic order makes a shared-prefix class contiguous. For ranks a<b, their LCP is the minimum adjacent LCP over ranks a+1 through b; RMQ and binary search therefore find the endpoints. Other exact interval constructions count. Identical runs can share intervals, and rank membership decides run equality.

**Review.** all checks passed

## N27 · Suffix intervals verify motif placements

*algorithm · depth 5 · source: exploration · routes: N1 + N10 + N25 + N26*

**Statement.** Build a suffix ordering for the motif and mosaic, and determine each motif run's matching suffix interval. For every legal placement, require each prescribed mosaic substring's suffix rank to lie in its run's interval. Output placements satisfying all requirements in row-major order.

**Anchors.** suffix intervals · legal placements · run membership · matches

**Accept.** One implementation builds adjacent LCP values and a range-minimum index, then uses two binary searches per distinct run. Any exact interval construction establishing the same rank-membership condition counts. Stop on the first failed run; no runs means every legal placement matches.

**Review.** all checks passed

## N28 · Sparse equal-color pair voting

*algorithm · depth 3 · source: exploration · routes: N1 + N17*

**Statement.** For each nonzero motif cell (i,j), enumerate same-colored mosaic cells (s,t) yielding legal placement (s-i,t-j), using zero-based coordinates, and increment that placement's counter. Output exactly placements whose counters equal the number of nonzero motif cells, in row-major order.

**Anchors.** same-colored cells · translation · placement counters

**Accept.** Indexes mosaic positions by color, optionally also by row, and restricts pairs to legal offset ranges. Each constrained cell contributes exactly once to a placement if it agrees, and never otherwise. Thus the counter is its agreement count. With no constrained cells, all legal counters meet the zero target.

**Review.** all checks passed

## N29 · Run hashes safely reject mismatches

*key_property · depth 3 · source: exploration · routes: N10*

**Statement.** Under consistent hash arithmetic, equal motif runs and mosaic substrings have equal hashes. Unequal hashes therefore certify a run mismatch without rejecting any true motif occurrence; equal hashes alone do not certify equality because collisions are possible.

**Anchors.** motif runs · mosaic substrings · hash rejection · collisions

**Accept.** Polynomial hashes with row-wise or flattened prefix hashes are one realization. For H[k+1]=H[k]B+x[k], a substring hash is H[x+l]-H[x]B^l; equivalent orientations and extraction formulas count. Precomputed powers permit constant-time extraction. Any consistent modulus or unsigned wraparound is valid for rejection-only use.

**Review.** all checks passed

## N30 · Hash filtering with exact verification

*algorithm · depth 4 · source: exploration · routes: N1 + N10 + N29*

**Statement.** Precompute motif-run hashes and mosaic prefix hashes. Enumerate legal placements, rejecting any with an unequal prescribed run hash. Verify every remaining placement by comparing all nonzero motif cells exactly, and output precisely the verified placements in row-major order.

**Anchors.** hash filter · exact verification · legal placements

**Accept.** Uses constant-time hash extraction per run and short-circuits on the first mismatch. Exact comparison of surviving placements guarantees correctness even under adversarial hash collisions. With no runs, every legal placement survives and verifies.

**Review.** all checks passed

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 \| N1 + N2 + N3 + N5 + N6 \| N1 + N7 \| N1 + N8 + N9 \| N1 + N10 + N11 \| N1 + N10 + N12 + N13 + N14 \| N1 + N10 + N15 + N16 \| N1 + N17 + N18 + N19 \| N1 + N20 + N21 \| N1 + N22 + N23 + N24 \| N1 + N10 + N25 + N26 + N27 \| N1 + N17 + N28 \| N1 + N10 + N29 + N30

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N4 \| N6 \| N7 \| N9 \| N11 \| N14 \| N16 \| N19 \| N21 \| N24 \| N27 \| N28 \| N30

## Hazards (END → program)

- **H1** The entire motif rectangle, including empty squares, must fit. Flattening must not admit row-wrapped placements. If every motif cell is zero, every legal placement must be reported, even when no constraints or runs are processed. *Check:* Reject oversized motifs and restrict starts to rows 0 through rq-rp and columns 0 through cq-cp. Ensure an empty constraint or run list imposes no rejection and does not suppress output.
- **H2** Accumulated mismatch scores and motif constants can exceed signed 32-bit range; the weighted score additionally involves cubic motif terms. *Check:* Use 64-bit totals or adequately accurate floating point. The unweighted score is at most 9,801,000,000; the weighted score is at most 980,100,000,000. Constants ∑P² and ∑P³ can reach 10,000,000,000 and 1,000,000,000,000 respectively. Form products in sufficiently wide arithmetic.
- **H3** Transform padding must leave inspected placement coefficients uncorrupted by aliasing, and floating-point error must not change whether the computed score or count represents a match. *Check:* Full linear-convolution padding suffices. Shorter cyclic transforms also count when wraparound contributions miss inspected coefficients. Establish adequate numerical separation of matching and nonmatching integer values; nearest-integer recovery or a justified near-zero or target-count test is valid.
- **H4** Output the match count first, followed by one-based coordinates sorted by row and then column. *Check:* Collect or enumerate matches in row-major order, print their total, and add one to zero-based coordinates.
- **H5** NTT primes and roots must support the chosen transform length; modular products and subtraction must not overflow or leave invalid residues. *Check:* For the cq-stride full-convolution layout, a power-of-two length at most 2^21 suffices. Other layouts require compatible lengths and roots. Use sufficiently wide modular products, normalized differences, and correct inverse-transform normalization.
- **H6** Word-based shifts must avoid shifting by the word width, reading beyond the source bitset, or exposing padding bits as legal matches. *Check:* Handle zero shift separately, allocate zero sentinel words or check source bounds, and mask unused bits in the final candidate or pattern-state word. Multiword state shifts must propagate carries correctly.
- **H7** Multi-pattern matching must retain repeated run offsets and suffix matches, and must not count run occurrences crossing two mosaic rows. *Check:* Store all run-offset records at shared terminals and report terminal suffixes through output links or an equivalent mechanism. Exclude cross-row occurrences using row resets, separators, or explicit boundary filtering.

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4

Represent each legal placement by the sum of squared color differences over the motif's nonempty squares; it matches exactly when this nonnegative score is zero. Flatten the grids with the mosaic's row stride and compute both terms of this score by convolution, packing them into one complex convolution. Three FFTs of length at most 2^21 compute all scores, and row-major enumeration produces the required ordered output.

New nodes: N1, N2, N3, N4 · judge: AC on 43 tests, slowest 0.118s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N2, N3, N5, N6

The same integer squared-error correlations can be evaluated exactly with number-theoretic transforms instead of floating-point FFTs. A score is at most 9801 times the number of constrained cells, so one modulus suffices when it exceeds that bound; otherwise two NTT primes have a product larger than every possible score. A legal placement is reported precisely when all computed residues are zero.

New nodes: N5, N6 · judge: AC on 43 tests, slowest 0.222s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N7

Directly enumerate every legal top-left position and compare the mosaic against the motif's nonempty cells, stopping at the first mismatch. This follows the definition without algebra or transforms; checking rarer mosaic colors first only changes the order of tests. Its worst case is large, so whether early rejection is sufficient is left to the judge.

New nodes: N7 · judge: AC on 43 tests, slowest 1.289s · program: `paths/P3.cpp` · None submission(s)
### P4 · N1, N8, N9

For every mosaic row and color, store a bitset of columns having that color. For a fixed top row, each nonempty motif cell restricts the possible starting columns to a shifted one of these bitsets; intersecting all such restrictions gives exactly the matches. Word-parallel intersections test 64 starting columns at once and can stop as soon as no candidate remains.

New nodes: N8, N9 · judge: AC on 43 tests, slowest 0.088s · program: `paths/P4.cpp` · None submission(s)
### P5 · N1, N10, N11

Decompose each motif row into maximal contiguous nonempty runs. A placement matches exactly when each run occurs at its prescribed offset in the corresponding mosaic row. For each top row, KMP finds the permissible starting columns of each run, and successive intersection removes all placements violating a run.

New nodes: N10, N11 · judge: AC on 43 tests, slowest 4.772s · program: `paths/P5.cpp` · None submission(s)
### P6 · N1, N10, N12, N13, N14

Use the decomposition into nonempty horizontal runs, but verify each run in constant time with deterministic substring identifiers rather than scanning rows with KMP. Assign collision-free identifiers to all power-of-two-length substrings by repeatedly ranking pairs of half-length identifiers; two overlapping blocks then decide equality for any run length. Enumerate legal placements and require every prescribed run comparison to succeed.

New nodes: N12, N13, N14 · judge: AC on 43 tests, slowest 3.131s · program: `paths/P6.cpp` · None submission(s)
### P7 · N1, N10, N15, N16

Use Aho–Corasick to find every nonempty motif run in the mosaic, and count the run constraints supported by each legal placement. The previous implementation spent excessive time visiting motif offsets that could not yield legal placements; this version groups each terminal's offsets by row and uses binary searches to report only offsets in the relevant row and column ranges. The vote criterion remains exact, including repeated copies of the same run.

New nodes: N15, N16 · judge: AC on 43 tests, slowest 2.767s · program: `paths/P7.cpp` · None submission(s)
### P8 · N1, N17, N18, N19

Count agreeing constrained cells instead of summing squared differences. For each color, convolve its reversed motif indicator with its mosaic indicator, then sum these correlations; a placement matches exactly when this count equals the number of nonempty motif cells. The implementation packs each pair of real indicators into one FFT and accumulates all colors before a single inverse transform; the judge determines whether up to 100 colors fit.

New nodes: N17, N18, N19 · judge: AC on 43 tests, slowest 1.761s · program: `paths/P8.cpp` · None submission(s)
### P9 · N1, N20, N21

Represent colors by their seven binary bits and count bit disagreements only at nonempty motif cells. The expanded masked Hamming distance is a constant plus seven correlations, and it is zero exactly for a match. Since its maximum is only seven million, one NTT modulus evaluates it without any possibility of modular collision.

New nodes: N20, N21 · judge: AC on 43 tests, slowest 0.291s · program: `paths/P9.cpp` · None submission(s)
### P10 · N1, N22, N23, N24

Flatten the mosaic and insert wildcard gaps between motif rows so that the motif becomes one wildcard string with the same row stride. Run the bit-parallel Shift-And recurrence on this string, seeding new partial matches only at legal top-left positions. A completed prefix of the full motif length is exactly a match; active-word bounds avoid processing regions of the state known to be zero.

New nodes: N22, N23, N24 · judge: AC on 43 tests, slowest 0.304s · program: `paths/P10.cpp` · None submission(s)
### P11 · N1, N10, N25, N26, N27

The suffix-array/LCP version timed out because it issued a range-minimum query for every run at every placement. This revision finds each distinct run's contiguous suffix-array interval once, using LCP queries only during preprocessing; subsequent run tests are single suffix-rank interval checks. The intervals contain exactly the suffixes beginning with the run, so the result remains deterministic and exact.

New nodes: N25, N26, N27 · judge: AC on 43 tests, slowest 1.091s · program: `paths/P11.cpp` · None submission(s)
### P12 · N1, N17, N28

Compute the equal-color agreement counts directly from sparse color-position lists instead of convolutions. Each nonempty motif cell and same-colored mosaic cell determine one translated top-left position; increment its counter if that position is legal. A placement is reported exactly when its counter reaches the number of nonempty motif cells, and sorted row-wise color lists avoid enumerating pairs that cannot yield legal columns.

New nodes: N28 · judge: AC on 43 tests, slowest 1.654s · program: `paths/P12.cpp` · None submission(s)
### P13 · N1, N10, N29, N30

Use rolling hashes of nonempty horizontal runs as a fast rejection filter, then compare constrained cells exactly only for surviving placements. Equal strings always have equal polynomial hashes, so the filter cannot discard a real match; direct verification removes all hash collisions. This provides a hashing-based path without making correctness probabilistic.

New nodes: N29, N30 · judge: AC on 43 tests, slowest 3.528s · program: `paths/P13.cpp` · None submission(s)

## Exploration

Finished: True · 16 submissions · reason: Thirteen genuinely different paths have been implemented and accepted on all 43 tests, covering direct comparison, sparse voting, bitset intersections, streaming Shift-And, several convolution characterizations, exact string matching, deterministic substring indexes, and verified hashing. I have no further distinct approach to submit that is not an implementation variation or combination of these established claims.

Ideas the explorer considered and dropped:

- Unindexed Aho–Corasick occurrence voting was submitted and received TLE on secret-42_max_zero_one_500. Indexing terminal offsets by row and column fixed it; the revised approach was accepted.
- Suffix-array verification with an RMQ for every run at every placement was submitted and received TLE on secret-40_max_zero_one_250. Precomputing each run's suffix-array interval fixed it; the revised approach was accepted.
- Hash-only acceptance was rejected because collisions can produce false matches. The submitted hashing path instead verifies surviving placements exactly and was accepted.
- Using one small modulus for unrestricted squared-error scores was rejected because a positive score can be a multiple of that modulus. The accepted exact NTT path uses the score bound and enough coprime moduli.
- Applying ordinary KMP directly with wildcard-compatible pattern comparisons was rejected: wildcard compatibility is not transitive, so the ordinary failure-function argument does not hold. Exact runs and Shift-And provide accepted alternatives.
- Transposing grids, using Z matching instead of KMP, changing FFT packing, and combining sparse pair enumeration with color convolutions do not introduce a new underlying characterization beyond the accepted paths.
- Enumerating assignments to all wildcard cells is exponentially large in their number and is unnecessary; all accepted paths handle empty squares without assigning colors.

## Review

END ok: True — Every END route contains the claims needed to implement its accepted approach. No route is rejected for a weak worst-case running-time bound; the recommended splits improve localization of reasoning rather than repair missing algorithmic content.

Hazards ok: True — The hazards cover rectangle legality, the all-wildcard case, output indexing and ordering, numerical range and precision, transform aliasing and NTT compatibility, bitset boundary safety, and repeated or cross-row run occurrences. Their implementation checks provide usable ways to meet the applicable constraints.

**Advisories.**

- N1 (bundles claims a solver can have separately; split it): Whole-rectangle legality and wildcard color semantics are independently learnable: a solver can compare all nonzero cells correctly yet incorrectly trim empty borders when deciding legal starts. Separate these two modeling claims.
- N3 (bundles claims a solver can have separately; split it): Expanding the squared-error score into correlations and realizing those 2D correlations as correctly indexed convolutions are separate obstacles. Split the algebraic expansion from the padding, reversal, and coefficient-alignment claim.
- N18 (bundles claims a solver can have separately; split it): A solver can express agreements as indicator correlations while still being unable to preserve the grid alignment in a convolution. Keep the agreement-correlation identity here and extract convolution alignment into a shared prerequisite with N3 and N21.
- N21 (bundles claims a solver can have separately; split it): The masked-XOR correlation expansion is a new algebraic insight, distinct from evaluating it with aligned NTTs and using a sufficiently large modulus to enumerate matches. Extract the expansion as a prerequisite, leaving this node as the output-determining NTT algorithm.
- order: Split N1 into rectangle legality and wildcard matching semantics. Separate correlation identities from convolution alignment in N3 and N18, sharing the alignment claim with N21 where appropriate. Extract the masked-XOR expansion from N21 before its NTT enumeration algorithm; retain N21 as P9's key node.

**Builder's notes.** All node and hazard ids are retained, with routes unchanged. The score family now includes both unweighted and weighted identities, with corresponding bounds and constants. Zero-score characterization and expansion are separated across N2/N3 and N20/N21. Implementation-specific layouts, hashing formulas, and LCP-query machinery are examples in accept rather than mandatory statements. The all-zero-motif requirement is explicit in H1.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `7e35407fd82cd73f` | 13 | 5 | revise |
| 2 | `6eca7330a54fb9ee` | 0 | 5 | revise |
