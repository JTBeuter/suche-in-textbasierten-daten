#!/usr/bin/env python3
"""Skalierungsversuch: aus der Repositorywurzel nach `pip install -e .`."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory
import unicodedata

from gemeinsam import load_corpus, prepare_corpus, tokenize
from gemeinsam.datengenerator import GeneratedCorpus, generate_corpus
from gemeinsam.messung import (
    MeasurementPlan,
    QuerySpec,
    measure_phase,
    measure_queries,
    summarize_measurements,
    write_measurements,
)
from direkte_suche import search_direct_word


REPOSITORY = Path(__file__).resolve().parents[3]
PARAMETERS = {
    "total_tokens": [10_000, 100_000, 1_000_000],
    "document_count": 20,
    "seed": 20261006,
    "vocabulary": "wort0000..wort0999",
    "frequent": "Fehler at position 0 and each position divisible by 100 in every document",
    "rare": "Verbindung at the last position of doc00.txt only",
    "missing": "Unauffindbar never planted or sampled",
    "measurement_plan": asdict(MeasurementPlan()),
}


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments], cwd=REPOSITORY, text=True,
    ).strip()


def _metadata(plan: MeasurementPlan, pilot: bool) -> dict:
    code_paths = sorted({
        *REPOSITORY.glob("gemeinsam/src/gemeinsam/*.py"),
        *REPOSITORY.glob("themen/01_textaufbereitung_direkte_suche/src/direkte_suche/*.py"),
        Path(__file__).resolve(), REPOSITORY / "pyproject.toml", REPOSITORY / "requirements-dev.txt",
    })
    code_hashes = {
        path.relative_to(REPOSITORY).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in code_paths if path.is_file()
    }
    cpu_model = platform.processor()
    cpu_info = Path("/proc/cpuinfo")
    if cpu_info.exists():
        for line in cpu_info.read_text().splitlines():
            if line.startswith("model name"):
                cpu_model = line.partition(":")[2].strip()
                break
    memory_info = Path("/proc/meminfo")
    total_memory = next(
        (line for line in memory_info.read_text().splitlines() if line.startswith("MemTotal:")),
        "unknown",
    ) if memory_info.exists() else "unknown"
    return {
        "run_id": "01_pilot" if pilot else "01_final",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "git_status_at_start": _git("status", "--porcelain"),
        "code_sha256": code_hashes,
        "environment": {
            "python": sys.version, "implementation": platform.python_implementation(),
            "platform": platform.platform(), "machine": platform.machine(),
            "cpu_model": cpu_model, "memory_total": total_memory,
            "matplotlib": version("matplotlib"), "pytest": version("pytest"),
            "unicode_database": unicodedata.unidata_version,
        },
        "parameters": PARAMETERS,
        "measurement_plan": asdict(plan),
        "timer": "time.perf_counter_ns; elapsed_ns retains integer block duration",
        "cache": "warm: corpus initially read and verified; repeated loading with 5 warmups in final; OS cache not cleared",
        "timing_boundaries": {
            "load": "complete load_corpus including traversal, sorting, byte read and UTF-8 decode; block_size=1",
            "preparation": "complete prepare_corpus including validation, document sorting, normalization and tokenization; block_size=1",
            "build": "not applicable for direct search; CSV blank",
            "query": "public search_direct_word on prepared corpus; query normalization, sequential token comparisons, complete sorted unique result included",
            "blocks": "query blocks retain 10 full result lists; block loop and list allocation overhead included identically per query",
            "excluded": "expectation checks, counting, metadata, plotting, disk output and printing outside intervals",
        },
        "statistics": "median and inclusive quartiles via statistics.quantiles(n=4, method='inclusive'); IQR=q3-q1",
        "memory": "not measured; index_bytes and peak_memory_bytes CSV fields blank",
        "dataset_order": "generated 10000,100000,1000000 then real; query order shuffled deterministically for each warmup and measured repetition",
        "datasets": [],
    }


def _check_tokens(prepared, expected: dict[str, tuple[str, ...]]) -> None:
    observed = {document.document_id: document.tokens for document in prepared}
    if observed != expected:
        raise AssertionError("Tokenfolgen oder Dokumentkennungen weichen von der unabhängigen Erwartung ab")


def _dataset_measurements(
    root: Path,
    dataset_id: str,
    queries: list[QuerySpec],
    plan: MeasurementPlan,
    metadata: dict,
    generated: GeneratedCorpus | None = None,
    real_fixture: dict | None = None,
) -> list[dict]:
    raw = load_corpus(root)
    prepared = prepare_corpus(raw)
    if generated is not None:
        _check_tokens(prepared, generated.expected_tokens)
    if real_fixture is not None:
        expected_prefix = tuple(real_fixture["first_tokens"])
        if tuple(prepared[0].tokens[:len(expected_prefix)]) != expected_prefix:
            raise AssertionError("Realer Korpus: erwarteter handgeprüfter Tokenanfang stimmt nicht")
        if sum(len(document.tokens) for document in prepared) != real_fixture["token_count"]:
            raise AssertionError("Realer Korpus: Tokenanzahl weicht vom gesicherten Fixture ab")
    token_count = sum(len(document.tokens) for document in prepared)
    text_bytes = sum(len(document.raw_text.encode("utf-8")) for document in raw)
    files = [
        {"document_id": document.document_id, "source_path": document.source_path,
         "bytes": len(document.raw_text.encode("utf-8")),
         "sha256": hashlib.sha256(document.raw_text.encode("utf-8")).hexdigest()}
        for document in raw
    ]
    if generated is not None:
        if token_count != generated.total_tokens:
            raise AssertionError("Generierter Korpus hat eine abweichende Tokenzahl")
        if {entry["document_id"]: entry["sha256"] for entry in files} != generated.file_sha256:
            raise AssertionError("Generierter Korpus: geladene Bytes stimmen nicht mit dem Generator überein")
    if real_fixture is not None:
        if len(files) != 1 or files[0]["sha256"] != real_fixture["sha256"]:
            raise AssertionError("Realer Korpus: Prüfsumme weicht vom Fixture ab")
    query_metadata = []
    for query in queries:
        # Feste Anfrage-Tokens vermeiden zirkuläre Häufigkeitsprüfungen.
        word = {"Fehler": "fehler", "Verbindung": "verbindung", "Unauffindbar": "unauffindbar",
                "Gregor": "gregor", "Fenster": "fenster"}[query.text]
        expected_count = (generated.expected_occurrences[query.query_id] if generated else
                          real_fixture["queries"][query.query_id]["occurrences"])
        observed_count = sum(document.tokens.count(word) for document in prepared)
        if observed_count != expected_count:
            raise AssertionError(f"{dataset_id}/{query.query_id}: Häufigkeit weicht vom Pflanzplan/Fixture ab")
        if real_fixture is not None:
            positions = [position for position, token in enumerate(prepared[0].tokens) if token == word]
            if positions != real_fixture["queries"][query.query_id]["positions"]:
                raise AssertionError(f"{dataset_id}/{query.query_id}: Positionen weichen vom unabhängigen Fixture ab")
        if search_direct_word(prepared, query.text) != list(query.expected_ids):
            raise AssertionError(f"{dataset_id}/{query.query_id}: Treffer weichen von der festen Erwartung ab")
        query_metadata.append({
            **asdict(query), "normalized_token_expected": word,
            "expected_occurrences": expected_count, "observed_occurrences": observed_count,
            "observed_document_hits": len(query.expected_ids),
        })
    metadata["datasets"].append({
        "dataset_id": dataset_id, "kind": "generated" if generated else "real",
        "document_count": len(raw), "text_bytes": text_bytes, "token_count": token_count,
        "files": files, "queries": query_metadata,
        "corpus_sha256": hashlib.sha256(
            json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "source_fixture": real_fixture if real_fixture else None,
    })
    context = {
        "run_id": metadata["run_id"], "git_commit": metadata["git_commit"],
        "seed": plan.seed, "dataset_id": dataset_id, "document_count": len(raw),
        "text_bytes": text_bytes, "token_count": token_count, "algorithm": "direct_word",
    }

    def validate_raw(observed) -> None:
        if observed != raw:
            raise AssertionError("Laden verändert Dokumente, Reihenfolge oder Quelldaten")

    def validate_prepared(observed) -> None:
        if observed != prepared:
            raise AssertionError("Aufbereitung verändert die gesicherten Tokenfolgen")

    print(f"{dataset_id}: {len(raw)} Dokumente, {token_count} Tokens; Laden", flush=True)
    rows = measure_phase(lambda: load_corpus(root), validate_raw, plan, phase="load", context=context)
    print(f"{dataset_id}: Aufbereitung", flush=True)
    rows.extend(measure_phase(
        lambda: prepare_corpus(raw), validate_prepared, plan, phase="preparation", context=context,
    ))
    print(f"{dataset_id}: drei Suchfälle", flush=True)
    rows.extend(measure_queries(lambda text: search_direct_word(prepared, text), queries, plan, context=context))
    return rows


def _tokenize_rule(text: str, case_rule: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFC", text)
    normalized = unicodedata.normalize("NFC", getattr(normalized, case_rule)())
    tokens = []
    current = []
    for character in normalized:
        category = unicodedata.category(character)
        if category.startswith("L") or category == "Nd":
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current.clear()
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


def rule_comparison() -> dict:
    """Genau eine Änderung: casefold() wird durch lower() ersetzt."""
    texts = {
        "r0.txt": "Straße STRASSE", "r1.txt": "Straße", "r2.txt": "STRASSE",
        "r3.txt": "Cafe\u0301 Übermaß 2026 x\u0301y",
    }
    expected = {
        "casefold": {"r0.txt": ("strasse", "strasse"), "r1.txt": ("strasse",),
                     "r2.txt": ("strasse",), "r3.txt": ("café", "übermass", "2026", "x", "y")},
        "lower": {"r0.txt": ("straße", "strasse"), "r1.txt": ("straße",),
                  "r2.txt": ("strasse",), "r3.txt": ("café", "übermaß", "2026", "x", "y")},
    }
    expected_hits = {
        "casefold": {"Straße": ["r0.txt", "r1.txt", "r2.txt"], "STRASSE": ["r0.txt", "r1.txt", "r2.txt"]},
        "lower": {"Straße": ["r0.txt", "r1.txt"], "STRASSE": ["r0.txt", "r2.txt"]},
    }
    outcomes = {}
    for case_rule in ("casefold", "lower"):
        prepared = {key: _tokenize_rule(text, case_rule) for key, text in texts.items()}
        if prepared != expected[case_rule]:
            raise AssertionError("Regelvergleich weicht von fest vorgegebenen Tokenfolgen ab")
        if case_rule == "casefold" and prepared != {key: tokenize(text) for key, text in texts.items()}:
            raise AssertionError("Regelvergleich bildet die zentrale Hauptregel nicht korrekt ab")
        hits = {}
        for query in ("Straße", "STRASSE"):
            (word,) = _tokenize_rule(query, case_rule)
            hits[query] = sorted(key for key, tokens in prepared.items() if word in tokens)
        if hits != expected_hits[case_rule]:
            raise AssertionError("Regelvergleich weicht von fest vorgegebenen Dokumenttreffern ab")
        outcomes[case_rule] = {"tokens": prepared, "hits": hits, "expected_hits": expected_hits[case_rule]}
    return {
        "changed_rule_only": "casefold() versus lower(), applied identically to documents and queries",
        "unchanged": "NFC before and after case conversion; token characters Unicode L* and Nd; remaining combining marks separate tokens",
        "texts": texts, "variants": outcomes, "correct": True,
        "runtime_claim": "none; only token sequences and document hits compared",
    }


def _plots(summary: list[dict], output: Path, metadata: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams["svg.hashsalt"] = "textsuche-thema01"
    generated = {dataset["dataset_id"] for dataset in metadata["datasets"] if dataset["kind"] == "generated"}
    labels = {"missing": "Fehlend: Unauffindbar", "rare": "Selten: Verbindung", "frequent": "Früher Treffer: Fehler"}
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for query_id, label in labels.items():
        values = sorted((row for row in summary if row["dataset_id"] in generated and row["phase"] == "query" and
                         row["query_id"] == query_id), key=lambda row: row["token_count"])
        x = [row["token_count"] for row in values]
        y = [row["median_ms"] for row in values]
        ax.plot(x, y, marker="o", label=label)
        ax.fill_between(x, [row["q1_ms"] for row in values], [row["q3_ms"] for row in values], alpha=0.18)
    ax.set(xscale="log", yscale="log", xlabel="Gesamtzahl Tokens N (20 Dokumente)",
           ylabel="Zeit je Wortanfrage (ms, logarithmisch)", title="Direkte Suche: Median und Quartilsbereich")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    output.mkdir(parents=True, exist_ok=True)
    for extension in ("svg", "png"):
        fig.savefig(output / f"01_direkte_suche_skala.{extension}", dpi=180,
                    metadata={"Date": None} if extension == "svg" else {})
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for phase, label in (("load", "Einlesen (warmer Dateicache)"), ("preparation", "Aufbereitung")):
        values = sorted((row for row in summary if row["dataset_id"] in generated and row["phase"] == phase),
                        key=lambda row: row["token_count"])
        ax.plot([row["token_count"] for row in values], [row["median_ms"] for row in values], marker="o", label=label)
        ax.fill_between([row["token_count"] for row in values], [row["q1_ms"] for row in values],
                        [row["q3_ms"] for row in values], alpha=0.18)
    ax.set(xscale="log", yscale="log", xlabel="Gesamtzahl Tokens N (20 Dokumente)",
           ylabel="Zeit je vollständigem Schritt (ms)", title="Vorbereitung: Median und Quartilsbereich")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    for extension in ("svg", "png"):
        fig.savefig(output / f"01_laden_aufbereitung.{extension}", dpi=180,
                    metadata={"Date": None} if extension == "svg" else {})
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true", help="1 Aufwärmlauf, 3 Messungen; keine finalen Abbildungen")
    args = parser.parse_args()
    output = REPOSITORY / "ergebnisse/messungen" / ("01_pilot" if args.pilot else "01_direkte_suche")
    plan = MeasurementPlan(warmups=1, repeats=3) if args.pilot else MeasurementPlan()
    if not args.pilot:
        pilot_path = REPOSITORY / "ergebnisse/messungen/01_pilot/pilot_decision.json"
        if not pilot_path.exists():
            raise SystemExit("Zuerst --pilot ausführen: Parameter werden erst nach erfolgreichem Pilotlauf gesperrt.")
        if json.loads(pilot_path.read_text())["locked_parameters"] != PARAMETERS:
            raise SystemExit("Parameter unterscheiden sich vom erfolgreichen Pilotlauf; Pilot erneut ausführen.")
    metadata = _metadata(plan, args.pilot)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    with TemporaryDirectory(prefix="textsuche-01-") as temporary:
        for total in PARAMETERS["total_tokens"]:
            generated = generate_corpus(Path(temporary) / f"n{total}", total)
            queries = [QuerySpec(query_id, text, query_type, generated.expected_hits[query_id])
                       for query_id, text, query_type in (("frequent", "Fehler", "frequent"),
                                                         ("rare", "Verbindung", "rare"),
                                                         ("missing", "Unauffindbar", "missing"))]
            rows.extend(_dataset_measurements(generated.root, f"generated_{total}", queries, plan, metadata,
                                              generated=generated))
            write_measurements(output / "raw.csv", rows)
            _write_json(output / "metadata.json", metadata)
        real_root = REPOSITORY / "daten/real/kafka_verwandlung"
        real_fixture_path = real_root / "manifest.json"
        if not real_fixture_path.exists():
            raise SystemExit(f"Realer Pflichtkorpus samt unabhängig geprüften Erwartungen fehlt: {real_fixture_path}")
        source_manifest = json.loads(real_fixture_path.read_text(encoding="utf-8"))
        fixture = {
            "manifest_path": real_fixture_path.relative_to(REPOSITORY).as_posix(),
            "manifest_sha256": hashlib.sha256(real_fixture_path.read_bytes()).hexdigest(),
            "sha256": source_manifest["documents"][0]["sha256"],
            "token_count": 1271,
            "first_tokens": source_manifest["expected_prefix_tokens"],
            "queries": {
                {"Gregor": "frequent", "Fenster": "rare", "Unauffindbar": "missing"}[entry["query"]]: {
                    "text": entry["query"],
                    "query_type": {"Gregor": "frequent", "Fenster": "rare", "Unauffindbar": "missing"}[entry["query"]],
                    "expected_ids": entry["expected_document_ids"],
                    "occurrences": entry["expected_occurrences"],
                    "positions": entry["expected_token_positions"],
                }
                for entry in source_manifest["verified_queries"]
            },
        }
        queries = [QuerySpec(key, value["text"], value["query_type"], tuple(value["expected_ids"]))
                   for key, value in fixture["queries"].items()]
        rows.extend(_dataset_measurements(real_root, "real_kafka_anfang", queries, plan, metadata, real_fixture=fixture))
    metadata["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    summary = summarize_measurements(rows)
    write_measurements(output / "raw.csv", rows)
    _write_json(output / "summary.json", summary)
    _write_json(output / "metadata.json", metadata)
    _write_json(output / "rule_comparison.json", rule_comparison())
    if args.pilot:
        _write_json(output / "pilot_decision.json", {
            "pilot_correct": True,
            "decision": "alle Größen und Trefferprüfungen ausführbar; vorab geplante Parameter unverändert für final gesperrt",
            "locked_parameters": PARAMETERS,
            "pilot_plan": asdict(plan),
            "pilot_is_not_final_measurement": True,
        })
    else:
        _plots(summary, REPOSITORY / "ergebnisse/abbildungen", metadata)
    print(f"Gespeichert: {output.relative_to(REPOSITORY)}; {len(rows)} Rohwerte, {len(summary)} Gruppen", flush=True)


if __name__ == "__main__":
    main()
