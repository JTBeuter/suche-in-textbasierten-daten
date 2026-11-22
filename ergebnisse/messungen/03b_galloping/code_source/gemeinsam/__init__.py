"""Importadapter für die fachliche Repositorystruktur.

Im Repository steht der Ordner gemeinsam/ vor setuptools' editable finder.
Dieser reguläre Paketadapter verhindert, dass Python ihn als leeren Namespace
importiert. Die Implementierung bleibt unter src/gemeinsam/; installierte
Wheels verwenden unmittelbar dessen __init__.py. PYTHONPATH ist nicht nötig.
"""

from pathlib import Path as _Path

__path__.append(str(_Path(__file__).parent / "src" / "gemeinsam"))

from .corpus import load_corpus, prepare_corpus
from .models import CorpusError, PreparedDocument, QueryError, RawDocument
from .text import normalize_query, normalize_text, tokenize

__all__ = [
    "CorpusError",
    "PreparedDocument",
    "QueryError",
    "RawDocument",
    "load_corpus",
    "normalize_query",
    "normalize_text",
    "prepare_corpus",
    "tokenize",
]
