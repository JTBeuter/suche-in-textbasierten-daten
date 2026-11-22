#!/usr/bin/env python3
"""Thema 02: Pilot, gesperrter Zeitlauf und separater Speicherprozess."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import random
from statistics import median
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns
import unicodedata

from gemeinsam import load_corpus, prepare_corpus
from gemeinsam.messung import (MeasurementPlan, QuerySpec, measure_phase,
                              summarize_measurements, write_measurements)
from direkte_suche import search_direct_word
from invertierter_index import build_inverted_index, search_index_word

from generator import generate_corpus
from memory import profile_index


ROOT = Path(__file__).resolve().parents[3]
PARAMETERS = {
    "seed": 20261006,
    "datasets": [
        {"dataset_id": "n10000", "total_tokens": 10_000, "document_count": 10, "base_vocabulary": 1000, "series": ["N"]},
        {"dataset_id": "n100000", "total_tokens": 100_000, "document_count": 100, "base_vocabulary": 1000, "series": ["N", "V"]},
        {"dataset_id": "n1000000", "total_tokens": 1_000_000, "document_count": 1000, "base_vocabulary": 1000, "series": ["N"]},
        {"dataset_id": "v100", "total_tokens": 100_000, "document_count": 100, "base_vocabulary": 100, "series": ["V"]},
        {"dataset_id": "v10000", "total_tokens": 100_000, "document_count": 100, "base_vocabulary": 10_000, "series": ["V"]},
    ],
    "real_dataset_id": "real_kafka_anfang", "real_token_count": 1271,
    "generator": "fixed equal lengths; guaranteed base vocabulary; seeded randrange and sample placement",
    "frequent": "Fehler at position 0 and every hundredth token in each document",
    "rare": "Verbindung at final token of first document only", "missing": "Unauffindbar absent",
    "final_plan": asdict(MeasurementPlan()), "memory_repeats": 3,
    "schedule": "all six (algorithm,query) complete blocks shuffled once per warmup/repetition with fixed seed",
}
MEMORY_FIELDS = ("run_id", "dataset_id", "document_count", "token_count", "vocabulary_size",
                 "posting_count", "repeat", "retained_traced_bytes", "peak_traced_bytes", "exclusive_index_bytes")


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_paths() -> list[Path]:
    return sorted({*ROOT.glob("gemeinsam/src/gemeinsam/*.py"),
                   *ROOT.glob("themen/01_textaufbereitung_direkte_suche/src/direkte_suche/*.py"),
                   *ROOT.glob("themen/02_invertierter_index_einzelwortsuche/src/invertierter_index/*.py"),
                   ROOT / "gemeinsam/__init__.py", ROOT / "pyproject.toml", ROOT / "requirements-dev.txt",
                   Path(__file__).resolve(), Path(__file__).with_name("generator.py"),
                   Path(__file__).with_name("memory.py")})


def code_hashes() -> dict[str, str]:
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in code_paths() if path.is_file()}


def make_metadata(plan: MeasurementPlan, pilot: bool, output: Path) -> dict:
    def git(*args):
        try:
            return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                           stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            # Kein Git-Arbeitsverzeichnis (z. B. aus einer ZIP-Datei entpackt)
            return "kein-git" if args[:1] == ("rev-parse",) else ""
    model = platform.processor()
    if Path("/proc/cpuinfo").exists():
        model = next((line.partition(":")[2].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                      if line.startswith("model name")), model)
    total_memory = next((line for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemTotal:")), "unknown") if Path("/proc/meminfo").exists() else "unknown"
    hashes = code_hashes()
    for relative in hashes:
        snapshot = output / "code_source" / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes((ROOT / relative).read_bytes())
    return {"run_id": "02_pilot" if pilot else "02_final", "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
            "git_status_at_start": git("status", "--porcelain"), "code_sha256": hashes,
            "source_archive": "code_source/", "parameters": PARAMETERS, "measurement_plan": asdict(plan),
            "environment": {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
                            "implementation": platform.python_implementation(), "cpu_model": model,
                            "memory_total": total_memory, "python_hash_seed": os.environ.get("PYTHONHASHSEED", "random"),
                            "unicode_database": unicodedata.unidata_version,
                            "matplotlib": version("matplotlib"), "pytest": version("pytest")},
            "background_load": "ordinary desktop background load; operator schedules experiment without parallel project tests or PDF build; not isolated",
            "cache": "prepared corpus and built index prechecked and reused; no cold-cache measurement",
            "timer": "time.perf_counter_ns; integer elapsed_ns per complete block",
            "timing_boundaries": {"build": "complete public build_inverted_index on already prepared corpus; result check after timer",
                "query": "public search_direct_word or search_index_word; normalization and full fresh sorted result list included",
                "blocks": "identical list-of-results and loop overhead in both methods; query_block_size full calls retained then checked",
                "excluded": "load/preparation, expectation checks, counters, disk output, plotting and memory instrumentation"},
            "statistics": "median, inclusive Q1/Q3, IQR=Q3-Q1; one block is one sample, quartiles are not confidence intervals",
            "memory": {"separate_process": True, "repeats": PARAMETERS["memory_repeats"],
                "retained_traced_bytes": "tracemalloc current_after_build-current_before_build; tracer starts after preparation",
                "peak_traced_bytes": "peak_since_reset-current_before_build; includes transient build allocations",
                "exclusive_index_bytes": "sys.getsizeof unique index/proxy/backing dict/tuple/str objects, excluding corpus token and ID string identities",
                "limitations": "Python traced allocations and object graph estimates, not RSS; corpus and query result memory excluded; no traced times used"},
            "datasets": []}


def independent_postings(tokens_by_id: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    """Einfache Referenz auf erwarteten Tokenfolgen, ohne Indexfunktion."""
    words = {word for words in tokens_by_id.values() for word in words}
    return {word: tuple(sorted(identifier for identifier, tokens in tokens_by_id.items() if word in tokens))
            for word in words}


def linear_expected_postings(tokens_by_id: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    """Unabhängiger Pflanzplan-Durchlauf statt des langsameren V-mal-Scans."""
    postings: dict[str, set[str]] = {}
    for identifier, tokens in tokens_by_id.items():
        for word in tokens:
            postings.setdefault(word, set()).add(identifier)
    return {word: tuple(sorted(ids)) for word, ids in postings.items()}


def measure_comparison(operations: dict, queries: list[QuerySpec], plan: MeasurementPlan, context: dict) -> list[dict]:
    """Gemeinsame Grenzen; lokale Orchestrierung randomisiert beide Verfahren.

    measure_queries aus 01 hat einen Algorithmus pro Lauf. Dieser kleine
    Treiber variiert zusätzlich die Verfahren innerhalb jeder Wiederholung.
    Kein Dispatch, Validieren oder Zufallsgenerator liegt im Zeitintervall.
    """
    if len({query.query_id for query in queries}) != len(queries):
        raise ValueError("query_id muss eindeutig sein")
    tasks = [(name, query) for name in sorted(operations) for query in queries]
    rng = random.Random(plan.seed)
    rows = []
    for iteration in range(-plan.warmups, plan.repeats):
        order = list(tasks)
        rng.shuffle(order)
        for position, (algorithm, query) in enumerate(order):
            operation = operations[algorithm]
            start = perf_counter_ns()
            results = [operation(query.text) for _ in range(plan.query_block_size)]
            elapsed = perf_counter_ns() - start
            for result in results:
                if result != list(query.expected_ids):
                    raise AssertionError(f"{algorithm}/{query.query_id}: falsche vollständige Treffer")
            if iteration >= 0:
                rows.append({**context, "algorithm": algorithm, "phase": "query", "query_id": query.query_id,
                             "query_text": query.text, "query_type": query.query_type, "repeat": iteration,
                             "order_index": position, "block_size": plan.query_block_size, "elapsed_ns": elapsed,
                             "query_ms": elapsed / 1_000_000 / plan.query_block_size,
                             "hit_count": len(query.expected_ids), "correct": True})
            # Auch die Freigabe des vorigen Blocks gehört außerhalb des nächsten
            # Timers: sonst würde df des Vorgängers dessen Messung beeinflussen.
            del result, results
    return rows


def fixture() -> dict:
    manifest_path = ROOT / "daten/real/kafka_verwandlung/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"manifest_path": manifest_path.relative_to(ROOT).as_posix(), "manifest_sha256": sha(manifest_path),
            "token_count": PARAMETERS["real_token_count"], "first_tokens": manifest["expected_prefix_tokens"],
            "file_sha256": {entry["document_id"]: entry["sha256"] for entry in manifest["documents"]},
            "queries": {{"Gregor": "frequent", "Fenster": "rare", "Unauffindbar": "missing"}[entry["query"]]: entry
                        for entry in manifest["verified_queries"]}}


def datasets(temporary: Path):
    for recipe in PARAMETERS["datasets"]:
        generated = generate_corpus(temporary / recipe["dataset_id"], recipe["total_tokens"],
                                    document_count=recipe["document_count"], base_vocabulary=recipe["base_vocabulary"],
                                    seed=PARAMETERS["seed"])
        yield recipe["dataset_id"], generated.root, generated, None, recipe
    real = fixture()
    yield PARAMETERS["real_dataset_id"], ROOT / "daten/real/kafka_verwandlung", None, real, {"series": ["real"]}


def validate_dataset(identifier, root, generated, real, recipe):
    raw = load_corpus(root)
    prepared = prepare_corpus(raw)
    actual_tokens = {doc.document_id: doc.tokens for doc in prepared}
    files = [{"document_id": doc.document_id, "source_path": doc.source_path,
              "bytes": len(doc.raw_text.encode("utf-8")), "sha256": hashlib.sha256(doc.raw_text.encode("utf-8")).hexdigest()}
             for doc in raw]
    hashes = {entry["document_id"]: entry["sha256"] for entry in files}
    if generated:
        if actual_tokens != generated.expected_tokens or hashes != generated.file_sha256:
            raise AssertionError("Generierte Dateien/ganze Tokenfolgen weichen vom Pflanzplan ab")
        expected_tokens = generated.expected_tokens
        queries = [QuerySpec(qid, text, "word", generated.expected_hits[qid])
                   for qid, text in (("frequent", "Fehler"), ("rare", "Verbindung"), ("missing", "Unauffindbar"))]
    else:
        if hashes != real["file_sha256"] or len(prepared) != 1 or len(prepared[0].tokens) != real["token_count"]:
            raise AssertionError("Realer Korpus stimmt nicht mit Fixture überein")
        if prepared[0].tokens[:len(real["first_tokens"])] != tuple(real["first_tokens"]):
            raise AssertionError("Realer Tokenanfang stimmt nicht")
        expected_tokens = actual_tokens  # Vollständige realen Tokens nicht handverifiziert: Grenze dokumentiert.
        queries = [QuerySpec(qid, entry["query"], "word", tuple(entry["expected_document_ids"]))
                   for qid, entry in real["queries"].items()]
    expected_index = linear_expected_postings(expected_tokens)
    index = build_inverted_index(prepared)
    if dict(index) != expected_index:
        raise AssertionError("Index verletzt vollständige Posting-Erwartung")
    if generated and len(index) != generated.base_vocabulary + 2:
        raise AssertionError("Wortschatzvariation wurde nicht erreicht")
    query_metadata = []
    for query in queries:
        word = {"Fehler": "fehler", "Verbindung": "verbindung", "Unauffindbar": "unauffindbar",
                "Gregor": "gregor", "Fenster": "fenster"}[query.text]
        positions = {doc.document_id: [i for i, token in enumerate(doc.tokens) if token == word] for doc in prepared}
        occurrence = sum(len(values) for values in positions.values())
        wanted = generated.expected_occurrences[query.query_id] if generated else real["queries"][query.query_id]["expected_occurrences"]
        if occurrence != wanted:
            raise AssertionError("Wortvorkommen weicht von unabhängiger Erwartung ab")
        if real and positions[prepared[0].document_id] != real["queries"][query.query_id]["expected_token_positions"]:
            raise AssertionError("Reale Wortpositionen weichen von Fixture ab")
        if any(search(prepared if search is search_direct_word else index, query.text) != list(query.expected_ids)
               for search in (search_direct_word, search_index_word)):
            raise AssertionError("Suchverfahren verletzt feste Treffererwartung")
        visited = sum(values[0] + 1 if values else len(actual_tokens[doc_id]) for doc_id, values in positions.items())
        query_metadata.append({**asdict(query), "normalized_token_expected": word,
                               "expected_occurrences": wanted, "observed_occurrences": occurrence,
                               "document_frequency": len(query.expected_ids), "direct_visited_tokens": visited})
    lengths = [len(doc.tokens) for doc in prepared]
    count = sum(lengths)
    dataset = {"dataset_id": identifier, "kind": "generated" if generated else "real", "series": recipe["series"],
               "generator_parameters": ({key: recipe[key] for key in ("total_tokens", "document_count", "base_vocabulary")} if generated else None),
               "document_count": len(prepared), "token_count": count, "text_bytes": sum(entry["bytes"] for entry in files),
               "vocabulary_size": len(index), "posting_count": sum(len(ids) for ids in index.values()),
               "document_lengths": {"minimum": min(lengths), "maximum": max(lengths), "total": count,
                                    "distribution": {str(length): lengths.count(length) for length in sorted(set(lengths))}},
               "files": files, "corpus_sha256": hashlib.sha256(json.dumps(files, ensure_ascii=False, sort_keys=True,
                                                                         separators=(",", ":")).encode()).hexdigest(),
               "queries": query_metadata, "source_fixture": real}
    return prepared, index, expected_index, queries, dataset


def timing_run(output: Path, plan: MeasurementPlan, pilot: bool) -> None:
    metadata = make_metadata(plan, pilot, output)
    rows = []
    with TemporaryDirectory(prefix="textsuche-02-time-") as temporary:
        for identifier, root, generated, real, recipe in datasets(Path(temporary)):
            prepared, index, expected, queries, dataset = validate_dataset(identifier, root, generated, real, recipe)
            metadata["datasets"].append(dataset)
            context = {"run_id": metadata["run_id"], "git_commit": metadata["git_commit"], "seed": plan.seed,
                       "dataset_id": identifier, "document_count": dataset["document_count"],
                       "text_bytes": dataset["text_bytes"], "token_count": dataset["token_count"]}
            print(f"{identifier}: N={dataset['token_count']}, D={dataset['document_count']}, V={dataset['vocabulary_size']}, P={dataset['posting_count']}; Aufbau/Abfragen", flush=True)
            def validate_build(observed):
                if dict(observed) != expected:
                    raise AssertionError("Zeitlauf-Build weicht von unabhängigen Postings ab")
            rows.extend(measure_phase(lambda: build_inverted_index(prepared), validate_build, plan,
                                      phase="build", context={**context, "algorithm": "inverted_index"}))
            rows.extend(measure_comparison({"direct_word": lambda text: search_direct_word(prepared, text),
                                            "inverted_index": lambda text: search_index_word(index, text)}, queries, plan, context))
            # Abfragen müssen den zuvor gesicherten Index und Ausgangskorpus erhalten.
            if dict(index) != expected or (generated and {doc.document_id: doc.tokens for doc in prepared} != generated.expected_tokens):
                raise AssertionError("Abfragefolge verändert Index oder Korpus")
            write_measurements(output / "raw.csv", rows)
            write_json(output / "metadata.json", metadata)
    metadata["timing_completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "metadata.json", metadata)
    write_json(output / "summary.json", summarize_measurements(rows))


def memory_run(output: Path) -> None:
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    if metadata["code_sha256"] != code_hashes():
        raise SystemExit("Code hat sich seit Zeitlauf geändert; getrennten Profilinglauf abgebrochen")
    rows = []
    by_id = {dataset["dataset_id"]: dataset for dataset in metadata["datasets"]}
    with TemporaryDirectory(prefix="textsuche-02-memory-") as temporary:
        for identifier, root, generated, real, recipe in datasets(Path(temporary)):
            prepared, index, expected, queries, observed = validate_dataset(identifier, root, generated, real, recipe)
            if json.loads(json.dumps(observed)) != by_id[identifier]:
                raise AssertionError("Speicherlauf benutzt anderen Korpus als Zeitlauf")
            del index
            print(f"{identifier}: separater Speicherlauf", flush=True)
            for profile in profile_index(prepared, expected, repeats=PARAMETERS["memory_repeats"]):
                rows.append({"run_id": metadata["run_id"], "dataset_id": identifier,
                             **{key: observed[key] for key in ("document_count", "token_count", "vocabulary_size", "posting_count")},
                             **profile})
    with (output / "memory.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MEMORY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = [{"dataset_id": identifier, **{f"median_{field}": median(row[field] for row in rows if row["dataset_id"] == identifier)
                for field in ("retained_traced_bytes", "peak_traced_bytes", "exclusive_index_bytes")}}
               for identifier in by_id]
    write_json(output / "memory.json", {"schema": list(MEMORY_FIELDS), "measurement": metadata["memory"],
                                        "rows": rows, "summary": summary})


def plots(output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams["svg.hashsalt"] = "textsuche-thema02"
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    memory = json.loads((output / "memory.json").read_text(encoding="utf-8"))
    target = ROOT / "ergebnisse/abbildungen"
    target.mkdir(parents=True, exist_ok=True)
    def save(fig, name):
        fig.tight_layout()
        for extension in ("png", "svg"):
            fig.savefig(target / f"{name}.{extension}", dpi=180,
                        metadata={"Date": None} if extension == "svg" else {})
        plt.close(fig)
    for series, xkey, xlabel in (("N", "token_count", "Tokens N (L=1000; D wächst)"),
                                 ("V", "vocabulary_size", "Erreichter Wortschatz V (N=100000; D=100)")):
        chosen = sorted((ds for ds in metadata["datasets"] if series in ds["series"]), key=lambda ds: ds[xkey])
        ids = {ds["dataset_id"] for ds in chosen}
        x = [ds[xkey] for ds in chosen]
        fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
        for ax, (qid, label) in zip(axes, (("missing", "Fehlend"), ("rare", "Selten"), ("frequent", "Früher Treffer in jedem Dokument"))):
            for algorithm, alglabel in (("direct_word", "Direkt"), ("inverted_index", "Index")):
                values = {row["dataset_id"]: row for row in summary if row["dataset_id"] in ids and row["phase"] == "query"
                          and row["query_id"] == qid and row["algorithm"] == algorithm}
                ordered = [values[ds["dataset_id"]] for ds in chosen]
                ax.plot(x, [row["median_ms"] for row in ordered], marker="o", label=alglabel)
                ax.fill_between(x, [row["q1_ms"] for row in ordered], [row["q3_ms"] for row in ordered], alpha=.18)
            ax.set(xscale="log", yscale="log", xlabel=xlabel, ylabel="ms je Anfrage", title=label)
            ax.grid(True, which="both", alpha=.25)
            ax.legend()
        save(fig, f"02_abfragen_{series.lower()}")
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
        builds = {row["dataset_id"]: row for row in summary if row["phase"] == "build"}
        axes[0].plot(x, [builds[ds["dataset_id"]]["median_ms"] for ds in chosen], marker="o")
        axes[0].fill_between(x, [builds[ds["dataset_id"]]["q1_ms"] for ds in chosen],
                             [builds[ds["dataset_id"]]["q3_ms"] for ds in chosen], alpha=.18)
        axes[0].set(xscale="log", yscale="log", xlabel=xlabel, ylabel="Aufbau ms", title="Median / Quartilsbereich")
        mem = {row["dataset_id"]: row for row in memory["summary"]}
        for field, label in (("retained_traced_bytes", "Bleibend (tracemalloc)"), ("peak_traced_bytes", "Spitze (tracemalloc)"),
                             ("exclusive_index_bytes", "Exklusiver Objektgraph")):
            axes[1].plot(x, [mem[ds["dataset_id"]][f"median_{field}"] / 1024 for ds in chosen], marker="o", label=label)
        axes[1].set(xscale="log", yscale="log", xlabel=xlabel, ylabel="Zusätzlicher Index KiB", title="Separater Profilingprozess")
        axes[1].legend(fontsize=8)
        for ax in axes:
            ax.grid(True, which="both", alpha=.25)
        save(fig, f"02_aufbau_speicher_{series.lower()}")


def require_pilot(path: Path) -> None:
    if not path.is_file():
        raise SystemExit("Zuerst --pilot ausführen: erfolgreicher Pilot muss Parameter sperren")
    decision = json.loads(path.read_text(encoding="utf-8"))
    if decision.get("pilot_correct") is not True or decision.get("locked_parameters") != PARAMETERS:
        raise SystemExit("Erfolgreicher Pilot mit genau diesen Parametern fehlt; Pilot erneut ausführen")
    if decision.get("method_code_sha256") != code_hashes():
        raise SystemExit("Messcode hat sich nach Pilot geändert; Pilot erneut ausführen")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true", help="1 Warmup, 3 Messungen, Parameterfreigabe; keine finalen Diagramme")
    parser.add_argument("--memory", action="store_true", help="nur getrennter Speicherprozess auf schon gemessenem Datensatz")
    args = parser.parse_args()
    output = ROOT / "ergebnisse/messungen" / ("02_pilot" if args.pilot else "02_invertierter_index")
    if args.memory:
        memory_run(output)
        return
    if not args.pilot:
        require_pilot(ROOT / "ergebnisse/messungen/02_pilot/pilot_decision.json")
    output.mkdir(parents=True, exist_ok=True)
    plan = MeasurementPlan(warmups=1, repeats=3) if args.pilot else MeasurementPlan()
    timing_run(output, plan, args.pilot)
    command = [sys.executable, str(Path(__file__).resolve()), "--memory"]
    if args.pilot:
        command.append("--pilot")
    subprocess.run(command, cwd=ROOT, check=True)
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    metadata["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "metadata.json", metadata)
    if args.pilot:
        write_json(output / "pilot_decision.json", {"pilot_correct": True, "locked_parameters": PARAMETERS,
            "method_code_sha256": metadata["code_sha256"], "pilot_plan": asdict(plan),
            "decision": "beide begrenzten Reihen, unabhängige Erwartungen und eigener Speicherprozess ausführbar; Parameter unverändert gesperrt",
            "pilot_is_not_final_measurement": True})
    else:
        plots(output)
    print(f"Gespeichert: {output.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
