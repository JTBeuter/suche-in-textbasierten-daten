#!/usr/bin/env python3
"""Kontrollierte boolesche Messungen: Pilot, gesperrter Zeitlauf, Diagnose."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import random
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns
import unicodedata

from gemeinsam import load_corpus, prepare_corpus
from gemeinsam.messung import MeasurementPlan, measure_phase, summarize_measurements, write_measurements
from invertierter_index import build_inverted_index
from boolesche_suche import normalize_terms, search_direct_boolean, search_index_boolean

from boolean_generator import GROUPS, expected_hits, generate_corpus
from boolean_diagnostics import diagnose_direct, diagnose_postings


ROOT = Path(__file__).resolve().parents[3]
PARAMETERS = {
    "seed": 20261006,
    "synthetic": {"dataset_id": "boolean_controlled", "document_count": 1000, "tokens_per_document": 100},
    "real_dataset_id": "real_kafka_anfang", "real_token_count": 1271,
    "query_lengths": [2, 3, 5], "query_orders": ["forward", "reverse"],
    "groups": {key: list(value) for key, value in GROUPS.items()},
    "final_plan": asdict(MeasurementPlan(query_block_size=5)),
    "schedule": "shuffle all eligible (algorithm,operator,query) blocks per repetition; fixed seed",
    "generator": "exact fixed membership recipes; 100 tokens/doc; all query/filler tokens four ASCII characters; seeded filler and position shuffle; uppercase + punctuation",
}
ALGORITHMS = ("direct_boolean", "and_input_order", "and_shortest_first", "or_input_order")


@dataclass(frozen=True)
class BooleanQuerySpec:
    query_id: str
    terms: tuple[str, ...]
    operator: str
    group: str
    order: str
    expected_ids: tuple[str, ...]

    @property
    def text(self):
        return json.dumps(self.terms, ensure_ascii=False, separators=(",", ":"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_hashes():
    files = {*ROOT.glob("gemeinsam/src/gemeinsam/*.py"),
             *ROOT.glob("themen/02_invertierter_index_einzelwortsuche/src/invertierter_index/*.py"),
             *ROOT.glob("themen/03_boolesche_mehrwortsuche/src/boolesche_suche/*.py"),
             *Path(__file__).resolve().parent.glob("*.py"),
             ROOT / "gemeinsam/__init__.py", ROOT / "pyproject.toml", ROOT / "requirements-dev.txt"}
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(files) if path.is_file()}


def metadata(plan, output, pilot):
    def git(*args):
        try:
            return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                           stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            # Kein Git-Arbeitsverzeichnis (z. B. aus einer ZIP-Datei entpackt)
            return "kein-git" if args[:1] == ("rev-parse",) else ""
    hashes = code_hashes()
    for relative in hashes:
        source = output / "code_source" / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((ROOT / relative).read_bytes())
    cpu = platform.processor()
    if Path("/proc/cpuinfo").exists():
        cpu = next((line.partition(":")[2].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")), cpu)
    return {"run_id": "03_pilot" if pilot else "03_final", "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
            "git_status_at_start": git("status", "--porcelain"), "code_sha256": hashes,
            "source_archive": "code_source/", "parameters": PARAMETERS, "measurement_plan": asdict(plan),
            "environment": {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
                            "implementation": platform.python_implementation(), "cpu_model": cpu,
                            "python_hash_seed": os.environ.get("PYTHONHASHSEED", "random"),
                            "unicode_database": unicodedata.unidata_version, "pytest": version("pytest")},
            "timer": "time.perf_counter_ns; integer elapsed_ns per complete block",
            "background_load": "ordinary desktop background load; project tests and LaTeX build paused during timing; not isolated",
            "cache": "prepared corpus and prechecked index reused; no cold-cache measurement; load includes OS cache effects",
            "timing_boundaries": {"load": "complete public load_corpus on fixed disk files",
                "preparation": "complete public prepare_corpus on already loaded raw documents",
                "build": "complete public build_inverted_index on prepared documents",
                "query": "complete public search including query normalization, posting gathering, stable length sort if applicable, merging, full fresh result list",
                "block": "five complete identical calls retained then checked; loop/list-of-results overhead included equally; previous results deleted before next timer",
                "excluded": "generation, correctness, diagnostics, disk output, summary and plotting; no memory instrumentation"},
            "statistics": "median, inclusive Q1/Q3, IQR; one block is one sample; quartiles are not confidence intervals",
            "memory": "not measured in topic03; CSV index_bytes and peak_memory_bytes remain empty",
            "datasets": []}


def make_queries(membership, *, real=False):
    groups = {key: values for key, values in GROUPS.items()}
    if real:
        groups = {"real_present": ("gregor", "fenster", "er", "samsa", "morgens"),
                  "real_unknown": ("gregor", "unauffindbar")}
    queries = []
    for group, words in groups.items():
        lengths = (2,) if group == "real_unknown" else (2, 3, 5)
        for k in lengths:
            for order in ("forward", "reverse"):
                terms = tuple(words[:k])
                if order == "reverse":
                    terms = terms[::-1]
                for operator in ("AND", "OR"):
                    queries.append(BooleanQuerySpec(f"{group}_k{k}_{order}_{operator.lower()}", terms,
                        operator, group, order, expected_hits(membership, terms, operator)))
    original = ("Gregor", "GREGOR", "Fenster") if real else ("Q010", "q010", "q014")
    normalized = ("gregor", "fenster") if real else ("q010", "q014")
    for operator in ("AND", "OR"):
        queries.append(BooleanQuerySpec(f"deduplicated_{operator.lower()}", original, operator, "duplicates", "forward",
            expected_hits(membership, normalized, operator)))
    return queries


def independent_tokens(text):
    # Regex is independent of the production token scan; equivalent for this
    # fixed prose, whose remaining combining/number categories are checked.
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
    return directory, {entry["document_id"]: tokens}, {"manifest_path": "daten/real/kafka_verwandlung/manifest.json",
        "manifest_sha256": sha(directory / "manifest.json"), "source_sha256": manifest["source_sha256"],
        "corpus_selection": "existing single eight-paragraph document unchanged; no new paragraph segmentation"}


def independent_postings(tokens_by_id):
    words = set(word for tokens in tokens_by_id.values() for word in tokens)
    return {word: tuple(sorted(identifier for identifier, tokens in tokens_by_id.items() if word in tokens)) for word in words}


def query_metadata(query, postings, tokens_by_id):
    normalized = normalize_terms(query.terms)
    variants = ("input_order", "shortest_first") if query.operator == "AND" else ("input_order",)
    diagnostics = {variant: diagnose_postings(postings, normalized, query.operator, variant) for variant in variants}
    direct = diagnose_direct(tokens_by_id, normalized, query.operator)
    assert tuple(direct["result_ids"]) == query.expected_ids
    assert all(tuple(value["result_ids"]) == query.expected_ids for value in diagnostics.values())
    del direct["result_ids"]
    for value in diagnostics.values():
        del value["result_ids"]
    return {"query_id": query.query_id, "terms": list(query.terms), "normalized_terms": list(normalized),
            "operator": query.operator, "group": query.group, "order": query.order, "text": query.text,
            "original_term_count": len(query.terms), "effective_term_count": len(normalized),
            "posting_lengths_input_order": [len(postings.get(term, ())) for term in normalized],
            "expected_ids": list(query.expected_ids), "hit_count": len(query.expected_ids),
            "diagnostics": diagnostics, "direct_diagnostics": direct}


def validate_dataset(identifier, directory, tokens_by_id, membership, source_fixture=None):
    raw = load_corpus(directory)
    prepared = prepare_corpus(raw)
    assert {doc.document_id: doc.tokens for doc in prepared} == tokens_by_id, "Aufbereitung weicht von unabhängigen Tokenfolgen ab"
    postings = independent_postings(tokens_by_id)
    if membership is not None:
        assert all(postings.get(term, ()) == ids for term, ids in membership.items()), "Pflanzplan verletzt"
    else:
        membership = postings
    index = build_inverted_index(prepared)
    assert dict(index) == postings, "Index weicht von unabhängiger Referenz ab"
    queries = make_queries(membership, real=source_fixture is not None)
    fixed_index = dict(index)
    for query in queries:
        assert search_direct_boolean(prepared, query.terms, query.operator) == list(query.expected_ids)
        for variant in (("input_order", "shortest_first") if query.operator == "AND" else ("input_order",)):
            assert search_index_boolean(index, query.terms, query.operator, variant) == list(query.expected_ids)
    assert dict(index) == fixed_index
    files = [{"document_id": doc.document_id, "source_path": doc.source_path,
              "bytes": len(doc.raw_text.encode("utf-8")), "sha256": hashlib.sha256(doc.raw_text.encode("utf-8")).hexdigest()}
             for doc in raw]
    encoded = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    dataset = {"dataset_id": identifier, "kind": "real" if source_fixture else "generated", "files": files,
               "corpus_sha256": hashlib.sha256(encoded).hexdigest(), "document_count": len(raw),
               "text_bytes": sum(entry["bytes"] for entry in files), "token_count": sum(len(doc.tokens) for doc in prepared),
               "vocabulary_size": len(postings), "queries": [query_metadata(q, postings, tokens_by_id) for q in queries]}
    if source_fixture:
        dataset["source_fixture"] = source_fixture
    return raw, prepared, index, queries, dataset


def eligible(algorithm, query):
    return algorithm == "direct_boolean" or (query.operator == "AND" and algorithm.startswith("and_")) or (query.operator == "OR" and algorithm == "or_input_order")


def measure_comparison(operations, queries, plan, context):
    """Gemeinsames Schema mit Randomisierung aller Verfahren innerhalb eines Laufs."""
    assert len({query.query_id for query in queries}) == len(queries), "query_id muss eindeutig sein"
    tasks = [(algorithm, query) for algorithm in sorted(operations) for query in queries if eligible(algorithm, query)]
    rng = random.Random(plan.seed)
    rows = []
    for iteration in range(-plan.warmups, plan.repeats):
        order = list(tasks)
        rng.shuffle(order)
        for position, (algorithm, query) in enumerate(order):
            operation = operations[algorithm]
            start = perf_counter_ns()
            results = [operation(query.terms, query.operator) for _ in range(plan.query_block_size)]
            elapsed = perf_counter_ns() - start
            for result in results:
                if result != list(query.expected_ids):
                    raise AssertionError(f"{algorithm}/{query.query_id}: falsche vollständige Treffer")
            if iteration >= 0:
                rows.append({**context, "algorithm": algorithm, "phase": "query", "query_id": query.query_id,
                             "query_text": query.text, "query_type": query.operator.lower(), "repeat": iteration,
                             "order_index": position, "block_size": plan.query_block_size, "elapsed_ns": elapsed,
                             "query_ms": elapsed / 1_000_000 / plan.query_block_size,
                             "hit_count": len(query.expected_ids), "correct": True})
            del result, results
    return rows


def require_pilot(path):
    if not path.is_file():
        raise SystemExit("Zuerst run.py --pilot ausführen.")
    decision = json.loads(path.read_text(encoding="utf-8"))
    if decision.get("pilot_correct") is not True or decision.get("locked_parameters") != PARAMETERS:
        raise SystemExit("Erfolgreicher Pilot mit unveränderten Parametern erforderlich.")
    if decision.get("method_code_sha256") != code_hashes():
        raise SystemExit("Messcode geändert: Pilot erneut ausführen.")


def timing_run(output, plan, pilot):
    info = metadata(plan, output, pilot)
    rows = []
    with TemporaryDirectory(prefix="textsuche-03-") as temporary:
        generated = generate_corpus(Path(temporary) / "controlled", document_count=PARAMETERS["synthetic"]["document_count"],
                                    tokens_per_document=PARAMETERS["synthetic"]["tokens_per_document"], seed=PARAMETERS["seed"])
        real_root, real_tokens, real_source = real_fixture()
        datasets = [("boolean_controlled", generated.root, generated.expected_tokens, generated.membership, None),
                    (PARAMETERS["real_dataset_id"], real_root, real_tokens, None, real_source)]
        for identifier, directory, tokens, membership, source in datasets:
            raw, prepared, index, queries, description = validate_dataset(identifier, directory, tokens, membership, source)
            info["datasets"].append(description)
            context = {"run_id": info["run_id"], "git_commit": info["git_commit"], "seed": plan.seed,
                       **{field: description[field] for field in ("dataset_id", "document_count", "text_bytes", "token_count")}}
            def check(value, expected):
                assert value == expected, "Vorbereitungsphase verändert den Korpus"
            for phase, algorithm, operation, expected in (
                ("load", "corpus_loader", lambda: load_corpus(directory), raw),
                ("preparation", "tokenizer", lambda: prepare_corpus(raw), prepared),
                ("build", "inverted_index", lambda: build_inverted_index(prepared), index)):
                rows.extend(measure_phase(operation, lambda value: check(value, expected), plan,
                                          phase=phase, context={**context, "algorithm": algorithm}))
            operations = {"direct_boolean": lambda terms, operator: search_direct_boolean(prepared, terms, operator),
                          "and_input_order": lambda terms, operator: search_index_boolean(index, terms, operator, "input_order"),
                          "and_shortest_first": lambda terms, operator: search_index_boolean(index, terms, operator, "shortest_first"),
                          "or_input_order": lambda terms, operator: search_index_boolean(index, terms, operator, "input_order")}
            rows.extend(measure_comparison(operations, queries, plan, context))
    assert code_hashes() == info["code_sha256"], "Code während Messung geändert"
    write_measurements(output / "raw.csv", rows)
    write_json(output / "summary.json", summarize_measurements(rows))
    info["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "metadata.json", info)
    if pilot:
        write_json(output / "pilot_decision.json", {"pilot_correct": True, "locked_parameters": PARAMETERS,
            "method_code_sha256": info["code_sha256"], "pilot_plan": asdict(plan),
            "decision": "kontrollierte Rezepturen und reale Quelle korrekt; Parameter unverändert für Finalmessung gesperrt",
            "pilot_is_not_final_measurement": True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true", help="ein Warmup, drei Messungen; Parameter vor Finalmessung sperren")
    args = parser.parse_args()
    output = ROOT / "ergebnisse/messungen" / ("03_pilot" if args.pilot else "03_boolesche_mehrwortsuche")
    if not args.pilot:
        require_pilot(ROOT / "ergebnisse/messungen/03_pilot/pilot_decision.json")
    output.mkdir(parents=True, exist_ok=True)
    plan = MeasurementPlan(warmups=1, repeats=3, query_block_size=5) if args.pilot else MeasurementPlan(query_block_size=5)
    timing_run(output, plan, args.pilot)
    print(f"Gespeichert: {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
