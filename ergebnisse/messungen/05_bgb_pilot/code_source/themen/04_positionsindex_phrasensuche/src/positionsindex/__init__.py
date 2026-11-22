"""Öffentliche API für Positionsindex und exakte Tokenphrasen (Thema 04)."""

from .index import PositionalIndex, build_positional_index
from .query import validate_phrase_tokens
from .search import PhraseMatches, search_direct_phrase, search_index_phrase

__all__ = [
    "PhraseMatches", "PositionalIndex", "build_positional_index",
    "search_direct_phrase", "search_index_phrase", "validate_phrase_tokens",
]
