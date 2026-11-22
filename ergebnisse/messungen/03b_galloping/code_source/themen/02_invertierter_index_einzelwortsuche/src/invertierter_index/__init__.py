"""Öffentliche Schnittstelle für Einzelwortsuche und Postingzugriff."""

from .index import InvertedIndex, build_inverted_index, get_postings, search_index_word

__all__ = ["InvertedIndex", "build_inverted_index", "get_postings", "search_index_word"]
