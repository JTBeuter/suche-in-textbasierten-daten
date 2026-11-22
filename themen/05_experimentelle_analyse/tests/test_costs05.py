"""Unabhängige strikte Gesamtkostenorakel, einschließlich rationaler Grenzen."""

from fractions import Fraction
from itertools import product

import pytest

from experimentelle_analyse.costs import cheaper_range


@pytest.mark.parametrize("delta_c,delta_t,first,last,exists", [
    (6, 2, 4, None, True),
    (0, 2, 1, None, True),
    (-6, 2, 0, None, True),
    (6, 0, None, None, False),
    (0, 0, None, None, False),
    (-6, 0, 0, None, True),
    (6, -2, None, None, False),
    (0, -2, None, None, False),
    (-6, -2, 0, 2, True),
])
def test_all_nine_sign_combinations_have_expected_strict_ranges(delta_c, delta_t, first, last, exists):
    result = cheaper_range(delta_c, delta_t)
    assert result["has_advantage"] is exists
    assert result["first_cheaper_q"] == first
    assert result["last_cheaper_q"] == last


@pytest.mark.parametrize("q_min,q_max", [(0, 0), (0, 1), (0, 20), (3, 3), (3, 20), (12, 20)])
def test_bounded_ranges_agree_with_exhaustive_independent_fraction_inequality(q_min, q_max):
    deltas = (Fraction(-7, 3), Fraction(-1, 2), Fraction(0), Fraction(1, 2), Fraction(7, 3))
    for delta_c, delta_t in product(deltas, repeat=2):
        # Enumeration does not repeat the implementation's floor/ceil solution.
        expected = [q for q in range(q_min, q_max + 1) if Fraction(q) * delta_t > delta_c]
        result = cheaper_range(delta_c, delta_t, q_min, q_max)
        assert result["has_advantage"] is bool(expected), (delta_c, delta_t, q_min, q_max)
        assert result["first_cheaper_q"] == (expected[0] if expected else None)
        assert result["last_cheaper_q"] == (expected[-1] if expected else None)


@pytest.mark.parametrize("delta_c,delta_t,boundary,first,last", [
    (Fraction(7, 3), Fraction(1, 3), 7, 8, None),
    (Fraction(-7, 3), Fraction(-1, 3), 7, 0, 6),
    (Fraction(7, 3), Fraction(2, 3), Fraction(7, 2), 4, None),
    (Fraction(-7, 3), Fraction(-2, 3), Fraction(7, 2), 0, 3),
])
def test_exact_fraction_boundary_and_equality_are_never_rounded_into_advantage(
    delta_c, delta_t, boundary, first, last,
):
    result = cheaper_range(delta_c, delta_t)
    assert result["equality_q"] == float(boundary)
    assert result["first_cheaper_q"] == first
    assert result["last_cheaper_q"] == last
    if Fraction(boundary).denominator == 1:
        equality_q = int(boundary)
        at_equality = cheaper_range(delta_c, delta_t, equality_q, equality_q)
        assert at_equality["has_advantage"] is False


def test_large_integer_threshold_keeps_fraction_precision_beyond_float_mantissa():
    equality = 2**53 + 1
    result = cheaper_range(Fraction(equality, 2), Fraction(1, 2))
    assert result["first_cheaper_q"] == equality + 1
    assert cheaper_range(Fraction(equality, 2), Fraction(1, 2), equality, equality)["has_advantage"] is False
    assert cheaper_range(Fraction(equality, 2), Fraction(1, 2), equality + 1, equality + 1)["has_advantage"] is True


@pytest.mark.parametrize("kwargs", [
    {"q_min": -1}, {"q_min": True}, {"q_min": 1.0}, {"q_min": "1"}, {"q_min": None},
    {"q_max": -1}, {"q_max": True}, {"q_max": 1.0}, {"q_max": "1"},
    {"q_min": 3, "q_max": 2},
])
def test_invalid_query_count_bounds_are_input_errors(kwargs):
    with pytest.raises(ValueError):
        cheaper_range(1, 1, **kwargs)


@pytest.mark.parametrize("delta_c,delta_t", [(float("nan"), 1), (1, float("nan")), ("invalid", 1)])
def test_nonnumeric_or_nan_costs_are_rejected(delta_c, delta_t):
    with pytest.raises(ValueError):
        cheaper_range(delta_c, delta_t)
