#!/usr/bin/env python3
"""Prüft gespeicherte Ergebnisse unabhängig; führt keine Zeitmessung aus.

Standard ist die gelieferte Reihe 01_direkte_suche; --eingabe NAME prüft einen
anderen Ordner unter ergebnisse/messungen, etwa 01b_pilot oder 01b_direkte_suche.
--archive-only lässt abweichende aktive Quellen zu, sofern ein gemessener
Quellstand archiviert ist; dieses Archiv bleibt hashgeprüft.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import ast
import csv
import hashlib
import json
from pathlib import Path
from statistics import median, quantiles
import subprocess
from tempfile import TemporaryDirectory
import tomllib

from gemeinsam.datengenerator import generate_corpus
from gemeinsam.messung import CSV_FIELDS


ROOT = Path(__file__).resolve().parents[3]
MESSUNGEN = ROOT / "ergebnisse/messungen"
RESULTS = MESSUNGEN / "01_direkte_suche"
RUN_SCRIPT = "themen/01_textaufbereitung_direkte_suche/experimente/run.py"
PLANS = {
    "final": {"warmups": 5, "repeats": 20, "query_block_size": 10, "seed": 20261006},
    "pilot": {"warmups": 1, "repeats": 3, "query_block_size": 10, "seed": 20261006},
}
GENERATED_IDS = {"generated_10000", "generated_100000", "generated_1000000"}
# Gelieferte Läufe und 01b_pilot: Kafka; Neumessung ab 01b_pilot2: BGB.
REAL_IDS = {"real_kafka_anfang", "real_bgb"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_packaging_extension(
    expected_hash: str,
    archive_relative: str = "doku/pruefberichte/artefakte_02/pyproject_vorstufe01.toml",
) -> None:
    """Prüft gemessene Konfiguration und ausschließlich additive Fachpakete.

    Thema 02 erweitert die installierten Pakete/Testpfade. Die ursprüngliche
    Datei ist byteidentisch archiviert; sonstige Einstellungen dürfen durch
    diese Ausnahme nicht abweichen. Such-/Messcode bleibt streng hashgeprüft.
    """
    archive = ROOT / archive_relative
    assert sha(archive) == expected_hash, "gemessene Paketkonfiguration fehlt oder weicht ab"
    previous = tomllib.loads(archive.read_text(encoding="utf-8"))
    current = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for configuration in (previous, current):
        packages = configuration["tool"]["setuptools"]["packages"]
        tests = configuration["tool"]["pytest"]["ini_options"]["testpaths"]
        mapping = configuration["tool"]["setuptools"]["package-dir"]
        assert isinstance(packages, list) and all(isinstance(value, str) for value in packages)
        assert isinstance(tests, list) and all(isinstance(value, str) for value in tests)
        assert isinstance(mapping, dict) and all(isinstance(key, str) and isinstance(value, str) for key, value in mapping.items())
    previous_packages = previous["tool"]["setuptools"]["packages"]
    assert len(current["tool"]["setuptools"]["packages"]) == len(set(current["tool"]["setuptools"]["packages"]))
    assert all(package in current["tool"]["setuptools"]["packages"] for package in previous_packages)
    current["tool"]["setuptools"]["packages"] = previous_packages
    previous_mapping = previous["tool"]["setuptools"]["package-dir"]
    current_mapping = current["tool"]["setuptools"]["package-dir"]
    assert all(current_mapping.get(key) == value for key, value in previous_mapping.items())
    current["tool"]["setuptools"]["package-dir"] = previous_mapping
    previous_tests = previous["tool"]["pytest"]["ini_options"]["testpaths"]
    assert all(path in current["tool"]["pytest"]["ini_options"]["testpaths"] for path in previous_tests)
    current["tool"]["pytest"]["ini_options"]["testpaths"] = previous_tests
    assert current == previous, "mehr als additive Fachpakete/Testpfade geändert"
    print("Historischer pyproject-SHA geprüft; vorhandene Pakete/Testpfade und alle übrigen Einstellungen unverändert, neue Fachpakete additiv.")


def verify_cli_boolean_extension(expected_hash: str) -> ast.Module:
    """Prüft exakt den additiven Boolean-Dispatch vor der vollständigen alten CLI.

    Der gemessene Thema-02-Quelltext bleibt byteidentisch archiviert. Nur die
    beiden vereinbarten If-Anweisungen dürfen ihm vorangestellt werden; nach
    deren Entfernung muss der gesamte AST einschließlich Indexzweig gleich sein.
    """
    archive = ROOT / "doku/pruefberichte/artefakte_03/cli_vorstufe02.py"
    assert sha(archive) == expected_hash, "gemessener Thema-02-CLI-Quelltext fehlt oder weicht ab"
    previous = ast.parse(archive.read_text(encoding="utf-8"))
    current = ast.parse((ROOT / "themen/01_textaufbereitung_direkte_suche/src/direkte_suche/__main__.py").read_text(encoding="utf-8"))
    expected_prefix = ast.parse(
        'if argv is None:\n'
        '    import sys\n'
        '    argv = sys.argv[1:]\n'
        'if "--boolean" in argv:\n'
        '    from boolesche_suche.__main__ import main as boolean_main\n'
        '    return boolean_main([argument for argument in argv if argument != "--boolean"])\n'
    ).body
    main = next(node for node in current.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    assert len(main.body) >= 2 and all(
        ast.dump(actual) == ast.dump(expected)
        for actual, expected in zip(main.body[:2], expected_prefix)
    ), "bestehende CLI-Semantik verändert: Boolean-Dispatch ist nicht die erlaubte Ergänzung"
    del main.body[:2]
    assert ast.dump(current) == ast.dump(previous), "bestehende CLI-Semantik verändert"
    return current


def verify_cli_extension(expected_hash: str) -> None:
    """Historische CLI-SHAs; ausschließlich Indexzweig und exakter Boolean-Hook."""
    archive = ROOT / "doku/pruefberichte/artefakte_02/cli_vorstufe01.py"
    assert sha(archive) == expected_hash, "gemessener CLI-Quelltext fehlt oder weicht ab"
    previous = ast.parse(archive.read_text(encoding="utf-8"))
    current = ast.parse((ROOT / "themen/01_textaufbereitung_direkte_suche/src/direkte_suche/__main__.py").read_text(encoding="utf-8"))
    main = next(node for node in current.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    if main.body and isinstance(main.body[0], ast.If):
        current = verify_cli_boolean_extension(
            "f735ab06b333e1c95e355c64c0694e83449e6475ce1598dd68a089a5da806826"
        )
    mode_options = 0
    index_branches = 0
    for node in ast.walk(current):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument" and node.args
                and isinstance(node.args[0], ast.Constant) and node.args[0].value == "--mode"):
            choices = next(keyword.value for keyword in node.keywords if keyword.arg == "choices")
            assert isinstance(choices, ast.Tuple)
            assert [value.value for value in choices.elts] == ["word", "substring", "index"]
            choices.elts.pop()
            mode_options += 1
        if isinstance(node, ast.If) and len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            branch = node.orelse[0]
            expected_test = ast.parse('args.mode == "index"', mode="eval").body
            if ast.dump(branch.test) == ast.dump(expected_test):
                node.orelse = branch.orelse
                index_branches += 1
    assert mode_options == index_branches == 1
    assert ast.dump(current) == ast.dump(previous), "bestehende CLI-Semantik verändert"
    print("Historischer CLI-SHA und alte Word-/Substring-Zweige geprüft; ergänzter Indexmodus wird durch aktuelle Integrationstests validiert.")


def run_kind(metadata: dict) -> str:
    """Neue Läufe nennen ihre Art; gelieferte Läufe heißen 01_final bzw. 01_pilot."""
    kind = metadata.get("run_kind") or {"01_final": "final", "01_pilot": "pilot"}[metadata["run_id"]]
    assert kind in PLANS, f"unbekannte Laufart: {kind}"
    return kind


def verify_data(rows: list[dict], summary: list[dict], metadata: dict) -> tuple[int, int]:
    """Schema, Einheiten, Leerfelder, Treffer und Statistik aus Rohwerten."""
    plan = PLANS[run_kind(metadata)]
    assert metadata["measurement_plan"] == plan, "falscher gesperrter Messplan"
    repeats = plan["repeats"]
    by_dataset = {dataset["dataset_id"]: dataset for dataset in metadata["datasets"]}
    real = set(by_dataset) - GENERATED_IDS
    assert set(by_dataset) >= GENERATED_IDS and len(real) == 1 and real <= REAL_IDS
    # Je Datensatz Laden, Aufbereitung und eine Gruppe je Anfrage (Kafka 3, BGB 4).
    group_count = sum(2 + len(dataset["queries"]) for dataset in by_dataset.values())
    assert len(rows) == group_count * repeats and len(summary) == group_count
    groups = defaultdict(list)
    for row in rows:
        dataset = by_dataset[row["dataset_id"]]
        groups[row["dataset_id"], row["phase"], row["query_id"]].append(row)
        assert row["correct"] == "True"
        assert row["build_ms"] == row["index_bytes"] == row["peak_memory_bytes"] == ""
        assert int(row["document_count"]) == dataset["document_count"]
        assert int(row["token_count"]) == dataset["token_count"]
        assert int(row["text_bytes"]) == dataset["text_bytes"]
        assert row["git_commit"] == metadata["git_commit"] and row["run_id"] == metadata["run_id"]
        assert int(row["seed"]) == 20261006
        assert int(row["elapsed_ns"]) >= 0
        phase = row["phase"]
        assert phase in {"load", "preparation", "query"}
        assert float(row[f"{phase}_ms"]) == int(row["elapsed_ns"]) / 1_000_000 / int(row["block_size"])
        assert all(row[f"{other}_ms"] == "" for other in {"load", "preparation", "query"} - {phase})
        if phase == "query":
            expected = next(query for query in dataset["queries"] if query["query_id"] == row["query_id"])
            assert row["query_type"] == "word" and int(row["block_size"]) == 10
            assert row["query_text"] == expected["text"]
            assert int(row["hit_count"]) == len(expected["expected_ids"])
            assert int(row["order_index"]) in range(len(dataset["queries"]))
        else:
            assert int(row["block_size"]) == 1
            assert row["query_id"] == row["query_type"] == row["query_text"] == row["hit_count"] == ""
    for result in summary:
        group = groups[result["dataset_id"], result["phase"], result["query_id"]]
        assert sorted(int(row["repeat"]) for row in group) == list(range(repeats))
        values = [float(row[f"{row['phase']}_ms"]) for row in group]
        q1, _, q3 = quantiles(values, n=4, method="inclusive")
        assert result["sample_count"] == repeats
        assert result["median_ms"] == median(values)
        assert result["q1_ms"] == q1 and result["q3_ms"] == q3 and result["iqr_ms"] == q3 - q1
        assert result["minimum_ms"] == min(values) and result["maximum_ms"] == max(values)
        if result["phase"] == "query":
            assert result["query_type"] == "word"
    assert len(groups) == group_count
    for dataset_id, dataset in by_dataset.items():
        for repeat in range(repeats):
            query_rows = [row for row in rows if row["dataset_id"] == dataset_id and row["phase"] == "query" and int(row["repeat"]) == repeat]
            assert sorted(int(row["order_index"]) for row in query_rows) == list(range(len(dataset["queries"])))
    return len(rows), len(summary)


def verify_corpora(metadata: dict) -> int:
    """Rekonstruiert generierte Korpora byteidentisch und prüft den Realtext."""
    files_checked = 0
    with TemporaryDirectory(prefix="textsuche-verify-") as temporary:
        for dataset in metadata["datasets"]:
            canonical = json.dumps(dataset["files"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            assert hashlib.sha256(canonical).hexdigest() == dataset["corpus_sha256"]
            if dataset["kind"] == "generated":
                assert dataset["document_count"] == 20
                generated = generate_corpus(Path(temporary) / dataset["dataset_id"], dataset["token_count"], seed=20261006)
                assert {entry["document_id"]: entry["sha256"] for entry in dataset["files"]} == generated.file_sha256
                for query in dataset["queries"]:
                    assert tuple(query["expected_ids"]) == generated.expected_hits[query["query_id"]]
                    assert query["expected_occurrences"] == query["observed_occurrences"] == generated.expected_occurrences[query["query_id"]]
            elif dataset["dataset_id"] == "real_bgb":
                verify_bgb(dataset)
            else:
                manifest_path = ROOT / dataset["source_fixture"]["manifest_path"]
                assert sha(manifest_path) == dataset["source_fixture"]["manifest_sha256"]
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                assert dataset["token_count"] == 1271 and dataset["document_count"] == 1
                for entry in dataset["files"]:
                    assert sha(manifest_path.parent / entry["source_path"]) == entry["sha256"]
                    assert (manifest_path.parent / entry["source_path"]).stat().st_size == entry["bytes"]
                for query in dataset["queries"]:
                    fixed = next(entry for entry in manifest["verified_queries"] if entry["query"] == query["text"])
                    assert list(query["expected_ids"]) == fixed["expected_document_ids"]
                    assert query["expected_occurrences"] == query["observed_occurrences"] == fixed["expected_occurrences"]
            files_checked += len(dataset["files"])
    return files_checked


def _check_ids(identifiers: list[str], entry: dict) -> None:
    if "document_ids" in entry:
        assert identifiers == entry["document_ids"], f"{entry['query']}: Dokumentliste"
    else:
        assert len(identifiers) == entry["document_ids_count"]
        assert hashlib.sha256("\n".join(identifiers).encode("utf-8")).hexdigest() == entry["document_ids_sha256"]
        assert identifiers[:5] == entry["document_ids_first5"] and identifiers[-5:] == entry["document_ids_last5"]
    assert len(identifiers) == entry["df"]


def verify_bgb(dataset: dict) -> None:
    """BGB-Realteil gegen Manifest, Anfragevorschläge und die Dateien selbst."""
    fixture = dataset["source_fixture"]
    manifest_path, proposals_path = ROOT / fixture["manifest_path"], ROOT / fixture["proposals_path"]
    assert sha(manifest_path) == fixture["manifest_sha256"], "BGB-Manifest geändert"
    assert sha(proposals_path) == fixture["proposals_sha256"], "BGB-Anfragevorschläge geändert"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    proposals = json.loads(proposals_path.read_text(encoding="utf-8"))
    expectations = manifest["independent_expectations"]
    assert manifest["corpus_sha256"] == proposals["corpus_sha256"] == fixture["corpus_sha256"]
    by_manifest = {entry["document_id"]: entry for entry in manifest["documents"]}
    assert [entry["document_id"] for entry in dataset["files"]] == sorted(by_manifest)
    root = ROOT / fixture["corpus_root"]
    for entry in dataset["files"]:
        stored = by_manifest[entry["document_id"]]
        assert entry["sha256"] == stored["sha256"] and entry["bytes"] == stored["bytes"]
        assert sha(root / entry["source_path"]) == entry["sha256"] and (root / entry["source_path"]).stat().st_size == entry["bytes"]
    lines = "".join(f"{entry['sha256']}  {entry['document_id']}\n" for entry in dataset["files"])
    assert hashlib.sha256(lines.encode("utf-8")).hexdigest() == dataset["bgb_corpus_sha256"] == fixture["corpus_sha256"]
    assert dataset["document_count"] == expectations["document_count"] == len(dataset["files"])
    assert dataset["token_count"] == expectations["token_count"]
    assert sum(entry["bytes"] for entry in dataset["files"]) == dataset["text_bytes"] == manifest["counts"]["raw_bytes"]
    assert fixture["first_tokens"] == expectations["prefix_tokens_bgb_0001"]
    proposals_01 = {entry["query"]: entry for entry in proposals["reihe_01_direkte_suche"]}
    for query in dataset["queries"]:
        entry = proposals_01[query["text"]]
        assert fixture["queries"][query["query_id"]] == entry
        _check_ids(list(query["expected_ids"]), entry)
        assert query["normalized_token_expected"] == entry["term"]
        assert query["expected_occurrences"] == query["observed_occurrences"] == entry["cf"]
        assert query["direct_visited_tokens"] == entry["scanned_tokens_direct"]
        assert query["document_frequency"] == entry["df"]
        if entry["df"]:
            assert query["first_document"] == entry["first_document"] and query["first_position"] == entry["first_position"]


def verify_code(directory: Path, metadata: dict, *, archive_only: bool = False) -> list[str]:
    """Prüft gemessene Quellen; liefert Hinweise auf den verwendeten Prüfmodus.

    Neue Läufe archivieren jede gehashte Quelle unter code_source/. Gelieferte
    Läufe archivieren nur das gemessene run.py (run_source_measured.py); ihre
    übrigen Quellen werden ohne Archiv weiterhin gegen den aktiven Stand geprüft.
    """
    notes = []
    if (directory / "code_source").is_dir():
        assert metadata["source_archive"] == "code_source/"
        changed = []
        for relative, expected in metadata["code_sha256"].items():
            assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
            assert sha(directory / "code_source" / relative) == expected, f"Quelltextarchiv beschädigt: {relative}"
            if sha(ROOT / relative) != expected:
                changed.append(relative)
        if changed and not archive_only:
            raise AssertionError(f"aktiver Code weicht vom gemessenen Stand ab: {', '.join(changed)}")
        notes.append(f"{len(metadata['code_sha256'])} archivierte Quell-SHA-256 geprüft.")
        if changed:
            notes.append(f"Nur-Archiv-Modus: {len(changed)} aktive Quellen weichen ab ({', '.join(changed)}).")
        return notes
    correction = metadata.get("recording_correction")
    for relative, expected in metadata["code_sha256"].items():
        if relative == RUN_SCRIPT and correction:
            assert sha(ROOT / correction["measured_run_source_archive"]) == expected == correction["run_script_sha256_measured"]
            assert correction["timing_values_and_results_unchanged"] is True
            if sha(ROOT / relative) != correction["run_script_sha256_after_recording_correction"]:
                if not archive_only:
                    raise AssertionError(
                        "aktives run.py weicht vom Stand nach der Aufzeichnungskorrektur ab; "
                        "gelieferte Ergebnisse mit --archive-only prüfen"
                    )
                notes.append("Nur-Archiv-Modus: aktives run.py weicht ab; gemessenes run_source_measured.py bleibt hashgeprüft.")
        elif relative == "pyproject.toml" and sha(ROOT / relative) != expected:
            verify_packaging_extension(expected)
        elif relative == "themen/01_textaufbereitung_direkte_suche/src/direkte_suche/__main__.py" and sha(ROOT / relative) != expected:
            verify_cli_extension(expected)
        else:
            assert sha(ROOT / relative) == expected, f"Codezustand weicht ab: {relative}"
    notes.append(f"{len(metadata['code_sha256'])} Code-SHA-256 geprüft, einschließlich Root-Importadapter und archiviertem gemessenen Skript.")
    return notes


def verify_auxiliary(directory: Path, metadata: dict) -> None:
    """Regelvergleich, Hashseed-Angabe und Pilotsperre neuer Läufe."""
    comparison = json.loads((directory / "rule_comparison.json").read_text(encoding="utf-8"))
    assert comparison["correct"] is True and comparison["runtime_claim"].startswith("none")
    if "run_kind" not in metadata:
        return
    environment = metadata["environment"]
    assert isinstance(environment["python_hash_seed"], str) and isinstance(environment["python_hash_seed_set"], bool)
    if environment["python_hash_seed"] != "random":
        assert environment["python_hash_seed_set"] is True, "Hashseed-Angabe widersprüchlich"
    assert metadata["run_id"] == directory.name
    if metadata["run_kind"] == "pilot":
        decision = json.loads((directory / "pilot_decision.json").read_text(encoding="utf-8"))
        assert decision["pilot_correct"] is True and decision["pilot_is_not_final_measurement"] is True
        assert decision["locked_parameters"] == metadata["parameters"]
        assert decision["method_code_sha256"] == metadata["code_sha256"]
        assert decision["python_hash_seed"] == environment["python_hash_seed"]
        assert decision["pilot_plan"] == PLANS["pilot"]
    else:
        pilot = MESSUNGEN / Path(metadata["pilot_directory"]).name
        decision = json.loads((pilot / "pilot_decision.json").read_text(encoding="utf-8"))
        assert decision["locked_parameters"] == metadata["parameters"], "Hauptlauf passt nicht zum Pilot"
        assert decision["method_code_sha256"] == metadata["code_sha256"], "Hauptlauf mit anderem Code als Pilot"
        assert decision["python_hash_seed"] == environment["python_hash_seed"], "Hauptlauf mit anderem Hashseed als Pilot"
        for extension in ("svg", "png"):
            for name in ("01_direkte_suche_skala", "01_laden_aufbereitung"):
                assert (directory / "abbildungen" / f"{name}.{extension}").is_file(), f"Abbildung fehlt: {name}.{extension}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--eingabe", metavar="NAME", default=RESULTS.name,
                        help="Ordner unter ergebnisse/messungen (Standard 01_direkte_suche)")
    parser.add_argument("--archive-only", action="store_true",
                        help="abweichende aktive Quellen zulassen; archivierte gemessene Quellen bleiben geprüft")
    args = parser.parse_args(argv)
    if Path(args.eingabe).name != args.eingabe:
        raise SystemExit("--eingabe erwartet genau einen Ordnernamen unter ergebnisse/messungen")
    directory = MESSUNGEN / args.eingabe
    with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames) == CSV_FIELDS, "abweichendes CSV-Schema"
        rows = list(reader)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    row_count, group_count = verify_data(rows, summary, metadata)
    repeats = metadata["measurement_plan"]["repeats"]
    print(f"{directory.name}: {row_count} Rohwerte und {group_count} Gruppen mit je {repeats} Werten: Schema, Einheiten, Leerfelder, Treffer und Median/Q1/Q3/IQR korrekt.")
    files_checked = verify_corpora(metadata)
    print(f"Vier Korpusmanifeste und {files_checked} Datei-SHA-256 geprüft; alle generierten Größen byteidentisch rekonstruiert; Realteil {sorted(set(d['dataset_id'] for d in metadata['datasets']) - GENERATED_IDS)[0]}.")
    for note in verify_code(directory, metadata, archive_only=args.archive_only):
        print(note)
    verify_auxiliary(directory, metadata)
    print(f"Mess-Commit: {metadata['git_commit']}; Messung dirty={metadata['git_dirty']}.")
    if "run_kind" in metadata:
        print(f"PYTHONHASHSEED={metadata['environment']['python_hash_seed']} (gesetzt: {metadata['environment']['python_hash_seed_set']}); Hintergrundlast: {metadata['background_load']}")
    print("Grenzen: warmer Dateicache, Desktop-Hintergrundlast, Block-Schleifenaufwand enthalten; keine Speicher- oder Kaltstartmessung.")


if __name__ == "__main__":
    main()
