# Reasoning graph · Riddle of the Sphinx (2023/A-riddle-of-the-sphinx)

status **accepted** · version `2f15ef871a401492` · 17 nodes · 5 END route(s) · 3 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 2 review round(s)

**Route.** P1: Ask five predetermined questions whose coefficients are (1,t,t(t-1)/2) for t=0,1,2,3,4. P2: Use three singleton questions followed by an unweighted and a weighted checksum. P3: Interpret the same five legal questions as samples of a quadratic polynomial and decode them using a linear error-locator polynomial. P4: Use four quadratic-evaluation questions to reduce the possibilities to at most four nonnegative integer leg triples. P5: The singleton-and-checksum questions also admit an exact weighted least-absolute-deviations decoder.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Four truthful linear equations | statement |
| N2 | 1 | construction | Legal questions with independent triples | statement |
| N3 | 2 | key_property | Four agreements uniquely identify legs | N1 + N2 |
| N4 | 3 | algorithm | Decode by four-agreement candidate validation | N1 + N2 + N3 |
| N5 | 2 | reformulation | Parity checks isolate the single response error | N1 |
| N6 | 3 | key_property | Distinct syndrome directions locate one lie | N5 |
| N7 | 4 | algorithm | Correct singleton answers using two checksums | N5 + N6 |
| N8 | 2 | reformulation | Leg counts as corrupted quadratic evaluations | N1 + N2 |
| N9 | 3 | key_property | Locator equations characterize the true quadratic | N8 |
| N10 | 4 | algorithm | Decode through a cubic linear system | N2 + N8 + N9 |
| N11 | 2 | reformulation | Four replies leave at most four candidates | N1 + N2 |
| N12 | 3 | key_property | Multiple candidates exhaust the lie budget | N11 |
| N13 | 3 | construction | A legal question separates four candidates | N11 |
| N14 | 4 | algorithm | Adapt the final question to surviving candidates | N11 + N12 + N13 |
| N15 | 3 | key_property | Positive weights strictly expose syndrome columns | N5 |
| N16 | 4 | key_property | Weighted absolute residual uniquely recovers legs | N5 + N15 |
| N17 | 5 | algorithm | Decode by weighted robust regression | N5 + N16 |
| END | | | complete solution | N1 + N2 + N3 + N4 \| N1 + N5 + N6 + N7 \| N1 + N2 + N8 + N9 + N10 \| N1 + N2 + N11 + N12 + N13 + N14 \| N1 + N5 + N15 + N16 + N17 |

## N1 · Four truthful linear equations

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** For the hidden leg triple L, a truthful reply to question (a,b,c) equals (a,b,c)·L. Among the five received replies, at least four are truthful, so L is a nonnegative integer solution of at least four corresponding equations.

**Anchors.** questions · answers · number of legs

**Accept.** Models each response as a linear equation in the three unknown leg counts and allows at most one equation to fail, including the possibility that none fail.

**Review.** all checks passed

## N2 · Legal questions with independent triples

*construction · depth 1 · source: exploration · routes: statement*

**Statement.** There exist five legal question rows with every three linearly independent. Such a design makes any three truthful replies sufficient to determine the leg triple.

**Anchors.** five questions · legal coefficients · linearly independent question rows

**Accept.** Establishes independence of every three chosen legal rows. Examples are the singleton rows followed by (1,1,1),(1,2,3), or rows (1,t,t(t−1)/2) for t=0,…,4. For the former, nonzero checksum coefficients and distinct coefficient ratios establish independence; for the latter, Vandermonde determinants do. Other legal designs satisfying the same invariant count.

**Review.** all checks passed

## N3 · Four agreements uniquely identify legs

*key_property · depth 2 · source: exploration · routes: N1 + N2*

**Statement.** If every three of five question rows are linearly independent, at most one leg triple agrees with at least four replies. Two such triples would share at least three matching equations, whose independence forces the triples to be equal.

**Anchors.** five answers · leg triple · linearly independent questions

**Accept.** Uses intersection size at least 4+4−5=3 and invertibility of the shared equations. Equivalently proves that distinct truthful response vectors differ in at least three coordinates, permitting correction of one corrupted coordinate.

**Review.** all checks passed

## N4 · Decode by four-agreement candidate validation

*algorithm · depth 3 · source: exploration · routes: N1 + N2 + N3*

**Statement.** Using five legal rows with every three independent, generate candidate leg triples from reply subsets guaranteed to include an all-truthful determining subset. Output a nonnegative integer candidate agreeing with at least four replies. Such a candidate exists and is unique.

**Anchors.** five questions · candidate leg triples · four matching replies · output leg counts

**Accept.** Examples include solving all ten triples, or omitting each possible erroneous reply, solving three remaining equations, and verifying all four. Establishes that the true triple is generated and validates integrality, nonnegativity, and four agreements. Exact solving or numerically justified solving followed by rounding and reliable validation counts. Only constantly many fixed-size systems are needed.

**Review.** all checks passed

## N5 · Parity checks isolate the single response error

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** For three singleton questions and two legal checksum questions, let Q be their coefficient matrix and r their reply vector. Any parity-check matrix H satisfying HQ=0 cancels truthful responses. With one additive error δ in reply i, the syndrome Hr equals δh_i, where h_i is column i.

**Anchors.** singleton questions · checksum questions · parity-check matrix · syndrome

**Accept.** For checks (1,1,1),(1,2,3) and replies (A,B,C,S,W), use Hr=(S−A−B−C,W−A−2B−3C). Its columns are (−1,−1),(−1,−2),(−1,−3),(1,0),(0,1). Substitution or matrix multiplication proves the error formula. Other legal checksum coefficients and parity-check coordinate conventions satisfying HQ=0 count.

**Review.** all checks passed

## N6 · Distinct syndrome directions locate one lie

*key_property · depth 3 · source: exploration · routes: N5*

**Statement.** When the five syndrome columns are nonzero and pairwise nonparallel, a nonzero syndrome uniquely identifies the erroneous reply and its additive error. A zero syndrome then means every reply is truthful.

**Anchors.** syndrome columns · erroneous reply · error magnitude

**Accept.** Establishes nonzero, pairwise-distinct column directions for the chosen checks. For checks (1,1,1),(1,2,3), the directions have slopes 1,2,3,0 and vertical. Uses the at-most-one-error promise; a purported lie equal to the truthful value counts as no error.

**Review.** all checks passed

## N7 · Correct singleton answers using two checksums

*algorithm · depth 4 · source: exploration · routes: N5 + N6*

**Statement.** Ask three singleton questions and two checksums whose parity-check columns are nonzero and pairwise nonparallel. Compute the syndrome; if nonzero, identify the erroneous response and its error magnitude. Correct a singleton response when necessary, then output the three singleton values.

**Anchors.** output leg counts · checksum syndrome · singleton replies

**Accept.** Locates and measures an error through the syndrome, correcting a singleton only when that response is erroneous. For replies (A,B,C,S,W) to the displayed checks, set u=S−A−B−C and v=W−A−2B−3C. If u≠0 and v=i·u for i=1,2,3, add u to singleton i; otherwise leave the singleton replies unchanged. Other syndrome conventions and legal distinguishing checksum weights count.

**Review.** all checks passed

## N8 · Leg counts as corrupted quadratic evaluations

*reformulation · depth 2 · source: exploration · routes: N1 + N2*

**Statement.** Five legal questions can make truthful replies equal P(t) at five distinct t, where P has degree at most two and uniquely determines the leg triple. The received values differ from these polynomial evaluations in at most one position.

**Anchors.** quadratic evaluation questions · truthful polynomial · leg counts · corrupted evaluation

**Accept.** For q(t)=(1,t,t(t−1)/2), t=0,…,4, the truthful polynomial is P(t)=ℓa+ℓb·t+ℓc·t(t−1)/2. All coefficients are legal, and the polynomial basis gives a bijection between leg triples and quadratic coefficients. Other legal evaluation designs with an invertible coefficient-to-leg mapping count.

**Review.** all checks passed

## N9 · Locator equations characterize the true quadratic

*key_property · depth 3 · source: exploration · routes: N8*

**Statement.** For five distinct evaluations of the true quadratic P, with at most one corrupted reply r_t, the locator equations N(t)=r_tE(t), with monic linear E and deg N≤3, hold exactly when N=EP and E vanishes at the corrupted point, if any. Such solutions exist.

**Anchors.** locator equations · truthful evaluation points · error locator · polynomial division

**Accept.** Choose E vanishing at the erroneous evaluation point and N=EP; without an error, any monic linear E works. Conversely, N−EP has degree at most three and vanishes at four truthful points, hence is zero. At a genuinely corrupted point, the locator equation then forces E to vanish. This also proves division by E recovers P despite nonunique no-error locators.

**Review.** failed: atomic — A solver can construct a locator vanishing at the corrupted point and derive a consistent system using N=EP, yet still be stuck proving that every solution of that system recovers P. Separate locator formulation/existence from the converse recovery claim proved by the four truthful roots.

## N10 · Decode through a cubic linear system

*algorithm · depth 4 · source: exploration · routes: N2 + N8 + N9*

**Statement.** Ask five legal questions encoding quadratic evaluations. Solve N(t)=r_t(t+e) for the cubic coefficients and e, allowing free variables. Divide by t+e to obtain the true quadratic and recover the integer leg triple using the chosen polynomial representation.

**Anchors.** five replies · linear system · quadratic quotient · output leg counts

**Accept.** Reliably solves the five-variable locator system, permits free variables, and recovers the quotient's integer leg counts. Fixed-size rational elimination is one sufficient implementation; numerically justified solving and integer recovery also count. For the binomial-basis design, a quotient P=p0+p1·t+p2·t² yields legs (p0,p1+p2,2p2).

**Review.** all checks passed

## N11 · Four replies leave at most four candidates

*reformulation · depth 2 · source: exploration · routes: N1 + N2*

**Statement.** After four legal questions whose every three rows are independent, the leg triples compatible with at most one erroneous reply are exactly the nonnegative integer solutions of their three-reply subsystems. There are between one and four distinct candidates.

**Anchors.** first four questions · three-reply subsystems · candidate leg triples

**Accept.** At least three of the four replies are truthful. Each of the four three-question subsets determines one rational triple; retains precisely the nonnegative integral triples and deduplicates. The first four binomial-basis evaluation questions are one valid design, but any four legal rows satisfying the independence invariant count.

**Review.** all checks passed

## N12 · Multiple candidates exhaust the lie budget

*key_property · depth 3 · source: exploration · routes: N11*

**Statement.** If the first four replies produce multiple distinct candidates, at least one of those replies was false. Otherwise every three-reply subsystem would recover the same true triple. Therefore, with multiple candidates, the fifth reply is guaranteed truthful.

**Anchors.** candidate leg triples · first four replies · fifth reply

**Accept.** Uses independence of every three initial question rows and the at-most-one-lie promise. Does not assume the fifth answer truthful when only one candidate remains; that answer can instead be ignored.

**Review.** all checks passed

## N13 · A legal question separates four candidates

*construction · depth 3 · source: exploration · routes: N11*

**Statement.** For at most four distinct candidate leg triples, some legal question gives different totals for every candidate. Each candidate pair forbids at most 11² questions in {0,…,10}³, and at most six pairs cannot forbid all 11³ questions.

**Anchors.** legal question · candidate pairs · different totals

**Accept.** For a nonzero difference between two candidates, select a coordinate where it is nonzero. Fixing the other two question coefficients permits at most one value of the selected coefficient to make the totals equal. Union-bounds the six equality planes. Checking the 1331 legal questions is one sufficient construction; any proven separating choice counts.

**Review.** all checks passed

## N14 · Adapt the final question to surviving candidates

*algorithm · depth 4 · source: exploration · routes: N11 + N12 + N13*

**Statement.** Ask four legal questions with every three rows independent and generate their candidate set. For a singleton, ask any legal fifth question and output that candidate. Otherwise ask a separating fifth question and output the candidate matching its guaranteed-truthful reply. Complete exactly five rounds.

**Anchors.** adaptive fifth question · candidate set · five rounds · output leg counts

**Accept.** Uses the four-question candidate characterization, including filtering and deduplication. The first four binomial-basis evaluation rows are one example, not a requirement. For multiple candidates, constructs a legal question giving pairwise-distinct totals and selects by its reply. For one candidate, still asks and reads the fifth round but ignores that response.

**Review.** all checks passed

## N15 · Positive weights strictly expose syndrome columns

*key_property · depth 3 · source: exploration · routes: N5*

**Statement.** For nonzero, pairwise-nonparallel syndrome columns h_i, positive weights w_i can be chosen so that each h_i admits a vector z_i satisfying z_i·h_i=w_i and |z_i·h_j|<w_j for every j≠i.

**Anchors.** syndrome columns · positive weights · strict supporting functionals

**Accept.** Generally, w_i=||h_i||₂ and z_i=h_i/||h_i||₂ work by strict Cauchy–Schwarz. For the displayed singleton/checksum columns, weights (14,22,31,10,10) work with certificates (−7,−7),(−5,−17/2),(−5/2,−19/2),(10,0),(0,10). Any verified positive weights satisfying the strict supporting-functional property count.

**Review.** all checks passed

## N16 · Weighted absolute residual uniquely recovers legs

*key_property · depth 4 · source: exploration · routes: N5 + N15*

**Statement.** For singleton-and-checksum rows q_i, if positive weights w_i give every syndrome column a strict supporting functional, the true leg triple uniquely minimizes ∑w_i|r_i−q_i·L| over L∈ℝ³ despite at most one erroneous reply.

**Anchors.** weighted absolute residual · strict-support condition · true leg triple · single error

**Accept.** Write residual e=r−QL, whose syndrome equals the true error syndrome δh_k. Applying sign(δ)z_k lower-bounds the objective by w_k|δ|. Strict inequalities force every other residual coordinate to zero at equality, hence recover the true triple. With no error, the minimum is zero and the singleton rows give uniqueness. The particular numerical weights are immaterial once the strict-support condition holds.

**Review.** all checks passed

## N17 · Decode by weighted robust regression

*algorithm · depth 5 · source: exploration · routes: N5 + N16*

**Statement.** Ask singleton-and-checksum questions with weights satisfying the strict-support condition and output the triple minimizing the weighted absolute residual. It suffices to compare solutions of invertible three-reply subsystems: the truthful rows contain an independent triple and hence generate the unique minimizer.

**Anchors.** three-reply subsystems · weighted residual objective · reliable minimization · output leg counts

**Accept.** One implementation enumerates at most ten rational candidates and compares their weighted costs. Strict support excludes a nonzero response difference supported on one coordinate, so the four truthful rows span three dimensions. Accepts any weights satisfying the condition and any sufficiently reliable optimization, objective comparison, and integer recovery; exact rational enumeration with the displayed integer weights is one sufficient implementation.

**Review.** all checks passed

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 \| N1 + N5 + N6 + N7 \| N1 + N2 + N8 + N9 + N10 \| N1 + N2 + N11 + N12 + N13 + N14 \| N1 + N5 + N15 + N16 + N17

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N4 \| N7 \| N10 \| N14 \| N17

## Hazards (END → program)

- **H1** The interaction requires exactly five question lines, each flushed before reading its reply, followed by one flushed answer line. Standard output must contain no explanations or protocol markers. *Check:* Each question prints three legal integers and flushes, then reads one reply. The final triple is printed only after all five replies; no extra output is produced.
- **H2** Leg counts must be recovered as nonnegative integers. Arithmetic, objective comparisons, and response validation must avoid overflow and numerical errors that could change the selected answer. *Check:* Exact arithmetic or justified floating-point solving, rounding, and reliable validation can suffice. Signed 64-bit arithmetic covers Cramer determinants, numerators, and dot products for the displayed small-row designs and replies at most 100000. Separately justify intermediate bounds and numerical reliability for other calculations, including rational elimination.
- **H3** A lie is optional. An error-locator linear system can consequently have free variables; singularity must not be treated as an invalid interaction. *Check:* The solver permits nonpivot columns and selects arbitrary values for free variables, or separately handles the all-truthful case. The decoder must not require a unique locator polynomial.

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4

Ask five predetermined questions whose coefficients are (1,t,t(t-1)/2) for t=0,1,2,3,4. Any three questions are linearly independent, so two different leg triples cannot both agree with at least four replies. Solve each of the ten three-question subsystems exactly and output a nonnegative integer solution agreeing with at least four replies; this uses constant time and tolerates either one lie or no lies.

New nodes: N1, N2, N3, N4 · judge: AC on 50 tests, slowest 0.014s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N5, N6, N7

Use three singleton questions followed by an unweighted and a weighted checksum. The two checksum discrepancies form a syndrome: each possible corrupted reply produces a different direction, so they identify whether a singleton answer needs correction and by how much. The five questions and the decoder both use constant time and small exact integers.

New nodes: N5, N6, N7 · judge: AC on 50 tests, slowest 0.007s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N2, N8, N9, N10

Interpret the same five legal questions as samples of a quadratic polynomial and decode them using a linear error-locator polynomial. A monic linear polynomial can annihilate the one erroneous sample, making the product with the true quadratic a cubic satisfying five linear equations. Any solution of those equations recovers the true quadratic, since its difference from that product has four roots; exact elimination of this fixed-size system is easily fast enough.

New nodes: N8, N9, N10 · judge: AC on 50 tests, slowest 0.008s · program: `paths/P3.cpp` · None submission(s)
### P4 · N1, N2, N11, N12, N13, N14

Use four quadratic-evaluation questions to reduce the possibilities to at most four nonnegative integer leg triples. If several candidates survive, a lie has already occurred, so the final reply must be truthful; choose the fifth question adaptively to distinguish all candidates. Such a legal question always exists because the at most six forbidden equality planes cannot cover the 11-by-11-by-11 coefficient grid, which can be searched directly.

New nodes: N11, N12, N13, N14 · judge: AC on 50 tests, slowest 0.007s · program: `paths/P4.cpp` · None submission(s)
### P5 · N1, N5, N15, N16, N17

The singleton-and-checksum questions also admit an exact weighted least-absolute-deviations decoder. With specially chosen integer weights, each possible single-error syndrome has a strict supporting functional, proving that the true leg triple uniquely minimizes the weighted absolute residual over all real triples. Enumerating the ten three-equation intersections includes the true triple, so comparing their rational objective values exactly gives a constant-time robust-regression solution.

New nodes: N15, N16, N17 · judge: AC on 50 tests, slowest 0.008s · program: `paths/P5.cpp` · None submission(s)

## Exploration

Finished: True · 5 submissions · reason: Five genuinely different approaches were implemented and accepted: full-spark subsystem decoding, direct checksum-syndrome correction, polynomial error-locator decoding, an adaptive separating fifth question, and exact weighted absolute-residual minimization. I have no further distinct approach that I believe both correct and sufficiently efficient.

Ideas the explorer considered and dropped:

- Repeating each singleton question three times gives independent majority protection but requires nine questions, exceeding the five-round limit.
- Other full-spark matrices, alternative exact linear solvers, and finite-difference syndrome formulas only change constructions or implementations of the existing decoding principles.
- Ordinary least squares is not robust to an arbitrary false reply. Unweighted absolute-residual minimization also lacks the strict recovery guarantee; the accepted weighted decoder supplies the necessary geometry.
- Exhaustive enumeration of all three leg counts is unnecessarily large and offers no competitive alternative to the constant-sized candidate constructions.
- Packing all three unknown counts into one small-base response cannot be justified: coefficients are at most 10, and the statement does not bound each leg count below that base.

## Review

END ok: True — Each END route contains a complete decoder and enough information for a fast implementation. In particular, the adaptive route supplies both a bounded candidate set and a constructible separating question, and the weighted-regression route supplies verified weights and finite candidate enumeration.

Hazards ok: True — The hazards cover legal questions, exactly five request/reply rounds, flushing and output format, nonnegative integer recovery, arithmetic reliability, and the optional-lie case, including its effect on locator-system rank. The stated 64-bit guarantee is appropriately limited to the displayed determinant and dot-product calculations.

**Advisories.**

- N9 (bundles claims a solver can have separately; split it): A solver can construct a locator vanishing at the corrupted point and derive a consistent system using N=EP, yet still be stuck proving that every solution of that system recovers P. Separate locator formulation/existence from the converse recovery claim proved by the four truthful roots.
- order: Split N9 into locator-equation formulation/existence and universal recovery by the four-root argument. Place the recovery node after the formulation node, and make N10 depend on both; this distinguishes discovering the linearization from proving that arbitrary solutions, including no-error free-variable solutions, decode correctly.

**Builder's notes.** Kept every node, hazard, id, and route. To separate polynomial representation from the shared query-design invariant without adding nodes, N2 now states only the legal independent-triples design, N8 states the quadratic-evaluation reformulation, and N9 gives the locator characterization including existence and recovery. N4 now recognizes both all-triples enumeration and omit-one reconstruction, including the singleton-and-checksum design. Fixed matrices, syndrome coordinates, weights, certificates, and exact arithmetic are acceptance examples rather than universal requirements.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `7f3592be060b3561` | 11 | 2 | revise |
| 2 | `2f15ef871a401492` | 0 | 2 | revise |
