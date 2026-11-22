#!/usr/bin/env python3
"""Schema, Statistik, Pflanzplan, Speicher und gemessene Quellen ohne Zeitlauf."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import random
from statistics import median, quantiles
from tempfile import TemporaryDirectory

from gemeinsam import load_corpus, prepare_corpus
from gemeinsam.messung import CSV_FIELDS

from generator import generate_corpus


ROOT = Path(__file__).resolve().parents[3]
MEMORY_FIELDS = ("run_id", "dataset_id", "document_count", "token_count", "vocabulary_size",
                 "posting_count", "repeat", "retained_traced_bytes", "peak_traced_bytes", "exclusive_index_bytes")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_data(rows: list[dict], summary: list[dict], metadata: dict, memory: dict, memory_rows: list[dict]) -> None:
    """Rechnet unabhängig aus Rohwerten; keine Mess-/Suchfunktion wird aufgerufen."""
    plan = metadata["measurement_plan"]
    count = plan["repeats"]
    datasets = {ds["dataset_id"]: ds for ds in metadata["datasets"]}
    assert len(datasets) == 6
    assert len(rows) == len(datasets) * 7 * count
    assert len(summary) == len(datasets) * 7
    grouped = defaultdict(list)
    for row in rows:
        ds = datasets[row["dataset_id"]]
        phase = row["phase"]
        assert phase in {"build", "query"}
        assert row["algorithm"] in {"direct_word", "inverted_index"}
        assert row["correct"] == "True"
        assert row["run_id"] == metadata["run_id"] and row["git_commit"] == metadata["git_commit"]
        assert int(row["seed"]) == plan["seed"]
        for field in ("document_count", "token_count", "text_bytes"):
            assert int(row[field]) == ds[field]
        for field in ("load_ms", "preparation_ms", "index_bytes", "peak_memory_bytes"):
            assert row[field] == ""
        elapsed, block = int(row["elapsed_ns"]), int(row["block_size"])
        assert elapsed >= 0
        assert float(row[f"{phase}_ms"]) == elapsed / 1_000_000 / block
        assert row["query_ms" if phase == "build" else "build_ms"] == ""
        if phase == "build":
            assert row["algorithm"] == "inverted_index" and block == 1
            assert all(row[field] == "" for field in ("query_id", "query_type", "query_text", "hit_count", "order_index"))
        else:
            query = next(q for q in ds["queries"] if q["query_id"] == row["query_id"])
            assert row["query_text"] == query["text"] and row["query_type"] == "word"
            assert block == plan["query_block_size"]
            assert int(row["hit_count"]) == query["document_frequency"] == len(query["expected_ids"])
        grouped[row["dataset_id"], row["algorithm"], phase, row["query_id"]].append(row)
    assert len(grouped) == len(summary)
    seen_summary = set()
    for result in summary:
        key = result["dataset_id"], result["algorithm"], result["phase"], result["query_id"]
        assert key not in seen_summary
        seen_summary.add(key)
        group = grouped[key]
        assert sorted(int(row["repeat"]) for row in group) == list(range(count))
        assert result["sample_count"] == count
        assert result["token_count"] == datasets[key[0]]["token_count"]
        assert result["query_type"] == ("word" if key[2] == "query" else "")
        values = [float(row[f"{key[2]}_ms"]) for row in group]
        q1, _, q3 = quantiles(values, n=4, method="inclusive")
        assert result["median_ms"] == median(values)
        assert result["q1_ms"] == q1 and result["q3_ms"] == q3 and result["iqr_ms"] == q3 - q1
        assert result["minimum_ms"] == min(values) and result["maximum_ms"] == max(values)
    for identifier, ds in datasets.items():
        rng = random.Random(plan["seed"])
        tasks = [(alg, q["query_id"]) for alg in ("direct_word", "inverted_index") for q in ds["queries"]]
        for iteration in range(-plan["warmups"], count):
            order = list(tasks)
            rng.shuffle(order)
            if iteration < 0:
                continue
            observed = sorted((row for row in rows if row["dataset_id"] == identifier and row["phase"] == "query"
                               and int(row["repeat"]) == iteration), key=lambda row: int(row["order_index"]))
            assert [int(row["order_index"]) for row in observed] == list(range(6))
            assert [(row["algorithm"], row["query_id"]) for row in observed] == order
    assert tuple(memory["schema"]) == MEMORY_FIELDS
    assert len(memory_rows) == len(memory["rows"]) == len(datasets) * 3
    assert memory["measurement"] == metadata["memory"]
    assert [{field: str(row[field]) for field in MEMORY_FIELDS} for row in memory["rows"]] == memory_rows
    grouped_memory = defaultdict(list)
    for row in memory["rows"]:
        ds = datasets[row["dataset_id"]]
        assert row["run_id"] == metadata["run_id"]
        for field in ("document_count", "token_count", "vocabulary_size", "posting_count"):
            assert row[field] == ds[field]
        assert row["peak_traced_bytes"] >= row["retained_traced_bytes"] > 0
        assert row["exclusive_index_bytes"] > 0
        grouped_memory[row["dataset_id"]].append(row)
    assert len(memory["summary"]) == len(datasets)
    for result in memory["summary"]:
        group = grouped_memory[result["dataset_id"]]
        assert sorted(row["repeat"] for row in group) == [0, 1, 2]
        for field in ("retained_traced_bytes", "peak_traced_bytes", "exclusive_index_bytes"):
            assert result[f"median_{field}"] == median(row[field] for row in group)


def verify_corpora(metadata: dict) -> int:
    files_checked = 0
    with TemporaryDirectory(prefix="textsuche-02-verify-") as temporary:
        for ds in metadata["datasets"]:
            encoded = json.dumps(ds["files"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            assert hashlib.sha256(encoded).hexdigest() == ds["corpus_sha256"]
            if ds["kind"] == "generated":
                generated = generate_corpus(Path(temporary) / ds["dataset_id"], seed=metadata["parameters"]["seed"],
                                            **ds["generator_parameters"])
                tokens = generated.expected_tokens
                assert {f["document_id"]: f["sha256"] for f in ds["files"]} == generated.file_sha256
                assert ds["vocabulary_size"] == ds["generator_parameters"]["base_vocabulary"] + 2
                for f in ds["files"]:
                    assert (generated.root / f["source_path"]).stat().st_size == f["bytes"]
                for query in ds["queries"]:
                    assert tuple(query["expected_ids"]) == generated.expected_hits[query["query_id"]]
                    assert query["expected_occurrences"] == generated.expected_occurrences[query["query_id"]]
            else:
                fixture = ds["source_fixture"]
                manifest_path = ROOT / fixture["manifest_path"]
                assert sha(manifest_path) == fixture["manifest_sha256"]
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                assert sha(manifest_path.parent / manifest["source_file"]) == manifest["source_sha256"]
                for f in ds["files"]:
                    source = manifest_path.parent / f["source_path"]
                    assert sha(source) == f["sha256"] and source.stat().st_size == f["bytes"]
                prepared = prepare_corpus(load_corpus(manifest_path.parent))
                tokens = {doc.document_id: doc.tokens for doc in prepared}
                assert len(prepared) == 1 and len(prepared[0].tokens) == 1271
                assert prepared[0].tokens[:len(manifest["expected_prefix_tokens"])] == tuple(manifest["expected_prefix_tokens"])
                for query in ds["queries"]:
                    fixed = next(q for q in manifest["verified_queries"] if q["query"] == query["text"])
                    assert query["expected_ids"] == fixed["expected_document_ids"]
                    assert query["expected_occurrences"] == fixed["expected_occurrences"]
                    positions = [i for i, token in enumerate(prepared[0].tokens) if token == query["normalized_token_expected"]]
                    assert positions == fixed["expected_token_positions"]
            assert sum(map(len, tokens.values())) == ds["token_count"]
            assert len(tokens) == ds["document_count"]
            words = set().union(*(set(sequence) for sequence in tokens.values()))
            assert len(words) == ds["vocabulary_size"]
            assert sum(len(set(sequence)) for sequence in tokens.values()) == ds["posting_count"]
            lengths = list(map(len, tokens.values()))
            assert ds["document_lengths"] == {"minimum": min(lengths), "maximum": max(lengths), "total": sum(lengths),
                                               "distribution": {str(length): lengths.count(length) for length in sorted(set(lengths))}}
            for query in ds["queries"]:
                word = query["normalized_token_expected"]
                occurrence = sum(sequence.count(word) for sequence in tokens.values())
                hits = sorted(identifier for identifier, sequence in tokens.items() if word in sequence)
                visited = sum(sequence.index(word) + 1 if word in sequence else len(sequence) for sequence in tokens.values())
                assert query["observed_occurrences"] == query["expected_occurrences"] == occurrence
                assert query["expected_ids"] == hits and query["document_frequency"] == len(hits)
                assert query["direct_visited_tokens"] == visited
            files_checked += len(ds["files"])
    return files_checked


def verify_directory(directory: Path, *, check_active_code: bool = True) -> tuple[int, int]:
    def read_csv(name, schema):
        with (directory / name).open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            assert tuple(reader.fieldnames) == schema
            return list(reader)
    rows = read_csv("raw.csv", CSV_FIELDS)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    memory = json.loads((directory / "memory.json").read_text(encoding="utf-8"))
    verify_data(rows, summary, metadata, memory, read_csv("memory.csv", MEMORY_FIELDS))
    files = verify_corpora(metadata)
    for relative, expected in metadata["code_sha256"].items():
        assert sha(directory / "code_source" / relative) == expected, f"gemessener Quelltext beschädigt: {relative}"
        if check_active_code:
            if sha(ROOT / relative) == expected:
                continue
            # Thema 03 ergänzt ausschließlich Paket/Testpfade und einen exakt
            # begrenzten CLI-Dispatch. Gemessene Archive bleiben hashgeprüft;
            # alle übrigen aktiven Such-/Messquellen bleiben byteidentisch.
            verifier_path = ROOT / "themen/01_textaufbereitung_direkte_suche/experimente/verify_results.py"
            spec = importlib.util.spec_from_file_location("historical_integration_verifier", verifier_path)
            verifier = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(verifier)
            verifier.ROOT = ROOT
            if relative == "pyproject.toml":
                verifier.verify_packaging_extension(
                    expected, "doku/pruefberichte/artefakte_03/pyproject_vorstufe02.toml"
                )
            elif relative == "themen/01_textaufbereitung_direkte_suche/src/direkte_suche/__main__.py":
                verifier.verify_cli_boolean_extension(expected)
            else:
                raise AssertionError(f"aktiver Code weicht vom gemessenen Stand ab: {relative}")
    return len(rows), files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--archive-only", action="store_true", help="spätere Codeänderungen erlauben; gemessene Quelltext-Snapshots bleiben geprüft")
    args = parser.parse_args()
    directory = ROOT / "ergebnisse/messungen" / ("02_pilot" if args.pilot else "02_invertierter_index")
    rows, files = verify_directory(directory, check_active_code=not args.archive_only)
    print(f"{rows} Rohwerte, 42 Gruppen, 18 getrennte Speicherwerte, {files} Datei-Hashes, alle N/D/V/P und Suchfälle sowie Quelltext-Snapshots geprüft.")


if __name__ == "__main__":
    main()
