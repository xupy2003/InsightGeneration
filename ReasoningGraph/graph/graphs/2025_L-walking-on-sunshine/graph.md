# Reasoning graph · Walking on Sunshine (2025/L-walking-on-sunshine)

status **accepted** · version `3349bf7008e9185f` · 20 nodes · 12 END route(s) · 1 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 2 review round(s)

**Route.** P1: Horizontal travel is always free, so only the rectangles' vertical projections matter. P2: Because every vertical endpoint is integral, each open unit-height strip is either entirely coverable by shade or entirely uncovered. P3: Sweep the vertical endpoints of clipped rectangle projections while maintaining the number of active intervals. P4: Model relevant heights as vertices instead of explicitly computing interval coverage. P5: The direct-painting algorithm is unchanged, but stores unit-strip flags as packed bits and fills whole machine words. P6: Maintain the coverage union using a segment tree over unit-height strips. P7: Process each projection by deleting only its still-uncovered unit strips. P8: Maintain the uncovered portion of [ya,yc] directly as a set of disjoint intervals. P9: The repeated-scan greedy route can be accelerated using integral heights. P10: Expand the endpoint-height graph into every integer height between its minimum and maximum. P11: Analyze only zero-cost edges of the endpoint-height graph. P12: Use queue-based Bellman-Ford relaxation on the sparse endpoint-height graph instead of finalizing vertices with Dijkstra.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Free horizontal transfers erase x coordinates | statement |
| N2 | 2 | key_property | Uncovered levels force paid descent | N1 |
| N3 | 3 | reformulation | Answer equals uncovered vertical length | N1 + N2 |
| N4 | 4 | algorithm | Sorted interval union determines the answer | N3 |
| N5 | 4 | key_property | Integer heights partition cost into units | N3 |
| N6 | 5 | algorithm | Dense difference array counts uncovered strips | N5 |
| N7 | 4 | algorithm | Endpoint sweep integrates zero coverage | N3 |
| N8 | 2 | reformulation | Sparse directed graph of endpoint heights | N1 |
| N9 | 3 | algorithm | Dijkstra over heights and shaded shortcuts | N8 |
| N10 | 5 | algorithm | Directly paint every shaded unit strip | N5 |
| N11 | 5 | algorithm | Segment tree maintains projected union length | N5 |
| N12 | 5 | algorithm | Successor deletion counts newly covered strips | N5 |
| N13 | 4 | algorithm | Incrementally subtract shade from uncovered gaps | N3 |
| N14 | 4 | key_property | Deepest available free descent is safe | N3 |
| N15 | 5 | algorithm | Suffix minima accelerate the descending route | N14 + N5 |
| N16 | 3 | reformulation | Integer expansion makes all weights binary | N8 |
| N17 | 4 | algorithm | Zero-one BFS on integer heights | N16 |
| N18 | 3 | key_property | Free components characterize covered height gaps | N8 |
| N19 | 4 | algorithm | Contract free components and sum separating gaps | N18 |
| N20 | 3 | algorithm | Queue relaxation solves the height graph | N8 |
| END | | | complete solution | N1 + N2 + N3 + N4 \| N1 + N2 + N3 + N5 + N6 \| N1 + N2 + N3 + N7 \| N1 + N8 + N9 \| N1 + N2 + N3 + N5 + N10 \| N1 + N2 + N3 + N5 + N11 \| N1 + N2 + N3 + N5 + N12 \| N1 + N2 + N3 + N13 \| N1 + N2 + N3 + N5 + N14 + N15 \| N1 + N8 + N16 + N17 \| N1 + N8 + N18 + N19 \| N1 + N8 + N20 |

## N1 · Free horizontal transfers erase x coordinates

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** Horizontal and northward travel cost zero. All points at the same height are mutually reachable for free, so a rectangle permits free descent between any two heights in its vertical projection, regardless of the endpoints' x coordinates.

**Anchors.** horizontal travel · shaded areas · vertical projection

**Accept.** Recognizes that arbitrary horizontal detours are allowed and do not contribute to the objective. Replaces each rectangle by [y1,y2]; at a height belonging to that interval, one may move horizontally to an interior x coordinate and descend within the rectangle.

**Review.** all checks passed

## N2 · Uncovered levels force paid descent

*key_property · depth 2 · source: exploration · routes: N1*

**Statement.** When yc>ya, every route costs at least the length of the part of [ya,yc] outside the union of all rectangle projections. Each such height must be crossed southward in sunlight, and walked distance is at least its vertical component.

**Anchors.** yc · ya · sun shining in your eyes · vertical projection

**Accept.** A horizontal-level crossing argument or integration of southward vertical displacement establishes the bound, even for paths that move north or cross a level repeatedly. No rectangle can shade a point at an uncovered height.

**Review.** all checks passed

## N3 · Answer equals uncovered vertical length

*reformulation · depth 3 · source: exploration · routes: N1 + N2*

**Statement.** The minimum cost is zero if yc<=ya; otherwise it is the uncovered length of [ya,yc] under the rectangles' vertical projections. This bound is attainable by descending within shade wherever possible and transferring horizontally between rectangles at shared heights.

**Anchors.** minimum distance · yc · ya · union of projections

**Accept.** Shows that a connected union of projected intervals can be traversed downward for free using horizontal transfers, including transfers at touching endpoints. Gaps are traversed vertically, paying exactly their lengths. For yc<=ya, a horizontal-and-northward route has zero cost.

**Review.** all checks passed

## N4 · Sorted interval union determines the answer

*algorithm · depth 4 · source: exploration · routes: N3*

**Statement.** Compute the union of the rectangles' vertical projections by sorted interval merging. If yc>ya, output the length of [ya,yc] outside that union; otherwise output zero.

**Anchors.** rectangle projections · merged intervals · uncovered length · answer

**Accept.** Sorting by lower endpoint and merging overlaps is one realization; equivalent ascending or descending union scans also count. Projections may be clipped before merging, or merged components intersected with [ya,yc] afterward. Subtract covered length from yc-ya or sum uncovered gaps. Time O(n log n), space O(n); integer arithmetic is exact.

**Review.** all checks passed

## N5 · Integer heights partition cost into units

*key_property · depth 4 · source: exploration · routes: N3*

**Statement.** For integer h, the open strip of heights (h,h+1) is shaded somewhere exactly when some rectangle has y1<=h and y2>=h+1. Thus, for yc>ya, the answer equals the number of uncovered strips with ya<=h<yc.

**Anchors.** integer coordinates · unit-height strips · answer

**Accept.** Uses integrality of all rectangle and location coordinates to show no projection boundary lies inside a unit-height strip. The union complement's length is therefore precisely a count of unit strips, not a count of endpoints.

**Review.** all checks passed

## N6 · Dense difference array counts uncovered strips

*algorithm · depth 5 · source: exploration · routes: N5*

**Statement.** For yc>ya, add +1 at each clipped projection's lower endpoint and -1 at its upper endpoint in a height-indexed difference array. Prefix sums give unit-strip coverage counts; output the number of zero counts over [ya,yc). For yc<=ya, output zero.

**Anchors.** difference array · coverage counts · unit-height strips

**Accept.** Coordinates may be shifted by ya or by the global minimum. The prefix sum after processing height h describes (h,h+1). Allocate space for upper-endpoint updates and inspect only strips below yc. Work O(n+2000000) and memory O(2000000).

**Review.** all checks passed

## N7 · Endpoint sweep integrates zero coverage

*algorithm · depth 4 · source: exploration · routes: N3*

**Statement.** For yc>ya, sweep sorted endpoints of projections clipped to [ya,yc], increasing coverage at lower endpoints and decreasing it at upper endpoints. Add each gap between event heights precisely when coverage there is zero, including boundary gaps. Output this sum; for yc<=ya, output zero.

**Anchors.** projection endpoints · active coverage · height gaps

**Accept.** An endpoint-event sweep, an ordered map of signed events, or compressed-coordinate differences followed by a weighted gap sum establishes this algorithm. Coverage is constant between consecutive distinct endpoints. Equal-height events may be grouped or processed with zero-length gaps; negative and positive updates at that height must all precede the next gap.

**Review.** all checks passed

## N8 · Sparse directed graph of endpoint heights

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** Create vertices at yc, ya, and all rectangle y endpoints. Consecutive heights have a free northward edge and a southward edge weighted by their difference; each rectangle adds a zero-weight y2→y1 edge. The minimum hurt distance equals the shortest yc→ya path.

**Anchors.** endpoint heights · northward edges · rectangle shortcuts · shortest path

**Accept.** Every graph edge is realizable at no greater cost using horizontal transfers. Conversely, unshaded descent is represented by adjacent-height edges, while entering or leaving shade at intermediate heights can be represented by ascending freely to its top, taking its shortcut, and ascending freely from its bottom. Equivalently, subdivision at all endpoints turns covered elementary gaps into free descent paths through shortcuts.

**Review.** all checks passed

## N9 · Dijkstra over heights and shaded shortcuts

*algorithm · depth 3 · source: exploration · routes: N8*

**Statement.** Build the endpoint-height graph with adjacent-height movement edges and one downward zero-cost shortcut per rectangle. Run Dijkstra from the contest height and output the distance to the awards ceremony height.

**Anchors.** Dijkstra · contest height · awards ceremony height · shaded shortcuts

**Accept.** Sort and deduplicate heights, map rectangle endpoints and locations to vertices, and use nonnegative-edge shortest paths. A heap-based Dijkstra implementation processes O(n) vertices and edges in O(n log n) time. The northward edges automatically produce zero when ya>=yc.

**Review.** all checks passed

## N10 · Directly paint every shaded unit strip

*algorithm · depth 5 · source: exploration · routes: N5*

**Statement.** If yc>ya, initialize all unit-height strips of [ya,yc] as uncovered. For each clipped rectangle projection, mark every strip it contains as covered. Output the number still uncovered. If yc<=ya, output zero.

**Anchors.** unit-height strips · covered flags · rectangle projections

**Accept.** Uses Boolean, byte, or packed-bit flags and directly fills each projection's strip range; repeated marking is harmless. Counts uncovered strips after all rectangles. Word-packed realizations fill interior words and mask boundary words. This is direct range painting, without difference-array or interval-union optimization.

**Review.** all checks passed

## N11 · Segment tree maintains projected union length

*algorithm · depth 5 · source: exploration · routes: N5*

**Statement.** Use segment-tree range-coverage updates to maintain the union length of rectangle projections within [ya,yc] when yc>ya. Output yc-ya minus that covered length; output zero when yc<=ya.

**Anchors.** segment tree · union length · rectangle range updates

**Accept.** A tree may represent unit strips or weighted gaps between compressed endpoints. Range-cover assignments or coverage counts maintain union length: a fully covered node contributes its whole span; otherwise sum children. Updates may skip permanently covered nodes. The tree's total covered length, or a range query intersecting [ya,yc], supplies the subtraction.

**Review.** all checks passed

## N12 · Successor deletion counts newly covered strips

*algorithm · depth 5 · source: exploration · routes: N5*

**Statement.** For yc>ya, start with every unit strip uncovered. Successor queries locate uncovered strips within each clipped projection; remove each found strip and decrement an initially yc-ya answer. A disjoint-set successor structure skips removed strips. Output the remaining count, or zero if yc<=ya.

**Anchors.** unit strips · successor queries · disjoint sets · uncovered count

**Accept.** Each strip is charged only on its first removal. A successor structure returns the first unremoved strip at or after a queried index, with yc as a sentinel. It can use parent-to-next links with path compression, or union-by-size components storing their largest index. Range processing repeatedly removes successors until reaching the projection's upper endpoint.

**Review.** all checks passed

## N13 · Incrementally subtract shade from uncovered gaps

*algorithm · depth 4 · source: exploration · routes: N3*

**Statement.** If yc>ya, initialize the uncovered interval set to [ya,yc]. For each rectangle projection, remove its intersection with every affected uncovered interval, retaining any left and right remainders. Output the sum of remaining interval lengths. If yc<=ya, output zero.

**Anchors.** uncovered intervals · projection subtraction · left and right remainders

**Accept.** Maintains pairwise disjoint uncovered intervals and updates their total length while subtracting each projection. An ordered map or balanced search tree locates the first possible intersection and iterates only affected intervals. Each subtraction creates at most two remainder pieces; total insertions and erasures are O(n), giving O(n log n) time.

**Review.** all checks passed

## N14 · Deepest available free descent is safe

*key_property · depth 4 · source: exploration · routes: N3*

**Statement.** For yc>ya, clip projections to [ya,yc]. At height h, descend freely to the smallest bottom among rectangles with top>=h, if below h. Otherwise pay to reach the next lower top or ya. Repeating these choices is optimal.

**Anchors.** current height · deepest free descent · next rectangle top

**Accept.** A rectangle attaining a bottom below h and having top>=h contains h, so the jump is free. Choosing the lowest reachable bottom cannot skip a useful opportunity: all heights passed belong to that rectangle's projection. If no such rectangle exists, the gap down to the next top is uncovered and necessarily paid.

**Review.** all checks passed

## N15 · Suffix minima accelerate the descending route

*algorithm · depth 5 · source: exploration · routes: N14 + N5*

**Statement.** For yc>ya, group clipped projections by top and compute suffix minima of bottoms over integer heights. From yc, jump to this minimum when it is lower; otherwise pay one unit and decrease height by one. Output accumulated cost upon reaching ya. For yc<=ya, output zero.

**Anchors.** suffix minima · rectangle tops · free jumps · unit paid descent

**Accept.** For height h, a suffix minimum over tops at least h identifies the lowest free destination, bounded by h when no descent is possible. Integrality ensures that a failed free jump makes the entire next unit strip uncovered. The simulation strictly lowers height and takes O(n+U) total work including preprocessing, where U=yc-ya.

**Review.** all checks passed

## N16 · Integer expansion makes all weights binary

*reformulation · depth 3 · source: exploration · routes: N8*

**Statement.** Subdivide every adjacent-height edge of the endpoint graph at all intervening integer heights. Each upward unit edge has cost zero, each downward unit edge costs one, and rectangle shortcuts remain zero. Subdivision preserves the contest-to-awards shortest-path distance.

**Anchors.** integer heights · unit movement edges · rectangle shortcuts · binary weights

**Accept.** All endpoint heights are integers. A downward edge of length d becomes d unit-cost edges, while its reverse becomes a chain of zero-cost edges. New intermediate heights have no other shortcuts unless already original endpoints, so subdividing does not change shortest-path distances.

**Review.** all checks passed

## N17 · Zero-one BFS on integer heights

*algorithm · depth 4 · source: exploration · routes: N16*

**Statement.** Use integer heights between the minimum and maximum relevant endpoints, with zero-cost upward steps and rectangle shortcuts and unit-cost downward steps. Run 0-1 BFS from yc and output the distance to ya.

**Anchors.** 0-1 BFS · integer-height graph · binary weights · awards distance

**Accept.** Use the binary-weight deque invariant: for example, remove from the front, inserting weight-zero relaxations at the front and weight-one relaxations at the back; consistently reversing ends is equivalent. Finalization or stale-distance checks may be used. Adjacent-height edges can be implicit. With U<=2000001 height vertices, time and space are O(n+U).

**Review.** all checks passed

## N18 · Free components characterize covered height gaps

*key_property · depth 3 · source: exploration · routes: N8*

**Statement.** In the endpoint-height graph restricted to zero-cost edges, two adjacent height vertices have the same strongly connected component label exactly when a rectangle projection covers the gap between them.

**Anchors.** zero-cost edges · strongly connected components · adjacent-height gaps · rectangle projections

**Accept.** The free upward chain makes SCCs contiguous. A rectangle spanning an elementary gap gives a zero-cost reverse path; conversely, a zero-cost path crossing that gap downward must use a rectangle shortcut spanning it. Thus equal adjacent labels are equivalent to shaded gaps, and component boundaries are exactly uncovered gaps.

**Review.** all checks passed

## N19 · Contract free components and sum separating gaps

*algorithm · depth 4 · source: exploration · routes: N18*

**Statement.** Find strongly connected components using only zero-cost edges of the endpoint-height graph. If yc>ya, sum the differences between consecutive heights in [ya,yc] whose component labels differ, and output this sum. If yc<=ya, output zero.

**Anchors.** SCC labels · component boundaries · height differences · answer

**Accept.** Tarjan, Kosaraju, or another correct SCC algorithm identifies free-motion components. Their contiguity means contracting them leaves an ordered chain: descending across each separating gap costs its height difference, while movement inside each component is free. Iterative DFS avoids recursion depth issues at up to 200002 vertices.

**Review.** all checks passed

## N20 · Queue relaxation solves the height graph

*algorithm · depth 3 · source: exploration · routes: N8*

**Statement.** Build the endpoint-height graph and initialize only yc's distance to zero. Repeatedly process queued vertices, relaxing their adjacent-height edges and rectangle shortcuts and requeuing improved destinations. When the queue becomes empty, output ya's distance.

**Anchors.** height graph · distance relaxations · queue · rectangle shortcuts

**Accept.** A correct label-correcting shortest-path algorithm propagates every distance decrease and terminates only when no edge can improve a label. Nonnegative weights ensure no negative cycle; at convergence the labels are shortest distances. FIFO queues or small-label-first deque scheduling are valid, with an in-queue flag to avoid unnecessary duplicates.

**Review.** all checks passed

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 \| N1 + N2 + N3 + N5 + N6 \| N1 + N2 + N3 + N7 \| N1 + N8 + N9 \| N1 + N2 + N3 + N5 + N10 \| N1 + N2 + N3 + N5 + N11 \| N1 + N2 + N3 + N5 + N12 \| N1 + N2 + N3 + N13 \| N1 + N2 + N3 + N5 + N14 + N15 \| N1 + N8 + N16 + N17 \| N1 + N8 + N18 + N19 \| N1 + N8 + N20

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N4 \| N6 \| N7 \| N9 \| N10 \| N11 \| N12 \| N13 \| N15 \| N17 \| N19 \| N20

## Hazards (END → program)

- **H1** Measure coverage by endpoint differences, not inclusive counts; touching endpoints create no positive gap. Print the answer exactly as an integer or with sufficient precision for the required 10^-7 absolute or relative error. *Check:* Use r-l rather than r-l+1; zero-length intersections contribute zero. Exact integer output meets the tolerance. If using floating-point output, select adequate precision, such as fixed with at least seven fractional digits; default six significant digits can fail for large answers.

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4

Horizontal travel is always free, so only the rectangles' vertical projections matter. Every height between the destination and a higher start that belongs to no projection must be crossed southward in sunlight; all remaining descent can be performed inside rectangles, with free horizontal transfers. Thus the answer is the uncovered length of that vertical interval, computed by sorting and merging projections in O(n log n) time and O(n) space.

New nodes: N1, N2, N3, N4 · judge: AC on 59 tests, slowest 0.039s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N2, N3, N5, N6

Because every vertical endpoint is integral, each open unit-height strip is either entirely coverable by shade or entirely uncovered. Mark clipped rectangle intervals with a difference array and count zero-coverage strips between ya and yc. This avoids sorting and takes O(n+max(0,yc-ya)) time and at most about 8 MB of auxiliary memory.

New nodes: N5, N6 · judge: AC on 59 tests, slowest 0.039s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N2, N3, N7

Sweep the vertical endpoints of clipped rectangle projections while maintaining the number of active intervals. Between consecutive event heights, that count is constant, so add the height gap exactly when the active count is zero. This computes the uncovered length without explicitly forming union components, in O(n log n) time and O(n) space.

New nodes: N7 · judge: AC on 59 tests, slowest 0.046s · program: `paths/P3.cpp` · None submission(s)
### P4 · N1, N8, N9

Model relevant heights as vertices instead of explicitly computing interval coverage. Adjacent heights have a zero-cost northward edge and a southward edge costing their difference, while each rectangle adds a zero-cost edge from its top to its bottom. These edges represent all useful movement after free horizontal transfers, so Dijkstra's shortest path gives the answer in O(n log n) time and O(n) space.

New nodes: N8, N9 · judge: AC on 59 tests, slowest 0.104s · program: `paths/P4.cpp` · None submission(s)
### P5 · N1, N2, N3, N5, N10

The direct-painting algorithm is unchanged, but stores unit-strip flags as packed bits and fills whole machine words. It still computes exactly the union of covered unit strips, then subtracts the number of set bits from the total strip count. Packing reduces the repeated range writes by a factor of eight in memory traffic; this is the one performance retry after the byte-array version timed out.

New nodes: N10 · judge: AC on 59 tests, slowest 0.283s · program: `paths/P5.cpp` · None submission(s)
### P6 · N1, N2, N3, N5, N11

Maintain the coverage union using a segment tree over unit-height strips. Each rectangle performs a range assignment to covered; a fully covered tree node needs no further work, and every other node stores the sum of its children's covered lengths. The root gives the total free descent, so subtract it from yc-ya; this takes O(n log U) update time and O(U) space, with U at most 2,000,000.

New nodes: N11 · judge: AC on 59 tests, slowest 0.062s · program: `paths/P6.cpp` · None submission(s)
### P7 · N1, N2, N3, N5, N12

Process each projection by deleting only its still-uncovered unit strips. A disjoint-set successor structure jumps over strips covered by earlier rectangles, so each of at most 2,000,000 strips is deleted once. With union by size, path compression, and the maximum index stored per component, the algorithm takes O((n+U) alpha(U)) time and O(U) memory.

New nodes: N12 · judge: AC on 59 tests, slowest 0.068s · program: `paths/P7.cpp` · None submission(s)
### P8 · N1, N2, N3, N13

Maintain the uncovered portion of [ya,yc] directly as a set of disjoint intervals. Subtract each rectangle's vertical projection, deleting fully covered gaps and splitting partially covered ones; the final total gap length is the answer. An ordered map finds affected gaps, and since each update creates at most two replacement pieces, the total running time is O(n log n) with O(n) space.

New nodes: N13 · judge: AC on 59 tests, slowest 0.078s · program: `paths/P8.cpp` · None submission(s)
### P9 · N1, N2, N3, N5, N14, N15

The repeated-scan greedy route can be accelerated using integral heights. Group projections by their top height and take suffix minima of their bottoms, giving the deepest free descent available from every height. Then repeatedly jump downward for free when possible, or pay for one unit of descent otherwise; this is the one retry after the quadratic scan timed out, and takes O(n+U) time and O(U) space.

New nodes: N14, N15 · judge: AC on 59 tests, slowest 0.044s · program: `paths/P9.cpp` · None submission(s)
### P10 · N1, N8, N16, N17

Expand the endpoint-height graph into every integer height between its minimum and maximum. Upward unit edges and rectangle shortcuts have weight zero, while downward unit edges have weight one, so a deque-based 0-1 BFS computes the optimum without a priority queue. There are at most 2,000,001 vertices and O(n+2,000,000) edges, generated implicitly except for rectangle shortcuts.

New nodes: N16, N17 · judge: AC on 59 tests, slowest 0.072s · program: `paths/P10.cpp` · None submission(s)
### P11 · N1, N8, N18, N19

Analyze only zero-cost edges of the endpoint-height graph. Their strongly connected components are contiguous blocks of heights, and an adjacent-height gap is free exactly when both endpoints lie in the same component. Compute these components and sum the height gaps between different components on the downward route from yc to ya; this uses O(n log n) time including coordinate sorting and O(n) memory.

New nodes: N18, N19 · judge: AC on 59 tests, slowest 0.129s · program: `paths/P11.cpp` · None submission(s)
### P12 · N1, N8, N20

Use queue-based Bellman-Ford relaxation on the sparse endpoint-height graph instead of finalizing vertices with Dijkstra. Every improved distance is propagated until no relaxation remains, at which point all graph shortest distances are correct. The graph uses O(n) memory; worst-case relaxation time is quadratic, so I leave runtime to the judge.

New nodes: N20 · judge: AC on 59 tests, slowest 0.107s · program: `paths/P12.cpp` · None submission(s)

## Exploration

Finished: True · 16 submissions · reason: The judge reports that the graph has reached its limit of 12 accepted paths and explicitly requests finishing. The accepted paths cover sorted union, dense differences, endpoint sweeping, direct packed painting, segment trees, successor deletion, interval subtraction, greedy suffix minima, Dijkstra, 0-1 BFS, zero-cost SCC contraction, and queue-based shortest-path relaxation.

Ideas the explorer considered and dropped:

- Complete graph of shaded regions with transfer weight max(0,bottom_i-top_j), solved by dense Dijkstra: submitted and received TLE on secret-02-wg; abandoned the quadratic implementation.
- Independently scan every projection for each elementary endpoint gap: submitted and received TLE on secret-02-wg; abandoned.
- Byte-array direct painting: submitted and received TLE on secret-01-wg. Its single performance retry used packed bits and was accepted as the direct-painting path.
- Repeated full scans to choose the deepest free descent or next paid gap: submitted and received TLE on secret-02-wg. Its single retry used precomputed suffix minima and was accepted.
- Compressed difference arrays, ordered event maps, alternate sort directions, and bucketed reach scans were treated as equivalent realizations of already represented sweep, merge, or greedy claims rather than additional paths.
- A sparse factorization of the complete shaded-region transfer graph was considered but not submitted because the graph reached its explicit 12-path limit; it was not rejected for presumed speed.
- Summing rectangle heights directly is incorrect because vertically overlapping projections can come from disjoint rectangles and must not be counted repeatedly. Horizontal separation does not prevent free transfers.

## Review

END ok: True — Every END route includes the geometric reduction or an equivalent height-graph model and a complete output algorithm. The accepted packed-painting realization is covered by N10's acceptance explanation; neither its repeated work nor the queue-relaxation route's worst-case bound invalidates the accepted approaches.

Hazards ok: True — H1 correctly distinguishes interval length from endpoint counts, handles touching endpoints and zero-length intersections, and specifies a usable output-accuracy check. Required height differences and the answer are at most 2,000,000, so no additional wide-integer requirement is essential. The algorithm nodes already cover non-southward destinations and empty coverage.

**Builder's notes.** Moved implementation choices from the statements of N4, N11, and N17 into their acceptance explanations. N18 now states only the shaded-gap/SCC-label characterization, with contiguity in its supporting explanation. Because hazard ids are fixed, incorporated the requested output-accuracy constraint into H1 while preserving its existing geometric-length requirements.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `5130c49d7000601e` | 4 | 2 | revise |
| 2 | `3349bf7008e9185f` | 0 | 0 | accept |
