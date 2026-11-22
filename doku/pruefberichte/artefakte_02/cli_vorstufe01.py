"""Minimaler ausführbarer Einstieg: python -m direkte_suche."""

import argparse
import json

from gemeinsam import CorpusError, QueryError, load_corpus, prepare_corpus

from .search import search_direct_substring, search_direct_word


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Direkte Suche in lokalen UTF-8-Textdateien")
    parser.add_argument("--corpus", required=True, help="Verzeichnis mit .txt-Dateien")
    parser.add_argument("--query", required=True, help="Suchwort bzw. Zeichenfolge")
    parser.add_argument("--mode", choices=("word", "substring"), default="word")
    args = parser.parse_args(argv)
    try:
        raw_corpus = load_corpus(args.corpus)
        if args.mode == "word":
            matches = search_direct_word(prepare_corpus(raw_corpus), args.query)
        else:
            matches = search_direct_substring(raw_corpus, args.query)
    except (CorpusError, QueryError) as error:
        parser.error(str(error))
    print(json.dumps({"mode": args.mode, "query": args.query, "matches": matches}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
