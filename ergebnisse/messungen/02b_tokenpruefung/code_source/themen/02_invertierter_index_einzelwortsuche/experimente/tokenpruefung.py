#!/usr/bin/env python3
"""Zusatzmessung 02b: Anteil der Tokenprüfung an der Aufbauzeit (V-Reihe).

build_inverted_index prüft jedes verschiedene Token einmal mit der zentralen
Tokenisierung (tokenize(token) == (token,)). Diese Messung vergleicht auf den
drei V-Datensätzen der Reihe 02 (N=100.000, D=100, V≈100/1.000/10.000)
(a) die öffentliche Funktion mit (b) einer messinternen Kopie ohne diese
Prüfung. Der Produktionscode bleibt unverändert; die Kopie wird vor jeder
Messung per AST gegen die Produktionsfunktion abzüglich der Prüfung
abgeglichen. Beide Varianten müssen identische Indizes liefern.

Pilot und Hauptlauf schreiben in neue Ordner unter ergebnisse/messungen
(Standard 02b_pilot und 02b_tokenpruefung); vorhandene nicht-leere Ordner
werden nie überschrieben. --pruefen NAME prüft einen gespeicherten Lauf.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from collections.abc import Iterable
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.util
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
from statistics import median, quantiles
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import get_clock_info
from types import MappingProxyType
import unicodedata

from gemeinsam import CorpusError, PreparedDocument, load_corpus, prepare_corpus
from gemeinsam.messung import CSV_FIELDS, MeasurementPlan, measure_phase, summarize_measurements, write_measurements
from invertierter_index import InvertedIndex, build_inverted_index
import invertierter_index.index as index_module


EXPERIMENTS = Path(__file__).resolve().parent
ROOT = EXPERIMENTS.parents[2]
MESSUNGEN = ROOT / "ergebnisse/messungen"
REFERENCE = "ergebnisse/messungen/02_invertierter_index"
STANDARD_PILOT = "02b_pilot"
STANDARD_FINAL = "02b_tokenpruefung"
PUBLIC, WITHOUT_CHECK = "inverted_index", "inverted_index_ohne_tokenpruefung"
VARIANTS = (PUBLIC, WITHOUT_CHECK)
PLANNED_BACKGROUND = (
    "planned protocol: no parallel project tests, PDF builds or other benchmark series; "
    "ordinary desktop background load; machine not isolated; not checked by the script"
)
PARAMETERS = {
    "seed": 20261006,
    # Exakt die V-Reihe aus Reihe 02; der Lauf prüft sie gegen deren Metadaten.
    "datasets": [
        {"dataset_id": "v100", "total_tokens": 100_000, "document_count": 100, "base_vocabulary": 100},
        {"dataset_id": "n100000", "total_tokens": 100_000, "document_count": 100, "base_vocabulary": 1000},
        {"dataset_id": "v10000", "total_tokens": 100_000, "document_count": 100, "base_vocabulary": 10_000},
    ],
    "reference_run": REFERENCE,
    "variants": {
        PUBLIC: "public build_inverted_index, unchanged production code",
        WITHOUT_CHECK: "measurement-internal copy without checked_tokens set and tokenize(token) contract check; "
                       "AST otherwise identical to production function",
    },
    # Wechselnde Reihenfolge, damit keine Variante stets zuerst gemessen wird.
    "variant_order": {"v100": [PUBLIC, WITHOUT_CHECK], "n100000": [WITHOUT_CHECK, PUBLIC],
                      "v10000": [PUBLIC, WITHOUT_CHECK]},
    "final_plan": asdict(MeasurementPlan()),
    "pilot_plan": asdict(MeasurementPlan(warmups=1, repeats=3)),
    "share": "(median_a - median_b) / median_a per dataset; a=public build, b=copy without token check",
}
PLANS = {"final": PARAMETERS["final_plan"], "pilot": PARAMETERS["pilot_plan"]}
REMOVED_CHECK = (
    "if token not in checked_tokens:\n"
    "    if tokenize(token) != (token,):\n"
    "        raise CorpusError(f'Kein normalisiertes einzelnes Token: {token!r}')\n"
    "    checked_tokens.add(token)"
)


def build_ohne_tokenpruefung(corpus: Iterable[PreparedDocument]) -> InvertedIndex:
    """Messinterne Kopie von build_inverted_index ohne Tokenvertragsprüfung.

    Abgesehen von Name und Docstring fehlen nur das Set checked_tokens und
    die tokenize-Prüfung je verschiedenem Token; copy_matches_production
    sichert das per AST. Nur für die Zusatzmessung 02b, nicht für Suchen.
    """
    if isinstance(corpus, (str, bytes)):
        raise CorpusError("Der Korpus muss ein Iterable von PreparedDocument sein.")
    try:
        documents = iter(corpus)
    except TypeError as error:
        raise CorpusError("Der Korpus muss ein Iterable von PreparedDocument sein.") from error
    identifiers: set[str] = set()
    postings: dict[str, list[str]] = {}
    for document in documents:
        if not isinstance(document, PreparedDocument):
            raise CorpusError("Der Korpus enthält ein Element, das kein PreparedDocument ist.")
        if document.document_id in identifiers:
            raise CorpusError(f"Doppelte Dokumentkennung: {document.document_id}")
        identifiers.add(document.document_id)
        for token in set(document.tokens):
            postings.setdefault(token, []).append(document.document_id)
    immutable = {token: tuple(sorted(ids)) for token, ids in postings.items()}
    index = object.__new__(InvertedIndex)
    object.__setattr__(index, "_postings", MappingProxyType(immutable))
    return index


def _function(source: str, name: str) -> ast.FunctionDef:
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    function.name = "build"
    if function.body and isinstance(function.body[0], ast.Expr) and isinstance(function.body[0].value, ast.Constant):
        del function.body[0]
    return function


def copy_matches_production(production_source: str, copy_source: str) -> None:
    """Kopie = Produktionsfunktion ohne genau die Tokenprüfung (AST-Vergleich)."""
    production = _function(production_source, "build_inverted_index")
    declarations = [node for node in production.body if isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name) and node.target.id == "checked_tokens"]
    if len(declarations) != 1:
        raise AssertionError("Produktionsfunktion: Set checked_tokens nicht eindeutig gefunden")
    production.body.remove(declarations[0])
    removed = []
    for node in ast.walk(production):
        if isinstance(node, ast.For):
            checks = [child for child in node.body if isinstance(child, ast.If)
                      and ast.unparse(child.test) == "token not in checked_tokens"]
            removed.extend(checks)
            node.body = [child for child in node.body if child not in checks]
    if [ast.unparse(node) for node in removed] != [REMOVED_CHECK]:
        raise AssertionError("Produktionsfunktion: Tokenprüfung hat sich verändert")
    if ast.dump(production) != ast.dump(_function(copy_source, "build_ohne_tokenpruefung")):
        raise AssertionError("Messinterne Kopie weicht über die Tokenprüfung hinaus von build_inverted_index ab")


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
             *ROOT.glob("themen/02_invertierter_index_einzelwortsuche/src/invertierter_index/*.py"),
             ROOT / "gemeinsam/__init__.py", ROOT / "pyproject.toml", ROOT / "requirements-dev.txt",
             Path(__file__).resolve(), EXPERIMENTS / "generator.py"}
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


def _generator():
    """02-Generator per Dateipfad; kein Namenskonflikt mit anderen generator.py."""
    name = "experiment02b_generator"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, EXPERIMENTS / "generator.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def expected_postings(tokens_by_id: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    """Unabhängige Sollpostings aus dem Pflanzplan, ohne Indexfunktion."""
    postings: dict[str, set[str]] = {}
    for identifier, tokens in tokens_by_id.items():
        for word in tokens:
            postings.setdefault(word, set()).add(identifier)
    return {word: tuple(sorted(ids)) for word, ids in postings.items()}


def reference_datasets() -> dict[str, dict]:
    """Gespeicherte V-Datensätze der Reihe 02 (nur lesend)."""
    metadata = json.loads((ROOT / REFERENCE / "metadata.json").read_text(encoding="utf-8"))
    if metadata["parameters"]["seed"] != PARAMETERS["seed"]:
        raise AssertionError("Seed weicht von Reihe 02 ab")
    by_id = {dataset["dataset_id"]: dataset for dataset in metadata["datasets"]}
    for recipe in PARAMETERS["datasets"]:
        stored = by_id[recipe["dataset_id"]]
        parameters = {key: recipe[key] for key in ("total_tokens", "document_count", "base_vocabulary")}
        if "V" not in stored["series"] or stored["generator_parameters"] != parameters:
            raise AssertionError(f"{recipe['dataset_id']}: Generatorparameter weichen von der V-Reihe 02 ab")
    return by_id


def prepare_dataset(recipe: dict, temporary: Path, reference: dict) -> tuple:
    """Erzeugt, prüft und beschreibt einen Datensatz außerhalb jeder Zeitmessung."""
    generated = _generator().generate_corpus(
        temporary / recipe["dataset_id"], recipe["total_tokens"], document_count=recipe["document_count"],
        base_vocabulary=recipe["base_vocabulary"], seed=PARAMETERS["seed"])
    raw = load_corpus(generated.root)
    prepared = prepare_corpus(raw)
    if {document.document_id: document.tokens for document in prepared} != generated.expected_tokens:
        raise AssertionError("Generierte Tokenfolgen weichen vom Pflanzplan ab")
    files = [{"document_id": doc.document_id, "source_path": doc.source_path,
              "bytes": len(doc.raw_text.encode("utf-8")),
              "sha256": hashlib.sha256(doc.raw_text.encode("utf-8")).hexdigest()} for doc in raw]
    corpus_sha256 = hashlib.sha256(json.dumps(files, ensure_ascii=False, sort_keys=True,
                                              separators=(",", ":")).encode()).hexdigest()
    stored = reference[recipe["dataset_id"]]
    if corpus_sha256 != stored["corpus_sha256"]:
        raise AssertionError(f"{recipe['dataset_id']}: Korpus ist nicht byteidentisch mit Reihe 02")
    expected = expected_postings(generated.expected_tokens)
    public, copy = build_inverted_index(prepared), build_ohne_tokenpruefung(prepared)
    if type(copy) is not InvertedIndex or dict(public) != expected or dict(copy) != expected:
        raise AssertionError(f"{recipe['dataset_id']}: Varianten liefern nicht den erwarteten Index")
    if list(public) != list(copy) or any(public[token] != copy[token] for token in public):
        raise AssertionError(f"{recipe['dataset_id']}: Varianten liefern verschiedene Indizes")
    posting_count = sum(len(ids) for ids in public.values())
    if len(public) != stored["vocabulary_size"] or posting_count != stored["posting_count"]:
        raise AssertionError(f"{recipe['dataset_id']}: V oder P weicht von Reihe 02 ab")
    description = {
        "dataset_id": recipe["dataset_id"], "generator_parameters": {
            key: recipe[key] for key in ("total_tokens", "document_count", "base_vocabulary")},
        "document_count": len(prepared), "token_count": sum(len(doc.tokens) for doc in prepared),
        "text_bytes": sum(entry["bytes"] for entry in files), "vocabulary_size": len(public),
        "posting_count": posting_count, "corpus_sha256": corpus_sha256,
        "reference_corpus_sha256": stored["corpus_sha256"],
        # Je verschiedenem Token ein tokenize-Aufruf, je Posting eine Set-Abfrage.
        "token_checks": {"tokenize_calls": len(public), "checked_tokens_lookups": posting_count},
        "variants_identical_before_timing": True,
    }
    return prepared, expected, description


def make_metadata(plan: MeasurementPlan, pilot: bool, output: Path, background: str) -> dict:
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    hashes = code_hashes()
    for relative in hashes:
        snapshot = output / "code_source" / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes((ROOT / relative).read_bytes())
    cpu = platform.processor()
    if Path("/proc/cpuinfo").is_file():
        cpu = next((line.partition(":")[2].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")), cpu)
    reference = ROOT / REFERENCE
    return {
        "run_id": output.name, "run_kind": "pilot" if pilot else "final", "output_directory": _display(output),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
        "git_status_at_start": git("status", "--porcelain"), "code_sha256": hashes, "source_archive": "code_source/",
        "parameters": PARAMETERS, "measurement_plan": asdict(plan),
        "reference": {"run": REFERENCE, "metadata_sha256": sha(reference / "metadata.json"),
                      "summary_sha256": sha(reference / "summary.json")},
        "environment": {"python": sys.version, "implementation": platform.python_implementation(),
                        "platform": platform.platform(), "machine": platform.machine(), "cpu_model": cpu,
                        "logical_cpus": os.cpu_count(), "python_hash_seed": python_hash_seed(),
                        "python_hash_seed_set": "PYTHONHASHSEED" in os.environ,
                        "unicode_database": unicodedata.unidata_version, "pytest": version("pytest")},
        "timer": "time.perf_counter_ns via gemeinsam.messung.measure_phase; integer elapsed_ns per complete build",
        "clock": vars(get_clock_info("perf_counter")),
        "background_load": background,
        "cache": "same prepared corpus reused for every build; no cold-cache claim",
        "timing_boundaries": {
            PUBLIC: "complete public build_inverted_index on already prepared corpus, as build phase of series 02",
            WITHOUT_CHECK: "identical except checked_tokens bookkeeping and tokenize(token) contract check",
            "excluded": "generation, loading, preparation, AST check, index equality checks, result validation, output",
        },
        "statistics": "median, inclusive Q1/Q3, IQR=Q3-Q1; share=(median_a-median_b)/median_a; "
                      "variants measured in separate measure_phase blocks, so repeats are not paired; "
                      "quartiles are not confidence intervals",
        "interpretation_limits": [
            "Difference a-b contains tokenize calls per distinct token and the checked_tokens set bookkeeping per posting.",
            "Copy and production code are separate functions; equal AST does not exclude small interpreter-level differences.",
            "Only the V series of series 02 (N=100000, D=100); no statement about other corpora.",
        ],
        "datasets": [],
    }


def timing_run(output: Path, plan: MeasurementPlan, pilot: bool, background: str) -> tuple[list, list, dict]:
    production_source = Path(index_module.__file__).read_text(encoding="utf-8")
    copy_matches_production(production_source, Path(__file__).read_text(encoding="utf-8"))
    reference = reference_datasets()
    metadata = make_metadata(plan, pilot, output, background)
    rows = []
    with TemporaryDirectory(prefix="textsuche-02b-") as temporary:
        for recipe in PARAMETERS["datasets"]:
            identifier = recipe["dataset_id"]
            prepared, expected, description = prepare_dataset(recipe, Path(temporary), reference)
            metadata["datasets"].append({**description, "variant_order": PARAMETERS["variant_order"][identifier]})
            context = {"run_id": metadata["run_id"], "git_commit": metadata["git_commit"], "seed": plan.seed,
                       "dataset_id": identifier, "document_count": description["document_count"],
                       "text_bytes": description["text_bytes"], "token_count": description["token_count"]}

            def validate(observed, expected=expected):
                if type(observed) is not InvertedIndex or dict(observed) != expected:
                    raise AssertionError("Aufbau weicht von den unabhängigen Sollpostings ab")

            operations = {PUBLIC: lambda prepared=prepared: build_inverted_index(prepared),
                          WITHOUT_CHECK: lambda prepared=prepared: build_ohne_tokenpruefung(prepared)}
            print(f"{identifier}: V={description['vocabulary_size']}, P={description['posting_count']}; "
                  f"Aufbau in Reihenfolge {', '.join(PARAMETERS['variant_order'][identifier])}", flush=True)
            for variant in PARAMETERS["variant_order"][identifier]:
                rows.extend(measure_phase(operations[variant], validate, plan, phase="build",
                                          context={**context, "algorithm": variant}))
            write_measurements(output / "raw.csv", rows)
            write_json(output / "metadata.json", metadata)
    if code_hashes() != metadata["code_sha256"]:
        raise SystemExit("Messcode hat sich während des Laufs geändert; Ergebnisse sind nicht zuordenbar.")
    metadata["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    summary = summarize_measurements(rows)
    return rows, summary, metadata


def evaluate(summary: list[dict], metadata: dict) -> dict:
    """Median, IQR und Anteil (a-b)/a je V; abgeleitet allein aus summary."""
    groups = {(row["dataset_id"], row["algorithm"]): row for row in summary if row["phase"] == "build"}
    results = []
    for dataset in metadata["datasets"]:
        public, copy = groups[dataset["dataset_id"], PUBLIC], groups[dataset["dataset_id"], WITHOUT_CHECK]
        difference = public["median_ms"] - copy["median_ms"]
        results.append({
            "dataset_id": dataset["dataset_id"], "vocabulary_size": dataset["vocabulary_size"],
            "posting_count": dataset["posting_count"], "token_count": dataset["token_count"],
            "sample_count": public["sample_count"],
            "median_a_ms": public["median_ms"], "q1_a_ms": public["q1_ms"], "q3_a_ms": public["q3_ms"],
            "iqr_a_ms": public["iqr_ms"],
            "median_b_ms": copy["median_ms"], "q1_b_ms": copy["q1_ms"], "q3_b_ms": copy["q3_ms"],
            "iqr_b_ms": copy["iqr_ms"],
            "difference_ms": difference, "share": difference / public["median_ms"],
        })
    return {"run_id": metadata["run_id"], "run_kind": metadata["run_kind"],
            "definition": PARAMETERS["share"], "results": results,
            "limits": "ratio of medians from separate blocks; no confidence interval; pilot values are not results"
                      if metadata["run_kind"] == "pilot" else
                      "ratio of medians from separate blocks; no confidence interval"}


def run(args: argparse.Namespace) -> Path:
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
    rows, summary, metadata = timing_run(output, plan, args.pilot, args.hintergrundlast)
    if not args.pilot:
        metadata["pilot_directory"] = _display(MESSUNGEN / args.pilot_ordner)
    evaluation = evaluate(summary, metadata)
    write_measurements(output / "raw.csv", rows)
    write_json(output / "summary.json", summary)
    write_json(output / "auswertung.json", evaluation)
    write_json(output / "metadata.json", metadata)
    if args.pilot:
        write_json(output / "pilot_decision.json", {
            "pilot_correct": True, "locked_parameters": PARAMETERS,
            "method_code_sha256": metadata["code_sha256"],
            "python_hash_seed": metadata["environment"]["python_hash_seed"], "pilot_plan": asdict(plan),
            "decision": "drei V-Datensätze byteidentisch zu Reihe 02, beide Varianten identisch und messbar; Parameter gesperrt",
            "pilot_is_not_final_measurement": True})
    for result in evaluation["results"]:
        print(f"{result['dataset_id']}: V={result['vocabulary_size']}: a={result['median_a_ms']:.3f} ms "
              f"(IQR {result['iqr_a_ms']:.3f}), b={result['median_b_ms']:.3f} ms (IQR {result['iqr_b_ms']:.3f}), "
              f"Anteil={result['share']:.1%}", flush=True)
    print(f"Gespeichert: {_display(output)}; {len(rows)} Rohwerte, {len(summary)} Gruppen", flush=True)
    return output


def verify_directory(directory: Path, *, archive_only: bool = False) -> dict:
    """Prüft einen gespeicherten 02b-Lauf ohne neue Zeitmessung."""
    directory = Path(directory)
    with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames) == CSV_FIELDS, "abweichendes CSV-Schema"
        rows = list(reader)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    evaluation = json.loads((directory / "auswertung.json").read_text(encoding="utf-8"))
    assert metadata["parameters"] == PARAMETERS, "Parameter weichen ab"
    assert metadata["run_kind"] in PLANS and metadata["measurement_plan"] == PLANS[metadata["run_kind"]]
    repeats = metadata["measurement_plan"]["repeats"]
    datasets = {dataset["dataset_id"]: dataset for dataset in metadata["datasets"]}
    assert list(datasets) == [recipe["dataset_id"] for recipe in PARAMETERS["datasets"]]
    assert len(rows) == len(datasets) * len(VARIANTS) * repeats and len(summary) == len(datasets) * len(VARIANTS)
    grouped = defaultdict(list)
    for row in rows:
        dataset = datasets[row["dataset_id"]]
        assert row["algorithm"] in VARIANTS and row["phase"] == "build" and row["correct"] == "True"
        assert row["run_id"] == metadata["run_id"] and row["git_commit"] == metadata["git_commit"]
        assert int(row["seed"]) == metadata["measurement_plan"]["seed"]
        assert all(int(row[field]) == dataset[field] for field in ("document_count", "text_bytes", "token_count"))
        elapsed = int(row["elapsed_ns"])
        assert elapsed >= 0 and int(row["block_size"]) == 1
        assert float(row["build_ms"]) == elapsed / 1_000_000
        assert all(row[field] == "" for field in ("load_ms", "preparation_ms", "query_ms", "index_bytes",
                                                  "peak_memory_bytes", "query_id", "query_type", "query_text",
                                                  "order_index", "hit_count"))
        grouped[row["dataset_id"], row["algorithm"]].append(row)
    order = [(row["dataset_id"], row["algorithm"]) for row in rows]
    expected_order = [(identifier, variant) for identifier in datasets
                      for variant in PARAMETERS["variant_order"][identifier] for _ in range(repeats)]
    assert order == expected_order, "Messreihenfolge weicht vom gesperrten Plan ab"
    for result in summary:
        group = grouped[result["dataset_id"], result["algorithm"]]
        assert sorted(int(row["repeat"]) for row in group) == list(range(repeats))
        values = [float(row["build_ms"]) for row in group]
        q1, _, q3 = quantiles(values, n=4, method="inclusive")
        assert result["phase"] == "build" and result["sample_count"] == repeats
        assert result["median_ms"] == median(values) and result["q1_ms"] == q1 and result["q3_ms"] == q3
        assert result["iqr_ms"] == q3 - q1
        assert result["minimum_ms"] == min(values) and result["maximum_ms"] == max(values)
    assert evaluation == json.loads(json.dumps(evaluate(summary, metadata))), "Auswertung nicht aus summary ableitbar"
    reference = reference_datasets()
    for identifier, dataset in datasets.items():
        stored = reference[identifier]
        assert dataset["corpus_sha256"] == dataset["reference_corpus_sha256"] == stored["corpus_sha256"]
        assert dataset["vocabulary_size"] == stored["vocabulary_size"]
        assert dataset["posting_count"] == stored["posting_count"]
        assert dataset["token_count"] == stored["token_count"] and dataset["text_bytes"] == stored["text_bytes"]
        assert dataset["variants_identical_before_timing"] is True
    changed = []
    for relative, expected in metadata["code_sha256"].items():
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        assert sha(directory / "code_source" / relative) == expected, f"Quelltextarchiv beschädigt: {relative}"
        if sha(ROOT / relative) != expected:
            changed.append(relative)
    if changed and not archive_only:
        raise AssertionError(f"aktiver Code weicht vom gemessenen Stand ab: {', '.join(changed)}")
    archive = directory / "code_source"
    copy_matches_production(
        (archive / "themen/02_invertierter_index_einzelwortsuche/src/invertierter_index/index.py").read_text(encoding="utf-8"),
        (archive / "themen/02_invertierter_index_einzelwortsuche/experimente/tokenpruefung.py").read_text(encoding="utf-8"))
    environment = metadata["environment"]
    if environment["python_hash_seed"] != "random":
        assert environment["python_hash_seed_set"] is True
    if metadata["run_kind"] == "pilot":
        decision = json.loads((directory / "pilot_decision.json").read_text(encoding="utf-8"))
    else:
        decision = json.loads((MESSUNGEN / Path(metadata["pilot_directory"]).name / "pilot_decision.json")
                              .read_text(encoding="utf-8"))
    assert decision["pilot_correct"] is True and decision["locked_parameters"] == PARAMETERS
    assert decision["method_code_sha256"] == metadata["code_sha256"], "Lauf und Pilot mit verschiedenem Code"
    assert decision["python_hash_seed"] == environment["python_hash_seed"], "Lauf und Pilot mit verschiedenem Hashseed"
    return {"rows": len(rows), "groups": len(summary), "changed_sources": changed,
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
    args = parser.parse_args(argv)
    if args.pruefen:
        if Path(args.pruefen).name != args.pruefen:
            raise SystemExit("--pruefen erwartet genau einen Ordnernamen unter ergebnisse/messungen")
        counts = verify_directory(MESSUNGEN / args.pruefen, archive_only=args.archive_only)
        print(f"{args.pruefen}: {counts['rows']} Rohwerte, {counts['groups']} Gruppen, Auswertung, Reihenfolge, "
              f"Korpus-Hashes gegen Reihe 02, AST-Kopie und Quellarchiv geprüft; PYTHONHASHSEED={counts['python_hash_seed']}.")
        if counts["changed_sources"]:
            print(f"Nur-Archiv-Modus: aktive Quellen weichen ab: {', '.join(counts['changed_sources'])}")
        return
    run(args)


if __name__ == "__main__":
    main()
