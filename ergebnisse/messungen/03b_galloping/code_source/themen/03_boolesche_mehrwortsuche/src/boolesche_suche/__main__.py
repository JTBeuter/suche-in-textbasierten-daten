"""CLI: Begriffe und Operator getrennt; Ergebnis als eine JSON-Zeile."""

import argparse
import json

from gemeinsam import CorpusError, QueryError, load_corpus, prepare_corpus
from invertierter_index import build_inverted_index

from .query import normalize_boolean_query
from .search import VARIANTS, search_direct_boolean, search_index_boolean


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AND-/OR-Wortsuche in lokalen UTF-8-Textdateien")
    parser.add_argument("--corpus", required=True, help="Verzeichnis mit .txt-Dateien")
    parser.add_argument("--terms", required=True, nargs="+", help="Einzelne Suchwörter, ohne Operatoren")
    parser.add_argument("--operator", required=True, choices=("AND", "OR"))
    parser.add_argument("--method", choices=("direct", "index"), default="index")
    parser.add_argument("--variant", choices=VARIANTS, default="input_order",
                        help="shortest_first und galloping nur für --operator AND --method index")
    parser.add_argument("--exclude", metavar="WORT",
                        help="Genau ein auszuschließendes Wort (AND NOT), nur mit --operator AND")
    args = parser.parse_args(argv)
    try:
        if args.exclude is not None and args.operator != "AND":
            raise QueryError("--exclude ist ausschließlich mit --operator AND zulässig.")
        query = normalize_boolean_query(args.terms, args.operator, args.exclude)
        if args.method == "direct" and args.variant != "input_order":
            raise QueryError("Die direkte Referenz verwendet ausschließlich variant='input_order'.")
        if args.operator == "OR" and args.variant != "input_order":
            raise QueryError("OR unterstützt ausschließlich variant='input_order'.")
        corpus = prepare_corpus(load_corpus(args.corpus))
        if args.method == "direct":
            matches = search_direct_boolean(corpus, args.terms, args.operator, args.exclude)
        else:
            matches = search_index_boolean(
                build_inverted_index(corpus), args.terms, args.operator, args.variant, args.exclude,
            )
    except (CorpusError, QueryError) as error:
        parser.error(str(error))
    output = {
        "mode": "boolean", "method": args.method, "operator": query.operator,
        "variant": args.variant, "terms": args.terms, "normalized_terms": query.terms,
        "original_term_count": query.original_term_count,
        "effective_term_count": query.effective_term_count,
    }
    if args.exclude is not None:
        # Nur mit --exclude; ohne Schalter bleibt die Ausgabe unverändert.
        output.update(exclude=args.exclude, normalized_exclude=query.exclude)
    output["matches"] = matches
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
