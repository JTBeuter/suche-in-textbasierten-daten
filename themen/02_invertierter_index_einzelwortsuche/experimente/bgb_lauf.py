#!/usr/bin/env python3
"""Reihe 02, Realteil BGB: Indexaufbau auf Teilmengen und Einzelwortsuche.

Misst ausschließlich den realen BGB-Korpus (daten/real/bgb/dokumente, ein
Paragraph je Dokument); die synthetischen Reihen 02 werden nicht neu
gemessen. Teil 1: Aufbauzeit von build_inverted_index für die ersten 250,
500, 1.000, 1.500, 2.000 und alle 2.486 Paragraphen (Kennungsordnung =
Gesetzesreihenfolge), damit der Wortschatz V gegen N sichtbar wird (Heaps).
Teil 2: direkte Suche gegen Index auf dem ganzen BGB für die Anfragen der
Reihen 01b und 02. Teil 3: gehaltener und Spitzenspeicher je Teilmenge in
einem eigenen Python-Prozess nach dem Zeitlauf, wie Reihe 02.

Vor jeder Messung werden Dateien, Korpushash, eine unabhängige Regex-
Tokenisierung, D/N/V/P je Teilmenge und alle Trefferlisten gegen Manifest und
Anfragevorschläge geprüft. Pilot und Hauptlauf schreiben in neue Ordner unter
ergebnisse/messungen (Standard 02_bgb_pilot und 02_bgb); vorhandene
nicht-leere Ordner werden nie überschrieben. --pruefen NAME prüft einen Lauf.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.util
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import random
import re
from statistics import median, quantiles
import subprocess
import sys
from time import get_clock_info
import unicodedata

from gemeinsam import load_corpus, prepare_corpus
from gemeinsam.messung import (CSV_FIELDS, MeasurementPlan, QuerySpec, measure_phase,
                              summarize_measurements, write_measurements)
from direkte_suche import search_direct_word
from invertierter_index import InvertedIndex, build_inverted_index, search_index_word


EXPERIMENTS = Path(__file__).resolve().parent
ROOT = EXPERIMENTS.parents[2]
MESSUNGEN = ROOT / "ergebnisse/messungen"
STANDARD_PILOT = "02_bgb_pilot"
STANDARD_FINAL = "02_bgb"
ALGORITHMS = ("direct_word", "inverted_index")
PLANNED_BACKGROUND = (
    "planned protocol: no parallel project tests, PDF builds or other benchmark series; "
    "ordinary desktop background load; machine not isolated; not checked by the script"
)
PARAMETERS = {
    "dataset": "bgb-gesetze-im-internet-v1",
    "corpus_root": "daten/real/bgb/dokumente",
    "manifest": "daten/real/bgb/manifest.json",
    "proposals": "daten/real/bgb/anfragevorschlaege.json",
    "corpus_sha256": "dc1641fd49dfa45270a1865f454abd64cf7cf94d79b37af9657ff97d7602eadf",
    "subset_sizes": [250, 500, 1000, 1500, 2000, 2486],
    "subset_selection": "first k documents in document-ID byte order, which is the order of the law",
    # Anfragen der Reihen 01b (Beginn, der, Erbschaftskauf, Server) und 02 (Fehler, Verbindung, Unauffindbar).
    "queries": [
        {"query_id": "beginn", "text": "Beginn", "role": "early hit, series 01b"},
        {"query_id": "der", "text": "der", "role": "most frequent word, series 01b"},
        {"query_id": "erbschaftskauf", "text": "Erbschaftskauf", "role": "only in last document, series 01b"},
        {"query_id": "server", "text": "Server", "role": "missing, series 01b"},
        {"query_id": "fehler", "text": "Fehler", "role": "series 02 query word, rare in BGB"},
        {"query_id": "verbindung", "text": "Verbindung", "role": "series 02 query word, rare in BGB"},
        {"query_id": "unauffindbar", "text": "Unauffindbar", "role": "series 02 query word, missing"},
    ],
    "final_plan": asdict(MeasurementPlan()),
    "pilot_plan": asdict(MeasurementPlan(warmups=1, repeats=3)),
    "memory_repeats": 3,
    "schedule": "subset builds ascending with measure_phase; then all (algorithm, query) blocks on the full "
                "corpus shuffled once per warmup/repetition with fixed seed (measure_comparison of series 02)",
}
PLANS = {"final": PARAMETERS["final_plan"], "pilot": PARAMETERS["pilot_plan"]}
FULL = f"bgb_d{PARAMETERS['subset_sizes'][-1]:04d}"


def _load_series02():
    """run.py und memory.py der Reihe 02 per Dateipfad laden.

    run.py importiert generator und memory über einfache Modulnamen. Während
    des Ladens zeigen diese Namen auf die Dateien der Reihe 02, damit kein
    gleichnamiges Modul eines anderen Themas eingebunden wird.
    """
    names = {"generator": "experiment02_bgb_generator", "memory": "experiment02_bgb_memory",
             "run": "experiment02_bgb_run"}
    if names["run"] in sys.modules:
        return sys.modules[names["run"]], sys.modules[names["memory"]]
    saved = {plain: sys.modules.get(plain) for plain in ("generator", "memory")}
    try:
        for plain in ("generator", "memory", "run"):
            spec = importlib.util.spec_from_file_location(names[plain], EXPERIMENTS / f"{plain}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[names[plain]] = module
            if plain != "run":
                sys.modules[plain] = module
            spec.loader.exec_module(module)
    finally:
        for plain, module in saved.items():
            if module is None:
                sys.modules.pop(plain, None)
            else:
                sys.modules[plain] = module
    return sys.modules[names["run"]], sys.modules[names["memory"]]


SERIES02, MEMORY02 = _load_series02()
MEMORY_FIELDS = SERIES02.MEMORY_FIELDS


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def code_hashes() -> dict[str, str]:
    files = {*ROOT.glob("gemeinsam/src/gemeinsam/*.py"),
             *ROOT.glob("themen/01_textaufbereitung_direkte_suche/src/direkte_suche/*.py"),
             *ROOT.glob("themen/02_invertierter_index_einzelwortsuche/src/invertierter_index/*.py"),
             ROOT / "gemeinsam/__init__.py", ROOT / "pyproject.toml", ROOT / "requirements-dev.txt",
             Path(__file__).resolve(), EXPERIMENTS / "run.py", EXPERIMENTS / "memory.py",
             EXPERIMENTS / "generator.py"}
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(files) if path.is_file()}


def python_hash_seed() -> str:
    """Tatsächlicher PYTHONHASHSEED; "random", wenn die Variable fehlt."""
    return os.environ.get("PYTHONHASHSEED", "random")


def target_directory(name: str) -> Path:
    """Neuer Ergebnisordner unter ergebnisse/messungen; nie Überschreiben."""
    if not name or name in {".", ".."} or Path(name).name != name or "/" in name or "\\" in name:
        raise SystemExit(f"Ungültiger Ordnername {name!r}: genau ein Name unter ergebnisse/messungen erwartet.")
    target = MESSUNGEN / name
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise SystemExit(f"{_display(target)} existiert und ist nicht leer; "
                         "vorhandene Ergebnisse werden nicht überschrieben. Neuen Namen mit --ausgabe wählen.")
    return target


def require_pilot(path: Path) -> dict:
    """Hauptlauf nur nach erfolgreichem Pilot mit identischen Bedingungen."""
    if not path.is_file():
        raise SystemExit("Zuerst --pilot ausführen: erfolgreicher Pilot muss Parameter sperren.")
    decision = json.loads(path.read_text(encoding="utf-8"))
    if decision.get("pilot_correct") is not True or decision.get("locked_parameters") != PARAMETERS:
        raise SystemExit("Erfolgreicher Pilot mit genau diesen Parametern fehlt; Pilot erneut ausführen.")
    if decision.get("method_code_sha256") != code_hashes():
        raise SystemExit("Messcode hat sich nach dem Pilot geändert; Pilot in neuen Ordner erneut ausführen.")
    if decision.get("python_hash_seed") != python_hash_seed():
        raise SystemExit("PYTHONHASHSEED weicht vom Pilot ab; mit demselben Wert wie im Pilot starten.")
    return decision


# --- Unabhängige Erwartungen -------------------------------------------------

def independent_tokens(text: str) -> tuple[str, ...]:
    """Regex-Gegenprobe zu gemeinsam.tokenize (L* und Nd ohne M*, No, Nl)."""
    normalized = unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).casefold())
    if any(unicodedata.category(character)[0] == "M" or unicodedata.category(character) in {"No", "Nl"}
           for character in normalized):
        raise AssertionError("Regex-Gegenprobe gilt nur ohne M*, No und Nl")
    return tuple(re.findall(r"[^\W_]+", normalized))


def canonical_corpus_sha256(hashes: dict[str, str]) -> str:
    """SHA-256 über '<sha256>  <dateiname>\\n' in Bytereihenfolge (wie Manifest)."""
    lines = "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def check_document_list(identifiers: list[str], entry: dict) -> None:
    """Vollständige Liste oder Anzahl, Hash und Ränder wie im Manifest."""
    if "document_ids" in entry:
        if identifiers != entry["document_ids"]:
            raise AssertionError(f"{entry['query']}: Dokumentliste weicht von der unabhängigen Erwartung ab")
    elif (len(identifiers) != entry["document_ids_count"]
          or hashlib.sha256("\n".join(identifiers).encode("utf-8")).hexdigest() != entry["document_ids_sha256"]
          or identifiers[:5] != entry["document_ids_first5"] or identifiers[-5:] != entry["document_ids_last5"]):
        raise AssertionError(f"{entry['query']}: Dokumentliste weicht von Anzahl/Hash der Erwartung ab")
    if len(identifiers) != entry["df"]:
        raise AssertionError(f"{entry['query']}: df weicht ab")


def subset_statistics(tokens: dict[str, tuple[str, ...]], identifiers: list[str]) -> dict:
    vocabulary: set[str] = set()
    postings = 0
    for identifier in identifiers:
        distinct = set(tokens[identifier])
        postings += len(distinct)
        vocabulary |= distinct
    return {"D": len(identifiers), "N": sum(len(tokens[identifier]) for identifier in identifiers),
            "V": len(vocabulary), "P": postings}


def rank_frequency(tokens: dict[str, tuple[str, ...]]) -> list[dict]:
    """cf/df je Term, Rang nach cf absteigend, Gleichstand nach Term (wie Manifest)."""
    cf: dict[str, int] = defaultdict(int)
    df: dict[str, int] = defaultdict(int)
    for sequence in tokens.values():
        for token in sequence:
            cf[token] += 1
        for token in set(sequence):
            df[token] += 1
    ordered = sorted(cf, key=lambda term: (-cf[term], term))
    return [{"rank": rank, "term": term, "cf": cf[term], "df": df[term]} for rank, term in enumerate(ordered, 1)]


def bgb_reference() -> dict:
    """Prüft Dateien gegen Manifest und berechnet unabhängige Tokens und Erwartungen."""
    manifest_path, proposals_path = ROOT / PARAMETERS["manifest"], ROOT / PARAMETERS["proposals"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    proposals = json.loads(proposals_path.read_text(encoding="utf-8"))
    expectations = manifest["independent_expectations"]
    if not (manifest["dataset_id"] == proposals["dataset_id"] == PARAMETERS["dataset"]
            and manifest["corpus_sha256"] == proposals["corpus_sha256"] == expectations["corpus_sha256"]
            == PARAMETERS["corpus_sha256"]):
        raise AssertionError("BGB-Manifest oder Anfragevorschläge gehören zu einem anderen Datenstand")
    root = ROOT / PARAMETERS["corpus_root"]
    texts, hashes = {}, {}
    for entry in manifest["documents"]:
        payload = (root / entry["source_path"]).read_bytes()
        if len(payload) != entry["bytes"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise AssertionError(f"BGB-Datei weicht vom Manifest ab: {entry['document_id']}")
        texts[entry["document_id"]], hashes[entry["document_id"]] = payload.decode("utf-8"), entry["sha256"]
    if sorted(path.name for path in root.iterdir() if path.is_file() and path.suffix == ".txt") != sorted(texts):
        raise AssertionError("BGB-Korpusordner enthält andere Dateien als das Manifest")
    if canonical_corpus_sha256(hashes) != PARAMETERS["corpus_sha256"]:
        raise AssertionError("BGB: kanonischer Korpushash weicht ab")
    identifiers = sorted(texts)
    tokens = {identifier: independent_tokens(texts[identifier]) for identifier in identifiers}
    full = subset_statistics(tokens, identifiers)
    if [full[key] for key in "DNVP"] != [expectations[key] for key in
                                         ("document_count", "token_count", "vocabulary_size", "posting_count")]:
        raise AssertionError("BGB: D/N/V/P der unabhängigen Tokenisierung weichen vom Manifest ab")
    proposals_02 = proposals["reihe_02_index_teilmengen"]
    if [entry["D"] for entry in proposals_02] != PARAMETERS["subset_sizes"]:
        raise AssertionError("Teilmengengrößen weichen von den Anfragevorschlägen ab")
    subsets = []
    for size, entry in zip(PARAMETERS["subset_sizes"], proposals_02):
        chosen = identifiers[:size]
        statistics = subset_statistics(tokens, chosen)
        raw_bytes = sum(len(texts[identifier].encode("utf-8")) for identifier in chosen)
        if (statistics != {key: entry[key] for key in "DNVP"} or raw_bytes != entry["raw_bytes"]
                or chosen[0] != entry["first_document_id"] or chosen[-1] != entry["last_document_id"]):
            raise AssertionError(f"Teilmenge {size}: D/N/V/P oder Ränder weichen von den Anfragevorschlägen ab")
        subsets.append({"dataset_id": f"bgb_d{size:04d}", "document_count": size, "token_count": statistics["N"],
                        "vocabulary_size": statistics["V"], "posting_count": statistics["P"], "text_bytes": raw_bytes,
                        "first_document_id": chosen[0], "last_document_id": chosen[-1],
                        "proposal_subset": entry["subset"]})
    words = {entry["query"]: entry for entry in expectations["words"]}
    proposals_01 = {entry["query"]: entry for entry in proposals["reihe_01_direkte_suche"]}
    queries = []
    for item in PARAMETERS["queries"]:
        entry = words[item["text"]]
        (term,) = independent_tokens(item["text"])
        if term != entry["term"]:
            raise AssertionError(f"{item['text']}: unabhängige Normalform weicht ab")
        hits = [identifier for identifier in identifiers if term in tokens[identifier]]
        check_document_list(hits, entry)
        occurrences = sum(sequence.count(term) for sequence in tokens.values())
        visited = sum(tokens[identifier].index(term) + 1 if term in tokens[identifier] else len(tokens[identifier])
                      for identifier in identifiers)
        if occurrences != entry["cf"]:
            raise AssertionError(f"{item['text']}: cf weicht vom Manifest ab")
        if hits and (hits[0] != entry["first_document"] or tokens[hits[0]].index(term) != entry["first_position"]):
            raise AssertionError(f"{item['text']}: erste Position weicht vom Manifest ab")
        if item["text"] in proposals_01 and visited != proposals_01[item["text"]]["scanned_tokens_direct"]:
            raise AssertionError(f"{item['text']}: Tokenvergleiche der direkten Suche weichen ab")
        queries.append({**item, "query_type": "word", "normalized_token_expected": term,
                        "expected_ids": hits, "document_frequency": len(hits), "occurrences": occurrences,
                        "first_document": hits[0] if hits else None,
                        "first_position": tokens[hits[0]].index(term) if hits else None,
                        "direct_visited_tokens": visited})
    ranks = rank_frequency(tokens)
    for entry in expectations["rank_frequency"]:
        if ranks[entry["rank"] - 1] != {key: entry[key] for key in ("rank", "term", "cf", "df")}:
            raise AssertionError(f"Rang {entry['rank']}: Rang-Häufigkeit weicht vom Manifest ab")
    source = {"dataset": PARAMETERS["dataset"], "corpus_root": PARAMETERS["corpus_root"],
              "manifest_path": PARAMETERS["manifest"], "manifest_sha256": sha(manifest_path),
              "proposals_path": PARAMETERS["proposals"], "proposals_sha256": sha(proposals_path),
              "corpus_sha256": PARAMETERS["corpus_sha256"], "document_count": full["D"], "token_count": full["N"],
              "vocabulary_size": full["V"], "posting_count": full["P"]}
    return {"source": source, "tokens": tokens, "hashes": hashes, "subsets": subsets, "queries": queries,
            "ranks": ranks}


def prepared_corpus(reference: dict):
    """Produktive Aufbereitung des ganzen BGB, gegen die Gegenprobe geprüft."""
    raw = load_corpus(ROOT / PARAMETERS["corpus_root"])
    prepared = prepare_corpus(raw)
    if {document.document_id: document.tokens for document in prepared} != reference["tokens"]:
        raise AssertionError("Aufbereitung weicht von der unabhängigen Tokenisierung ab")
    if {document.document_id: hashlib.sha256(document.raw_text.encode("utf-8")).hexdigest()
            for document in raw} != reference["hashes"]:
        raise AssertionError("Geladene Texte weichen von den Manifest-Prüfsummen ab")
    return prepared


# --- Messung ------------------------------------------------------------------

def make_metadata(plan: MeasurementPlan, pilot: bool, output: Path, background: str) -> dict:
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
    if Path("/proc/cpuinfo").is_file():
        cpu = next((line.partition(":")[2].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")), cpu)
    total_memory = next((line for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemTotal:")), "unknown") if Path("/proc/meminfo").is_file() else "unknown"
    return {
        "run_id": output.name, "run_kind": "pilot" if pilot else "final", "output_directory": _display(output),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
        "git_status_at_start": git("status", "--porcelain"), "code_sha256": hashes, "source_archive": "code_source/",
        "parameters": PARAMETERS, "measurement_plan": asdict(plan),
        "environment": {"python": sys.version, "implementation": platform.python_implementation(),
                        "platform": platform.platform(), "machine": platform.machine(), "cpu_model": cpu,
                        "memory_total": total_memory, "logical_cpus": os.cpu_count(),
                        "python_hash_seed": python_hash_seed(),
                        "python_hash_seed_set": "PYTHONHASHSEED" in os.environ,
                        "unicode_database": unicodedata.unidata_version,
                        "matplotlib": version("matplotlib"), "pytest": version("pytest")},
        "timer": "time.perf_counter_ns; integer elapsed_ns per complete build or query block",
        "clock": vars(get_clock_info("perf_counter")),
        "background_load": background,
        "cache": "corpus loaded and prepared once before timing; prepared subsets and full index reused; no cold-cache claim",
        "timing_boundaries": {
            "build": "complete public build_inverted_index on already prepared first-k documents; check after timer",
            "query": "public search_direct_word or search_index_word on the full BGB; normalization and full fresh "
                     "sorted result list included; query_block_size complete calls retained then checked",
            "excluded": "loading, preparation, independent tokenization, expectation checks, memory profiling, output",
        },
        "statistics": "median, inclusive Q1/Q3, IQR=Q3-Q1; one block is one sample; quartiles are not confidence intervals",
        "memory": {"separate_process": True, "repeats": PARAMETERS["memory_repeats"],
                   "retained_traced_bytes": "tracemalloc current_after_build-current_before_build; tracer starts after preparation",
                   "peak_traced_bytes": "peak_since_reset-current_before_build; includes transient build allocations",
                   "exclusive_index_bytes": "sys.getsizeof unique index/proxy/dict/tuple/str objects, excluding corpus strings",
                   "limitations": "Python traced allocations and object graph estimates (memory.py of series 02), not RSS"},
        "interpretation_limits": [
            "Subsets are nested prefixes in the order of the law, not random samples; topic changes along the law.",
            "Real paragraphs have very unequal lengths (8 to 1168 tokens).",
            "Heaps fit over six nested subsets is descriptive, not a statistical model test.",
            "Expected postings derive from an independent regex tokenization checked against manifest counts.",
        ],
        "source": None, "datasets": [], "queries": [],
    }


def timing_run(output: Path, plan: MeasurementPlan, pilot: bool, background: str) -> tuple[list, dict, dict]:
    reference = bgb_reference()
    prepared = prepared_corpus(reference)
    metadata = make_metadata(plan, pilot, output, background)
    metadata["source"] = reference["source"]
    metadata["datasets"] = reference["subsets"]
    metadata["queries"] = reference["queries"]
    rows = []
    base = {"run_id": metadata["run_id"], "git_commit": metadata["git_commit"], "seed": plan.seed}
    for subset in reference["subsets"]:
        chosen = prepared[:subset["document_count"]]
        expected = SERIES02.linear_expected_postings(
            {document.document_id: reference["tokens"][document.document_id] for document in chosen})
        if dict(build_inverted_index(chosen)) != expected:
            raise AssertionError(f"{subset['dataset_id']}: Index verletzt die unabhängigen Sollpostings")
        context = {**base, "dataset_id": subset["dataset_id"], "document_count": subset["document_count"],
                   "text_bytes": subset["text_bytes"], "token_count": subset["token_count"],
                   "algorithm": "inverted_index"}

        def validate(observed, expected=expected):
            if type(observed) is not InvertedIndex or dict(observed) != expected:
                raise AssertionError("Zeitlauf-Build weicht von unabhängigen Postings ab")

        print(f"{subset['dataset_id']}: D={subset['document_count']}, N={subset['token_count']}, "
              f"V={subset['vocabulary_size']}, P={subset['posting_count']}; Aufbau", flush=True)
        rows.extend(measure_phase(lambda chosen=chosen: build_inverted_index(chosen), validate, plan,
                                  phase="build", context=context))
        write_measurements(output / "raw.csv", rows)
    full = reference["subsets"][-1]
    index = build_inverted_index(prepared)
    queries = [QuerySpec(item["query_id"], item["text"], "word", tuple(item["expected_ids"]))
               for item in reference["queries"]]
    for query in queries:
        if search_direct_word(prepared, query.text) != list(query.expected_ids) or \
                search_index_word(index, query.text) != list(query.expected_ids):
            raise AssertionError(f"{query.query_id}: Suchverfahren verletzt die unabhängige Erwartung")
    context = {**base, "dataset_id": full["dataset_id"], "document_count": full["document_count"],
               "text_bytes": full["text_bytes"], "token_count": full["token_count"]}
    print(f"{full['dataset_id']}: {len(queries)} Anfragen direkt gegen Index", flush=True)
    rows.extend(SERIES02.measure_comparison({"direct_word": lambda text: search_direct_word(prepared, text),
                                             "inverted_index": lambda text: search_index_word(index, text)},
                                            queries, plan, context))
    if dict(index) != SERIES02.linear_expected_postings(reference["tokens"]):
        raise AssertionError("Abfragefolge verändert den Index")
    if code_hashes() != metadata["code_sha256"]:
        raise SystemExit("Messcode hat sich während des Laufs geändert; Ergebnisse sind nicht zuordenbar.")
    metadata["timing_completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_measurements(output / "raw.csv", rows)
    write_json(output / "metadata.json", metadata)
    return rows, metadata, reference


def memory_run(output: Path) -> None:
    """Getrennter Prozess: drei neue Builds je Teilmenge mit tracemalloc."""
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    if metadata["code_sha256"] != code_hashes():
        raise SystemExit("Code hat sich seit Zeitlauf geändert; getrennten Speicherlauf abgebrochen")
    reference = bgb_reference()
    if reference["subsets"] != metadata["datasets"]:
        raise AssertionError("Speicherlauf benutzt andere Teilmengen als der Zeitlauf")
    prepared = prepared_corpus(reference)
    started = datetime.now(timezone.utc).isoformat()
    rows = []
    for subset in metadata["datasets"]:
        chosen = prepared[:subset["document_count"]]
        expected = SERIES02.linear_expected_postings(
            {document.document_id: reference["tokens"][document.document_id] for document in chosen})
        print(f"{subset['dataset_id']}: getrennter Speicherlauf", flush=True)
        for profile in MEMORY02.profile_index(chosen, expected, repeats=PARAMETERS["memory_repeats"]):
            rows.append({"run_id": metadata["run_id"], "dataset_id": subset["dataset_id"],
                         **{key: subset[key] for key in ("document_count", "token_count", "vocabulary_size",
                                                         "posting_count")}, **profile})
    with (output / "memory.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MEMORY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    write_json(output / "memory.json", {
        "schema": list(MEMORY_FIELDS), "measurement": metadata["memory"], "worker_pid": os.getpid(),
        "started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": rows, "summary": memory_summary(rows, metadata)})


def memory_summary(rows: list[dict], metadata: dict) -> list[dict]:
    return [{"dataset_id": subset["dataset_id"],
             **{f"median_{field}": median(row[field] for row in rows if row["dataset_id"] == subset["dataset_id"])
                for field in ("retained_traced_bytes", "peak_traced_bytes", "exclusive_index_bytes")}}
            for subset in metadata["datasets"]]


def heaps_fit(points: list[tuple[int, int]]) -> dict:
    """Kleinste Quadrate für log V = log K + beta log N (beschreibend)."""
    xs = [math.log(n) for n, _ in points]
    ys = [math.log(v) for _, v in points]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    beta = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / sum((x - mean_x) ** 2 for x in xs)
    return {"beta": beta, "k": math.exp(mean_y - beta * mean_x), "points": len(points),
            "method": "least squares on natural logs of (N, V) over the nested subsets"}


def evaluate(summary: list[dict], metadata: dict, memory: dict, ranks: list[dict]) -> dict:
    """Abgeleitete Kennzahlen; ausschließlich aus summary, memory und Tokens."""
    builds = {row["dataset_id"]: row for row in summary if row["phase"] == "build"}
    memory_by_id = {row["dataset_id"]: row for row in memory["summary"]}
    subsets = []
    for subset in metadata["datasets"]:
        build, stored = builds[subset["dataset_id"]], memory_by_id[subset["dataset_id"]]
        subsets.append({
            **{key: subset[key] for key in ("dataset_id", "document_count", "token_count", "vocabulary_size",
                                            "posting_count")},
            "vocabulary_per_token": subset["vocabulary_size"] / subset["token_count"],
            "build_median_ms": build["median_ms"], "build_q1_ms": build["q1_ms"], "build_q3_ms": build["q3_ms"],
            "build_iqr_ms": build["iqr_ms"],
            "build_median_us_per_posting": build["median_ms"] * 1000 / subset["posting_count"],
            **{f"median_{field}": stored[f"median_{field}"]
               for field in ("retained_traced_bytes", "peak_traced_bytes", "exclusive_index_bytes")},
            "retained_bytes_per_posting": stored["median_retained_traced_bytes"] / subset["posting_count"],
        })
    queries = []
    for query in metadata["queries"]:
        direct, index = (next(row for row in summary if row["phase"] == "query" and row["algorithm"] == algorithm
                              and row["query_id"] == query["query_id"]) for algorithm in ALGORITHMS)
        queries.append({"query_id": query["query_id"], "text": query["text"],
                        "document_frequency": query["document_frequency"], "occurrences": query["occurrences"],
                        "direct_visited_tokens": query["direct_visited_tokens"],
                        "direct_median_ms": direct["median_ms"], "direct_iqr_ms": direct["iqr_ms"],
                        "index_median_ms": index["median_ms"], "index_iqr_ms": index["iqr_ms"],
                        "median_ratio_direct_to_index": direct["median_ms"] / index["median_ms"]})
    return {"run_id": metadata["run_id"], "run_kind": metadata["run_kind"], "subsets": subsets,
            "heaps": heaps_fit([(subset["token_count"], subset["vocabulary_size"]) for subset in metadata["datasets"]]),
            "queries": queries,
            "zipf": {"terms": len(ranks), "cf_by_rank": [entry["cf"] for entry in ranks],
                     "top": ranks[:10], "tie_break": "cf descending, then term"},
            "limits": "medians of separate blocks; ratios are not confidence intervals"
                      + ("; pilot values are not results" if metadata["run_kind"] == "pilot" else "")}


def plots(output: Path, evaluation: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams["svg.hashsalt"] = "textsuche-thema02-bgb"
    subsets = evaluation["subsets"]
    n = [subset["token_count"] for subset in subsets]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.5))
    heaps = evaluation["heaps"]
    axes[0][0].plot(n, [subset["vocabulary_size"] for subset in subsets], marker="o", label="erreichter Wortschatz V")
    axes[0][0].plot(n, [heaps["k"] * value ** heaps["beta"] for value in n], linestyle="--",
                    label=f"Anpassung V = {heaps['k']:.1f} · N^{heaps['beta']:.2f}")
    axes[0][0].plot(n, n, color="grey", linewidth=.8, label="V = N")
    axes[0][0].set(xscale="log", yscale="log", xlabel="Tokens N (erste k Paragraphen)", ylabel="V",
                   title="Wortschatz (Heaps)")
    axes[0][1].plot(n, [subset["build_median_ms"] for subset in subsets], marker="o")
    axes[0][1].fill_between(n, [subset["build_q1_ms"] for subset in subsets],
                            [subset["build_q3_ms"] for subset in subsets], alpha=.18)
    axes[0][1].set(xscale="log", yscale="log", xlabel="Tokens N", ylabel="Aufbau ms",
                   title="Indexaufbau: Median / Quartilsbereich")
    for field, label in (("retained_traced_bytes", "Bleibend (tracemalloc)"), ("peak_traced_bytes", "Spitze (tracemalloc)"),
                         ("exclusive_index_bytes", "Exklusiver Objektgraph")):
        axes[1][0].plot(n, [subset[f"median_{field}"] / 1024 for subset in subsets], marker="o", label=label)
    axes[1][0].set(xscale="log", yscale="log", xlabel="Tokens N", ylabel="Zusätzlicher Index KiB",
                   title="Getrennter Speicherprozess")
    cf = evaluation["zipf"]["cf_by_rank"]
    axes[1][1].plot(range(1, len(cf) + 1), cf)
    axes[1][1].set(xscale="log", yscale="log", xlabel="Rang", ylabel="Vorkommen cf",
                   title="Rang-Häufigkeit, ganzes BGB (Zipf)")
    for row in axes:
        for ax in row:
            ax.grid(True, which="both", alpha=.25)
    axes[0][0].legend(fontsize=8)
    axes[1][0].legend(fontsize=8)
    fig.tight_layout()
    target = output / "abbildungen"
    target.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg"):
        fig.savefig(target / f"02_bgb_teilmengen.{extension}", dpi=180,
                    metadata={"Date": None} if extension == "svg" else {})
    plt.close(fig)


def run(args: argparse.Namespace, *, memory_in_process: bool = False) -> Path:
    output = target_directory(args.ausgabe or (STANDARD_PILOT if args.pilot else STANDARD_FINAL))
    plan = MeasurementPlan(warmups=1, repeats=3) if args.pilot else MeasurementPlan()
    if not args.pilot:
        pilot_directory = MESSUNGEN / args.pilot_ordner
        if Path(args.pilot_ordner).name != args.pilot_ordner or pilot_directory == output:
            raise SystemExit("--pilot-ordner muss ein anderer Ordnername unter ergebnisse/messungen sein.")
        require_pilot(pilot_directory / "pilot_decision.json")
    if python_hash_seed() != "0":
        print(f"Hinweis: PYTHONHASHSEED={python_hash_seed()}; dokumentierte Läufe verwenden PYTHONHASHSEED=0.", flush=True)
    output.mkdir(parents=True, exist_ok=True)
    rows, metadata, reference = timing_run(output, plan, args.pilot, args.hintergrundlast)
    if not args.pilot:
        metadata["pilot_directory"] = _display(MESSUNGEN / args.pilot_ordner)
    summary = summarize_measurements(rows)
    write_json(output / "summary.json", summary)
    write_json(output / "metadata.json", metadata)
    if memory_in_process:
        memory_run(output)
    else:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--speicherlauf", str(output)],
                       cwd=ROOT, check=True)
    memory = json.loads((output / "memory.json").read_text(encoding="utf-8"))
    evaluation = evaluate(summary, metadata, memory, reference["ranks"])
    write_json(output / "auswertung.json", evaluation)
    metadata["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "metadata.json", metadata)
    if args.pilot:
        write_json(output / "pilot_decision.json", {
            "pilot_correct": True, "locked_parameters": PARAMETERS, "method_code_sha256": metadata["code_sha256"],
            "python_hash_seed": metadata["environment"]["python_hash_seed"], "pilot_plan": asdict(plan),
            "decision": "BGB-Dateien, Teilmengen, Treffer und getrennter Speicherprozess ausführbar; Parameter gesperrt",
            "pilot_is_not_final_measurement": True})
    else:
        plots(output, evaluation)
    for subset in evaluation["subsets"]:
        print(f"{subset['dataset_id']}: N={subset['token_count']}, V={subset['vocabulary_size']}, "
              f"Aufbau {subset['build_median_ms']:.2f} ms, bleibend {subset['median_retained_traced_bytes'] / 1024:.0f} KiB",
              flush=True)
    print(f"Heaps-Anpassung: beta={evaluation['heaps']['beta']:.3f}, K={evaluation['heaps']['k']:.2f}", flush=True)
    print(f"Gespeichert: {_display(output)}; {len(rows)} Rohwerte, {len(summary)} Gruppen", flush=True)
    return output


# --- Prüfung ------------------------------------------------------------------

def verify_directory(directory: Path, *, archive_only: bool = False) -> dict:
    """Prüft einen gespeicherten BGB-Lauf ohne neue Zeitmessung."""
    directory = Path(directory)

    def read_csv(name, schema):
        with (directory / name).open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            assert tuple(reader.fieldnames) == tuple(schema), f"abweichendes Schema: {name}"
            return list(reader)

    rows = read_csv("raw.csv", CSV_FIELDS)
    memory_rows = read_csv("memory.csv", MEMORY_FIELDS)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    memory = json.loads((directory / "memory.json").read_text(encoding="utf-8"))
    evaluation = json.loads((directory / "auswertung.json").read_text(encoding="utf-8"))
    assert metadata["parameters"] == PARAMETERS, "Parameter weichen ab"
    assert metadata["run_kind"] in PLANS and metadata["measurement_plan"] == PLANS[metadata["run_kind"]]
    plan = metadata["measurement_plan"]
    repeats = plan["repeats"]
    subsets = {subset["dataset_id"]: subset for subset in metadata["datasets"]}
    queries = {query["query_id"]: query for query in metadata["queries"]}
    expected_keys = {(identifier, "inverted_index", "build", "") for identifier in subsets}
    expected_keys |= {(FULL, algorithm, "query", query_id) for algorithm in ALGORITHMS for query_id in queries}
    assert len(rows) == len(expected_keys) * repeats and len(summary) == len(expected_keys)
    grouped = defaultdict(list)
    for row in rows:
        subset = subsets[row["dataset_id"]]
        phase = row["phase"]
        key = (row["dataset_id"], row["algorithm"], phase, row["query_id"])
        assert key in expected_keys and row["correct"] == "True"
        assert row["run_id"] == metadata["run_id"] and row["git_commit"] == metadata["git_commit"]
        assert int(row["seed"]) == plan["seed"]
        assert all(int(row[field]) == subset[field] for field in ("document_count", "text_bytes", "token_count"))
        elapsed, block = int(row["elapsed_ns"]), int(row["block_size"])
        assert elapsed >= 0 and block > 0
        assert float(row[f"{phase}_ms"]) == elapsed / 1_000_000 / block
        assert all(row[field] == "" for field in ("load_ms", "preparation_ms", "index_bytes", "peak_memory_bytes"))
        assert row["query_ms" if phase == "build" else "build_ms"] == ""
        if phase == "build":
            assert block == 1
            assert all(row[field] == "" for field in ("query_id", "query_type", "query_text", "hit_count", "order_index"))
        else:
            query = queries[row["query_id"]]
            assert block == plan["query_block_size"] and row["query_type"] == "word"
            assert row["query_text"] == query["text"] and int(row["hit_count"]) == len(query["expected_ids"])
        grouped[key].append(row)
    assert set(grouped) == expected_keys
    for result in summary:
        key = (result["dataset_id"], result["algorithm"], result["phase"], result["query_id"])
        group = grouped[key]
        assert sorted(int(row["repeat"]) for row in group) == list(range(repeats))
        values = [float(row[f"{key[2]}_ms"]) for row in group]
        q1, _, q3 = quantiles(values, n=4, method="inclusive")
        assert result["sample_count"] == repeats and result["token_count"] == subsets[key[0]]["token_count"]
        assert result["median_ms"] == median(values) and result["q1_ms"] == q1 and result["q3_ms"] == q3
        assert result["iqr_ms"] == q3 - q1
        assert result["minimum_ms"] == min(values) and result["maximum_ms"] == max(values)
    # Reihenfolge: Teilmengen aufsteigend, danach gemischte Abfrageblöcke wie measure_comparison.
    builds = [row["dataset_id"] for row in rows if row["phase"] == "build"]
    assert builds == [identifier for identifier in subsets for _ in range(repeats)]
    rng = random.Random(plan["seed"])
    tasks = [(algorithm, query_id) for algorithm in ALGORITHMS for query_id in queries]
    for iteration in range(-plan["warmups"], repeats):
        order = list(tasks)
        rng.shuffle(order)
        if iteration < 0:
            continue
        observed = sorted((row for row in rows if row["phase"] == "query" and int(row["repeat"]) == iteration),
                          key=lambda row: int(row["order_index"]))
        assert [int(row["order_index"]) for row in observed] == list(range(len(tasks)))
        assert [(row["algorithm"], row["query_id"]) for row in observed] == order
    assert tuple(memory["schema"]) == MEMORY_FIELDS and memory["measurement"] == metadata["memory"]
    assert len(memory_rows) == len(memory["rows"]) == len(subsets) * PARAMETERS["memory_repeats"]
    assert [{field: str(row[field]) for field in MEMORY_FIELDS} for row in memory["rows"]] == memory_rows
    for row in memory["rows"]:
        subset = subsets[row["dataset_id"]]
        assert row["run_id"] == metadata["run_id"]
        assert all(row[field] == subset[field] for field in ("document_count", "token_count", "vocabulary_size",
                                                             "posting_count"))
        assert row["peak_traced_bytes"] >= row["retained_traced_bytes"] > 0 and row["exclusive_index_bytes"] > 0
    assert memory["summary"] == memory_summary(memory["rows"], metadata)
    assert datetime.fromisoformat(memory["started_at_utc"]) >= datetime.fromisoformat(metadata["timing_completed_at_utc"])
    # Teure Neuberechnung aus den BGB-Dateien erst nach den Rohwertprüfungen.
    reference = bgb_reference()
    assert metadata["source"] == reference["source"], "BGB-Quelle oder Erwartungen geändert"
    assert metadata["datasets"] == reference["subsets"], "Teilmengen weichen von der Neuberechnung ab"
    assert metadata["queries"] == json.loads(json.dumps(reference["queries"])), "Anfragen weichen ab"
    assert evaluation == json.loads(json.dumps(evaluate(summary, metadata, memory, reference["ranks"]))), \
        "Auswertung nicht aus Rohwerten ableitbar"
    changed = []
    for relative, expected in metadata["code_sha256"].items():
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        assert sha(directory / "code_source" / relative) == expected, f"Quelltextarchiv beschädigt: {relative}"
        if sha(ROOT / relative) != expected:
            changed.append(relative)
    if changed and not archive_only:
        raise AssertionError(f"aktiver Code weicht vom gemessenen Stand ab: {', '.join(changed)}")
    environment = metadata["environment"]
    if environment["python_hash_seed"] != "random":
        assert environment["python_hash_seed_set"] is True
    if metadata["run_kind"] == "pilot":
        decision = json.loads((directory / "pilot_decision.json").read_text(encoding="utf-8"))
    else:
        decision = json.loads((MESSUNGEN / Path(metadata["pilot_directory"]).name / "pilot_decision.json")
                              .read_text(encoding="utf-8"))
        for extension in ("png", "svg"):
            assert (directory / "abbildungen" / f"02_bgb_teilmengen.{extension}").is_file()
    assert decision["pilot_correct"] is True and decision["locked_parameters"] == PARAMETERS
    assert decision["method_code_sha256"] == metadata["code_sha256"], "Lauf und Pilot mit verschiedenem Code"
    assert decision["python_hash_seed"] == environment["python_hash_seed"], "Lauf und Pilot mit verschiedenem Hashseed"
    return {"rows": len(rows), "groups": len(summary), "memory_rows": len(memory_rows), "changed_sources": changed,
            "python_hash_seed": environment["python_hash_seed"]}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pilot", action="store_true", help="1 Warmup, 3 Messungen; sperrt Parameter und Code")
    parser.add_argument("--ausgabe", metavar="NAME",
                        help=f"neuer Ordner unter ergebnisse/messungen (Standard {STANDARD_PILOT} bzw. {STANDARD_FINAL})")
    parser.add_argument("--pilot-ordner", metavar="NAME", default=STANDARD_PILOT,
                        help=f"Pilotordner mit pilot_decision.json für den Hauptlauf (Standard {STANDARD_PILOT})")
    parser.add_argument("--hintergrundlast", metavar="TEXT", default=PLANNED_BACKGROUND,
                        help="tatsächliche Hintergrundlast für die Metadaten")
    parser.add_argument("--pruefen", metavar="NAME", help="gespeicherten Lauf prüfen statt messen")
    parser.add_argument("--archive-only", action="store_true",
                        help="mit --pruefen: abweichende aktive Quellen zulassen; Archiv bleibt geprüft")
    parser.add_argument("--speicherlauf", metavar="PFAD", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.speicherlauf:
        memory_run(Path(args.speicherlauf))
        return
    if args.pruefen:
        if Path(args.pruefen).name != args.pruefen:
            raise SystemExit("--pruefen erwartet genau einen Ordnernamen unter ergebnisse/messungen")
        counts = verify_directory(MESSUNGEN / args.pruefen, archive_only=args.archive_only)
        print(f"{args.pruefen}: {counts['rows']} Rohwerte, {counts['groups']} Gruppen, {counts['memory_rows']} "
              "Speicherwerte; Statistik, Reihenfolge, BGB-Dateien/Tokens/Teilmengen/Treffer, Auswertung, "
              f"Quellarchiv und Pilotsperre geprüft; PYTHONHASHSEED={counts['python_hash_seed']}.")
        if counts["changed_sources"]:
            print(f"Nur-Archiv-Modus: aktive Quellen weichen ab: {', '.join(counts['changed_sources'])}")
        return
    run(args)


if __name__ == "__main__":
    main()
