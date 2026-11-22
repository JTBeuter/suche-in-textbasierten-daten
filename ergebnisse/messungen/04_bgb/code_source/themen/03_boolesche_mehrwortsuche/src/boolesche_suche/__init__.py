"""Öffentliche API für reine boolesche Mehrwortsuche (Thema 03)."""

from .lists import difference_sorted, intersect_galloping, intersect_sorted, union_sorted
from .query import BooleanQuery, normalize_boolean_query, normalize_terms
from .search import VARIANTS, search_direct_boolean, search_index_boolean

__all__ = [
    "BooleanQuery", "VARIANTS", "difference_sorted", "intersect_galloping", "intersect_sorted",
    "union_sorted", "normalize_boolean_query", "normalize_terms", "search_direct_boolean",
    "search_index_boolean",
]
