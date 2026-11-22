#!/usr/bin/env python3
"""Reihe 03b: Galloping Search gegen Zwei-Zeiger (Pilot, gesperrter Zeitlauf, Diagnose)."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

HERE = Path(__file__).resolve().parent
# Eigener Ordner und Reihe-03-Ordner (Diagnosemodul) nur anhängen: gleichnamige
# Skripte der Reihe 03 (run, verify_results, analyse) dürfen nichts verdecken.
for _directory in (HERE, HERE.parent):
    if str(_directory) not in sys.path:
        sys.path.append(str(_directory))

from gemeinsam import load_corpus, prepare_corpus  # noqa: E402
from gemeinsam.messung import (  # noqa: E402
    MeasurementPlan, measure_phase, summarize_measurements, write_measurements,
)
from invertierter_index import build_inverted_index  # noqa: E402
from boolesche_suche import normalize_terms, search_direct_boolean, search_index_boolean  # noqa: E402

from galloping_generator import (  # noqa: E402
    CASES, DOCUMENT_COUNT, FILLER_WORDS, SHORT_LENGTH, STAGES, TOKENS_PER_DOCUMENT,
    expected_and, generate_corpus, long_word, short_word,
)
from boolean_diagnostics import diagnose_postings, diagnose_postings_galloping  # noqa: E402
import messlauf03  # noqa: E402


ROOT = HERE.parents[3]
STANDARD_PILOT = "03b_pilot"
STANDARD_FINAL = "03b_galloping"
# Standardordner; abweichende Namen über --ausgabe/--pilot-ordner bzw. --eingabe.
PILOT_DIRECTORY = messlauf03.MESSUNGEN / STANDARD_PILOT
FINAL_DIRECTORY = messlauf03.MESSUNGEN / STANDARD_FINAL
ALGORITHMS = ("and_galloping", "and_shortest_first")
VARIANT_OF = {"and_shortest_first": "shortest_first", "and_galloping": "galloping"}
REQUIRED_HASH_SEED = messlauf03.REQUIRED_HASH_SEED
PARAMETERS = {
    "seed": 20261006,
    "synthetic": {"dataset_id": "galloping_controlled", "document_count": DOCUMENT_COUNT,
                  "tokens_per_document": TOKENS_PER_DOCUMENT, "filler_words": FILLER_WORDS},
    "operator": "AND", "term_count": 2, "query_order": "short word first, then long word",
    "long_document_frequencies": list(STAGES), "short_document_frequency": SHORT_LENGTH,
    "cases": {"verteilt": "short list = long-list entries at (j+1)*df/10-1, j=0..9; last entry of long list included",
              "anfang": "short list = first 10 entries of long list"},
    "algorithms": {"and_shortest_first": "search_index_boolean(..., 'AND', 'shortest_first'); two-pointer intersect_sorted",
                   "and_galloping": "search_index_boolean(..., 'AND', 'galloping'); intersect_galloping"},
    "final_plan": asdict(MeasurementPlan(query_block_size=5)),
    "schedule": "shuffle all (algorithm,query) blocks per repetition; fixed seed",
    "generator": "fixed membership recipes; 100 tokens/doc; all query/filler tokens four ASCII characters; "
                 "seeded filler and position shuffle; uppercase + punctuation; fixed-width file names",
    "direct_search": "search_direct_boolean only as correctness check before the first timer; not timed",
    "required_python_hash_seed": REQUIRED_HASH_SEED,
}


@dataclass(frozen=True)
class GallopingQuery:
    query_id: str
    terms: tuple[str, ...]
    case: str
    stage: int
    long_document_frequency: int
    expected_ids: tuple[str, ...]

    @property
    def text(self):
        return json.dumps(self.terms, ensure_ascii=False, separators=(",", ":"))


write_json = messlauf03.write_json
sha = messlauf03.sha


def code_hashes():
    """Gebundener Messcode: Such-/Indexpakete, gemeinsame Messung, 03b-Skripte, Diagnose."""
    files = {*ROOT.glob("gemeinsam/src/gemeinsam/*.py"),
             *ROOT.glob("themen/02_invertierter_index_einzelwortsuche/src/invertierter_index/*.py"),
             *ROOT.glob("themen/03_boolesche_mehrwortsuche/src/boolesche_suche/*.py"),
             *HERE.glob("*.py"), HERE.parent / "boolean_diagnostics.py", HERE.parent / "messlauf03.py",
             ROOT / "gemeinsam/__init__.py", ROOT / "pyproject.toml", ROOT / "requirements-dev.txt"}
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(files) if path.is_file()}


def make_queries(membership):
    queries = []
    for case in CASES:
        for stage, df in enumerate(STAGES):
            terms = (short_word(case, stage), long_word(stage))
            queries.append(GallopingQuery(f"{case}_df{df:05d}", terms, case, stage, df,
                                          expected_and(membership, terms)))
    return queries


def independent_postings(tokens_by_id):
    """Referenzpostings aus den geplanten Tokenfolgen, nicht aus dem Suchindex."""
    postings = {}
    for identifier in sorted(tokens_by_id):
        for word in set(tokens_by_id[identifier]):
            postings.setdefault(word, []).append(identifier)
    return {word: tuple(ids) for word, ids in postings.items()}


def query_metadata(query, postings):
    normalized = normalize_terms(query.terms)
    two_pointer = diagnose_postings(postings, normalized, "AND", "shortest_first")
    galloping = diagnose_postings_galloping(postings, normalized)
    assert tuple(two_pointer["result_ids"]) == query.expected_ids
    assert tuple(galloping["result_ids"]) == query.expected_ids
    del two_pointer["result_ids"], galloping["result_ids"]
    return {"query_id": query.query_id, "terms": list(query.terms), "normalized_terms": list(normalized),
            "operator": "AND", "case": query.case, "stage": query.stage,
            "long_document_frequency": query.long_document_frequency, "text": query.text,
            "posting_lengths_input_order": [len(postings.get(term, ())) for term in normalized],
            "expected_ids": list(query.expected_ids), "hit_count": len(query.expected_ids),
            "diagnostics": {"and_shortest_first": two_pointer, "and_galloping": galloping}}


def validate_dataset(identifier, directory, tokens_by_id, membership):
    """Vollständige Prüfung vor dem ersten Timer; liefert die Datensatzbeschreibung."""
    raw = load_corpus(directory)
    prepared = prepare_corpus(raw)
    assert {doc.document_id: doc.tokens for doc in prepared} == tokens_by_id, \
        "Aufbereitung weicht von unabhängigen Tokenfolgen ab"
    postings = independent_postings(tokens_by_id)
    assert all(postings.get(term, ()) == ids for term, ids in membership.items()), "Pflanzplan verletzt"
    index = build_inverted_index(prepared)
    assert dict(index) == postings, "Index weicht von unabhängiger Referenz ab"
    queries = make_queries(membership)
    fixed_index = dict(index)
    for query in queries:
        assert len(query.expected_ids) == SHORT_LENGTH, "kurze Liste muss Teilmenge der langen sein"
        # Direkte Suche nur zur Trefferprüfung, nicht zeitlich gemessen.
        assert search_direct_boolean(prepared, query.terms, "AND") == list(query.expected_ids)
        for algorithm in ALGORITHMS:
            assert search_index_boolean(index, query.terms, "AND", VARIANT_OF[algorithm]) == list(query.expected_ids)
    assert dict(index) == fixed_index
    files = [{"document_id": doc.document_id, "source_path": doc.source_path,
              "bytes": len(doc.raw_text.encode("utf-8")),
              "sha256": hashlib.sha256(doc.raw_text.encode("utf-8")).hexdigest()} for doc in raw]
    encoded = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    dataset = {"dataset_id": identifier, "kind": "generated", "files": files,
               "corpus_sha256": hashlib.sha256(encoded).hexdigest(), "document_count": len(raw),
               "text_bytes": sum(entry["bytes"] for entry in files),
               "token_count": sum(len(doc.tokens) for doc in prepared), "vocabulary_size": len(postings),
               "membership_document_frequencies": {word: len(ids) for word, ids in sorted(membership.items())},
               "membership_sha256": hashlib.sha256(json.dumps(
                   {word: list(ids) for word, ids in sorted(membership.items())},
                   separators=(",", ":")).encode()).hexdigest(),
               "queries": [query_metadata(query, postings) for query in queries]}
    return raw, prepared, index, queries, dataset


def measure_comparison(operations, queries, plan, context):
    """Alle (Verfahren, Anfrage)-Blöcke je Wiederholung mit festem Seed gemischt."""
    assert len({query.query_id for query in queries}) == len(queries), "query_id muss eindeutig sein"
    tasks = [(algorithm, query) for algorithm in sorted(operations) for query in queries]
    rng = random.Random(plan.seed)
    rows = []
    for iteration in range(-plan.warmups, plan.repeats):
        order = list(tasks)
        rng.shuffle(order)
        for position, (algorithm, query) in enumerate(order):
            operation = operations[algorithm]
            start = perf_counter_ns()
            results = [operation(query.terms) for _ in range(plan.query_block_size)]
            elapsed = perf_counter_ns() - start
            for result in results:
                if result != list(query.expected_ids):
                    raise AssertionError(f"{algorithm}/{query.query_id}: falsche vollständige Treffer")
            if iteration >= 0:
                rows.append({**context, "algorithm": algorithm, "phase": "query", "query_id": query.query_id,
                             "query_text": query.text, "query_type": "and", "repeat": iteration,
                             "order_index": position, "block_size": plan.query_block_size, "elapsed_ns": elapsed,
                             "query_ms": elapsed / 1_000_000 / plan.query_block_size,
                             "hit_count": len(query.expected_ids), "correct": True})
            # Ergebnisse vor dem nächsten Timer freigeben.
            del result, results
    return rows


def metadata(plan, output, pilot, background=messlauf03.PLANNED_BACKGROUND, pilot_reference=None):
    hashes = code_hashes()
    messlauf03.archive_sources(output, hashes)
    info = {"run_id": "03b_pilot" if pilot else "03b_final", **messlauf03.run_header(output, pilot, background),
            "code_sha256": hashes, "source_archive": "code_source/", "parameters": PARAMETERS,
            "measurement_plan": asdict(plan),
            "timer": "time.perf_counter_ns; integer elapsed_ns per complete block",
            "cache": "prepared corpus and prechecked index reused; no cold-cache measurement; load includes OS cache effects",
            "timing_boundaries": {
                "load": "complete public load_corpus on fixed disk files",
                "preparation": "complete public prepare_corpus on already loaded raw documents",
                "build": "complete public build_inverted_index on prepared documents",
                "query": "complete public search_index_boolean including query normalization, posting gathering, "
                         "stable length sort, intersection and full fresh result list",
                "block": "five complete identical calls retained then checked; previous results deleted before next timer",
                "excluded": "generation, direct-search correctness check, diagnostics, disk output, summary and plotting; "
                            "no memory instrumentation"},
            "statistics": "median, inclusive Q1/Q3, IQR; one block is one sample; quartiles are not confidence intervals",
            "memory": "not measured in series 03b; CSV index_bytes and peak_memory_bytes remain empty",
            "datasets": []}
    if pilot_reference is not None:
        info["pilot_reference"] = pilot_reference
    return info


def require_pilot(path):
    """Finalmessung nur nach erfolgreichem Pilot mit gleichen Parametern, Code und Hashseed."""
    return messlauf03.require_pilot(path, PARAMETERS, code_hashes())


def timing_run(output, plan, pilot, background=messlauf03.PLANNED_BACKGROUND, pilot_reference=None):
    info = metadata(plan, output, pilot, background, pilot_reference)
    rows = []
    with TemporaryDirectory(prefix="textsuche-03b-") as temporary:
        generated = generate_corpus(Path(temporary) / "galloping", seed=PARAMETERS["seed"])
        identifier = PARAMETERS["synthetic"]["dataset_id"]
        directory = generated.root
        raw, prepared, index, queries, description = validate_dataset(
            identifier, directory, generated.expected_tokens, generated.membership)
        assert {entry["document_id"]: entry["sha256"] for entry in description["files"]} == generated.file_sha256
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
        operations = {
            "and_shortest_first": lambda terms: search_index_boolean(index, terms, "AND", "shortest_first"),
            "and_galloping": lambda terms: search_index_boolean(index, terms, "AND", "galloping"),
        }
        rows.extend(measure_comparison(operations, queries, plan, context))
    assert code_hashes() == info["code_sha256"], "Code während Messung geändert"
    write_measurements(output / "raw.csv", rows)
    write_json(output / "summary.json", summarize_measurements(rows))
    info["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "metadata.json", info)
    if pilot:
        write_json(output / "pilot_decision.json", {
            "pilot_correct": True, "locked_parameters": PARAMETERS, "method_code_sha256": info["code_sha256"],
            "pilot_plan": asdict(plan), "python_hash_seed": info["environment"]["python_hash_seed"],
            "decision": "Pflanzplan, Treffer und Diagnosen korrekt; Parameter unverändert für Finalmessung gesperrt",
            "pilot_is_not_final_measurement": True})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    messlauf03.add_run_options(parser, STANDARD_PILOT, STANDARD_FINAL)
    args = parser.parse_args(argv)
    if args.replace_pilot and not args.pilot:
        parser.error("--replace-pilot ist nur zusammen mit --pilot zulässig.")
    output = messlauf03.directory_name(args.ausgabe or (STANDARD_PILOT if args.pilot else STANDARD_FINAL))
    messlauf03.check_output(output, pilot=args.pilot, replace_pilot=args.replace_pilot)
    messlauf03.require_hash_seed()
    pilot_reference = None
    if not args.pilot:
        pilot = messlauf03.pilot_directory(args.pilot_ordner, output)
        pilot_reference = require_pilot(pilot / "pilot_decision.json")
    messlauf03.prepare_output(output, pilot=args.pilot, replace_pilot=args.replace_pilot)
    plan = MeasurementPlan(warmups=1, repeats=3, query_block_size=5) if args.pilot else MeasurementPlan(query_block_size=5)
    timing_run(output, plan, args.pilot, args.hintergrundlast, pilot_reference)
    print(f"Gespeichert: {messlauf03.display(output)}")


if __name__ == "__main__":
    main()
