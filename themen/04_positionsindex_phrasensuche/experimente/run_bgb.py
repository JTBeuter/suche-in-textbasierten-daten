#!/usr/bin/env python3
"""BGB-Realteil der Phrasenreihe 04: aus der Repositorywurzel nach `pip install -e .`.

Misst ausschließlich den realen Korpus daten/real/bgb/dokumente (ein Paragraph
je Dokument, 2486 Dokumente): Aufbau von Dokumentindex und Positionsindex sowie
direkte Phrasensuche gegen Positionsindex. Die synthetischen Korpora der Reihe
04 werden nicht neu gemessen; die gelieferte Reihe 04_positionsindex_phrasensuche
(mit dem früheren Kafka-Realteil) bleibt unverändert und wird weiterhin mit
verify_results.py geprüft.

Pilot und Hauptlauf schreiben in neue Ordner unter ergebnisse/messungen
(Standard 04_bgb_pilot und 04_bgb); vorhandene nicht-leere Ordner werden nie
überschrieben. Ein Befehl führt zuerst den Zeitlauf aus, danach den
Speicherlauf in getrennten Prozessen (memory.py) und zuletzt die vollständige
Prüfung (verify_bgb.py). Der Hauptlauf verlangt einen geprüften Pilot mit
gleichen Parametern, gleichem Messcode, gleichem Datenstand und gleichem
PYTHONHASHSEED. Dokumentierte Läufe starten mit PYTHONHASHSEED=0.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import get_clock_info
import unicodedata

from gemeinsam import normalize_query
from gemeinsam.messung import MeasurementPlan, measure_phase, summarize_measurements, write_measurements
from invertierter_index import build_inverted_index
from positionsindex import build_positional_index, search_direct_phrase, search_index_phrase

if __package__:
    from .generator import expected_positions
    from .run import (ROOT, code_hashes, describe_dataset, independent_tokens, installed_version,
                      measure_comparison, memory_run, sha, validate_positional, write_json)
else:
    from generator import expected_positions
    from run import (ROOT, code_hashes, describe_dataset, independent_tokens, installed_version,
                     measure_comparison, memory_run, sha, validate_positional, write_json)


SERIES = "04_bgb"
MESSUNGEN = ROOT / "ergebnisse/messungen"
DATA_ROOT = ROOT  # Basis der relativen Datenpfade; Tests ersetzen sie durch einen Kleinkorpus.
STANDARD_PILOT = "04_bgb_pilot"
STANDARD_FINAL = "04_bgb"
PILOT_PLAN = MeasurementPlan(warmups=1, repeats=3, query_block_size=5)
FINAL_PLAN = MeasurementPlan(query_block_size=5)
PLANNED_BACKGROUND = (
    "planned protocol: no parallel project tests, PDF builds or other benchmark series; "
    "ordinary desktop background load; machine not isolated; not checked by the script"
)


def _query(query_id, text, group, length, documents, starts):
    return {"query_id": query_id, "text": text, "group": group, "phrase_length": length,
            "document_count": documents, "match_count": starts}


PARAMETERS = {
    "series": SERIES,
    "scope": "real BGB part of phrase series 04 only; synthetic 04 corpora are not remeasured",
    "real": {
        "dataset_id": "real_bgb",
        "dataset": "bgb-gesetze-im-internet-v1",
        "corpus_root": "daten/real/bgb/dokumente",
        "manifest": "daten/real/bgb/manifest.json",
        "proposals": "daten/real/bgb/anfragevorschlaege.json",
        "corpus_sha256": "dc1641fd49dfa45270a1865f454abd64cf7cf94d79b37af9657ff97d7602eadf",
        "document_count": 2486, "token_count": 213718, "vocabulary_size": 11398, "posting_count": 133909,
    },
    # Auswahl aus anfragevorschlaege.json (reihe_04_phrasensuche); Erwartungen: Dokumente, Starts.
    "queries": [
        _query("bgb_frequent_k2", "nach Maßgabe", "bgb_frequent", 2, 57, 64),
        _query("bgb_frequent_k3", "im Sinne des", "bgb_frequent", 3, 62, 85),
        _query("bgb_frequent_k4", "es sei denn, dass", "bgb_frequent", 4, 82, 85),
        _query("bgb_frequent_k5", "nach den Vorschriften über die", "bgb_frequent", 5, 35, 35),
        _query("bgb_rare_k2", "Bürgerlichen Gesetzbuchs", "bgb_rare", 2, 1, 1),
        _query("bgb_rare_k3", "Beginn der Rechtsfähigkeit", "bgb_rare", 3, 1, 1),
        _query("bgb_rare_k4", "nach Treu und Glauben", "bgb_rare", 4, 1, 1),
        _query("bgb_rare_k5", "mit Rücksicht auf die Verkehrssitte", "bgb_rare", 5, 2, 2),
        _query("bgb_common_words_k2", "der die", "bgb_common_words", 2, 32, 34),
        _query("bgb_wrong_order_k2", "Maßgabe nach", "bgb_wrong_order", 2, 0, 0),
        _query("bgb_wrong_order_k3", "des Sinne im", "bgb_wrong_order", 3, 0, 0),
        _query("bgb_missing_k3", "Verbindung zum Server", "bgb_missing", 3, 0, 0),
    ],
    "selection": ("frequent and rare phrase for each length 2..5; two very frequent words with rare phrase; "
                  "present words in wrong order (k2, k3); one missing word (k3); all from reihe_04_phrasensuche"),
    "memory_repeats": 3,
    "pilot_plan": asdict(PILOT_PLAN),
    "final_plan": asdict(FINAL_PLAN),
    "schedule": "shuffle every (algorithm,query) block per repetition with fixed seed",
}


@dataclass(frozen=True)
class RealPhraseQuery:
    """Phrase mit Originaltext; die Anfrageaufbereitung bleibt im gemessenen Aufruf."""

    query_id: str
    text: str
    tokens: tuple[str, ...]
    group: str
    expected: dict[str, list[int]]


def _display(path: Path) -> str:
    """Repositoryrelativer Pfad für Metadaten und Meldungen."""
    try:
        return Path(path).relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def python_hash_seed() -> str:
    """Tatsächlicher PYTHONHASHSEED; "random", wenn die Variable fehlt."""
    return os.environ.get("PYTHONHASHSEED", "random")


def positions_sha256(positions):
    """Wie berechne_erwartungen.positions_hash: Zeilen '<dokument>\\t<start>,...' in Dokumentordnung."""
    lines = [f"{identifier}\t{','.join(map(str, starts))}" for identifier, starts in sorted(positions.items())]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def canonical_corpus_sha256(hashes):
    """BGB-Korpushash: SHA-256 über '<sha256>  <dateiname>\\n' in Bytereihenfolge der Namen."""
    lines = "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def _json_sha256(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _relevant_data_hashes(manifest, proposals):
    """Gesperrter Datenstand: nur die verwendeten Teile von Manifest und Vorschlägen.

    Ein erneuter Produktivabgleich schreibt production_comparison mit neuem
    Datum in manifest.json, ohne Dokumente oder Erwartungen zu ändern. Gesperrt
    werden deshalb Dokumentliste, Korpushash und unabhängige Erwartungen sowie
    die Vorschläge der Reihe 04; die Hashes ganzer Dateien stehen nur in den
    Metadaten.
    """
    return {
        "manifest_documents_expectations_sha256": _json_sha256(
            {key: manifest[key] for key in ("dataset_id", "corpus_root", "corpus_sha256", "documents",
                                            "independent_expectations")}),
        "proposals_reihe_04_sha256": _json_sha256(
            {key: proposals[key] for key in ("dataset_id", "corpus_sha256", "method", "reihe_04_phrasensuche")}),
    }


def _load_sources(base):
    real = PARAMETERS["real"]
    manifest_path, proposals_path = base / real["manifest"], base / real["proposals"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    proposals = json.loads(proposals_path.read_text(encoding="utf-8"))
    return manifest_path, manifest, proposals_path, proposals


def data_hashes(base=None):
    """Aktueller gesperrter Datenstand (siehe _relevant_data_hashes)."""
    _, manifest, _, proposals = _load_sources(DATA_ROOT if base is None else base)
    return _relevant_data_hashes(manifest, proposals)


def bgb_fixture(base=None):
    """Prüft den Korpus gegen das Manifest; liefert unabhängige Tokens und Anfragen.

    Mehrere Dokumente: jede Datei mit Bytes und SHA-256 aus dem Manifest, keine
    zusätzlichen Dateien, kanonischer Korpushash, D/N/V/P und Tokenanfang aus
    den unabhängigen Erwartungen. Für jede gewählte Phrase müssen gesperrter
    Parameter, Anfragevorschlag, Manifest (falls die Phrase dort steht) und das
    Tupelschnitt-Orakel auf der Regex-Tokenisierung übereinstimmen:
    Dokumentliste, alle Startpositionen, Start- und Dokumentzahl, df der Wörter.
    """
    base = DATA_ROOT if base is None else base
    real = PARAMETERS["real"]
    manifest_path, manifest, proposals_path, proposals = _load_sources(base)
    expectations = manifest["independent_expectations"]
    assert manifest["dataset_id"] == proposals["dataset_id"] == expectations["dataset_id"] == real["dataset"], \
        "BGB-Manifest oder Anfragevorschläge gehören zu einem anderen Datensatz"
    assert (manifest["corpus_sha256"] == proposals["corpus_sha256"] == expectations["corpus_sha256"]
            == real["corpus_sha256"]), "BGB-Korpushash in Manifest/Vorschlägen weicht vom gesperrten Wert ab"
    root = base / real["corpus_root"]
    assert (manifest_path.parent / manifest["corpus_root"]) == root, "Korpuswurzel weicht vom Manifest ab"
    identifiers = [entry["document_id"] for entry in manifest["documents"]]
    assert identifiers == sorted(identifiers) and len(set(identifiers)) == len(identifiers) == real["document_count"], \
        "Manifest: Dokumentkennungen nicht eindeutig, nicht sortiert oder falsche Anzahl"
    assert sorted(path.name for path in root.iterdir()) == identifiers, \
        "Korpusordner enthält andere Dateien als das Manifest"
    texts, hashes = {}, {}
    for entry in manifest["documents"]:
        assert entry["source_path"] == entry["document_id"], "Dokument-ID ist der Dateiname unter dokumente/"
        payload = (root / entry["source_path"]).read_bytes()
        hashes[entry["document_id"]] = hashlib.sha256(payload).hexdigest()
        assert len(payload) == entry["bytes"] and hashes[entry["document_id"]] == entry["sha256"], \
            f"BGB-Datei weicht vom Manifest ab: {entry['document_id']}"
        texts[entry["document_id"]] = payload.decode("utf-8")
    assert canonical_corpus_sha256(hashes) == real["corpus_sha256"], "kanonischer Korpushash weicht ab"
    tokens = {identifier: independent_tokens(texts[identifier]) for identifier in identifiers}
    document_frequency = {}
    for sequence in tokens.values():
        for token in set(sequence):
            document_frequency[token] = document_frequency.get(token, 0) + 1
    statistics = {"document_count": len(tokens), "token_count": sum(map(len, tokens.values())),
                  "vocabulary_size": len(document_frequency), "posting_count": sum(document_frequency.values())}
    for key, value in statistics.items():
        assert value == expectations[key] == real[key], f"BGB: {key} weicht von den unabhängigen Erwartungen ab"
    first, prefix = expectations["first_document_id"], expectations["prefix_tokens_bgb_0001"]
    assert identifiers[0] == first and list(tokens[first][:len(prefix)]) == prefix, "Tokenanfang von § 1 weicht ab"
    proposed = {entry["query"]: entry for entry in proposals["reihe_04_phrasensuche"]}
    in_manifest = {entry["query"]: entry for entry in expectations["phrases"]}
    assert len(proposed) == len(proposals["reihe_04_phrasensuche"]), "doppelte Anfragevorschläge"
    queries, selection = [], []
    for spec in PARAMETERS["queries"]:
        entry = proposed[spec["text"]]
        terms = independent_tokens(spec["text"])
        assert list(terms) == entry["terms"] and len(terms) == spec["phrase_length"], \
            f"{spec['query_id']}: Normalform oder Phrasenlänge weicht ab"
        assert [document_frequency.get(term, 0) for term in terms] == entry["df_terms"], \
            f"{spec['query_id']}: df der Phrasenwörter weicht ab"
        assert "positions" in entry, f"{spec['query_id']}: vollständige Startpositionen erforderlich"
        expected = expected_positions(tokens, terms)
        assert expected == entry["positions"], f"{spec['query_id']}: Dokumentliste/Startpositionen weichen ab"
        assert len(expected) == entry["document_count"] == spec["document_count"], \
            f"{spec['query_id']}: Dokumentzahl weicht ab"
        assert sum(map(len, expected.values())) == entry["match_count"] == spec["match_count"], \
            f"{spec['query_id']}: Startzahl weicht ab"
        assert positions_sha256(expected) == entry["positions_sha256"], f"{spec['query_id']}: Positionshash weicht ab"
        if spec["text"] in in_manifest:
            assert ({key: value for key, value in in_manifest[spec["text"]].items() if key != "note"}
                    == {key: value for key, value in entry.items() if key != "note"}), \
                f"{spec['query_id']}: Manifest und Anfragevorschlag widersprechen sich"
        queries.append(RealPhraseQuery(spec["query_id"], spec["text"], terms, spec["group"], expected))
        selection.append({"query_id": spec["query_id"], "group": spec["group"],
                          **{key: value for key, value in entry.items() if key != "positions"},
                          "also_in_manifest_phrases": spec["text"] in in_manifest})
    fixture = {
        "dataset": real["dataset"], "corpus_root": real["corpus_root"],
        "manifest_path": real["manifest"], "proposals_path": real["proposals"],
        "data_sha256": _relevant_data_hashes(manifest, proposals),
        "canonical_corpus_sha256": canonical_corpus_sha256(hashes),
        "retrieved_at": manifest["retrieved_at"],
        "independent_tokenizer": ("run.independent_tokens: NFC, casefold, NFC, regex [^\\W_]+ with checks "
                                  "excluding M*/No/Nl; compared with every prepared token sequence"),
        "statistics": statistics, "first_document_id": first, "first_tokens": prefix,
        "corpus_selection": "all paragraphs of the fixed BGB retrieval; one paragraph per document; ID = file name",
        "query_selection": selection,
    }
    return root, tokens, queries, fixture


def datasets(temporary=None):
    """Einziger Datensatz dieses Laufs; Signatur wie run.datasets für memory.py."""
    root, tokens, queries, fixture = bgb_fixture()
    yield PARAMETERS["real"]["dataset_id"], root, tokens, queries, {"kind": "real", "source_fixture": fixture}


def target_directory(name: str) -> Path:
    """Neuer Ergebnisordner unter ergebnisse/messungen; nie Überschreiben."""
    if not name or name in {".", ".."} or Path(name).name != name or "/" in name or "\\" in name:
        raise SystemExit(f"Ungültiger Ordnername {name!r}: genau ein Name unter ergebnisse/messungen erwartet.")
    target = MESSUNGEN / name
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise SystemExit(f"{_display(target)} existiert und ist nicht leer; "
                         "gelieferte Ergebnisse werden nicht überschrieben. Neuen Namen mit --ausgabe wählen.")
    return target


def require_pilot(path: Path) -> dict:
    """Hauptlauf nur nach geprüftem Pilot mit identischen Bedingungen."""
    if not path.is_file():
        raise SystemExit("Zuerst --pilot ausführen: Parameter werden erst nach erfolgreichem Pilotlauf gesperrt.")
    decision = json.loads(path.read_text(encoding="utf-8"))
    if decision.get("pilot_correct") is not True or decision.get("locked_parameters") != PARAMETERS:
        raise SystemExit("Parameter unterscheiden sich vom erfolgreichen Pilotlauf; Pilot erneut ausführen.")
    if decision.get("method_code_sha256") != code_hashes():
        raise SystemExit("Messcode hat sich nach dem Pilot geändert oder der Pilot sperrt keinen Code; Pilot erneut ausführen.")
    if decision.get("python_hash_seed") != python_hash_seed():
        raise SystemExit("PYTHONHASHSEED weicht vom Pilot ab; mit demselben Wert wie im Pilot starten.")
    if decision.get("data_sha256") != data_hashes():
        raise SystemExit("BGB-Datenstand hat sich nach dem Pilot geändert; Pilot erneut ausführen.")
    if not (path.parent / "memory.json").is_file():
        raise SystemExit("Speicherlauf des Pilots fehlt; Pilot erneut ausführen.")
    if __package__:
        from .verify_bgb import verify_directory
    else:
        from verify_bgb import verify_directory
    verify_directory(path.parent)
    return decision


def make_metadata(plan, output, pilot, background=PLANNED_BACKGROUND):
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
    memory_info = Path("/proc/meminfo")
    total_memory = next((line for line in memory_info.read_text().splitlines() if line.startswith("MemTotal:")),
                        "unknown") if memory_info.exists() else "unknown"
    real = PARAMETERS["real"]
    status = git("status", "--porcelain")
    return {
        "series": SERIES, "run_id": output.name, "run_kind": "pilot" if pilot else "final",
        "output_directory": _display(output), "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(status), "git_status_at_start": status,
        "code_sha256": hashes, "source_archive": "code_source/",
        "data_sha256": data_hashes(),
        "data_files_sha256": {real["manifest"]: sha(DATA_ROOT / real["manifest"]),
                              real["proposals"]: sha(DATA_ROOT / real["proposals"])},
        "parameters": PARAMETERS, "measurement_plan": asdict(plan),
        "environment": {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
                        "implementation": platform.python_implementation(), "cpu_model": cpu,
                        "memory_total": total_memory, "logical_cpus": os.cpu_count(),
                        "python_hash_seed": python_hash_seed(),
                        "python_hash_seed_set": "PYTHONHASHSEED" in os.environ,
                        "unicode_database": unicodedata.unidata_version,
                        "pytest": installed_version("pytest"), "setuptools": installed_version("setuptools")},
        "timer": "time.perf_counter_ns; integer elapsed_ns per complete block",
        "clock": vars(get_clock_info("perf_counter")),
        "background_load": background,
        "cache": "same already prepared corpus and checked index reused; no cold-cache claim",
        "timing_boundaries": {
            "build": "separate complete public inverted/positional index builds on identical prepared documents; validation included; results checked outside timer",
            "query": "normalize_query(raw,'phrase') plus public phrase kernel and full fresh dict/list of start positions for BOTH methods",
            "block": "five identical complete calls retained then checked; equal loop/list overhead; destroy results before next timer",
            "excluded": "loading, preparation, manifest and oracle checks, summaries, output, memory instrumentation",
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
            "Only the real BGB part is measured; synthetic phrase-length and result-size series of 04 are not remeasured.",
            "Real phrases differ not only in length but also in words, CF/DF, candidate documents and result size; phrase length is not an isolated factor.",
            "Every result contains ALL phrase starts; CSV hit_count counts documents, position_count in metadata counts starts.",
            "One fixed BGB retrieval (2486 paragraphs, 213718 tokens); juridical vocabulary and very unequal document lengths; findings do not generalize to other text types.",
        ],
        "datasets": [],
    }


def timing_run(output, plan, info):
    """Zeitlauf: Aufbau beider Indizes und Phrasensuche; Speicher getrennt danach."""
    rows = []
    for identifier, directory, tokens, queries, extra in datasets():
        prepared, postings, expected, description = describe_dataset(identifier, directory, tokens, queries, extra)
        info["datasets"].append(description)
        print(f"{identifier}: N={description['token_count']}, D={len(prepared)}, "
              f"V={description['vocabulary_size']}, Anfragen={len(queries)}", flush=True)
        context = {"run_id": info["run_id"], "git_commit": info["git_commit"], "seed": plan.seed,
                   **{field: description[field] for field in ("dataset_id", "document_count", "text_bytes", "token_count")}}

        def check_postings(index):
            assert dict(index) == postings, "build violates independent postings"

        # Jedes Aufbauergebnis wird vor dem nächsten Aufbau verworfen.
        print(f"{identifier}: Aufbau Dokumentindex und Positionsindex", flush=True)
        rows.extend(measure_phase(lambda: build_inverted_index(prepared), check_postings, plan,
                                  phase="build", context={**context, "algorithm": "inverted_index"}))
        rows.extend(measure_phase(lambda: build_positional_index(prepared),
                                  lambda index: validate_positional(index, expected), plan,
                                  phase="build", context={**context, "algorithm": "positional_index"}))
        index = build_positional_index(prepared)
        validate_positional(index, expected)
        for query in queries:
            assert search_direct_phrase(prepared, query.tokens) == query.expected, f"{query.query_id}: direkte Suche"
            assert search_index_phrase(index, query.tokens) == query.expected, f"{query.query_id}: Positionsindex"
        operations = {
            "direct_phrase": lambda text: search_direct_phrase(prepared, normalize_query(text, "phrase")),
            "positional_phrase": lambda text: search_index_phrase(index, normalize_query(text, "phrase")),
        }
        print(f"{identifier}: Phrasensuche direkt gegen Positionsindex", flush=True)
        rows.extend(measure_comparison(operations, queries, plan, context))
        validate_positional(index, expected)
        assert {doc.document_id: doc.tokens for doc in prepared} == tokens
        del index, operations
    assert code_hashes() == info["code_sha256"], "code changed during timing"
    write_measurements(output / "raw.csv", rows)
    summary = summarize_measurements(rows)
    write_json(output / "summary.json", summary)
    info["timing_completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "metadata.json", info)
    return rows, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pilot", action="store_true", help="1 Aufwärmlauf, 3 Messungen; sperrt Parameter, Code und Daten")
    parser.add_argument("--ausgabe", metavar="NAME",
                        help=f"neuer Ordner unter ergebnisse/messungen (Standard {STANDARD_PILOT} bzw. {STANDARD_FINAL})")
    parser.add_argument("--pilot-ordner", metavar="NAME", default=STANDARD_PILOT,
                        help=f"Pilotordner mit pilot_decision.json für den Hauptlauf (Standard {STANDARD_PILOT})")
    parser.add_argument("--hintergrundlast", metavar="TEXT", default=PLANNED_BACKGROUND,
                        help="tatsächliche Hintergrundlast für die Metadaten")
    args = parser.parse_args(argv)
    output = target_directory(args.ausgabe or (STANDARD_PILOT if args.pilot else STANDARD_FINAL))
    plan = PILOT_PLAN if args.pilot else FINAL_PLAN
    pilot_directory = None
    if not args.pilot:
        pilot_directory = MESSUNGEN / args.pilot_ordner
        if not args.pilot_ordner or Path(args.pilot_ordner).name != args.pilot_ordner or pilot_directory == output:
            raise SystemExit("--pilot-ordner muss ein anderer Ordnername unter ergebnisse/messungen sein.")
        require_pilot(pilot_directory / "pilot_decision.json")
    if python_hash_seed() != "0":
        print(f"Hinweis: PYTHONHASHSEED={python_hash_seed()}; dokumentierte Läufe verwenden PYTHONHASHSEED=0.", flush=True)
    output.mkdir(parents=True, exist_ok=True)
    info = make_metadata(plan, output, args.pilot, args.hintergrundlast)
    if pilot_directory is not None:
        info["pilot_directory"] = _display(pilot_directory)
    rows, summary = timing_run(output, plan, info)
    print("Speicherlauf: je Indexart ein eigener Prozess", flush=True)
    memory_run(output)
    if __package__:
        from .verify_bgb import verify_directory
    else:
        from verify_bgb import verify_directory
    counts = verify_directory(output, require_decision=False)
    if args.pilot:
        write_json(output / "pilot_decision.json", {
            "pilot_correct": True, "locked_parameters": PARAMETERS,
            "method_code_sha256": info["code_sha256"], "data_sha256": info["data_sha256"],
            "python_hash_seed": info["environment"]["python_hash_seed"], "pilot_plan": asdict(plan),
            "decision": ("BGB manifest, independent token and phrase expectations, full start positions, "
                         "timing and separate memory run verified; parameters, code and data locked for final"),
            "verified_counts": {"raw_rows": counts[0], "summary_groups": counts[1], "files": counts[2],
                                "memory_rows": counts[3]},
            "pilot_is_not_final_measurement": True,
        })
    print(f"Gespeichert und geprüft: {_display(output)}; {len(rows)} Rohwerte, {len(summary)} Gruppen, "
          f"{counts[3]} Speicherwerte", flush=True)


if __name__ == "__main__":
    main()
