#!/usr/bin/env python3
"""Skalierungsversuch: aus der Repositorywurzel nach `pip install -e .`.

Pilot und Hauptlauf schreiben in neue Ordner unter ergebnisse/messungen
(Standard 01b_pilot2 und 01b_direkte_suche); vorhandene nicht-leere Ordner
werden nie überschrieben. Der Hauptlauf verlangt einen erfolgreichen Pilot
mit gleichen Parametern, gleichem Messcode und gleichem PYTHONHASHSEED.
Realkorpus der Neumessung ist das BGB (daten/real/bgb, ein Paragraph je
Dokument); die gelieferte Reihe 01_direkte_suche verwendete Kafka.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import get_clock_info
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
MESSUNGEN = REPOSITORY / "ergebnisse/messungen"
STANDARD_PILOT = "01b_pilot2"
STANDARD_FINAL = "01b_direkte_suche"
PLANNED_BACKGROUND = (
    "planned protocol: no parallel project tests, PDF builds or other benchmark series; "
    "ordinary desktop background load; machine not isolated; not checked by the script"
)
PARAMETERS = {
    "total_tokens": [10_000, 100_000, 1_000_000],
    "document_count": 20,
    "seed": 20261006,
    "vocabulary": "wort0000..wort0999",
    "frequent": "Fehler at position 0 and each position divisible by 100 in every document",
    "rare": "Verbindung at the last position of doc00.txt only",
    "missing": "Unauffindbar never planted or sampled",
    "measurement_plan": asdict(MeasurementPlan()),
    # Realteil: BGB statt Kafka; Erwartungen aus manifest.json/anfragevorschlaege.json.
    "real": {
        "dataset_id": "real_bgb",
        "dataset": "bgb-gesetze-im-internet-v1",
        "corpus_root": "daten/real/bgb/dokumente",
        "manifest": "daten/real/bgb/manifest.json",
        "proposals": "daten/real/bgb/anfragevorschlaege.json",
        "corpus_sha256": "dc1641fd49dfa45270a1865f454abd64cf7cf94d79b37af9657ff97d7602eadf",
        "document_count": 2486,
        "token_count": 213718,
        "queries": {"early": "Beginn", "frequent": "der", "rare": "Erbschaftskauf", "missing": "Server"},
    },
}


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _git(*arguments: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *arguments], cwd=REPOSITORY, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        # Kein Git-Arbeitsverzeichnis (z. B. aus einer ZIP-Datei entpackt)
        return "kein-git" if arguments[:1] == ("rev-parse",) else ""


def code_hashes() -> dict[str, str]:
    """SHA-256 des gemessenen Such-, Aufbereitungs- und Messcodes."""
    code_paths = sorted({
        *REPOSITORY.glob("gemeinsam/src/gemeinsam/*.py"),
        *REPOSITORY.glob("themen/01_textaufbereitung_direkte_suche/src/direkte_suche/*.py"),
        REPOSITORY / "gemeinsam/__init__.py",
        Path(__file__).resolve(), REPOSITORY / "pyproject.toml", REPOSITORY / "requirements-dev.txt",
    })
    return {
        path.relative_to(REPOSITORY).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in code_paths if path.is_file()
    }


def _display(path: Path) -> str:
    """Repositoryrelativer Pfad für Metadaten und Meldungen."""
    try:
        return path.relative_to(REPOSITORY).as_posix()
    except ValueError:
        return path.as_posix()


def python_hash_seed() -> str:
    """Tatsächlicher PYTHONHASHSEED; "random", wenn die Variable fehlt."""
    return os.environ.get("PYTHONHASHSEED", "random")


def target_directory(name: str) -> Path:
    """Neuer Ergebnisordner unter ergebnisse/messungen; nie Überschreiben.

    Zulässig ist genau ein Ordnername. Ein vorhandener nicht-leerer Ordner,
    etwa die gelieferten Reihen 01_direkte_suche oder 01_pilot, bricht ab.
    """
    if not name or name in {".", ".."} or Path(name).name != name or "/" in name or "\\" in name:
        raise SystemExit(f"Ungültiger Ordnername {name!r}: genau ein Name unter ergebnisse/messungen erwartet.")
    target = MESSUNGEN / name
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise SystemExit(f"{_display(target)} existiert und ist nicht leer; "
                         "gelieferte Ergebnisse werden nicht überschrieben. Neuen Namen mit --ausgabe wählen.")
    return target


def require_pilot(path: Path) -> dict:
    """Hauptlauf nur nach erfolgreichem Pilot mit identischen Bedingungen."""
    if not path.is_file():
        raise SystemExit("Zuerst --pilot ausführen: Parameter werden erst nach erfolgreichem Pilotlauf gesperrt.")
    decision = json.loads(path.read_text(encoding="utf-8"))
    if decision.get("pilot_correct") is not True or decision.get("locked_parameters") != PARAMETERS:
        raise SystemExit("Parameter unterscheiden sich vom erfolgreichen Pilotlauf; Pilot erneut ausführen.")
    if decision.get("method_code_sha256") != code_hashes():
        raise SystemExit("Messcode hat sich nach dem Pilot geändert oder der Pilot sperrt keinen Code; Pilot erneut ausführen.")
    if decision.get("python_hash_seed") != python_hash_seed():
        raise SystemExit("PYTHONHASHSEED weicht vom Pilot ab; mit demselben Wert wie im Pilot starten.")
    return decision


def _metadata(plan: MeasurementPlan, pilot: bool, output: Path, background: str = PLANNED_BACKGROUND) -> dict:
    hashes = code_hashes()
    for relative in hashes:
        snapshot = output / "code_source" / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes((REPOSITORY / relative).read_bytes())
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
        "run_id": output.name,
        "run_kind": "pilot" if pilot else "final",
        "output_directory": _display(output),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "git_status_at_start": _git("status", "--porcelain"),
        "code_sha256": hashes,
        "source_archive": "code_source/",
        "environment": {
            "python": sys.version, "implementation": platform.python_implementation(),
            "platform": platform.platform(), "machine": platform.machine(),
            "cpu_model": cpu_model, "memory_total": total_memory, "logical_cpus": os.cpu_count(),
            "python_hash_seed": python_hash_seed(),
            "python_hash_seed_set": "PYTHONHASHSEED" in os.environ,
            "matplotlib": version("matplotlib"), "pytest": version("pytest"),
            "unicode_database": unicodedata.unidata_version,
        },
        "parameters": PARAMETERS,
        "measurement_plan": asdict(plan),
        "timer": "time.perf_counter_ns; elapsed_ns retains integer block duration",
        "clock": vars(get_clock_info("perf_counter")),
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
        "background_load": background,
        "dataset_order": "generated 10000,100000,1000000 then real BGB; query order shuffled deterministically for each warmup and measured repetition",
        "real_corpus": "BGB (daten/real/bgb/dokumente, 2486 paragraphs, one document each); delivered series 01_direkte_suche used the Kafka excerpt",
        "datasets": [],
    }


def independent_tokens(text: str) -> tuple[str, ...]:
    """Zweite Tokenisierung per Regex, ohne gemeinsam.tokenize.

    [^\\W_]+ entspricht L* und Nd nur ohne kombinierende Zeichen sowie No/Nl;
    beides wird geprüft. Für den BGB-Abrufstand gilt das laut Manifest.
    """
    normalized = unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).casefold())
    if any(unicodedata.category(character)[0] == "M" or unicodedata.category(character) in {"No", "Nl"}
           for character in normalized):
        raise AssertionError("Regex-Gegenprobe gilt nur ohne M*, No und Nl")
    return tuple(re.findall(r"[^\W_]+", normalized))


def canonical_corpus_sha256(hashes: dict[str, str]) -> str:
    """BGB-Korpushash: SHA-256 über '<sha256>  <dateiname>\\n' in Bytereihenfolge."""
    lines = "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def list_sha256(values: list[str]) -> str:
    """Hash der zeilenweise verbundenen Kennungen wie in anfragevorschlaege.json."""
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def check_document_list(identifiers: list[str], entry: dict) -> None:
    """Trefferliste gegen vollständige Liste oder Anzahl/Hash/Ränder der Erwartung."""
    if "document_ids" in entry:
        if identifiers != entry["document_ids"]:
            raise AssertionError(f"{entry['query']}: Dokumentliste weicht von der unabhängigen Erwartung ab")
    elif (len(identifiers) != entry["document_ids_count"] or list_sha256(identifiers) != entry["document_ids_sha256"]
          or identifiers[:5] != entry["document_ids_first5"] or identifiers[-5:] != entry["document_ids_last5"]):
        raise AssertionError(f"{entry['query']}: Dokumentliste weicht von Anzahl/Hash der Erwartung ab")
    if len(identifiers) != entry["df"]:
        raise AssertionError(f"{entry['query']}: df weicht ab")


def bgb_fixture() -> tuple[dict, dict[str, tuple[str, ...]], list[QuerySpec]]:
    """BGB-Erwartungen aus Manifest und Anfragevorschlägen, Tokens unabhängig.

    Liefert die Metadaten der Quelle, die Regex-Tokenfolgen aller Dokumente
    und die Anfragen samt vollständiger erwarteter Trefferliste.
    """
    real = PARAMETERS["real"]
    manifest_path, proposals_path = REPOSITORY / real["manifest"], REPOSITORY / real["proposals"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    proposals = json.loads(proposals_path.read_text(encoding="utf-8"))
    expectations = manifest["independent_expectations"]
    if not (manifest["dataset_id"] == proposals["dataset_id"] == real["dataset"]
            and manifest["corpus_sha256"] == proposals["corpus_sha256"] == expectations["corpus_sha256"]
            == real["corpus_sha256"]):
        raise AssertionError("BGB-Manifest oder Anfragevorschläge gehören zu einem anderen Datenstand")
    if expectations["document_count"] != real["document_count"] or expectations["token_count"] != real["token_count"]:
        raise AssertionError("BGB-Kennzahlen weichen von den gesperrten Parametern ab")
    root = REPOSITORY / real["corpus_root"]
    texts = {}
    for entry in manifest["documents"]:
        payload = (root / entry["source_path"]).read_bytes()
        if len(payload) != entry["bytes"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise AssertionError(f"BGB-Datei weicht vom Manifest ab: {entry['document_id']}")
        texts[entry["document_id"]] = payload.decode("utf-8")
    on_disk = sorted(path.name for path in root.iterdir() if path.is_file() and path.suffix == ".txt")
    if on_disk != sorted(texts):
        raise AssertionError("BGB-Korpusordner enthält andere Dateien als das Manifest")
    tokens = {identifier: independent_tokens(texts[identifier]) for identifier in sorted(texts)}
    if sum(map(len, tokens.values())) != real["token_count"]:
        raise AssertionError("BGB: unabhängige Tokenzahl weicht vom Manifest ab")
    words = {entry["query"]: entry for entry in expectations["words"]}
    entries = {entry["query"]: entry for entry in proposals["reihe_01_direkte_suche"]}
    queries, fixture_queries = [], {}
    for query_id, text in real["queries"].items():
        entry = entries[text]
        if any(words[text][key] != entry[key] for key in words[text] if key != "note" and key in entry):
            raise AssertionError(f"{text}: Anfragevorschlag und Manifest widersprechen sich")
        (term,) = independent_tokens(text)
        if term != entry["term"]:
            raise AssertionError(f"{text}: unabhängige Normalform weicht ab")
        hits = [identifier for identifier, sequence in tokens.items() if term in sequence]
        check_document_list(hits, entry)
        queries.append(QuerySpec(query_id, text, "word", tuple(hits)))
        fixture_queries[query_id] = entry
    fixture = {
        "dataset": real["dataset"], "corpus_root": real["corpus_root"],
        "manifest_path": real["manifest"], "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "proposals_path": real["proposals"],
        "proposals_sha256": hashlib.sha256(proposals_path.read_bytes()).hexdigest(),
        "corpus_sha256": manifest["corpus_sha256"], "document_count": expectations["document_count"],
        "token_count": expectations["token_count"], "first_document_id": expectations["first_document_id"],
        "first_tokens": expectations["prefix_tokens_bgb_0001"],
        "files": {entry["document_id"]: {"bytes": entry["bytes"], "sha256": entry["sha256"]}
                  for entry in manifest["documents"]},
        "queries": fixture_queries,
    }
    return fixture, tokens, queries


def _check_real_corpus(files: list[dict], prepared, fixture: dict, tokens: dict) -> None:
    """Mehrere Realdokumente: Dateien, Korpushash, Tokens, N und Tokenanfang."""
    if [entry["document_id"] for entry in files] != sorted(fixture["files"]):
        raise AssertionError("Realer Korpus: Dokumentkennungen weichen vom Manifest ab")
    for entry in files:
        expected = fixture["files"][entry["document_id"]]
        if entry["bytes"] != expected["bytes"] or entry["sha256"] != expected["sha256"]:
            raise AssertionError(f"Realer Korpus: Prüfsumme weicht ab: {entry['document_id']}")
    if canonical_corpus_sha256({entry["document_id"]: entry["sha256"] for entry in files}) != fixture["corpus_sha256"]:
        raise AssertionError("Realer Korpus: kanonischer Korpushash weicht vom Manifest ab")
    if {document.document_id: document.tokens for document in prepared} != tokens:
        raise AssertionError("Realer Korpus: Aufbereitung weicht von der unabhängigen Tokenisierung ab")
    if len(prepared) != fixture["document_count"] or sum(len(document.tokens) for document in prepared) != fixture["token_count"]:
        raise AssertionError("Realer Korpus: D oder N weicht vom Manifest ab")
    first = fixture["first_tokens"]
    if prepared[0].document_id != fixture["first_document_id"] or list(prepared[0].tokens[:len(first)]) != first:
        raise AssertionError("Realer Korpus: erwarteter Tokenanfang des ersten Paragraphen stimmt nicht")


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
    real_tokens: dict[str, tuple[str, ...]] | None = None,
) -> list[dict]:
    raw = load_corpus(root)
    prepared = prepare_corpus(raw)
    if generated is not None:
        _check_tokens(prepared, generated.expected_tokens)
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
        _check_real_corpus(files, prepared, real_fixture, real_tokens)
    query_metadata = []
    for query in queries:
        extra = {}
        if generated is not None:
            # Feste Anfrage-Tokens vermeiden zirkuläre Häufigkeitsprüfungen.
            word = {"Fehler": "fehler", "Verbindung": "verbindung", "Unauffindbar": "unauffindbar"}[query.text]
            expected_count = generated.expected_occurrences[query.query_id]
        else:
            entry = real_fixture["queries"][query.query_id]
            word, expected_count = entry["term"], entry["cf"]
        observed_count = sum(document.tokens.count(word) for document in prepared)
        if observed_count != expected_count:
            raise AssertionError(f"{dataset_id}/{query.query_id}: Häufigkeit weicht vom Pflanzplan/Fixture ab")
        # Tokenvergleiche der direkten Suche: Abbruch nur innerhalb eines Dokuments.
        visited = sum(document.tokens.index(word) + 1 if word in document.tokens else len(document.tokens)
                      for document in prepared)
        if real_fixture is not None:
            hits = [document.document_id for document in prepared if word in document.tokens]
            check_document_list(hits, entry)
            if hits != list(query.expected_ids) or visited != entry["scanned_tokens_direct"]:
                raise AssertionError(f"{dataset_id}/{query.query_id}: Treffer oder Tokenvergleiche weichen ab")
            if hits:
                first = next(document for document in prepared if document.document_id == hits[0])
                if first.document_id != entry["first_document"] or first.tokens.index(word) != entry["first_position"]:
                    raise AssertionError(f"{dataset_id}/{query.query_id}: erste Position weicht ab")
                extra = {"first_document": first.document_id, "first_position": first.tokens.index(word)}
            extra["document_frequency"] = len(hits)
        if search_direct_word(prepared, query.text) != list(query.expected_ids):
            raise AssertionError(f"{dataset_id}/{query.query_id}: Treffer weichen von der festen Erwartung ab")
        query_metadata.append({
            **asdict(query), "normalized_token_expected": word,
            "query_frequency": query.query_id,
            "expected_occurrences": expected_count, "observed_occurrences": observed_count,
            "observed_document_hits": len(query.expected_ids), "direct_visited_tokens": visited, **extra,
        })
    metadata["datasets"].append({
        "dataset_id": dataset_id, "kind": "generated" if generated else "real",
        "document_count": len(raw), "text_bytes": text_bytes, "token_count": token_count,
        "files": files, "queries": query_metadata,
        "corpus_sha256": hashlib.sha256(
            json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "source_fixture": ({key: value for key, value in real_fixture.items() if key != "files"}
                           if real_fixture else None),
        **({"bgb_corpus_sha256": canonical_corpus_sha256({entry["document_id"]: entry["sha256"] for entry in files})}
           if real_fixture else {}),
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
    print(f"{dataset_id}: {len(queries)} Suchfälle", flush=True)
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pilot", action="store_true", help="1 Aufwärmlauf, 3 Messungen; keine finalen Abbildungen")
    parser.add_argument("--ausgabe", metavar="NAME",
                        help=f"neuer Ordner unter ergebnisse/messungen (Standard {STANDARD_PILOT} bzw. {STANDARD_FINAL})")
    parser.add_argument("--pilot-ordner", metavar="NAME", default=STANDARD_PILOT,
                        help=f"Pilotordner mit pilot_decision.json für den Hauptlauf (Standard {STANDARD_PILOT})")
    parser.add_argument("--hintergrundlast", metavar="TEXT", default=PLANNED_BACKGROUND,
                        help="tatsächliche Hintergrundlast für die Metadaten")
    args = parser.parse_args(argv)
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
    metadata = _metadata(plan, args.pilot, output, args.hintergrundlast)
    if not args.pilot:
        metadata["pilot_directory"] = _display(MESSUNGEN / args.pilot_ordner)
    rows = []
    with TemporaryDirectory(prefix="textsuche-01-") as temporary:
        for total in PARAMETERS["total_tokens"]:
            generated = generate_corpus(Path(temporary) / f"n{total}", total)
            queries = [QuerySpec(query_id, text, query_type, generated.expected_hits[query_id])
                       for query_id, text, query_type in (("frequent", "Fehler", "word"),
                                                         ("rare", "Verbindung", "word"),
                                                         ("missing", "Unauffindbar", "word"))]
            rows.extend(_dataset_measurements(generated.root, f"generated_{total}", queries, plan, metadata,
                                              generated=generated))
            write_measurements(output / "raw.csv", rows)
            _write_json(output / "metadata.json", metadata)
        fixture, real_tokens, queries = bgb_fixture()
        rows.extend(_dataset_measurements(REPOSITORY / PARAMETERS["real"]["corpus_root"], PARAMETERS["real"]["dataset_id"],
                                          queries, plan, metadata, real_fixture=fixture, real_tokens=real_tokens))
    if code_hashes() != metadata["code_sha256"]:
        raise SystemExit("Messcode hat sich während des Laufs geändert; Ergebnisse sind nicht zuordenbar.")
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
            "method_code_sha256": metadata["code_sha256"],
            "python_hash_seed": metadata["environment"]["python_hash_seed"],
            "pilot_plan": asdict(plan),
            "pilot_is_not_final_measurement": True,
        })
    else:
        # Abbildungen nur im neuen Ergebnisordner; ergebnisse/abbildungen bleibt unverändert.
        _plots(summary, output / "abbildungen", metadata)
    print(f"Gespeichert: {_display(output)}; {len(rows)} Rohwerte, {len(summary)} Gruppen", flush=True)


if __name__ == "__main__":
    main()
