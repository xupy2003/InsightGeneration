# Reasoning graph · Bride of Pipe Stream (2025/C-bride-of-pipe-stream)

status **accepted** · version `480d0f98b0c98a0a` · 14 nodes · 4 END route(s) · 2 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 3 review round(s)

**Route.** P1: Normalize the factory inflow to one and dualize the max-min objective into minimizing a weighted-sum optimum over the reservoir-weight simplex. P2: Use the same weighted-sum dual, but obtain a supporting reservoir-flow vector from each optimal deterministic drainage policy. P3: Maintain a restricted collection of deterministic drainage policies and solve the max-min mixture problem for just those policies. P4: Apply the ellipsoid method to the low-dimensional reservoir-weight dual, using optimal policy vectors as separating subgradients.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Convex reservoir outcomes from duct flows | statement |
| N2 | 2 | reformulation | Reservoir-weight minimax dual | N1 |
| N3 | 2 | algorithm | Weighted drainage backward dynamic program | N1 |
| N4 | 3 | key_property | Partial minimization preserves drainage convexity | N2 + N3 |
| N5 | 4 | algorithm | Nested convex minimization produces percentage | N4 |
| N6 | 3 | key_property | Optimal policy supplies a supporting vector | N3 |
| N7 | 4 | key_property | Policy cuts retain the optimal sublevel | N2 + N6 |
| N8 | 5 | key_property | Retained volume bounds objective error | N7 |
| N9 | 6 | algorithm | Centroid cutting computes the optimum | N8 |
| N10 | 4 | reformulation | Restricted policy mixtures give lower bounds | N1 + N6 |
| N11 | 5 | key_property | Restricted dual provides an optimality certificate | N2 + N10 |
| N12 | 6 | algorithm | Policy generation closes the duality gap | N11 |
| N13 | 5 | key_property | Safe ellipse localization of reservoir weights | N7 |
| N14 | 6 | algorithm | Ellipsoid separation computes the percentage | N8 + N13 |
| END | | | complete solution | N1 + N2 + N3 + N4 + N5 \| N1 + N2 + N3 + N6 + N7 + N8 + N9 \| N1 + N2 + N3 + N6 + N10 + N11 + N12 \| N1 + N2 + N3 + N6 + N7 + N8 + N13 + N14 |

## N1 · Convex reservoir outcomes from duct flows

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** Normalize factory inflow to one. Duct flows are nonnegative; each station's total outgoing flow equals its incoming contributions, plus one only at station 1. Reservoir flows are their incoming contributions. These constraints give the compact convex set C of attainable reservoir vectors; maximize the smallest coordinate over C.

**Anchors.** station drainage · ducts · reservoirs · factory

**Accept.** Use duct flows as linear variables, with each output receiving p/100 of its duct's flow. Conversely, dividing outgoing duct flows by total station inflow realizes any feasible flow; zero-inflow stations may use arbitrary proportions. Altitude ordering and losses bound every flow. The reported percentage is 100 times the normalized optimum.

**Review.** all checks passed

## N2 · Reservoir-weight minimax dual

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** For reservoir weights w_j>=0 summing to one, let F(w)=max over u in C of w·u. The optimal minimum reservoir flow equals min over such w of F(w).

**Anchors.** reservoirs · minimum amount · station drainage

**Accept.** Apply finite-dimensional minimax to the compact convex outcome set and weight simplex, or derive the same equality by linear-programming duality. The identity min_j u_j=min over simplex weights of w·u establishes the primal max-min form.

**Review.** all checks passed

## N3 · Weighted drainage backward dynamic program

*algorithm · depth 2 · source: exploration · routes: N1*

**Statement.** For fixed reservoir weights, set V_(s+j)=w_j. In decreasing station order, set V_i=max over ducts from i of the sum of (p/100)V_o over that duct's outputs. Then V_1=F(w), computable by examining each duct output once.

**Anchors.** stations · duct outputs · percentages · reservoir weights

**Accept.** A unit entering a station earns a linear weighted reservoir reward. Splitting among ducts cannot exceed their best reward, and optimal downstream choices are independent of incoming volume, even when routes merge. Implement a decreasing-index pass with the original, possibly lossy, percentages.

**Review.** all checks passed

## N4 · Partial minimization preserves drainage convexity

*key_property · depth 3 · source: exploration · routes: N2 + N3*

**Statement.** For three reservoirs, G(x)=min_{0<=y<=1-x} F(x,y,1-x-y) is convex on [0,1]. This reduces minimization of the weighted drainage optimum over the simplex to nested one-dimensional convex minimizations; with two reservoirs only F(x,1-x) needs minimization.

**Anchors.** reservoir weights · two reservoirs · three reservoirs · partially minimized objective

**Accept.** F is the maximum of finitely many linear reservoir-outcome rewards, hence convex. Its restriction to a line is convex. Partial minimization over the convex triangle {(x,y):x>=0,y>=0,x+y<=1} preserves convexity in x. Equivalently, combine inner minimizers at two x values to obtain a feasible interpolated y and the convexity inequality.

**Review.** all checks passed

## N5 · Nested convex minimization produces percentage

*algorithm · depth 4 · source: exploration · routes: N4*

**Statement.** For one reservoir evaluate F(1). For two minimize F(x,1-x) on [0,1]. For three minimize G(x), evaluating G by minimizing F(x,y,1-x-y) on [0,1-x]. Use sufficiently accurate convex interval searches and output 100 times the resulting minimum.

**Anchors.** highest possible percentage · reservoirs · convex minimization

**Accept.** Golden-section or ternary searches using N3 suffice. The scalar objectives, including G, are 1-Lipschitz because reservoir shares lie in [0,1] and changing a coordinate redistributes that amount of weight. Budget inner-search error as well as outer interval width. For example, 55 golden-section iterations per level give widths below 4e-12 and sufficient overall accuracy. Three-reservoir runtime is O((s+sum n) log²(1/epsilon)).

**Review.** all checks passed

## N6 · Optimal policy supplies a supporting vector

*key_property · depth 3 · source: exploration · routes: N3*

**Statement.** Fix reservoir weights w and select a maximizing duct at each station in the backward dynamic program. The resulting deterministic policy has an attainable reservoir-flow vector q with w·q=F(w). For every weight vector v, F(v)>=v·q, so q is a subgradient at w.

**Anchors.** reservoir-flow vector · station drainage · maximizing duct · reservoir weights

**Accept.** Recover q either by propagating unit flow forward through the selected ducts or by propagating reservoir-outcome vectors backward while maximizing their weighted scores. Shared downstream stations use the same selected duct. Any maximizing choice at ties gives a valid supporting vector.

**Review.** all checks passed

## N7 · Policy cuts retain the optimal sublevel

*key_property · depth 4 · source: exploration · routes: N2 + N6*

**Statement.** For queries w^t with optimal policy vectors q^t, let b=min_t F(w^t). The region P={v in the weight simplex: q^t·v<=q^t·w^t for every t} contains the entire sublevel set {v:F(v)<=b}, hence every optimal reservoir weighting.

**Anchors.** reservoir weights · optimal policy · weight simplex · retained sublevel set

**Accept.** For each query, use q^t·v<=F(v)<=b<=F(w^t)=q^t·w^t. This establishes the cumulative retained-region invariant. In coordinates omitting the last weight, each cut's normal is (q_1-q_r,...,q_(r-1)-q_r). If this normal vanishes, the queried value is globally optimal.

**Review.** all checks passed

## N8 · Retained volume bounds objective error

*key_property · depth 5 · source: exploration · routes: N7*

**Statement.** Let k=r-1>0 and b be the best queried value. Any measurable region P containing all simplex weights with F(w)<=b satisfies b-min F<=rho^(1/k), where rho is its k-dimensional volume divided by that of the weight simplex.

**Anchors.** reservoir weights · retained region · best queried value · volume error bound

**Accept.** Write delta=b-min F. Since F<=1, convexity implies that scaling the simplex by delta about a minimizer places it inside F<=b. Its relative volume is delta^k. In coordinates omitting the last weight, rho is interval length for two reservoirs and twice the region's area for three reservoirs; the region may be a clipped polygon or an enclosing ellipse.

**Review.** all checks passed

## N9 · Centroid cutting computes the optimum

*algorithm · depth 6 · source: exploration · routes: N8*

**Statement.** For r>1, repeatedly query the centroid of the retained simplex region, update the best value, and clip by the policy halfspace. Stop when the retained-volume bound gives sufficient accuracy, then output 100 times the best value. For r=1, output 100F(1).

**Anchors.** highest possible percentage · centroid · reservoir weights · policy halfspace

**Accept.** Maintain an interval for r=2 or a convex polygon for r=3. A nonzero centroid cut leaves at most half the length or 5/9 of the area, yielding logarithmically many oracle calls. Long-double clipping with translated-coordinate area and centroid calculations is one accepted realization. A constant policy supporting plane certifies the global optimum and permits immediate termination.

**Review.** all checks passed

## N10 · Restricted policy mixtures give lower bounds

*reformulation · depth 4 · source: exploration · routes: N1 + N6*

**Statement.** For collected deterministic-policy reservoir vectors q^k, maximize t subject to λ_k>=0, sum λ_k=1, and sum λ_k q^k_j>=t for every reservoir. Convexly mixing their duct flows realizes these mixtures, so the restricted optimum is a lower bound on the full answer.

**Anchors.** deterministic policies · duct flows · minimum reservoir flow

**Accept.** Use one mixture variable per collected policy and one minimum-flow variable, with r reservoir inequalities and a mixture-mass equality. An equivalent implementation allows sum λ_k<=1 instead: complete any missing mass using an arbitrary collected policy. Since reservoir flows are nonnegative, this completion cannot decrease the minimum flow. Thus the subnormalized formulation has the same optimum.

**Review.** all checks passed

## N11 · Restricted dual provides an optimality certificate

*key_property · depth 5 · source: exploration · routes: N2 + N10*

**Statement.** The restricted policy LP's dual minimizes z subject to w>=0, sum w=1, and z>=q^k·w for every collected policy. At an optimum (w,z), z is a lower bound and F(w) an upper bound. If F(w)>z, an oracle policy supplies a violated constraint.

**Anchors.** reservoir weights · policy mixtures · lower bound · upper bound

**Accept.** Apply LP duality to the restricted mixture problem. Recover reservoir weights from the reservoir-constraint dual multipliers, normalizing their sum when using the at-most-one mass formulation. Evaluate F(w) with N6; any maximizing policy whose score exceeds z cannot already be among the collected constraints.

**Review.** all checks passed

## N12 · Policy generation closes the duality gap

*algorithm · depth 6 · source: exploration · routes: N11*

**Statement.** Start with an oracle policy. Repeatedly solve the restricted mixture LP, query its dual reservoir weights, and add the resulting maximizing policy. Stop when the best upper bound and restricted lower bound differ within the required accuracy, and output 100 times a value between these bounds.

**Anchors.** highest possible percentage · restricted mixture LP · oracle policy · duality gap

**Accept.** Use simplex on the restricted primal LP, which has at most four constraints, and recover its dual weights. Each added policy removes the current infeasible restricted-dual solution; finitely many deterministic policies exist, and a zero oracle gap certifies optimality. Each policy evaluation scans the duct outputs once, while master LP tableaux have only r+2 rows.

**Review.** all checks passed

## N13 · Safe ellipse localization of reservoir weights

*key_property · depth 5 · source: exploration · routes: N7*

**Statement.** For three reservoirs, maintain an ellipse containing all simplex weights with F(w)<=b, where b is the best queried value. A central cut from an optimal policy at a feasible center, or a violated simplex constraint at an infeasible center, preserves this invariant.

**Anchors.** reservoir weights · weight simplex · enclosing ellipse · feasible center · retained sublevel set

**Accept.** Initially enclose the entire weight simplex. At a feasible center, update b and use the policy cut. At an infeasible center, a violated weight nonnegativity or weight-sum constraint separates the center from every simplex weight; weakening it to pass through the center is safe. Any ellipse enclosing the retained intersection preserves the sublevel set. Represent an ellipse by (x-c)^T Q^(-1)(x-c)<=1 with positive-definite Q.

**Review.** all checks passed

## N14 · Ellipsoid separation computes the percentage

*algorithm · depth 6 · source: exploration · routes: N8 + N13*

**Statement.** For two or three reservoirs, enclose the weight simplex in an interval or ellipse. At each center, cut with a violated simplex constraint or an oracle policy subgradient. Apply enclosing-region updates until the volume error bound suffices; output the best percentage. For one reservoir, output 100F(1).

**Anchors.** highest possible percentage · reservoir weights · ellipsoid separation

**Accept.** For r=3, start at c=(1/3,1/3), Q=I. For nonzero cut normal g, let v=Qg/sqrt(g^TQg), then use c'=c-v/3 and Q'=(4/3)(Q-(2/3)vv^T). These updates enclose the retained half-ellipse and multiply area by 4/(3sqrt(3)); 220 cuts suffice. Use adequate precision for eccentric ellipses. Interval bisection handles r=2. Zero normals certify optimality. Evaluate only feasible centers, tracking and outputting 100 times the best F value.

**Review.** all checks passed

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 + N5 \| N1 + N2 + N3 + N6 + N7 + N8 + N9 \| N1 + N2 + N3 + N6 + N10 + N11 + N12 \| N1 + N2 + N3 + N6 + N7 + N8 + N13 + N14

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N5 \| N9 \| N12 \| N14

## Hazards (END → program)

- **H1** Duct output percentages may sum below 100, representing loss; never renormalize them to sum to 100. The requested result is a percentage of factory production, so all input coefficients, internal quantities, and output must use consistent units. *Check:* Verify that each duct contributes exactly its specified fraction of incoming flow and missing mass contributes nothing. Either normalized-flow computations with a final percentage conversion or equivalent percentage-scaled computations are valid. Conversion need not occur at input or output specifically.
- **H2** Percentage error must be at most 1e-6. Constant or zero objectives and boundary optima are valid; geometric searches must handle zero cut normals without division by zero or nonshrinking loops. *Check:* Use sufficient precision and output digits; normalized-flow accuracy must be 1e-8. Include approximate inner-search error in the budget. Do not assume strict convexity or interior optima. Detect zero cut normals and terminate with the certified value rather than normalize them; use numerically justified thresholds for near-zero normals.

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4, N5

Normalize the factory inflow to one and dualize the max-min objective into minimizing a weighted-sum optimum over the reservoir-weight simplex. For fixed weights, a reverse-altitude dynamic program computes that optimum because each station sends all its inflow into a best duct. With at most three reservoirs, the dual is minimized by one or two nested one-dimensional convex searches; 55 golden-section iterations per level give ample accuracy while requiring only a few thousand linear-time DAG evaluations.

New nodes: N1, N2, N3, N4, N5 · judge: AC on 82 tests, slowest 0.898s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N2, N3, N6, N7, N8, N9

Use the same weighted-sum dual, but obtain a supporting reservoir-flow vector from each optimal deterministic drainage policy. Its subgradient cuts away part of the reservoir-weight simplex while retaining every minimizer. Querying the centroid shrinks the retained interval or polygon geometrically, and the region's length or area gives an explicit bound on the remaining objective error, so only about a hundred DAG evaluations are needed.

New nodes: N6, N7, N8, N9 · judge: AC on 82 tests, slowest 0.224s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N2, N3, N6, N10, N11, N12

Maintain a restricted collection of deterministic drainage policies and solve the max-min mixture problem for just those policies. Its tiny linear program supplies reservoir dual weights; the DAG oracle either produces a missing policy or proves that the current lower and upper bounds agree. Each master LP has at most four constraints, and policy generation requires only a linear DAG pass, avoiding geometric search over the entire simplex.

New nodes: N10, N11, N12 · judge: AC on 82 tests, slowest 0.07s · program: `paths/P3.cpp` · None submission(s)
### P4 · N1, N2, N3, N6, N7, N8, N13, N14

Apply the ellipsoid method to the low-dimensional reservoir-weight dual, using optimal policy vectors as separating subgradients. An infeasible center is separated by a simplex constraint, while a feasible center supplies an upper bound and a policy cut. The enclosing ellipse loses a constant fraction of its area at every step, and the retained-volume certificate bounds the final objective error; high-precision geometry prevents extremely thin ellipses from becoming numerically singular.

New nodes: N13, N14 · judge: AC on 82 tests, slowest 0.518s · program: `paths/P4.cpp` · None submission(s)

## Exploration

Finished: True · 5 submissions · reason: Four genuinely different approaches were implemented and accepted: nested convex interval minimization, centroid halfspace localization, restricted-policy LP generation, and ellipsoid separation. I do not have another distinct approach with a sufficiently reliable implementation and running-time argument for these limits.

Ideas the explorer considered and dropped:

- Explicitly propagate convex hulls of attainable reservoir vectors through the DAG. Ducts require Minkowski sums and stations require convex hulls; the number of intermediate vertices can grow too large, even with three reservoirs.
- Solve the complete duct-flow LP directly with a dense simplex tableau. Up to 20,000 duct variables and 10,000 station conservation equations make its memory and pivot costs unsuitable; a robust sparse LP implementation would require substantially different machinery.
- Replace the routing network with ordinary or generalized maximum flow. A duct simultaneously distributes to several outputs in fixed proportions, which ordinary independently adjustable flow edges do not enforce.
- Use projected subgradient descent or a discretized weight grid. Their generic accuracy dependence is too costly for the required 1e-8 normalized error, compared with the accepted localization methods.
- Use derivative-guided nested searches, alternative polygon query points, or binary-search feasibility cuts. These largely reuse the convex-search and supporting-halfspace claims already represented, rather than establishing a sufficiently different reasoning path.

## Review

END ok: True — Each route includes the flow model, minimax equality, weighted DAG oracle, and its final optimization procedure. The geometric routes include both sublevel preservation and a volume-to-objective certificate; the policy-generation route includes the restricted LP, dual-weight oracle queries, and an upper/lower-bound stopping certificate. No essential claim of the stated accepted approaches is missing.

Hazards ok: True — H1 correctly covers lossy duct coefficients and percentage units. H2 covers the required absolute-error budget, approximate inner evaluations, boundary and constant objectives, and safe handling of zero normals when geometric cuts are used. No additional essential overflow or output convention is missing.

**Builder's notes.** N10 now states the restricted convex-mixture optimization with mixture mass exactly one and its lower-bound property. The optional at-most-one formulation and completion argument appear only in its acceptance examples. All other texts, ids, and routes are preserved.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `093aebe7dbd7034f` | 2 | 3 | revise |
| 2 | `407741780f857a30` | 1 | 1 | revise |
| 3 | `480d0f98b0c98a0a` | 0 | 0 | accept |
