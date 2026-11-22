#!/usr/bin/env python3
"""Prüft einen BGB-Lauf der Reihe 04 unabhängig; führt keine Zeitmessung aus.

Standard ist 04_bgb; --eingabe NAME prüft einen anderen Ordner unter
ergebnisse/messungen, etwa 04_bgb_pilot. --archive-only lässt abweichende
aktive Quellen zu; die archivierten gemessenen Quellen bleiben hashgeprüft,
die Semantik wird mit dem aktiven Code neu berechnet. --timing-only prüft
ohne Speicherwerte. Die gelieferte Reihe mit Kafka-Realteil prüft weiterhin
verify_results.py.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess

from gemeinsam.messung import CSV_FIELDS
from invertierter_index import build_inverted_index
from positionsindex import build_positional_index, search_direct_phrase, search_index_phrase

if __package__:
    from . import run_bgb
    from .run import MEMORY_FIELDS, ROOT, code_hashes, describe_dataset, sha, validate_positional
    from .verify_results import verify_memory, verify_timing_rows
else:
    import run_bgb
    from run import MEMORY_FIELDS, ROOT, code_hashes, describe_dataset, sha, validate_positional
    from verify_results import verify_memory, verify_timing_rows


def verify_code(directory, metadata, *, archive_only=False):
    """Quellarchiv immer; aktiver Code nur ohne --archive-only."""
    assert metadata["source_archive"] == "code_source/" and metadata["code_sha256"]
    changed = []
    for relative, expected in metadata["code_sha256"].items():
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        assert sha(directory / "code_source" / relative) == expected, f"Quelltextarchiv beschädigt: {relative}"
        if not (ROOT / relative).is_file() or sha(ROOT / relative) != expected:
            changed.append(relative)
    added = sorted(set(code_hashes()) - set(metadata["code_sha256"]))
    if not archive_only:
        assert not changed and not added, f"aktiver Code weicht vom gemessenen Stand ab: {', '.join(changed + added)}"
    notes = [f"{len(metadata['code_sha256'])} archivierte Quell-SHA-256 geprüft."]
    if changed or added:
        notes.append(f"Nur-Archiv-Modus: {len(changed + added)} aktive Quellen weichen ab ({', '.join(changed + added)}).")
    return notes


def verify_contract(directory, metadata):
    """Lauf, Plan, ein Realdatensatz mit mehreren Dokumenten und gesperrte Anfrageauswahl."""
    parameters = run_bgb.PARAMETERS
    assert metadata["series"] == run_bgb.SERIES
    assert metadata["parameters"] == parameters, "Parametervertrag geändert"
    kind = metadata["run_kind"]
    assert kind in ("pilot", "final"), f"unbekannte Laufart: {kind}"
    assert metadata["measurement_plan"] == parameters[f"{kind}_plan"], "falscher gesperrter Messplan"
    assert metadata["run_id"] == directory.name
    assert metadata["data_sha256"] == run_bgb.data_hashes(), "BGB-Datenstand weicht vom gemessenen Stand ab"
    environment = metadata["environment"]
    assert isinstance(environment["python_hash_seed"], str) and isinstance(environment["python_hash_seed_set"], bool)
    if environment["python_hash_seed"] != "random":
        assert environment["python_hash_seed_set"] is True, "Hashseed-Angabe widersprüchlich"
    (dataset,) = metadata["datasets"]
    real = parameters["real"]
    assert dataset["dataset_id"] == real["dataset_id"] and dataset["kind"] == "real"
    for field in ("document_count", "token_count", "vocabulary_size", "posting_count"):
        assert dataset[field] == real[field], f"{field} weicht vom Parametervertrag ab"
    assert len(dataset["files"]) == len(dataset["document_lengths"]) == real["document_count"] > 1
    assert dataset["source_fixture"]["data_sha256"] == metadata["data_sha256"]
    assert dataset["source_fixture"]["canonical_corpus_sha256"] == real["corpus_sha256"]
    queries = dataset["queries"]
    assert [query["query_id"] for query in queries] == [spec["query_id"] for spec in parameters["queries"]]
    for query, spec in zip(queries, parameters["queries"]):
        assert query["text"] == spec["text"] and query["group"] == spec["group"]
        assert query["phrase_length"] == spec["phrase_length"]
        assert query["hit_count"] == len(query["expected_positions"]) == spec["document_count"]
        assert query["position_count"] == spec["match_count"]
    return dataset


def verify_corpus(metadata):
    """Korpus, Erwartungen und beide Suchverfahren mit aktivem Code neu prüfen."""
    (saved,) = metadata["datasets"]
    (identifier, directory, tokens, queries, extra), = list(run_bgb.datasets())
    prepared, postings, positional, description = describe_dataset(identifier, directory, tokens, queries, extra)
    assert description == saved, "Datensatz-/Anfrage-/Positionsmetadaten weichen von der unabhängigen Neuberechnung ab"
    inverted = build_inverted_index(prepared)
    assert dict(inverted) == postings, "Dokumentindex weicht von unabhängigen Postings ab"
    del inverted
    index = build_positional_index(prepared)
    validate_positional(index, positional)
    for query in queries:
        assert search_direct_phrase(prepared, query.tokens) == query.expected, f"{query.query_id}: direkte Suche"
        assert search_index_phrase(index, query.tokens) == query.expected, f"{query.query_id}: Positionsindex"
    return len(saved["files"])


def verify_decision(directory, metadata, *, require_decision=True):
    """Pilotsperre (Pilot) bzw. Bindung an den Pilot (Hauptlauf)."""
    if metadata["run_kind"] == "pilot":
        if not require_decision:
            return
        decision = json.loads((directory / "pilot_decision.json").read_text(encoding="utf-8"))
        assert decision["pilot_correct"] is True and decision["pilot_is_not_final_measurement"] is True
        assert decision["pilot_plan"] == run_bgb.PARAMETERS["pilot_plan"]
    else:
        pilot = run_bgb.MESSUNGEN / Path(metadata["pilot_directory"]).name
        decision = json.loads((pilot / "pilot_decision.json").read_text(encoding="utf-8"))
    assert decision["locked_parameters"] == metadata["parameters"], "Lauf passt nicht zur Pilotsperre"
    assert decision["method_code_sha256"] == metadata["code_sha256"], "Lauf mit anderem Code als Pilot"
    assert decision["data_sha256"] == metadata["data_sha256"], "Lauf mit anderem Datenstand als Pilot"
    assert decision["python_hash_seed"] == metadata["environment"]["python_hash_seed"], "anderer Hashseed als Pilot"


def verify_directory(directory, *, archive_only=False, require_memory=True, require_decision=True):
    directory = Path(directory)
    with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames) == CSV_FIELDS, "abweichendes CSV-Schema"
        rows = list(reader)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    verify_contract(directory, metadata)
    verify_code(directory, metadata, archive_only=archive_only)
    verify_timing_rows(rows, summary, metadata)
    files = verify_corpus(metadata)
    memory_count = 0
    if require_memory or (directory / "memory.json").exists():
        memory = json.loads((directory / "memory.json").read_text(encoding="utf-8"))
        with (directory / "memory.csv").open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            assert tuple(reader.fieldnames) == MEMORY_FIELDS
            memory_rows = list(reader)
        verify_memory(memory, memory_rows, metadata)
        memory_count = len(memory_rows)
    verify_decision(directory, metadata, require_decision=require_decision)
    return len(rows), len(summary), files, memory_count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--eingabe", metavar="NAME", default=run_bgb.STANDARD_FINAL,
                        help=f"Ordner unter ergebnisse/messungen (Standard {run_bgb.STANDARD_FINAL})")
    parser.add_argument("--archive-only", action="store_true",
                        help="abweichende aktive Quellen zulassen; archivierte gemessene Quellen bleiben geprüft")
    parser.add_argument("--timing-only", action="store_true", help="ohne Speicherwerte prüfen")
    args = parser.parse_args(argv)
    if not args.eingabe or Path(args.eingabe).name != args.eingabe:
        raise SystemExit("--eingabe erwartet genau einen Ordnernamen unter ergebnisse/messungen")
    directory = run_bgb.MESSUNGEN / args.eingabe
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    for note in verify_code(directory, metadata, archive_only=args.archive_only):
        print(note)
    counts = verify_directory(directory, archive_only=args.archive_only, require_memory=not args.timing_only)
    print(f"{directory.name}: {counts[0]} Rohwerte, {counts[1]} Statistikgruppen, {counts[2]} Dateien und "
          f"{counts[3]} Speicherwerte geprüft; Manifest, unabhängige Tokens, volle Startpositionen, "
          "Randomisierung, Statistik, Quellarchiv und Pilotsperre korrekt.")
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    print(f"Lauf {metadata['run_kind']}; PYTHONHASHSEED={metadata['environment']['python_hash_seed']}; "
          f"Mess-Commit {metadata['git_commit']} (dirty={metadata['git_dirty']}); aktueller Git-Stand "
          f"dirty={bool(status)}; Hintergrundlast: {metadata['background_load']}")


if __name__ == "__main__":
    main()
