"""Kleine CLI; Dateizugriff und Aufbereitung bleiben außerhalb der Kernsuche."""

import argparse
import json
import sys

from gemeinsam import CorpusError, QueryError, load_corpus, prepare_corpus

from .index import build_inverted_index, search_index_word


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Einzelwortsuche mit invertiertem Index")
    parser.add_argument("--corpus", required=True, help="Verzeichnis mit UTF-8-.txt-Dateien")
    parser.add_argument("--query", required=True, help="Rohtextanfrage mit genau einem Token")
    args = parser.parse_args(argv)
    try:
        corpus = prepare_corpus(load_corpus(args.corpus))
        index = build_inverted_index(corpus)
        matches = search_index_word(index, args.query)
    except (CorpusError, QueryError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"mode": "word", "query": args.query, "matches": matches}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
