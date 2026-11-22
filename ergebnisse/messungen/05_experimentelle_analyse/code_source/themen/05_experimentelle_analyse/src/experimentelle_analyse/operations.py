"""Adapter der geprüften Fach-APIs; kein Algorithmusersatz."""
import hashlib
import json

from gemeinsam import normalize_query
from direkte_suche import search_direct_word
from invertierter_index import build_inverted_index, search_index_word
from boolesche_suche import search_direct_boolean, search_index_boolean
from positionsindex import build_positional_index, search_direct_phrase, search_index_phrase


BUILDERS = {"inverted_index": build_inverted_index, "positional_index": build_positional_index}


def variants(kind):
    return ("direct", "index", "index_shortest") if kind == "and" else ("direct", "index")


def search_operation(corpus, index, query, algorithm):
    """Rohtextnormalisierung und vollständiges Ergebnis gehören zum Aufruf."""
    kind, text = query["kind"], query["text"]
    if kind == "word":
        return (search_direct_word(corpus, text) if algorithm == "direct"
                else search_index_word(index, text))
    if kind == "phrase":
        terms = normalize_query(text, "phrase")
        return (search_direct_phrase(corpus, terms) if algorithm == "direct"
                else search_index_phrase(index, terms))
    terms = text.split()
    if algorithm == "direct":
        return search_direct_boolean(corpus, terms, kind.upper())
    return search_index_boolean(index, terms, kind.upper(),
        variant="shortest_first" if algorithm == "index_shortest" else "input_order")


def result_hash(result):
    return hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest()


def validate_result(result, query, corpus):
    """Vollständiger Orakelvergleich und explizite Ausgabeinvarianten."""
    if result != query["expected"]:
        raise AssertionError(f"{query['id']}: Ergebnis weicht vom unabhängigen Orakel ab")
    known = {d.document_id: d.tokens for d in corpus}
    if query["kind"] == "phrase":
        if type(result) is not dict or list(result) != sorted(set(result)):
            raise AssertionError("Phrasendokumente nicht sortiert/eindeutig")
        terms = tuple(query["terms"])
        for doc, starts in result.items():
            if doc not in known or type(starts) is not list or not starts:
                raise AssertionError("Unzulässige Positionsliste")
            if starts != sorted(set(starts)):
                raise AssertionError("Positionen nicht sortiert/eindeutig")
            for p in starts:
                if type(p) is not int or p < 0 or known[doc][p:p+len(terms)] != terms:
                    raise AssertionError("Unzulässige Startposition")
    elif type(result) is not list or result != sorted(set(result)) or any(d not in known for d in result):
        raise AssertionError("Dokumenttreffer nicht sortiert/eindeutig")


def index_oracle(tokens, positional=False):
    oracle = {}
    for doc, words in sorted(tokens.items()):
        for p, word in enumerate(words):
            if positional:
                oracle.setdefault(word, {}).setdefault(doc, []).append(p)
            else:
                docs = oracle.setdefault(word, [])
                if not docs or docs[-1] != doc:
                    docs.append(doc)
    return oracle


def validate_index(index, oracle, positional=False):
    observed = ({w: {d: list(p) for d, p in docs.items()} for w, docs in index.items()}
                if positional else {w: list(docs) for w, docs in index.items()})
    if observed != oracle:
        raise AssertionError("Indexstruktur weicht vom unabhängigen Tokenplan ab")
