# Reasoning graph · Blackboard Game (2025/B-blackboard-game)

status **accepted** · version `29b348c251b23c0f` · 26 nodes · 6 END route(s) · 5 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 4 review round(s)

**Route.** P1: For large n, three primes in (n/4,n/3] give a constant-size pairing strategy: starting at twice one prime, every opponent move can be answered inside six semiprimes. P2: Use the same constant-size prime pairing strategy whenever three suitable primes exist, but solve the small exceptional boards with a different optimization problem. P3: Keep the large-board prime pairing construction, but characterize the small-board answer through minimum vertex covers instead of matching reachability. P4: Use a different large-board construction based on all semiprimes in the upper half of the board. P5: Use the prime pairing construction for large boards, and encode the choice of an even first move by adding one auxiliary vertex adjacent to all even integers on a small board. P6: Store exact outcomes and winning even starts for boards through 83, and answer larger boards by choosing twice the largest prime not exceeding n/3.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Prime-ratio vertex geography | statement |
| N2 | 2 | key_property | Three-prime neighborhood gadget | N1 |
| N3 | 3 | construction | Closed pairing wins from twice prime | N2 |
| N4 | 2 | key_property | Prime-factor parity bipartition | N1 |
| N5 | 2 | key_property | Exposable starting vertices win | N1 |
| N6 | 3 | algorithm | Alternating paths identify winning even starts | N4 + N5 |
| N7 | 1 | key_property | Small bound on prime-gadget exceptions | statement |
| N8 | 4 | algorithm | Prime gadget with exact small fallback | N3 + N6 + N7 |
| N9 | 3 | reformulation | Minimize covered even vertices | N5 |
| N10 | 4 | algorithm | Flow optimizes matching size and even coverage | N4 + N9 |
| N11 | 5 | algorithm | Prime gadget with weighted matching fallback | N3 + N7 + N10 |
| N12 | 3 | reformulation | Minimum covers characterize compulsory vertices | N4 + N5 |
| N13 | 3 | key_property | Two extremal covers capture their union | N4 |
| N14 | 4 | algorithm | Weighted board covers reduce to cuts | N13 |
| N15 | 5 | algorithm | Prime gadget with extremal-cover fallback | N3 + N7 + N12 + N14 |
| N16 | 2 | reformulation | Upper-half semiprime incidence graph | N1 |
| N17 | 3 | key_property | Cyclic components match their prime vertices | N16 |
| N18 | 3 | key_property | Bicyclic cores survive any edge deletion | N16 |
| N19 | 4 | construction | Even semiprime in bicyclic core wins | N16 + N17 + N18 |
| N20 | 3 | key_property | Prime triples force a bicyclic core | N2 + N7 + N16 |
| N21 | 5 | algorithm | Semiprime-core search with exact fallback | N19 + N20 + N6 |
| N22 | 3 | reformulation | Auxiliary vertex encodes the first move | N5 |
| N23 | 4 | algorithm | One general augmentation tests the start | N22 |
| N24 | 5 | algorithm | Prime gadget with auxiliary-blossom fallback | N3 + N7 + N23 |
| N25 | 4 | construction | Largest lower-third prime wins | N3 + N6 + N7 |
| N26 | 5 | algorithm | Exact small boards and largest prime | N6 + N25 |
| END | | | complete solution | N1 + N2 + N3 + N4 + N5 + N6 + N7 + N8 \| N1 + N2 + N3 + N4 + N5 + N7 + N9 + N10 + N11 \| N1 + N2 + N3 + N4 + N5 + N7 + N12 + N13 + N14 + N15 \| N1 + N2 + N4 + N5 + N6 + N7 + N16 + N17 + N18 + N19 + N20 + N21 \| N1 + N2 + N3 + N5 + N7 + N22 + N23 + N24 \| N1 + N2 + N3 + N4 + N5 + N6 + N7 + N25 + N26 |

## N1 · Prime-ratio vertex geography

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** Form an undirected graph on 1 through n, joining two integers when the larger divided by the smaller is prime. After the initial even vertex is circled, play follows a path without revisiting vertices; the player unable to extend it loses.

**Anchors.** circled number · prime · erases · even number

**Accept.** Identifies multiplication and exact division by a prime as graph edges. Erasing the previous circled integer makes every previously visited vertex unavailable. The initial selection is itself the first player's turn.

**Review.** all checks passed

## N2 · Three-prime neighborhood gadget

*key_property · depth 2 · source: exploration · routes: N1*

**Statement.** Let p,q,r be distinct primes exceeding 3 with n/4 < p,q,r <= n/3. For S={2p,3p,2q,3q,2r,3r}, the neighborhood is exactly {p,q,r,2,3}; each 2s has neighbors s,2 and each 3s has neighbors s,3.

**Anchors.** prime · multiplied · divided · n · even number

**Accept.** Every product is at most n and exceeds n/2, so multiplication is impossible. Division yields exactly its displayed prime factors. Distinct primes exceeding 3 make the six products and five neighbors distinct and the sets disjoint. An integer implementation selects primes greater than floor(n/4) and at most floor(n/3), excluding 2 and 3.

**Review.** all checks passed

## N3 · Closed pairing wins from twice prime

*construction · depth 3 · source: exploration · routes: N2*

**Statement.** For distinct primes p,q,r>3 in (n/4,n/3], let S={2p,3p,2q,3q,2r,3r}. For any start x in {2p,2q,2r}, the neighborhood of S can be matched into S excluding x. Replying along that matching makes x a winning first move.

**Anchors.** first move · winning strategy · three primes · neighborhood matching

**Accept.** For x=2p, one matching is p–3p, q–3q, r–2r, 2–2q, 3–3r. Any matching saturating the neighborhood and avoiding x counts. Each reply returns to S; whenever an opponent selects an unused neighbor, its paired semiprime is unused too. Relabeling p,q,r permits any of the three even starts.

**Review.** all checks passed

## N4 · Prime-factor parity bipartition

*key_property · depth 2 · source: exploration · routes: N1*

**Statement.** The prime-ratio graph is bipartite: color an integer by the parity of its total number of prime factors, counted with multiplicity. Every legal move changes that parity.

**Anchors.** prime factorization · prime · integers from 1 to n

**Accept.** Uses Omega(1)=0 and Omega(xp)=Omega(x)+1, including repeated prime factors. Computing Omega(x) from Omega(x/spf[x])+1 is one realization; counting only distinct prime divisors is not. Any equivalent two-coloring of the graph counts.

**Review.** all checks passed

## N5 · Exposable starting vertices win

*key_property · depth 2 · source: exploration · routes: N1*

**Statement.** An even starting vertex v wins for the first player exactly when some maximum matching of the prime-ratio graph leaves v unmatched.

**Anchors.** winning first move · maximum matching · even number

**Accept.** If a maximum matching exposes v, the first player answers along matching edges; failure would create an augmenting path. If every maximum matching covers v, the second player moves to v's mate. The remaining matching is maximum after deleting v and exposes that mate, so the second player has the pairing strategy.

**Review.** all checks passed

## N6 · Alternating paths identify winning even starts

*algorithm · depth 3 · source: exploration · routes: N4 + N5*

**Statement.** In the prime-ratio graph, fix a maximum matching and search from unmatched vertices using successive nonmatching-edge/matching-edge pairs. The reached even-labelled vertices, including even roots, are exactly the winning initial selections.

**Anchors.** prime-ratio graph · maximum matching · alternating paths · winning even starts

**Accept.** Flipping an even-length alternating path preserves matching size and exposes its endpoint. Conversely, symmetric difference with a maximum matching exposing a vertex supplies such a path. Thus the search finds all exposable board vertices, and its even-labelled vertices are precisely legal winning starts. Search may be separate for the two colors or combined in two-edge steps.

**Review.** all checks passed

## N7 · Small bound on prime-gadget exceptions

*key_property · depth 1 · source: exploration · routes: statement*

**Statement.** Every integer n with 177 <= n <= 10^7 has at least three primes exceeding 3 in the interval (n/4,n/3]. Thus any board in the allowed range lacking the three-prime gadget has n <= 176.

**Anchors.** n · prime · 10^7

**Accept.** This finite arithmetic claim can be verified by an Eratosthenes sieve and prefix prime counts over the stated range. Equivalently, check 177 through 187 directly, then verify 3*p[i+3] <= 4*p[i] for consecutive primes with 47 <= p[i] <= 2500000.

**Review.** all checks passed

## N8 · Prime gadget with exact small fallback

*algorithm · depth 4 · source: exploration · routes: N3 + N6 + N7*

**Statement.** Sieve primes. If (n/4,n/3] contains three primes exceeding 3, output first and twice any of them. Otherwise compute a maximum matching, mark vertices exposable by alternating paths, and output first with any marked even vertex, or second if none exists.

**Anchors.** first · second · winning first move · test cases

**Accept.** The sieve need only reach the largest n divided by 3. Interval searches find three suitable primes. Exceptional boards have at most 176 vertices, so explicit edges, ordinary bipartite augmenting paths, and alternating reachability easily fit the limits. The pairing construction justifies large answers; exposure characterizes all small answers.

**Review.** all checks passed

## N9 · Minimize covered even vertices

*reformulation · depth 3 · source: exploration · routes: N5*

**Statement.** Among maximum-cardinality matchings, choose one minimizing the number of covered even integers. The first player wins exactly when this matching leaves an even integer uncovered; any such integer is a winning first move.

**Anchors.** even integer · winning first move · maximum matching

**Accept.** A winning even vertex is uncovered in some maximum matching, whose covered-even count is below floor(n/2). Minimization therefore also leaves an even vertex uncovered. Conversely, any uncovered even vertex in the chosen maximum matching satisfies the winning characterization. Cardinality must take priority over the secondary objective.

**Review.** all checks passed

## N10 · Flow optimizes matching size and even coverage

*algorithm · depth 4 · source: exploration · routes: N4 + N9*

**Statement.** A unit-capacity flow network representing the prime-ratio bipartition can realize matching cardinality as flow value and covered even integers as total cost. A minimum-cost maximum flow therefore yields a maximum matching minimizing even coverage.

**Anchors.** prime-factor parity · legal move · even endpoints · maximum matching

**Accept.** Use source-to-left, legal left-to-right, and right-to-sink arcs, all unit-capacity. Charge one per even matched endpoint, either on its terminal arc or by summing endpoint charges on each cross-arc. Integral flows correspond to matchings; value and cost equal their size and covered-even count. Any correct min-cost maximum-flow algorithm on these small networks counts.

**Review.** all checks passed

## N11 · Prime gadget with weighted matching fallback

*algorithm · depth 5 · source: exploration · routes: N3 + N7 + N10*

**Statement.** Find three primes exceeding 3 in (n/4,n/3] and output first with twice any one if they exist. Otherwise obtain a maximum matching minimizing covered even vertices by min-cost flow; output first with an uncovered even vertex, or second if every even vertex is covered.

**Anchors.** first · second · even integer · test cases

**Accept.** Sieve primes through max(n)/3 and test the interval. For an exceptional board, build all prime-ratio edges and the unit-capacity network, augment to maximum flow at minimum cost, and inspect the matching's covered vertices. The sieve dominates memory and large-input work; flow networks have at most 178 nodes.

**Review.** all checks passed

## N12 · Minimum covers characterize compulsory vertices

*reformulation · depth 3 · source: exploration · routes: N4 + N5*

**Statement.** In the prime-ratio graph, a vertex is covered by every maximum matching exactly when it belongs to at least one minimum-cardinality vertex cover. Thus an even integer is a winning first move exactly when no minimum vertex cover contains it.

**Anchors.** even integer · maximum matching · minimum vertex cover

**Accept.** By bipartite matching-cover duality, deleting v reduces maximum matching size exactly when it reduces minimum cover size. A minimum cover containing v loses one vertex upon deletion; conversely, adding v to a cover of G-v of size tau(G)-1 yields a minimum cover containing v.

**Review.** all checks passed

## N13 · Two extremal covers capture their union

*key_property · depth 3 · source: exploration · routes: N4*

**Statement.** Let L,R be the prime-factor-parity classes. Choose minimum-cardinality covers C_L,C_R maximizing their numbers of vertices in L,R respectively. The union C_L union C_R contains exactly the vertices appearing in at least one minimum-cardinality vertex cover.

**Anchors.** prime-factor parity · minimum vertex cover · L · R

**Accept.** For minimum covers C,D, combining their union on L with their intersection on R gives another minimum cover; the opposite combination does too. Consequently all possible L-members can occur simultaneously, and likewise all possible R-members. Maximizing the corresponding count therefore includes every possible member of that class.

**Review.** all checks passed

## N14 · Weighted board covers reduce to cuts

*algorithm · depth 4 · source: exploration · routes: N13*

**Statement.** A minimum-weight vertex cover of the prime-ratio graph corresponds to a minimum source–left–right–sink cut: vertex weights are terminal-arc capacities, and legal-move arcs prohibit leaving an edge uncovered.

**Anchors.** legal move · prime-factor parity · weighted vertex cover · minimum cut

**Accept.** Use the prime-factor-parity bipartition. Source-to-left and right-to-sink capacities are nonnegative vertex weights; left-to-right legal-move arcs exceed the total vertex weight. A minimum cut cannot cross a legal-move arc. It selects left vertices on the sink side and right vertices on the source side. Its capacity equals their cover weight, so minimum cuts recover minimum-weight covers.

**Review.** all checks passed

## N15 · Prime gadget with extremal-cover fallback

*algorithm · depth 5 · source: exploration · routes: N3 + N7 + N12 + N14*

**Statement.** If three primes exceeding 3 lie in (n/4,n/3], output first with twice one. Otherwise, use weighted cuts prioritizing minimum cover cardinality then maximum membership in each parity class. Output first with an even vertex outside both covers, or second if none exists.

**Anchors.** first · second · winning first move · extremal minimum covers

**Accept.** One lexicographic encoding gives the favored class weight B-1 and the other class B, with B>n. Cover weight is B times cardinality minus favored membership; minimizing it therefore produces the required extremal cover. Repeat for both classes and inspect their union. Equivalent encodings count. Sieve queries handle large boards; exceptional cut networks have at most 178 nodes.

**Review.** all checks passed

## N16 · Upper-half semiprime incidence graph

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** For each semiprime pq with n/2 < pq <= n, create an edge between primes p and q, allowing a loop when p=q. Its blackboard neighbors are exactly its prime factors. Thus these semiprimes and their legal neighbors form the incidence graph of this prime-product graph.

**Anchors.** prime · multiplied · divided · semiprime · n

**Accept.** A number above n/2 cannot be multiplied by a prime while remaining on the board. A semiprime can only be divided to its prime factors. A square has one distinct game neighbor, represented by a loop in the auxiliary prime-product graph; repeated adjacency entries in a game-graph implementation need not be removed if harmless.

**Review.** all checks passed

## N17 · Cyclic components match their prime vertices

*key_property · depth 3 · source: exploration · routes: N16*

**Statement.** A connected component of the prime-product graph admits a matching of every prime vertex to a distinct incident semiprime exactly when it contains a cycle, with a loop counting as a cycle.

**Anchors.** prime-product graph · prime vertices · semiprimes · cycle

**Accept.** A tree has fewer edges than vertices, making such an assignment impossible. In a cyclic component, retain a spanning unicyclic subgraph, assign cycle vertices distinct cycle edges, and assign each remaining vertex its edge toward the cycle. This also handles a loop as the unique cycle.

**Review.** all checks passed

## N18 · Bicyclic cores survive any edge deletion

*key_property · depth 3 · source: exploration · routes: N16*

**Statement.** In a connected component of the prime-product graph's 2-core with more edges than vertices, deleting any one edge leaves every resulting component cyclic. Loops contribute two to degree and one to the edge count.

**Anchors.** prime-product graph · 2-core · edge deletion · cycle

**Accept.** Deleting a nonbridge leaves a connected graph with at least as many edges as vertices. Deleting a bridge leaves each side with minimum degree at least two except possibly one vertex; a finite tree cannot have only one possible leaf. Thus both sides retain cycles. Implementations must count a prime-square loop as two incidences but one edge.

**Review.** all checks passed

## N19 · Even semiprime in bicyclic core wins

*construction · depth 4 · source: exploration · routes: N16 + N17 + N18*

**Statement.** An even semiprime whose edge lies in a prime-product 2-core component with more edges than vertices is a winning first move. Delete that edge and match every core prime to a distinct remaining incident semiprime; answer opponent moves using these pairs.

**Anchors.** even semiprime · winning first move · 2-core · pairing strategy

**Accept.** Every component after deletion is cyclic, so the matching exists. Every legal move from a selected core semiprime reaches a core prime, whose paired semiprime is available whenever the prime is. Returning to semiprimes after every response prevents the opponent from escaping the paired set.

**Review.** all checks passed

## N20 · Prime triples force a bicyclic core

*key_property · depth 3 · source: exploration · routes: N2 + N7 + N16*

**Statement.** For every 177 <= n <= 10^7, the prime-product 2-core has a component with more edges than vertices containing an even semiprime. Three primes in (n/4,n/3] produce a K(2,3) subgraph between {2,3} and those primes.

**Anchors.** three primes · n · 2-core · even semiprime

**Accept.** The six products are upper-half semiprimes. Their K(2,3) subgraph has six edges and five vertices and survives degree-below-two peeling. Its containing core component has cycle rank at least two and includes edges incident to prime 2, hence even semiprimes.

**Review.** all checks passed

## N21 · Semiprime-core search with exact fallback

*algorithm · depth 5 · source: exploration · routes: N19 + N20 + N6*

**Statement.** Build the upper-half semiprime prime-product graph and peel degree-below-two vertices. If the remaining component containing 2 has more edges than vertices, output first with any semiprime incident to 2 there. Otherwise use maximum matching and alternating exposure to output a winning even start, or second.

**Anchors.** first · second · prime 2 · semiprime · test cases

**Accept.** Sieve primes through max(n)/2; enumerate each product once by ordering its prime factors. Degree peeling and component traversal are linear in graph size, bounded by O(n). Only n<=176 can reach the exact matching fallback. Count loops twice in degrees and once as edges.

**Review.** all checks passed

## N22 · Auxiliary vertex encodes the first move

*reformulation · depth 3 · source: exploration · routes: N5*

**Statement.** Add an auxiliary vertex adjacent to every even integer. The first player wins exactly when the enlarged graph's maximum matching is larger than the original graph's. In that case, the auxiliary vertex's mate in any enlarged maximum matching is a winning first move.

**Anchors.** even integer · first move · maximum matching · auxiliary vertex

**Accept.** A maximum original matching exposing an even vertex extends by its auxiliary edge. Conversely, removing the auxiliary vertex and its edge from a larger matching leaves a maximum original matching exposing that even mate. Adding one vertex can increase matching size by at most one.

**Review.** all checks passed

## N23 · One general augmentation tests the start

*algorithm · depth 4 · source: exploration · routes: N22*

**Statement.** Start with a maximum matching of the original prime-ratio graph and add the unmatched auxiliary vertex. A general-graph augmenting-path search rooted there succeeds exactly when the first player wins; after augmenting, its mate is a winning even first move.

**Anchors.** auxiliary vertex · augmenting path · even first move

**Accept.** No augmenting path exists entirely in the original graph, so any new one must have the auxiliary vertex as an endpoint. Edmonds blossom contraction handles odd cycles caused by connecting the auxiliary vertex to both prime-factor-parity classes. For n<=176, ordinary cubic-time general matching is ample.

**Review.** all checks passed

## N24 · Prime gadget with auxiliary-blossom fallback

*algorithm · depth 5 · source: exploration · routes: N3 + N7 + N23*

**Statement.** If three primes exceeding 3 occur in (n/4,n/3], output first with twice one. Otherwise maximum-match the board graph, add an auxiliary vertex adjacent to every even integer, and search for an augmentation from it. Output first with its resulting mate if successful, or second otherwise.

**Anchors.** first · second · winning first move · test cases

**Accept.** Prime sieving and interval search handle all large inputs. For exceptional boards, construct exact prime-ratio edges, use general matching, then perform the single auxiliary-rooted augmentation. The original graph has at most 176 vertices, and the auxiliary graph at most 177.

**Review.** all checks passed

## N25 · Largest lower-third prime wins

*construction · depth 4 · source: exploration · routes: N3 + N6 + N7*

**Statement.** For every 84 <= n <= 10^7, let p be the largest prime not exceeding n/3. Circling 2p is a winning first move.

**Anchors.** n · prime · even number · winning first move

**Accept.** For 84 through 176, exact maximum matching and alternating exposure certify that 2p is exposable. For n >= 177, N7 supplies three primes in the required interval; the largest prime at most n/3 belongs to that interval and can be included in a triple, so N3 applies. No perfect matching of the entire graph after deleting 2p is required.

**Review.** all checks passed

## N26 · Exact small boards and largest prime

*algorithm · depth 5 · source: exploration · routes: N6 + N25*

**Statement.** For n <= 83, output first with any even vertex exposable by a maximum matching, or second if none exists. For n >= 84, output first with twice the largest prime not exceeding n/3.

**Anchors.** first · second · winning first move · test cases

**Accept.** Small-board outcomes and witnesses may be computed on demand using N6 or stored in an exactly certified table; zero may denote second and a positive entry a winning even start. For large boards, sieve through floor(max(n)/3) and retain predecessor-prime values, or search the sorted primes. With M=max(n), O(M log log M) sieve work plus bounded small-board computations fits the limits.

**Review.** all checks passed

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 + N5 + N6 + N7 + N8 \| N1 + N2 + N3 + N4 + N5 + N7 + N9 + N10 + N11 \| N1 + N2 + N3 + N4 + N5 + N7 + N12 + N13 + N14 + N15 \| N1 + N2 + N4 + N5 + N6 + N7 + N16 + N17 + N18 + N19 + N20 + N21 \| N1 + N2 + N3 + N5 + N7 + N22 + N23 + N24 \| N1 + N2 + N3 + N4 + N5 + N6 + N7 + N25 + N26

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N8 \| N11 \| N15 \| N21 \| N24 \| N26

## Hazards (END → program)

- **H1** The first move must be an even integer between 1 and n; circling it consumes the first player's initial turn. *Check:* Return first only with an even starting vertex, not a move for the player subsequently facing the circled vertex. In the matching solution, exposed vertices favor the initial selector.
- **H2** Division by a prime is legal only when it produces an integer. A multiplication result exceeding n is not on the board. *Check:* Generate division moves only for prime divisors and multiplication moves only within the initial range. A graph-based solution must represent exactly these prime-ratio adjacencies.
- **H3** An erased number cannot be selected again, even when its ratio with the current circled number is prime. *Check:* Direct game simulations must exclude all previously visited vertices. Graph-based reasoning must model vertex deletion, not unrestricted walks or merely forbidding reuse of an edge.
- **H4** Output one line per test case: either second or first followed by a valid winning even integer. *Check:* Do not print the strategy, matching, or diagnostic information; handle all t boards independently.
- **H5** Unchecked products in prime testing, sieving, or move generation can exceed 32-bit range although n<=10^7; comparisons must not rely on overflowing arithmetic. *Check:* Use sufficiently wide arithmetic for unchecked products, or compare against n divided by a factor before multiplying. Products already proved at most n need not use a wider type.

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4, N5, N6, N7, N8

For large n, three primes in (n/4,n/3] give a constant-size pairing strategy: starting at twice one prime, every opponent move can be answered inside six semiprimes. A sieve verifies that this condition holds for every 177 <= n <= 10^7. For the remaining small boards, solve undirected vertex geography using maximum bipartite matching and alternating-path reachability; the sieve dominates the running time.

New nodes: N1, N2, N3, N4, N5, N6, N7, N8 · judge: AC on 118 tests, slowest 0.033s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N2, N3, N4, N5, N7, N9, N10, N11

Use the same constant-size prime pairing strategy whenever three suitable primes exist, but solve the small exceptional boards with a different optimization problem. Among maximum-cardinality matchings, minimize the number of covered even vertices using min-cost maximum flow; its unmatched even vertices give precisely the existence and a witness needed for the first move. The exceptional boards have at most 176 vertices, so this weighted optimization is inexpensive.

New nodes: N9, N10, N11 · judge: AC on 118 tests, slowest 0.026s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N2, N3, N4, N5, N7, N12, N13, N14, N15

Keep the large-board prime pairing construction, but characterize the small-board answer through minimum vertex covers instead of matching reachability. A vertex is compulsory in every maximum matching exactly when it belongs to some minimum vertex cover; two extremal minimum covers together contain every such vertex. Compute those covers by two weighted minimum cuts, then choose an even integer outside their union, if one exists.

New nodes: N12, N13, N14, N15 · judge: AC on 118 tests, slowest 0.024s · program: `paths/P3.cpp` · None submission(s)
### P4 · N1, N2, N4, N5, N6, N7, N16, N17, N18, N19, N20, N21

Use a different large-board construction based on all semiprimes in the upper half of the board. Regard each such semiprime as an edge between its prime factors, peel the resulting graph to its 2-core, and find a component with more edges than vertices containing an even semiprime; a cyclic-component matching supplies a closed winning pairing. The three-prime bound guarantees this succeeds for n >= 177, and maximum matching handles the remaining small boards; enumeration and peeling are linear in the number of primes and semiprimes.

New nodes: N16, N17, N18, N19, N20, N21 · judge: AC on 118 tests, slowest 0.058s · program: `paths/P4.cpp` · None submission(s)
### P5 · N1, N2, N3, N5, N7, N22, N23, N24

Use the prime pairing construction for large boards, and encode the choice of an even first move by adding one auxiliary vertex adjacent to all even integers on a small board. The first player wins exactly when this addition increases the maximum matching size; the auxiliary vertex's mate then gives a winning first move. Starting with a maximum matching of the original board, one Edmonds augmenting-path search from the auxiliary vertex decides this, including the odd cycles created by its new edges.

New nodes: N22, N23, N24 · judge: AC on 118 tests, slowest 0.031s · program: `paths/P5.cpp` · None submission(s)
### P6 · N1, N2, N3, N4, N5, N6, N7, N25, N26

Store exact outcomes and winning even starts for boards through 83, and answer larger boards by choosing twice the largest prime not exceeding n/3. The large-board rule follows from maximum-matching exposure: certify the bounded intermediate range exactly and use the existing three-prime pairing construction thereafter. A prime sieve and predecessor-prime table make preprocessing fast enough and each test-case lookup constant time.

New nodes: N25, N26 · judge: AC on 118 tests, slowest 0.021s · program: `paths/P6.cpp` · None submission(s)

## Exploration

Finished: True · 5 submissions · reason: Five correct, fast approaches have been accepted: prime-gadget construction with alternating-exposure matching, weighted matching, extremal minimum covers, a semiprime bicyclic-core construction, and auxiliary-vertex blossom augmentation. I do not have another genuinely different approach with both a correctness argument and suitable running time.

Ideas the explorer considered and dropped:

- Full minimax over erased-number subsets: exponential state space, even on the boards below the prime-gadget threshold.
- Descending greedy prime-divisor pairing: not necessarily maximum; for n=18 it can leave an even vertex exposed despite that vertex being compulsory in every maximum matching.
- Generic maximum matching on all n vertices: correct in principle, but unnecessary and lacks a convincing one-second bound at n=10^7.
- Leaf stripping alone: useful reduction but can leave cyclic cores requiring additional reasoning; the accepted semiprime-core approach supplies that reasoning for a suitable restricted graph.
- Repeated matching after deleting each candidate, alternative bipartite matching implementations, and direct flow-residual reachability: these reuse the existing exposability characterization rather than introduce a substantially new reasoning path.
- Algebraic matching via randomized matrix rank: introduces probabilistic errors without a practical deterministic guarantee, while the accepted approaches are exact.

## Review

END ok: True — All six routes supply a winning-start construction, an exact decision procedure for their exceptional boards, and bounds keeping those procedures small. No essential algorithmic step is missing before routine implementation.

Hazards ok: True — The hazards cover the initial-turn convention, legal prime-ratio moves, erased vertices, required output, and overflow-safe products. They impose semantic or arithmetic constraints without requiring a particular representation or integer type.

**Advisories.**

- the editorial's approach is not among the paths: P6 reproduces the reference solution's small-table/largest-prime output algorithm, but not the supplied editorial's reasoning: that editorial does not establish the maximum-matching exposure and prime-gadget prerequisites of the END route. Its claimed perfect-matching characterization and large-board perfect matching after deleting 2p are false; for even n, that deletion leaves an odd number of vertices. Those claims should remain excluded rather than be added to the graph; P6 supplies a corrected justification.

**Builder's notes.** N26 now states the exact-small-board/largest-prime output rule without requiring caching; its accept explicitly permits on-demand computation and certified lookup. N14's accept also clarifies that minimum cuts avoid the high-capacity legal-move arcs, rather than calling such cuts merely finite. I agree that P6 reproduces the reference solution's output rule with a repaired justification, not the supplied editorial's false perfect-matching argument. That false theorem remains excluded. All ids, routes, END routes, nodes, and hazards are preserved.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `6848039efc70dbb7` | 5 | 2 | revise |
| 2 | `37d90689111adc0e` | 0 | 1 | accept |
| 3 | `64c0de0042f5ebdf` | 1 | 2 | revise |
| 4 | `29b348c251b23c0f` | 0 | 1 | accept |
