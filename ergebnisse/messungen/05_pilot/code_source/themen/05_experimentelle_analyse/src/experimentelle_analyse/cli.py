"""Gemeinsame CLI: Suchdemonstration, Datenerzeugung, Messung und Auswertung."""

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Direkte und indexbasierte Textsuche unter gleichen Suchregeln",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search", help="Lokale UTF-8-Dokumente durchsuchen")
    search.add_argument("--corpus", required=True, type=Path, help="Verzeichnis mit .txt-Dateien")
    search.add_argument("--kind", required=True, choices=("word", "and", "or", "phrase"))
    search.add_argument("--method", choices=("direct", "index"), default="index")
    search.add_argument(
        "--query", required=True,
        help="Rohtext; bei AND/OR zählt jedes normalisierte Token als Suchbegriff",
    )
    search.add_argument(
        "--variant", choices=("basic", "shortest_first"), default="basic",
        help="shortest_first ist nur für indexbasierte AND-Suche zulässig",
    )
    for command, description in (
        ("run", "Konfigurierten Versuch ausführen"),
        ("generate", "Korpora aus einer Versuchskonfiguration erzeugen"),
        ("analyse", "Gespeicherte Rohmessungen auswerten"),
        ("verify", "Gespeicherte Messungen und Herkunft prüfen"),
    ):
        child = commands.add_parser(command, help=description)
        if command in ("run", "generate"):
            child.add_argument("--config", required=True, type=Path)
        else:
            child.add_argument("--input", required=True, type=Path)
        if command != "verify":
            child.add_argument("--output", required=True, type=Path)
    return parser


def execute_search(args: argparse.Namespace) -> dict:
    """Verwendet alle vier unveränderten Fach-APIs auf derselben Aufbereitung.

    Der boolesche CLI-Text ist eine Tokenfolge ohne eigene Operatorsprache.
    Der Operator stammt ausschließlich aus --kind. Damit bedeutet etwa
    ``--kind and --query 'Verbindung, Server'`` zwei ganze Suchwörter; ein
    wörtlich eingegebenes AND wird ebenfalls als gesuchtes Token behandelt.
    Die Fach-API dedupliziert boolesche Begriffe stabil. Phrasen bewahren
    Reihenfolge und Wiederholungen sowie sämtliche nullbasierten Starts.
    """
    from gemeinsam import QueryError, load_corpus, normalize_query, prepare_corpus

    if args.variant == "shortest_first" and (args.kind != "and" or args.method != "index"):
        raise QueryError("shortest_first ist ausschließlich für --kind and --method index zulässig.")
    tokens = normalize_query(args.query, "word" if args.kind == "word" else "phrase")
    corpus = prepare_corpus(load_corpus(args.corpus))
    if args.kind == "word":
        if args.method == "direct":
            from direkte_suche import search_direct_word
            matches = search_direct_word(corpus, args.query)
        else:
            from invertierter_index import build_inverted_index, search_index_word
            matches = search_index_word(build_inverted_index(corpus), args.query)
    elif args.kind in ("and", "or"):
        from boolesche_suche import normalize_boolean_query, search_direct_boolean, search_index_boolean

        query = normalize_boolean_query(tokens, args.kind.upper())
        tokens = query.terms
        if args.method == "direct":
            matches = search_direct_boolean(corpus, tokens, query.operator)
        else:
            from invertierter_index import build_inverted_index
            variant = "input_order" if args.variant == "basic" else "shortest_first"
            matches = search_index_boolean(build_inverted_index(corpus), tokens, query.operator, variant)
    else:
        from positionsindex import build_positional_index, search_direct_phrase, search_index_phrase

        if args.method == "direct":
            matches = search_direct_phrase(corpus, tokens)
        else:
            matches = search_index_phrase(build_positional_index(corpus), tokens)
    return {
        "kind": args.kind,
        "method": args.method,
        "variant": args.variant,
        "query": args.query,
        "normalized_tokens": tokens,
        "matches": matches,
    }


def _execute_command(args: argparse.Namespace):
    if args.command == "search":
        return execute_search(args)
    if args.command == "run":
        from .pipeline import run_experiment
        return run_experiment(args.config, args.output)
    if args.command == "analyse":
        from .analysis import analyse
        return analyse(args.input, args.output)
    if args.command == "verify":
        from .verify import verify_run
        return verify_run(args.input)
    from .datasets import generate_from_config
    return generate_from_config(args.config, args.output)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        # Progress from commands belongs to stderr; stdout stays one JSON value.
        with redirect_stdout(sys.stderr):
            result = _execute_command(args)
    except (ValueError, OSError, AssertionError) as error:
        parser.error(str(error) or type(error).__name__)
    if result is None:
        result = {"command": args.command, "status": "ok"}
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0
