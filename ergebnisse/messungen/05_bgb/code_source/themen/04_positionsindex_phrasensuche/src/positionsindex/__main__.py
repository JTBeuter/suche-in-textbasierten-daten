"""CLI: gemeinsame Aufbereitung, gewählte Phrasensuche, eine JSON-Zeile."""

import argparse
import json

from gemeinsam import CorpusError, QueryError, load_corpus, normalize_query, prepare_corpus

from .index import build_positional_index
from .search import search_direct_phrase, search_index_phrase


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exakte Tokenphrasen in lokalen UTF-8-Textdateien")
    parser.add_argument("--corpus", required=True, help="Verzeichnis mit .txt-Dateien")
    parser.add_argument("--phrase", required=True, help="Nichtleere Rohtextphrase")
    parser.add_argument("--method", choices=("direct", "index"), default="index")
    args = parser.parse_args(argv)
    try:
        phrase_tokens = normalize_query(args.phrase, query_type="phrase")
        corpus = prepare_corpus(load_corpus(args.corpus))
        if args.method == "direct":
            matches = search_direct_phrase(corpus, phrase_tokens)
        else:
            matches = search_index_phrase(build_positional_index(corpus), phrase_tokens)
    except (CorpusError, QueryError) as error:
        parser.error(str(error))
    print(json.dumps({
        "mode": "phrase", "method": args.method, "phrase": args.phrase,
        "normalized_tokens": phrase_tokens, "matches": matches,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
