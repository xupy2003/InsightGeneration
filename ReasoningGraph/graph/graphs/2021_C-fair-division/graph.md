# Reasoning graph · Fair Division (2021/C-fair-division)

status **accepted** · version `eca5789a26b6a2ca` · 13 nodes · 4 END route(s) · 4 hazard(s) · gpt-6-astra (build ?, review high) · ? submission(s), 3 review round(s)

**Route.** P1: Write the remaining fraction as a/b in lowest terms. P2: Instead of testing every reduced ratio, enumerate the divisors of m as the possible primitive weight sums. P3: When k divides n, the k-term primitive geometric sum divides the full n-term sum, so feasibility forces this smaller polynomial to divide m. P4: Use the primitive-prime-divisor theorem for b^n-a^n: except for n=6 and (a,b)=(1,2), a feasible ratio yields an order-n element a/b modulo some prime factor of m.

| node | depth | kind | name | routes |
|---|---:|---|---|---|
| N1 | 1 | modeling | Infinite shares form a geometric progression | statement |
| N2 | 2 | reformulation | Primitive weight sum must divide loot | N1 |
| N3 | 3 | key_property | Feasible reduced denominators are small | N2 |
| N4 | 4 | algorithm | Enumerate bounded primitive weight sums | N2 + N3 |
| N5 | 3 | key_property | Weight sum is coordinatewise increasing | N2 |
| N6 | 4 | algorithm | Staircase finds a prescribed weight sum | N3 + N5 |
| N7 | 5 | algorithm | Search divisor level sets for optimum | N2 + N3 + N6 |
| N8 | 3 | key_property | Shorter geometric blocks divide full sum | N2 |
| N9 | 4 | algorithm | Search short-block divisor level sets | N3 + N5 + N8 |
| N10 | 5 | algorithm | Combine prime and composite pirate searches | N2 + N3 + N9 |
| N11 | 3 | key_property | Feasibility produces a primitive prime witness | N2 |
| N12 | 4 | algorithm | Generate all possible witness residues | N11 |
| N13 | 5 | algorithm | Enumerate primitive-witness congruence candidates | N2 + N3 + N11 + N12 |
| END | | | complete solution | N1 + N2 + N3 + N4 \| N1 + N2 + N3 + N5 + N6 + N7 \| N1 + N2 + N3 + N5 + N8 + N9 + N10 \| N1 + N2 + N3 + N11 + N12 + N13 |

## N1 · Infinite shares form a geometric progression

*modeling · depth 1 · source: exploration · routes: statement*

**Statement.** Let r=1-f. Pirate i, numbered from zero, receives x_i=m(1-r)r^i/(1-r^n) after infinitely many rounds. Thus the final shares have common ratio r and sum to m.

**Anchors.** fraction f · pirates · total loot

**Accept.** Sum the geometric series of payments m(1-r)r^(i+kn), for k>=0. Equivalent reasoning using the ratio between adjacent pirates and conservation of the total loot also establishes the formula.

**Review.** all checks passed

## N2 · Primitive weight sum must divide loot

*reformulation · depth 2 · source: exploration · routes: N1*

**Statement.** Write r=a/b with 1<=a<b and gcd(a,b)=1. Define D=sum from i=0 to n-1 of b^(n-1-i)a^i. Every final share is an integer exactly when D divides m; the corresponding fraction is f=(b-a)/b.

**Anchors.** fraction f · integer total loot · a · b · D

**Accept.** The shares are m times the integer weights b^(n-1-i)a^i divided by D. The endpoint weights are coprime, so integrality of all shares forces D|m by Bezout; divisibility also plainly suffices. The equivalent expression D=(b^n-a^n)/(b-a) is valid.

**Review.** all checks passed

## N3 · Feasible reduced denominators are small

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** For a feasible pair, b^(n-1)<D<=m and D>=2^n-1. Under the input limits this implies n<=59 and b<=3981.

**Anchors.** number of pirates n · total loot m · denominator b · D

**Accept.** Each term of D is positive, and a>=1,b>=2 minimizes D at a=1,b=2. Compare 2^60-1 and 3982^5 with 10^18, using n>=6. Tighter bounds from m or the minimum D for a particular b also count.

**Review.** failed: atomic — The bound on n and the bound on b are independently discoverable: a solver can establish either without establishing the other. Split the minimum-sum argument yielding n<=59 from the leading-term argument bounding denominators.

## N4 · Enumerate bounded primitive weight sums

*algorithm · depth 4 · source: exploration · routes: N2 + N3*

**Statement.** If n>=60, output impossible. Otherwise enumerate coprime 1<=a<b with b^(n-1)<m, test D|m, and output (b-a,b) minimizing (b,b-a). If no tested pair succeeds, output impossible.

**Anchors.** smallest q · smallest p · impossible · D

**Accept.** Enumerating denominators increasingly and a decreasingly makes the first valid pair optimal. Compute D by its sum, geometric quotient, or Horner recurrence, rejecting values exceeding m. At most about eight million pairs occur, and O(n) arithmetic plus a gcd per pair fits the limits.

**Review.** all checks passed

## N5 · Weight sum is coordinatewise increasing

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** For every integer h>=2, the geometric weight sum D_h(a,b)=sum from i=0 to h-1 of b^(h-1-i)a^i is strictly increasing in either positive integer argument.

**Anchors.** geometric weight sum D_h · a · b

**Accept.** Increasing either argument never decreases a term and strictly increases an endpoint term. This applies to the full n-term sum and to shorter block sums, even when a and b are not coprime.

**Review.** all checks passed

## N6 · Staircase finds a prescribed weight sum

*algorithm · depth 4 · source: exploration · routes: N3 + N5*

**Statement.** For each positive target d, all positive integer pairs a<b satisfying D(a,b)=d can be enumerated by monotone row/column elimination within a bounded search region containing every solution.

**Anchors.** D · target d · a · b

**Accept.** One realization starts a=1,b=floor(d^(1/(n-1))). When D<d discard the current a by increasing it; when D>d discard the current b by decreasing it. After equality, strict monotonicity permits discarding both. Stop at a>=b. Equivalent staircase initializations and updates count if they preserve complete coverage. This realization uses O(d^(1/(n-1))) evaluations.

**Review.** all checks passed

## N7 · Search divisor level sets for optimum

*algorithm · depth 5 · source: exploration · routes: N2 + N3 + N6*

**Statement.** Reject n>=60. Factor m and enumerate its positive divisors d. For each d, find all D(a,b)=d pairs by staircase search and retain coprime pairs. Output (b-a,b) minimizing (b,b-a), or impossible if none exists.

**Anchors.** divisors of m · smallest q · smallest p · impossible

**Accept.** Generate divisors from the prime factorization, using a suitable 64-bit factorization method. Exact staircase searches cost O(n times the sum over d|m of d^(1/(n-1))) arithmetic operations. Divisors below 2^n-1 may be omitted; once a denominator is known, larger denominators and unreachable larger divisors may be omitted.

**Review.** all checks passed

## N8 · Shorter geometric blocks divide full sum

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** For every divisor k>=2 of n, D_k(a,b)=(b^k-a^k)/(b-a) divides D_n(a,b). Consequently every feasible reduced pair satisfies D_k(a,b)|m.

**Anchors.** number of pirates n · D_k · D_n · total loot m

**Accept.** Factor b^n-a^n as (b^k-a^k) times the geometric sum in b^k and a^k. Equivalently, group the n primitive weights into blocks of length k. The quotient is an integer for all positive a<b.

**Review.** all checks passed

## N9 · Search short-block divisor level sets

*algorithm · depth 4 · source: exploration · routes: N3 + N5 + N8*

**Statement.** For composite n, choose a proper divisor k>=2 and an upper bound B for feasible denominators. Enumerating divisors d|m up to D_k(B-1,B), then their level sets D_k(a,b)=d with 1<=a<b<=B, includes every feasible pair.

**Anchors.** shorter sum D_k · divisors of m · candidate ratios · denominator bound B

**Accept.** Use a small enough k and denominator bound for efficient enumeration; reject B<2. One realization takes the smallest prime factor k and B=floor(m^(1/(n-1))). For composite n<=59, its target bound is at most 93457, allowing direct divisibility checks instead of factoring m. Monotone staircase searches enumerate each level set in O(B) evaluations. Other choices count when they preserve coverage and fit the limits.

**Review.** all checks passed

## N10 · Combine prime and composite pirate searches

*algorithm · depth 5 · source: exploration · routes: N2 + N3 + N9*

**Statement.** Reject n>=60. For prime n enumerate bounded coprime pairs; for composite n use the short-block divisor searches. Among candidates with gcd(a,b)=1 and D_n(a,b)|m, output (b-a,b) minimizing (b,b-a), or impossible if none exists.

**Anchors.** smallest q · smallest p · prime n · composite n · impossible

**Accept.** A direct full-sum test removes candidates satisfying only the necessary short-block condition. Compare denominators first, then numerators. With B=floor(m^(1/(n-1))), prime n>=7 implies B<=1000. The smallest-prime-factor short-block realization uses at most 93457 target checks and O(B) staircase steps per dividing target, comfortably within the limits.

**Review.** all checks passed

## N11 · Feasibility produces a primitive prime witness

*key_property · depth 3 · source: exploration · routes: N2*

**Statement.** For coprime 1<=a<b and n>=6, except (n,a,b)=(6,1,2), some prime ℓ dividing D_n makes a/b have multiplicative order n modulo ℓ. Thus every such feasible pair has a witness ℓ|m with n|(ℓ-1).

**Anchors.** primitive sum D_n · prime divisors of m · ratio a/b

**Accept.** Apply the Bang–Zsigmondy primitive-prime-divisor theorem to b^n-a^n. A primitive prime divides neither ab nor b-a, divides D_n, and gives b/a, hence a/b, exact order n. For n>=6 the theorem's only exception is b=2,a=1,n=6.

**Review.** all checks passed

## N12 · Generate all possible witness residues

*algorithm · depth 4 · source: exploration · routes: N11*

**Statement.** For a prime ℓ with n|(ℓ-1), all order-n witness ratios are exactly w^j modulo ℓ, where w is any residue of order n and 1<=j<=n satisfies gcd(j,n)=1.

**Anchors.** prime witness ℓ · order-n residues · ratio a/b

**Accept.** Find any order-n element, for example by projecting random nonzero g to w=g^((ℓ-1)/n), verifying w^(n/t)!=1 for each prime t|n. Cyclicity ensures such an element exists and its coprime powers give all and only order-n residues. Uniform random projection succeeds with probability φ(n)/n; other complete subgroup-generation methods also count.

**Review.** all checks passed

## N13 · Enumerate primitive-witness congruence candidates

*algorithm · depth 5 · source: exploration · routes: N2 + N3 + N11 + N12*

**Statement.** Form candidates from bounded pairs satisfying a≡rb modulo some prime ℓ|m and some order-n residue r, together with (a,b)=(1,2) when n=6. Retain coprime pairs with D_n|m; output (b-a,b) minimizing (b,b-a), or impossible.

**Anchors.** smallest q · smallest p · prime witnesses · exceptional pair · impossible

**Accept.** Reject n>=60 before enumeration. Factor m and enumerate order-n residues for eligible primes. For each bounded b not divisible by ℓ, enumerate 1<=a<b in the residue class rb. Include the exceptional pair independently; testing denominator two upfront for all n is also valid. The denominator bound keeps this manageable, and the full divisibility test remains necessary.

**Review.** all checks passed

## END

**Statement.** A solver holding every node of one END route can write a correct, fast enough program by routine coding; each route is an approach whose program the judge accepted.

**Routes (solution families).** N1 + N2 + N3 + N4 \| N1 + N2 + N3 + N5 + N6 + N7 \| N1 + N2 + N3 + N5 + N8 + N9 + N10 \| N1 + N2 + N3 + N11 + N12 + N13

**Key nodes (holding them is reaching END; the other route members are steps on the way).** N4 \| N7 \| N10 \| N13

## Hazards (END → program)

- **H1** Polynomial values and intermediate products can exceed 64-bit ranges even though m<=10^18; overflow must not create false divisibility or bounds. *Check:* Use guarded/capped multiplication or sufficiently wide arithmetic with proven bounds. For candidates satisfying b^(n-1)<=m, a<b and n<=59, the sum and one extra multiplication fit __int128. Denominator-bound computations also need safe evaluation; b<=3981 and n<=59 alone do not establish safety.
- **H2** The chosen fraction must satisfy the denominator-first, numerator-second minimum; equivalent unreduced representations cannot improve the answer. *Check:* Enumerate reduced pairs or reduce fractions before comparison. For fixed denominator b, the smallest numerator b-a corresponds to the largest feasible a. Print impossible only when no feasible pair exists.
- **H3** If factorization is used, primality decisions, prime factors, and divisors must be correct for m<=10^18; modular products must not overflow. *Check:* Use exact or overflow-safe modular arithmetic. Deterministic 64-bit Miller–Rabin bases and Pollard rho with retries on trivial factors are valid examples; other correct factorization methods also count.
- **H4** Search bounds and their rounding must preserve every candidate that could still improve the answer within the region or target being searched. *Check:* An unconditional global feasibility bound must cover every feasible denominator. Target-specific bounds need cover only that target; after finding denominator b0, larger denominators can be discarded. Use exact, conservative, or verified rounded bounds. Equality b^(n-1)=m may be excluded because D>b^(n-1).

## Paths (approaches the explorer worked out and the judge accepted)

### P1 · N1, N2, N3, N4

Write the remaining fraction as a/b in lowest terms. The pirates' final shares are proportional to the coprime integer weights b^(n-1), ab^(n-2), ..., a^(n-1), so their sum D must divide m. Feasibility forces n<=59 and b<=3981, allowing exhaustive enumeration of all reduced pairs and selection of the required minimum denominator and numerator.

New nodes: N1, N2, N3, N4 · judge: AC on 73 tests, slowest 0.337s · program: `paths/P1.cpp` · None submission(s)
### P2 · N1, N2, N3, N5, N6, N7

Instead of testing every reduced ratio, enumerate the divisors of m as the possible primitive weight sums. For each divisor d, the symmetric polynomial D(a,b) is strictly increasing in both arguments, so a two-pointer staircase finds all pairs with D(a,b)=d in only O(d^(1/(n-1))) evaluations. Factorization uses deterministic 64-bit Miller–Rabin with Pollard rho, and all polynomial tests use exact integer arithmetic.

New nodes: N5, N6, N7 · judge: AC on 73 tests, slowest 0.037s · program: `paths/P2.cpp` · None submission(s)
### P3 · N1, N2, N3, N5, N8, N9, N10

When k divides n, the k-term primitive geometric sum divides the full n-term sum, so feasibility forces this smaller polynomial to divide m. For composite n, choose its smallest prime factor k: the relevant smaller sums are at most 93457, allowing direct divisor enumeration and monotone searches without factoring m. Prime n is at least seven, where bounded pair enumeration is already small; all candidates are checked against the full divisibility condition and compared lexicographically.

New nodes: N8, N9, N10 · judge: AC on 73 tests, slowest 0.023s · program: `paths/P3.cpp` · None submission(s)
### P4 · N1, N2, N3, N11, N12, N13

Use the primitive-prime-divisor theorem for b^n-a^n: except for n=6 and (a,b)=(1,2), a feasible ratio yields an order-n element a/b modulo some prime factor of m. Factor m, generate the order-n residues for its eligible prime factors, and enumerate only bounded integer pairs satisfying the resulting congruences. Exact gcd and full-sum divisibility checks remove false positives, while a direct denominator-two test covers the theorem's exception.

New nodes: N11, N12, N13 · judge: AC on 73 tests, slowest 0.114s · program: `paths/P4.cpp` · None submission(s)

## Exploration

Finished: True · 4 submissions · reason: Four accepted approaches cover bounded ratio enumeration, divisor-level monotone search, short-block factor searches, and primitive-prime congruence enumeration. The remaining ideas either reuse these same mechanisms or introduce substantially more complexity without a genuinely different solution path.

Ideas the explorer considered and dropped:

- Enumerating individual integer pirate shares or the common scaling factor: their ranges can reach 10^18, unlike the bounded reduced denominator.
- Binary-searching each divisor level set instead of using a staircase: this reuses the same monotonicity and divisor characterization, so it is an implementation alternative rather than a new approach.
- Stern–Brocot or Farey enumeration of reduced ratios: this changes how the bounded coprime pairs are generated, but still follows the first path's enumeration rule.
- Special formulas for n=6 and even n: their useful divisibility constraints are already covered by the short-block factorization path.
- Enumerating all modular roots of the geometric-sum polynomial rather than primitive order-n roots: this broadens the existing prime-witness candidate enumeration rather than introducing a distinct search mechanism.
- Floating-point optimization or numerical integrality testing: neither replaces the exact divisibility condition reliably at the input bounds.

## Review

END ok: True — Each route supplies the infinite-process model, the exact divisibility criterion, complete bounded candidate generation, and the required output selection. The staircase elimination is valid on the triangular region a<b, the short-block bound covers every feasible pair, and the primitive-prime route correctly includes the sole relevant Zsigmondy exception.

Hazards ok: True — The hazards cover potentially oversized polynomial and modular arithmetic, reduced-fraction optimization, reliable factorization when used, and conservative search-bound rounding. H4 correctly distinguishes global coverage from target-specific and incumbent-based pruning. No essential numerical or output constraint is missing.

**Advisories.**

- N3 (bundles claims a solver can have separately; split it): The bound on n and the bound on b are independently discoverable: a solver can establish either without establishing the other. Split the minimum-sum argument yielding n<=59 from the leading-term argument bounding denominators.
- order: For finer stuck-point attribution, split N3 into the minimum primitive-sum bound on n and the leading-term bound on b. This is a structural recommendation; the existing combined claim is correct and usable.

**Builder's notes.** H4 now distinguishes unconditional feasibility bounds from target-specific and incumbent-based pruning. Splitting N3 remains a structural recommendation requiring permission to add a node and update the fixed routes; this submission preserves the mandated IDs and routes.


## Review history

| round | version | blocking | advisory | verdict |
|---|---|---|---|---|
| 1 | `b7808627a2226252` | 5 | 3 | revise |
| 2 | `c6a6389298216cdf` | 1 | 2 | revise |
| 3 | `eca5789a26b6a2ca` | 0 | 2 | accept |
