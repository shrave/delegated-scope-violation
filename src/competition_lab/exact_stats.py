"""Exact statistical tests and intervals. The single source for every
inferential number the paper prints.

WHY THIS MODULE EXISTS
----------------------
Before it, `scripts/paper_tables.py` computed no statistics at all: 1,254 lines
rendering hand-entered p-values. That is how a literal "p=0.0002" survived in
the GPT CI/CD row when the exact value is 0.0083 -- wrong by 40x, and
unreachable by any code in the repo, so no test could have caught it.

The rule this module enforces: no statistic appears in a table that the table
builder did not compute. Import from here; do not re-derive.

TOLERANCE
---------
Fisher's exact test sums the null probabilities of every table at most as
likely as the observed one. "At most as likely" needs a tolerance, because the
probabilities are floating point and equally-likely tables must all be counted
or none. An ABSOLUTE tolerance breaks on small probabilities: with
`p <= obs + 1e-12`, an observed table of probability 2.2e-59 admits every table
below 1e-12 -- effectively all of them -- and the function returns ~1e-12
instead of ~1e-59. Measured before the fix:

    (100,0,0,100)  returned 1.45e-12  exact 2.21e-59   off by 6.6e46
    (80,0,0,80)    returned 2.41e-13  exact 2.17e-47   off by 1.1e34

The error is always conservative, so nothing published was a false positive,
and every value above ~1e-11 was unaffected -- the reported 6.5534e-05 and the
tea-tasting 0.485714 both reproduce exactly. But any printed p below ~1e-11 was
fabricated. A RELATIVE tolerance scales with the magnitude being compared and
is correct at every scale.
"""
from __future__ import annotations

import math
from fractions import Fraction

# Relative, not absolute. See module docstring.
_REL_TOL = 1e-7


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]].

    Sums the hypergeometric probability of every table with the same margins
    that is at most as likely as the observed one.
    """
    for name, v in (("a", a), ("b", b), ("c", c), ("d", d)):
        if v < 0:
            raise ValueError(f"cell {name} must be non-negative, got {v}")
    n = a + b + c + d
    if n == 0:
        raise ValueError("table is empty")
    if (a + b) == 0 or (c + d) == 0 or (a + c) == 0 or (b + d) == 0:
        # A zero margin leaves exactly one table possible, so p = 1.
        return 1.0

    obs = math.comb(a + b, a) * math.comb(c + d, c) / math.comb(n, a + c)
    total = 0.0
    for i in range(0, min(a + b, a + c) + 1):
        j = a + c - i
        if j < 0 or j > c + d:
            continue
        p = math.comb(a + b, i) * math.comb(c + d, j) / math.comb(n, a + c)
        if p <= obs * (1.0 + _REL_TOL):
            total += p
    return min(total, 1.0)


def fisher_exact_fraction(a: int, b: int, c: int, d: int) -> Fraction:
    """Exact rational two-sided Fisher p. The reference `fisher_exact` is
    validated against; too slow for large n but never wrong.
    """
    n = a + b + c + d
    if (a + b) == 0 or (c + d) == 0 or (a + c) == 0 or (b + d) == 0:
        return Fraction(1)
    obs = Fraction(math.comb(a + b, a) * math.comb(c + d, c), math.comb(n, a + c))
    total = Fraction(0)
    for i in range(0, min(a + b, a + c) + 1):
        j = a + c - i
        if j < 0 or j > c + d:
            continue
        p = Fraction(math.comb(a + b, i) * math.comb(c + d, j), math.comb(n, a + c))
        if p <= obs:
            total += p
    return total


def clopper_pearson(
    events: int, total: int, alpha: float = 0.05
) -> tuple[float, float]:
    """Exact (Clopper-Pearson) CI for a binomial proportion.

    Replaces Wilson for cell rates. Wilson is correct code but the wrong
    estimator here: it inverts a normal approximation, and at n=20 with 0
    events it returns [0, 0.161] where the exact interval is [0, 0.168]. Most
    cells in this corpus are k=0 or small k at n=20, which is exactly where
    Wilson's coverage is challenged.

    Uses the Beta quantile relationship rather than a root-find, so the
    endpoints are the exact ones.
    """
    if total <= 0:
        raise ValueError("total must be positive")
    if not 0 <= events <= total:
        raise ValueError(f"events {events} outside [0, {total}]")
    lo = 0.0 if events == 0 else _beta_ppf(alpha / 2, events, total - events + 1)
    hi = (
        1.0
        if events == total
        else _beta_ppf(1 - alpha / 2, events + 1, total - events)
    )
    return lo, hi


def _beta_ppf(q: float, a: float, b: float) -> float:
    """Inverse regularised incomplete beta, by bisection on `_betainc`.

    Bisection rather than Newton: the domain is [0,1], 200 halvings give ~1e-60
    which is far past double precision, and it cannot diverge. Speed is
    irrelevant -- this is called a few dozen times per table build.
    """
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _betainc(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _betainc(x: float, a: float, b: float) -> float:
    """Regularised incomplete beta I_x(a, b), via its continued fraction."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1 - x) - lbeta)
    # Lentz's algorithm; the symmetry swap keeps it in its convergent region.
    if x > (a + 1) / (a + b + 2):
        return 1.0 - _betainc(1 - x, b, a)
    f, c, d = 1.0, 1.0, 0.0
    for i in range(0, 300):
        m = i // 2
        if i == 0:
            num = 1.0
        elif i % 2 == 0:
            num = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m))
        else:
            num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        c = 1.0 + num / c
        if abs(c) < 1e-30:
            c = 1e-30
        f *= c * d
        if abs(1.0 - c * d) < 1e-15:
            break
    return front * (f - 1.0) / a


def newcombe_diff(e1: int, n1: int, e2: int, n2: int,
                  alpha: float = 0.05) -> tuple[float, float]:
    """Newcombe score CI for the DIFFERENCE of two proportions (p1 - p2).

    There was no difference-interval code in the repo at all, and neither
    Clopper-Pearson nor Wilson supplies one -- both are single-proportion
    methods. Every "X% vs Y%" claim in the paper needs this.

    Newcombe's method 10: build a Wilson interval for each proportion, then
    combine the roots. It keeps coverage when a cell is 0 or n, which the
    normal-approximation difference interval does not.
    """
    if n1 <= 0 or n2 <= 0:
        raise ValueError("both totals must be positive")
    z = _z_for(alpha)
    l1, u1 = _wilson_bounds(e1, n1, z)
    l2, u2 = _wilson_bounds(e2, n2, z)
    d = e1 / n1 - e2 / n2
    lo = d - z * math.sqrt(l1 * (1 - l1) / n1 + u2 * (1 - u2) / n2)
    hi = d + z * math.sqrt(u1 * (1 - u1) / n1 + l2 * (1 - l2) / n2)
    return max(lo, -1.0), min(hi, 1.0)


def _wilson_bounds(events: int, total: int, z: float) -> tuple[float, float]:
    """Wilson score bounds -- an INPUT to Newcombe, not a reported interval.

    Kept deliberately private: reported cell rates use clopper_pearson.
    """
    p = events / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _z_for(alpha: float) -> float:
    """Two-sided normal quantile. 1.959964 at alpha=0.05."""
    return _norm_ppf(1 - alpha / 2)


def _norm_ppf(q: float) -> float:
    """Inverse standard normal CDF, by bisection on erf."""
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
