from fractions import Fraction
from math import comb


def upper_tail_counts(a: int, b: int) -> tuple[int, int]:
    if any(type(count) is not int or count < 0 for count in (a, b)):
        raise ValueError('disagreement counts must be nonnegative integers')
    n = a + b
    favourable = sum(comb(n, successes) for successes in range(a, n + 1))
    return favourable, 1 << n


def exact_upper_tail(a: int, b: int) -> Fraction:
    return Fraction(*upper_tail_counts(a, b))
