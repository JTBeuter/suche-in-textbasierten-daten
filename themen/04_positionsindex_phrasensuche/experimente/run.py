#!/usr/bin/env python3
"""Phrasenversuche: Pilot, gesperrter Zeitlauf und separater Speicherlauf."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import random
from statistics import median
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import get_clock_info, perf_counter_ns
import unicodedata
import re

from gemeinsam import load_corpus, normalize_query, prepare_corpus
from gemeinsam.messung import MeasurementPlan, measure_phase, summarize_measurements, write_measurements
from invertierter_index import build_inverted_index
from positionsindex import build_positional_index, search_direct_phrase, search_index_phrase

if __package__:
    from .generator import LENGTHS, PhraseQuery, expected_positions, generate_corpus, synthetic_queries
else:
    from generator import LENGTHS, PhraseQuery, expected_positions, generate_corpus, synthetic_queries


ROOT = Path(__file__).resolve().parents[3]
ALGORITHMS = ("direct_phrase", "positional_phrase")
PARAMETERS = {
    "seed": 20261006,
    "synthetic": {"document_count": 200, "tokens_per_document": 500},
    "result_document_counts": [0, 20, 200], "full_query_result_count": 200,
    "real_dataset_id": "real_kafka_anfang", "real_token_count": 1271,
    "phrase_lengths": list(LENGTHS), "memory_repeats": 3,
    "final_plan": asdict(MeasurementPlan(query_block_size=5)),
    "generator": "four-character ASCII tokens; fixed plant positions;50 guaranteed filler tokens; uppercase period separators; z000..z004 reorder with constant per-token CF/DF",
    "schedule": "shuffle every (algorithm,query) block per repetition with fixed seed; reset schedule per dataset",
}
MEMORY_FIELDS = ("run_id", "dataset_id", "algorithm", "document_count", "token_count", "vocabulary_size",
                 "posting_count", "repeat", "worker_pid", "retained_traced_bytes", "peak_traced_bytes", "transient_peak_bytes")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def installed_version(distribution):
    """Paketversion oder None; setuptools ist ab Python 3.12 nicht vorinstalliert."""
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def code_hashes():
    files = {*ROOT.glob("gemeinsam/src/gemeinsam/*.py"),
             *ROOT.glob("themen/02_invertierter_index_einzelwortsuche/src/invertierter_index/*.py"),
             *ROOT.glob("themen/03_boolesche_mehrwortsuche/src/boolesche_suche/*.py"),
             *ROOT.glob("themen/04_positionsindex_phrasensuche/src/positionsindex/*.py"),
             *Path(__file__).resolve().parent.glob("*.py"),
             ROOT / "gemeinsam/__init__.py", ROOT / "pyproject.toml", ROOT / "requirements-dev.txt"}
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(files) if path.is_file()}


def make_metadata(plan, output, pilot):
    def git(*args):
        try:
            return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                           stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            # Kein Git-Arbeitsverzeichnis (z. B. aus einer ZIP-Datei entpackt)
            return "kein-git" if args[:1] == ("rev-parse",) else ""
    hashes = code_hashes()
    for relative in hashes:
        snapshot = output / "code_source" / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes((ROOT / relative).read_bytes())
    cpu = platform.processor()
    if Path("/proc/cpuinfo").exists():
        cpu = next((line.partition(":")[2].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")), cpu)
    return {
        "run_id": "04_pilot" if pilot else "04_final", "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
        "git_status_at_start": git("status", "--porcelain"), "code_sha256": hashes, "source_archive": "code_source/",
        "parameters": PARAMETERS, "measurement_plan": asdict(plan),
        "environment": {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
                        "implementation": platform.python_implementation(), "cpu_model": cpu,
                        "python_hash_seed": os.environ.get("PYTHONHASHSEED", "random"),
                        "unicode_database": unicodedata.unidata_version,
                        "pytest": version("pytest"), "setuptools": installed_version("setuptools")},
        "timer": "time.perf_counter_ns; integer elapsed_ns per complete block",
        "clock": vars(get_clock_info("perf_counter")),
        "background_load": "ordinary desktop background load; project tests and PDF builds paused during time runs; no CPU isolation",
        "cache": "same already prepared corpus and checked index reused; no cold-cache claim",
        "timing_boundaries": {
            "build": "separate complete public inverted/positional index builds on identical prepared documents; validation included; results checked outside timer",
            "query": "normalize_query(raw,'phrase') plus public phrase kernel and full fresh dict/list of start positions for BOTH methods",
            "block": "five identical complete calls retained then checked; equal loop/list overhead; destroy results before next timer",
            "excluded": "loading, preparation, generation, correctness oracle, summaries, output, memory instrumentation",
        },
        "statistics": "median, inclusive Q1/Q3 and IQR; block is one sample; quartiles are not confidence intervals",
        "memory": {
            "separate_process_per_dataset_and_algorithm": True, "repeats": PARAMETERS["memory_repeats"],
            "retained_traced_bytes": "current_after_build-current_before_build; tracer begins after corpus preparation",
            "peak_traced_bytes": "peak_since_reset-current_before_build",
            "transient_peak_bytes": "peak_traced_bytes-retained_traced_bytes",
            "limitations": "Python-traced additional allocations, not RSS or serialized size; preparation and preexisting independent oracle containers excluded; no simultaneous production alternative index; no profiling times in raw.csv",
        },
        "interpretation_limits": [
            "Every result contains ALL phrase starts; single-word output is larger than inverted word search output.",
            "Length prefixes preserve input corpus but repeated phrases change position counts; length is not fully isolated from result size.",
            "Result-size variants preserve CF/DF, token counts, word lengths and candidate documents but changed token order affects merge progress as well as output allocation.",
            "Real corpus is one unchanged1271-token excerpt; findings do not generalize to large real corpora.",
        ],
        "datasets": [],
    }


def independent_tokens(text):
    normalized = unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).casefold())
    assert all(unicodedata.category(ch)[0] != "M" for ch in normalized)
    assert all(not unicodedata.category(ch).startswith("N") or unicodedata.category(ch) == "Nd" for ch in normalized)
    return tuple(re.findall(r"[^\W_]+", normalized))


def real_fixture():
    directory = ROOT / "daten/real/kafka_verwandlung"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert sha(directory / manifest["source_file"]) == manifest["source_sha256"]
    source = (directory / manifest["source_file"]).read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    start, end = manifest["selection"]["start_inclusive"], manifest["selection"]["end_exclusive"]
    assert source.count(start) == source.count(end) == 1
    selected = source[source.index(start):source.index(end)].strip() + "\n"
    entry = manifest["documents"][0]
    assert selected.encode("utf-8") == (directory / entry["source_path"]).read_bytes()
    assert sha(directory / entry["source_path"]) == entry["sha256"]
    tokens = independent_tokens(selected)
    assert len(tokens) == PARAMETERS["real_token_count"]
    assert tokens[:len(manifest["expected_prefix_tokens"])] == tuple(manifest["expected_prefix_tokens"])
    for query in manifest["verified_queries"]:
        assert [i for i, word in enumerate(tokens) if word == query["query"].casefold()] == query["expected_token_positions"]
    return directory, {entry["document_id"]: tokens}, {
        "manifest_path": "daten/real/kafka_verwandlung/manifest.json",
        "manifest_sha256": sha(directory / "manifest.json"), "source_sha256": manifest["source_sha256"],
        "corpus_selection": "existing first eight paragraphs as one unchanged document",
        "query_selection": "first sentence prefixes at start0; common er; repeated Gregor; absent x999; reversed prefix tokens present but wrong order",
    }


def real_queries(tokens_by_id):
    tokens = next(iter(tokens_by_id.values()))
    queries = []
    for group, words in (("real_prefix", tokens[:5]), ("real_common", ("er",) * 5),
                         ("real_repeated", ("gregor",) * 5), ("real_unknown", ("x999",) * 5)):
        for length in LENGTHS:
            phrase = tuple(words[:length])
            queries.append(PhraseQuery(f"{group}_k{length}", phrase, group, expected_positions(tokens_by_id, phrase)))
    for length in (2, 3, 5):
        phrase = tokens[:length][::-1]
        expected = expected_positions(tokens_by_id, phrase)
        assert expected == {}
        queries.append(PhraseQuery(f"real_wrong_order_k{length}", phrase, "real_wrong_order", expected))
    return queries


def datasets(temporary):
    for hits in PARAMETERS["result_document_counts"]:
        identifier = f"phrase_h{hits:03d}"
        generated = generate_corpus(Path(temporary) / identifier, **PARAMETERS["synthetic"],
                                    result_document_count=hits, seed=PARAMETERS["seed"])
        yield identifier, generated.root, generated.expected_tokens, synthetic_queries(generated, full=hits == PARAMETERS["full_query_result_count"]), {
            "kind": "generated", "recipe": generated.recipe, "planted_positions": generated.planted_positions,
        }
    directory, tokens, fixture = real_fixture()
    yield PARAMETERS["real_dataset_id"], directory, tokens, real_queries(tokens), {"kind": "real", "source_fixture": fixture}


def independent_indexes(tokens_by_id):
    positions = {}
    for identifier, tokens in sorted(tokens_by_id.items()):
        for position, token in enumerate(tokens):
            positions.setdefault(token, {}).setdefault(identifier, []).append(position)
    positional = {token: {identifier: tuple(locations) for identifier, locations in docs.items()}
                  for token, docs in sorted(positions.items())}
    postings = {token: tuple(docs) for token, docs in positional.items()}
    return postings, positional


def query_metadata(query, tokens_by_id, postings, positional):
    phrase = query.tokens
    assert normalize_query(query.text, "phrase") == phrase
    assert expected_positions(tokens_by_id, phrase) == query.expected
    candidates = set(tokens_by_id)
    for token in set(phrase):
        candidates.intersection_update(postings.get(token, ()))
    lengths = {identifier: [len(positional.get(token, {}).get(identifier, ())) for token in phrase]
               for identifier in sorted(candidates)}
    return {"query_id": query.query_id, "text": query.text, "phrase_tokens": list(phrase),
            "phrase_length": len(phrase), "group": query.group,
            "collection_frequencies": [sum(len(p) for p in positional.get(token, {}).values()) for token in phrase],
            "document_frequencies": [len(postings.get(token, ())) for token in phrase],
            "candidate_document_ids": sorted(candidates), "candidate_count": len(candidates),
            "position_list_lengths_by_candidate": lengths,
            "expected_positions": query.expected, "hit_count": len(query.expected),
            "position_count": sum(map(len, query.expected.values()))}


def describe_dataset(identifier, directory, tokens_by_id, queries, extra):
    raw = load_corpus(directory)
    prepared = prepare_corpus(raw)
    assert {doc.document_id: doc.tokens for doc in prepared} == tokens_by_id, "prepared Tokenfolgen differ from independent plan"
    postings, positional = independent_indexes(tokens_by_id)
    files = [{"document_id": doc.document_id, "source_path": doc.source_path,
              "bytes": len(doc.raw_text.encode("utf-8")), "sha256": hashlib.sha256(doc.raw_text.encode("utf-8")).hexdigest()}
             for doc in raw]
    encoded = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    description = {"dataset_id": identifier, **extra, "files": files,
                   "corpus_sha256": hashlib.sha256(encoded).hexdigest(), "document_count": len(raw),
                   "text_bytes": sum(entry["bytes"] for entry in files), "token_count": sum(len(doc.tokens) for doc in prepared),
                   "vocabulary_size": len(postings), "posting_count": sum(map(len, postings.values())),
                   "unigram_statistics": {token: {"cf": sum(map(len, docs.values())), "df": len(docs)}
                                          for token, docs in positional.items()},
                   "document_lengths": [len(doc.tokens) for doc in prepared],
                   "queries": [query_metadata(query, tokens_by_id, postings, positional) for query in queries]}
    return prepared, postings, positional, description


def validate_positional(index, expected):
    assert {token: dict(docs) for token, docs in index.items()} == expected, "positions index violates independent oracle"


def measure_comparison(operations, queries, plan, context):
    assert len({q.query_id for q in queries}) == len(queries)
    tasks = [(algorithm, query) for algorithm in sorted(operations) for query in queries]
    rng = random.Random(plan.seed)
    rows = []
    for iteration in range(-plan.warmups, plan.repeats):
        order = tasks[:]
        rng.shuffle(order)
        for order_index, (algorithm, query) in enumerate(order):
            operation = operations[algorithm]
            start = perf_counter_ns()
            results = [operation(query.text) for _ in range(plan.query_block_size)]
            elapsed = perf_counter_ns() - start
            for result in results:
                assert result == query.expected, f"{algorithm}/{query.query_id}: incorrect full positions"
            if iteration >= 0:
                rows.append({**context, "algorithm": algorithm, "phase": "query", "query_id": query.query_id,
                             "query_text": query.text, "query_type": "phrase", "repeat": iteration,
                             "order_index": order_index, "block_size": plan.query_block_size, "elapsed_ns": elapsed,
                             "query_ms": elapsed / 1_000_000 / plan.query_block_size,
                             "hit_count": len(query.expected), "correct": True})
            del result, results
    return rows


def timing_run(output, plan, pilot):
    info = make_metadata(plan, output, pilot)
    rows = []
    with TemporaryDirectory(prefix="textsuche-04-time-") as temporary:
        for identifier, directory, tokens, queries, extra in datasets(temporary):
            prepared, postings, expected, description = describe_dataset(identifier, directory, tokens, queries, extra)
            info["datasets"].append(description)
            print(f"{identifier}: N={description['token_count']}, D={len(prepared)}, V={description['vocabulary_size']}, queries={len(queries)}", flush=True)
            context = {"run_id": info["run_id"], "git_commit": info["git_commit"], "seed": plan.seed,
                       **{field: description[field] for field in ("dataset_id", "document_count", "text_bytes", "token_count")}}
            # Each build result is discarded before the other algorithm begins.
            rows.extend(measure_phase(lambda: build_inverted_index(prepared),
                lambda index: _assert_equal(dict(index), postings), plan, phase="build", context={**context, "algorithm": "inverted_index"}))
            rows.extend(measure_phase(lambda: build_positional_index(prepared),
                lambda index: validate_positional(index, expected), plan, phase="build", context={**context, "algorithm": "positional_index"}))
            index = build_positional_index(prepared)
            validate_positional(index, expected)
            for query in queries:
                assert search_direct_phrase(prepared, query.tokens) == query.expected
                assert search_index_phrase(index, query.tokens) == query.expected
            operations = {
                "direct_phrase": lambda text: search_direct_phrase(prepared, normalize_query(text, "phrase")),
                "positional_phrase": lambda text: search_index_phrase(index, normalize_query(text, "phrase")),
            }
            rows.extend(measure_comparison(operations, queries, plan, context))
            validate_positional(index, expected)
            assert {doc.document_id: doc.tokens for doc in prepared} == tokens
            del index, operations
    assert code_hashes() == info["code_sha256"], "code changed during timing"
    write_measurements(output / "raw.csv", rows)
    write_json(output / "summary.json", summarize_measurements(rows))
    info["timing_completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "metadata.json", info)
    if pilot:
        write_json(output / "pilot_decision.json", {"pilot_correct": True, "locked_parameters": PARAMETERS,
            "method_code_sha256": info["code_sha256"], "pilot_plan": asdict(plan),
            "decision": "full positional results and independent corpus plans verified; final parameters locked; separated memory run required before final",
            "pilot_is_not_final_measurement": True})


def _assert_equal(value, expected):
    assert value == expected, "build violates independent postings"


def memory_run(output):
    info = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    assert info["code_sha256"] == code_hashes(), "code changed since timing"
    rows, workers = [], []
    with TemporaryDirectory(prefix="textsuche-04-workers-") as temporary:
        for dataset in info["datasets"]:
            for algorithm in ("inverted_index", "positional_index"):
                target = Path(temporary) / f"{dataset['dataset_id']}-{algorithm}.json"
                command = [sys.executable, str(Path(__file__).with_name("memory.py")), "--metadata", str(output / "metadata.json"),
                           "--dataset", dataset["dataset_id"], "--algorithm", algorithm, "--output", str(target)]
                subprocess.run(command, cwd=ROOT, check=True)
                worker = json.loads(target.read_text(encoding="utf-8"))
                workers.append({key: worker[key] for key in ("dataset_id", "algorithm", "worker_pid", "started_at_utc", "completed_at_utc", "code_sha256")})
                rows.extend(worker["rows"])
    assert info["code_sha256"] == code_hashes(), "code changed during memory profiling"
    with (output / "memory.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MEMORY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = [{"dataset_id": dataset["dataset_id"], "algorithm": algorithm,
                **{f"median_{field}": median(row[field] for row in rows if row["dataset_id"] == dataset["dataset_id"] and row["algorithm"] == algorithm)
                   for field in ("retained_traced_bytes", "peak_traced_bytes", "transient_peak_bytes")}}
               for dataset in info["datasets"] for algorithm in ("inverted_index", "positional_index")]
    write_json(output / "memory.json", {"schema": list(MEMORY_FIELDS), "measurement": info["memory"],
                                       "code_sha256": info["code_sha256"], "workers": workers, "rows": rows, "summary": summary})


def require_pilot(path):
    if not path.is_file():
        raise SystemExit("Zuerst run.py --pilot und run.py --pilot --memory ausführen.")
    decision = json.loads(path.read_text(encoding="utf-8"))
    if decision.get("pilot_correct") is not True or decision.get("locked_parameters") != PARAMETERS:
        raise SystemExit("Erfolgreicher Pilot mit unveränderten Parametern erforderlich.")
    if decision.get("method_code_sha256") != code_hashes():
        raise SystemExit("Messcode geändert: Pilot erneut ausführen.")
    if not (path.parent / "memory.json").is_file():
        raise SystemExit("Separater Pilot-Speicherlauf fehlt: --pilot --memory ausführen.")
    if __package__:
        from .verify_results import verify_directory
    else:
        from verify_results import verify_directory
    verify_directory(path.parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--memory", action="store_true", help="separate workers; requires completed timing run")
    args = parser.parse_args()
    output = ROOT / "ergebnisse/messungen" / ("04_pilot" if args.pilot else "04_positionsindex_phrasensuche")
    if args.memory:
        memory_run(output)
    else:
        # Feste Ausgabeziele: gelieferte Archive nie überschreiben (BGB-Realteil: run_bgb.py).
        if output.exists() and any(output.iterdir()):
            raise SystemExit(f"{output.relative_to(ROOT)} ist nicht leer; gelieferte Ergebnisse werden "
                             "nicht überschrieben. Neue Läufe nur in einer getrennten Arbeitskopie.")
        if not args.pilot:
            require_pilot(ROOT / "ergebnisse/messungen/04_pilot/pilot_decision.json")
        output.mkdir(parents=True, exist_ok=True)
        plan = MeasurementPlan(warmups=1, repeats=3, query_block_size=5) if args.pilot else MeasurementPlan(query_block_size=5)
        timing_run(output, plan, args.pilot)
    print(f"Gespeichert: {output.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
