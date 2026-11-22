#!/usr/bin/env python3
"""Reihe 03, Realteil BGB: boolesche Suche auf dem BGB (ein Paragraph je Dokument).

Nur der Realteil wird neu gemessen; die synthetische Reihe 03 bleibt unverändert.
Pilot und Finallauf schreiben in neue Ordner unter ergebnisse/messungen
(Standard 03_bgb_pilot und 03_bgb); nicht leere Ordner werden nie überschrieben.
Der Finallauf verlangt einen erfolgreichen Pilot mit gleichen Parametern, gleichem
Messcode und PYTHONHASHSEED=0.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import sys
from time import perf_counter_ns
import unicodedata

HERE = Path(__file__).resolve().parent
# Eigener Ordner und Reihe-03-Ordner (Diagnose, Laufkonvention) nur anhängen:
# gleichnamige Skripte der Reihe 03 (run, verify_results, analyse) dürfen nichts verdecken.
for _directory in (HERE, HERE.parent):
    if str(_directory) not in sys.path:
        sys.path.append(str(_directory))

from gemeinsam import load_corpus, prepare_corpus  # noqa: E402
from gemeinsam.messung import (  # noqa: E402
    MeasurementPlan, measure_phase, summarize_measurements, write_measurements,
)
from invertierter_index import build_inverted_index  # noqa: E402
from boolesche_suche import normalize_boolean_query, search_direct_boolean, search_index_boolean  # noqa: E402

from boolean_diagnostics import (  # noqa: E402
    diagnose_direct, diagnose_direct_exclude, diagnose_postings, diagnose_postings_galloping,
    difference_diagnostic,
)
import messlauf03  # noqa: E402


ROOT = HERE.parents[3]
STANDARD_PILOT = "03_bgb_pilot"
STANDARD_FINAL = "03_bgb"
REQUIRED_HASH_SEED = messlauf03.REQUIRED_HASH_SEED
ALGORITHMS = ("and_galloping", "and_input_order", "and_shortest_first", "direct_boolean", "or_input_order")
INDEX_VARIANT = {"and_input_order": "input_order", "and_shortest_first": "shortest_first",
                 "and_galloping": "galloping", "or_input_order": "input_order"}
# Kleine Auswahl aus daten/real/bgb/anfragevorschlaege.json (reihe_03_boolesche_suche).
QUERY_PLAN = [
    {"query_id": "and_k2_selten_vorn", "terms": ["Verbindung", "der"], "operator": "AND", "exclude": None,
     "purpose": "Reihenfolge: kurze Liste vorn; Galloping bei großem Längenverhältnis (16 zu 2280)"},
    {"query_id": "and_k2_haeufig_vorn", "terms": ["der", "Verbindung"], "operator": "AND", "exclude": None,
     "purpose": "Reihenfolge: lange Liste vorn, dieselben Wörter"},
    {"query_id": "and_k2_extrem", "terms": ["Erbschaftskauf", "der"], "operator": "AND", "exclude": None,
     "purpose": "Galloping bei extremem Längenverhältnis (1 zu 2280)"},
    {"query_id": "and_k2_aehnlich", "terms": ["Mieter", "Vermieter"], "operator": "AND", "exclude": None,
     "purpose": "Galloping bei ähnlichen Listenlängen (79 zu 82)"},
    {"query_id": "and_k2_mittel", "terms": ["Vertrag", "Schadensersatz"], "operator": "AND", "exclude": None,
     "purpose": "Begriffszahl k=2, mittlere Wörter; Grundlage des AND-NOT-Falls"},
    {"query_id": "and_k3_mittel", "terms": ["Gläubiger", "Schuldner", "Frist"], "operator": "AND", "exclude": None,
     "purpose": "Begriffszahl k=3, mittlere Wörter"},
    {"query_id": "and_k5_mittel", "terms": ["Vertrag", "Schadensersatz", "Frist", "Gläubiger", "Schuldner"],
     "operator": "AND", "exclude": None, "purpose": "Begriffszahl k=5, mittlere Wörter, leerer Schnitt"},
    {"query_id": "and_k5_selten_vorn", "terms": ["Verbindung", "der", "die", "des", "und"], "operator": "AND",
     "exclude": None, "purpose": "k=5, ein seltenes und vier häufige Wörter, seltenes vorn"},
    {"query_id": "and_k5_selten_hinten", "terms": ["und", "des", "die", "der", "Verbindung"], "operator": "AND",
     "exclude": None, "purpose": "Reihenfolge bei k=5: dieselben Wörter, seltenes hinten"},
    {"query_id": "and_k5_haeufig", "terms": ["der", "die", "des", "und", "oder"], "operator": "AND", "exclude": None,
     "purpose": "k=5, fünf häufige Wörter mit ähnlichen Längen, großes Ergebnis"},
    {"query_id": "and_leer_vorhanden", "terms": ["Mieter", "Erblasser"], "operator": "AND", "exclude": None,
     "purpose": "leeres Ergebnis, obwohl beide Wörter vorkommen"},
    {"query_id": "or_k2_mittel", "terms": ["Vertrag", "Schadensersatz"], "operator": "OR", "exclude": None,
     "purpose": "OR, k=2, mittlere Wörter"},
    {"query_id": "or_k3_mittel", "terms": ["Gläubiger", "Schuldner", "Frist"], "operator": "OR", "exclude": None,
     "purpose": "OR, k=3, mittlere Wörter"},
    {"query_id": "or_k5_haeufig", "terms": ["der", "die", "des", "und", "oder"], "operator": "OR", "exclude": None,
     "purpose": "OR mit großer Ergebnismenge (fast alle Dokumente)"},
    {"query_id": "and_not_k2", "terms": ["Vertrag", "Schadensersatz"], "operator": "AND", "exclude": "Verbraucher",
     "purpose": "AND NOT: Vertrag AND Schadensersatz AND NOT Verbraucher"},
]
PARAMETERS = {
    "seed": 20261006,
    "dataset_id": "real_bgb",
    "dataset": "bgb-gesetze-im-internet-v1",
    "corpus_root": "daten/real/bgb/dokumente",
    "manifest": "daten/real/bgb/manifest.json",
    "proposals": "daten/real/bgb/anfragevorschlaege.json",
    "proposal_section": "reihe_03_boolesche_suche",
    "corpus_sha256": "dc1641fd49dfa45270a1865f454abd64cf7cf94d79b37af9657ff97d7602eadf",
    "document_count": 2486,
    "token_count": 213718,
    "queries": QUERY_PLAN,
    "algorithms": {
        "direct_boolean": "search_direct_boolean (all queries, with exclude for AND NOT)",
        "and_input_order": "search_index_boolean(..., 'AND', 'input_order'[, exclude])",
        "and_shortest_first": "search_index_boolean(..., 'AND', 'shortest_first'[, exclude])",
        "and_galloping": "search_index_boolean(..., 'AND', 'galloping'[, exclude])",
        "or_input_order": "search_index_boolean(..., 'OR', 'input_order')"},
    "final_plan": asdict(MeasurementPlan(query_block_size=5)),
    "schedule": "shuffle all eligible (algorithm,query) blocks per repetition; fixed seed",
    "required_python_hash_seed": REQUIRED_HASH_SEED,
    "synthetic_series_03": "not remeasured; delivered 03_boolesche_mehrwortsuche stays as is",
}


@dataclass(frozen=True)
class RealQuery:
    query_id: str
    terms: tuple[str, ...]
    operator: str
    exclude: str | None
    expected_ids: tuple[str, ...]

    @property
    def query_type(self):
        return "and_not" if self.exclude is not None else self.operator.lower()

    @property
    def text(self):
        value = {"terms": list(self.terms), "operator": self.operator}
        if self.exclude is not None:
            value["exclude"] = self.exclude
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


write_json = messlauf03.write_json
sha = messlauf03.sha


def code_hashes():
    """Gebundener Messcode: Such-/Indexpakete, gemeinsame Messung, Skripte, Diagnose, Laufkonvention."""
    files = {*ROOT.glob("gemeinsam/src/gemeinsam/*.py"),
             *ROOT.glob("themen/02_invertierter_index_einzelwortsuche/src/invertierter_index/*.py"),
             *ROOT.glob("themen/03_boolesche_mehrwortsuche/src/boolesche_suche/*.py"),
             *HERE.glob("*.py"), HERE.parent / "boolean_diagnostics.py", HERE.parent / "messlauf03.py",
             ROOT / "gemeinsam/__init__.py", ROOT / "pyproject.toml", ROOT / "requirements-dev.txt"}
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(files) if path.is_file()}


def independent_tokens(text):
    """Zweite Tokenisierung per Regex ohne gemeinsam.tokenize (wie Reihe 01 und das Manifest).

    [^\\W_]+ entspricht L* und Nd nur ohne kombinierende Zeichen sowie No/Nl; beides wird geprüft.
    """
    normalized = unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).casefold())
    if any(unicodedata.category(character)[0] == "M" or unicodedata.category(character) in {"No", "Nl"}
           for character in normalized):
        raise AssertionError("Regex-Gegenprobe gilt nur ohne M*, No und Nl")
    return tuple(re.findall(r"[^\W_]+", normalized))


def independent_word(raw):
    tokens = independent_tokens(raw)
    if len(tokens) != 1:
        raise AssertionError(f"{raw!r} ergibt nicht genau ein Token")
    return tokens[0]


def canonical_corpus_sha256(hashes):
    lines = "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def list_sha256(values):
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def check_document_list(identifiers, entry, label):
    """Trefferliste gegen vollständige Liste oder Anzahl/Hash/Ränder der Erwartung."""
    if "document_ids" in entry:
        if list(identifiers) != entry["document_ids"]:
            raise AssertionError(f"{label}: Trefferliste weicht von der unabhängigen Erwartung ab")
    elif (len(identifiers) != entry["document_ids_count"] or list_sha256(list(identifiers)) != entry["document_ids_sha256"]
          or list(identifiers[:5]) != entry["document_ids_first5"] or list(identifiers[-5:]) != entry["document_ids_last5"]):
        raise AssertionError(f"{label}: Trefferliste weicht von Anzahl/Hash der Erwartung ab")
    if len(identifiers) != entry["hit_count"]:
        raise AssertionError(f"{label}: Trefferzahl weicht ab")


def find_proposal(proposals, kind, terms, exclude):
    """Vorschlag mit gleicher Art und gleichen Wörtern; Permutation nur bei gleicher Wortmenge."""
    candidates = [entry for entry in proposals if entry["kind"] == kind and entry.get("exclude_term") == exclude]
    for entry in candidates:
        if entry["terms"] == list(terms):
            return entry, "exact"
    for entry in candidates:
        if sorted(entry["terms"]) == sorted(terms):
            return entry, "permutation"
    raise AssertionError(f"kein Anfragevorschlag für {kind} {terms} {exclude}")


def bgb_fixture():
    """Dateien, Korpushash und Tokens gegen das Manifest; Anfragen gegen die Vorschläge.

    Alle Erwartungen entstehen aus der Regex-Tokenisierung und den unabhängig
    berechneten Vorschlägen, nicht aus Produktionscode.
    """
    manifest_path, proposals_path = ROOT / PARAMETERS["manifest"], ROOT / PARAMETERS["proposals"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    proposals_file = json.loads(proposals_path.read_text(encoding="utf-8"))
    expectations = manifest["independent_expectations"]
    if not (manifest["dataset_id"] == proposals_file["dataset_id"] == PARAMETERS["dataset"]
            and manifest["corpus_sha256"] == proposals_file["corpus_sha256"] == expectations["corpus_sha256"]
            == PARAMETERS["corpus_sha256"]):
        raise AssertionError("BGB-Manifest oder Anfragevorschläge gehören zu einem anderen Datenstand")
    if (expectations["document_count"], expectations["token_count"]) != (PARAMETERS["document_count"],
                                                                        PARAMETERS["token_count"]):
        raise AssertionError("BGB-Kennzahlen weichen von den gesperrten Parametern ab")
    root = ROOT / PARAMETERS["corpus_root"]
    texts, hashes = {}, {}
    for entry in manifest["documents"]:
        payload = (root / entry["source_path"]).read_bytes()
        if len(payload) != entry["bytes"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise AssertionError(f"BGB-Datei weicht vom Manifest ab: {entry['document_id']}")
        texts[entry["document_id"]] = payload.decode("utf-8")
        hashes[entry["document_id"]] = entry["sha256"]
    on_disk = sorted(path.name for path in root.iterdir() if path.is_file() and path.suffix == ".txt")
    if on_disk != sorted(texts):
        raise AssertionError("BGB-Korpusordner enthält andere Dateien als das Manifest")
    if canonical_corpus_sha256(hashes) != PARAMETERS["corpus_sha256"]:
        raise AssertionError("BGB: kanonischer Korpushash weicht ab")
    tokens = {identifier: independent_tokens(texts[identifier]) for identifier in sorted(texts)}
    if sum(map(len, tokens.values())) != PARAMETERS["token_count"]:
        raise AssertionError("BGB: unabhängige Tokenzahl weicht vom Manifest ab")
    postings = independent_postings(tokens)
    manifest_df = {entry["term"]: entry["df"] for entry in expectations["words"]}
    proposals = proposals_file[PARAMETERS["proposal_section"]]
    queries, references = [], {}
    for plan in QUERY_PLAN:
        terms = tuple(independent_word(raw) for raw in plan["terms"])
        exclude = None if plan["exclude"] is None else independent_word(plan["exclude"])
        kind = "and_not" if exclude is not None else plan["operator"].lower()
        entry, match = find_proposal(proposals, kind, terms, exclude)
        df = {term: len(postings.get(term, ())) for term in terms}
        if [df[term] for term in entry["terms"]] != entry["df"]:
            raise AssertionError(f"{plan['query_id']}: Dokumentfrequenzen weichen vom Vorschlag ab")
        for term in (*terms, *([exclude] if exclude else [])):
            if term in manifest_df and manifest_df[term] != len(postings.get(term, ())):
                raise AssertionError(f"{plan['query_id']}: df({term}) widerspricht dem Manifest")
        sets = [set(postings.get(term, ())) for term in terms]
        hits = set.intersection(*sets) if plan["operator"] == "AND" else set.union(*sets)
        if exclude is not None:
            if len(hits) != entry["and_hit_count_before_exclude"] or len(postings.get(exclude, ())) != entry["exclude_df"]:
                raise AssertionError(f"{plan['query_id']}: AND-Teil oder NOT-Liste weicht vom Vorschlag ab")
            hits -= set(postings.get(exclude, ()))
        expected = tuple(sorted(hits))
        check_document_list(expected, entry, plan["query_id"])
        queries.append(RealQuery(plan["query_id"], tuple(plan["terms"]), plan["operator"], plan["exclude"], expected))
        references[plan["query_id"]] = {"proposal_note": entry["note"], "proposal_match": match,
                                        "proposal_terms": entry["terms"], "proposal_df": entry["df"]}
    fixture = {"dataset": PARAMETERS["dataset"], "corpus_root": PARAMETERS["corpus_root"],
               "manifest_path": PARAMETERS["manifest"], "manifest_sha256": sha(manifest_path),
               "proposals_path": PARAMETERS["proposals"], "proposals_sha256": sha(proposals_path),
               "corpus_sha256": manifest["corpus_sha256"], "files": hashes}
    return fixture, tokens, postings, queries, references


def independent_postings(tokens_by_id):
    postings = {}
    for identifier in sorted(tokens_by_id):
        for word in set(tokens_by_id[identifier]):
            postings.setdefault(word, []).append(identifier)
    return {word: tuple(ids) for word, ids in postings.items()}


def eligible(algorithm, query):
    if algorithm == "direct_boolean":
        return True
    if algorithm.startswith("and_"):
        return query.operator == "AND"
    return query.operator == "OR"


def index_diagnostics(postings, normalized, query, algorithm):
    """Vergleichszähler außerhalb der Timer; AND NOT ergänzt die Differenz."""
    variant = INDEX_VARIANT[algorithm]
    if algorithm == "and_galloping":
        value = diagnose_postings_galloping(postings, normalized.terms)
    else:
        value = diagnose_postings(postings, normalized.terms, query.operator, variant)
    if normalized.exclude is not None:
        excluded = postings.get(normalized.exclude, ())
        value["difference_input_lengths"] = [len(value["result_ids"]), len(excluded)]
        if value["result_ids"]:
            value["result_ids"], comparisons, advances = difference_diagnostic(value["result_ids"], excluded)
        else:
            comparisons = advances = 0
        value["difference_id_comparisons"] = comparisons
        value["difference_pointer_advances"] = advances
        value["total_id_comparisons"] = value["id_comparisons"] + comparisons
    return value


def query_metadata(query, postings, tokens_by_id, reference):
    normalized = normalize_boolean_query(query.terms, query.operator, query.exclude)
    diagnostics = {}
    for algorithm in ALGORITHMS:
        if algorithm == "direct_boolean" or not eligible(algorithm, query):
            continue
        value = index_diagnostics(postings, normalized, query, algorithm)
        assert tuple(value.pop("result_ids")) == query.expected_ids, f"{query.query_id}/{algorithm}: Diagnose"
        diagnostics[algorithm] = value
    if normalized.exclude is None:
        direct = diagnose_direct(tokens_by_id, normalized.terms, query.operator)
    else:
        direct = diagnose_direct_exclude(tokens_by_id, normalized.terms, normalized.exclude)
    assert tuple(direct.pop("result_ids")) == query.expected_ids, f"{query.query_id}: direkte Diagnose"
    return {"query_id": query.query_id, "terms": list(query.terms), "normalized_terms": list(normalized.terms),
            "operator": query.operator, "exclude": query.exclude, "normalized_exclude": normalized.exclude,
            "query_type": query.query_type, "text": query.text,
            "purpose": next(plan["purpose"] for plan in QUERY_PLAN if plan["query_id"] == query.query_id),
            "effective_term_count": len(normalized.terms),
            "posting_lengths_input_order": [len(postings.get(term, ())) for term in normalized.terms],
            "exclude_posting_length": (None if normalized.exclude is None
                                       else len(postings.get(normalized.exclude, ()))),
            "expected_ids": list(query.expected_ids), "hit_count": len(query.expected_ids),
            "proposal": reference, "diagnostics": diagnostics, "direct_diagnostics": direct}


def validate_dataset():
    """Vollständige Prüfung vor dem ersten Timer; liefert Daten und Datensatzbeschreibung."""
    fixture, tokens, postings, queries, references = bgb_fixture()
    directory = ROOT / PARAMETERS["corpus_root"]
    raw = load_corpus(directory)
    prepared = prepare_corpus(raw)
    files = [{"document_id": doc.document_id, "source_path": doc.source_path,
              "bytes": len(doc.raw_text.encode("utf-8")),
              "sha256": hashlib.sha256(doc.raw_text.encode("utf-8")).hexdigest()} for doc in raw]
    assert {entry["document_id"]: entry["sha256"] for entry in files} == fixture["files"], "Dateien weichen ab"
    assert {doc.document_id: doc.tokens for doc in prepared} == tokens, \
        "Aufbereitung weicht von der unabhängigen Tokenisierung ab"
    index = build_inverted_index(prepared)
    assert dict(index) == postings, "Index weicht von unabhängigen Postings ab"
    fixed_index = dict(index)
    for query in queries:
        expected = list(query.expected_ids)
        assert search_direct_boolean(prepared, query.terms, query.operator, query.exclude) == expected, query.query_id
        for algorithm in ALGORITHMS:
            if algorithm != "direct_boolean" and eligible(algorithm, query):
                assert search_index_boolean(index, query.terms, query.operator, INDEX_VARIANT[algorithm],
                                            query.exclude) == expected, f"{query.query_id}/{algorithm}"
    assert dict(index) == fixed_index
    del fixture["files"]
    dataset = {"dataset_id": PARAMETERS["dataset_id"], "kind": "real", "source_fixture": fixture,
               "corpus_sha256": canonical_corpus_sha256({entry["document_id"]: entry["sha256"] for entry in files}),
               "document_count": len(raw), "text_bytes": sum(entry["bytes"] for entry in files),
               "token_count": sum(len(doc.tokens) for doc in prepared), "vocabulary_size": len(postings),
               "posting_count": sum(map(len, postings.values())),
               "queries": [query_metadata(query, postings, tokens, references[query.query_id]) for query in queries]}
    return directory, raw, prepared, index, queries, dataset


def measure_comparison(operations, queries, plan, context):
    """Alle zulässigen (Verfahren, Anfrage)-Blöcke je Wiederholung mit festem Seed gemischt."""
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
            results = [operation(query) for _ in range(plan.query_block_size)]
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
            # Ergebnisse vor dem nächsten Timer freigeben.
            del result, results
    return rows


def metadata(plan, output, pilot, background, pilot_reference=None):
    hashes = code_hashes()
    messlauf03.archive_sources(output, hashes)
    info = {"run_id": "03_bgb_pilot" if pilot else "03_bgb_final", **messlauf03.run_header(output, pilot, background),
            "code_sha256": hashes, "source_archive": "code_source/", "parameters": PARAMETERS,
            "measurement_plan": asdict(plan),
            "timer": "time.perf_counter_ns; integer elapsed_ns per complete block",
            "cache": "prepared corpus and prechecked index reused; no cold-cache measurement; load includes OS cache effects",
            "timing_boundaries": {
                "load": "complete public load_corpus on daten/real/bgb/dokumente",
                "preparation": "complete public prepare_corpus on already loaded raw documents",
                "build": "complete public build_inverted_index on prepared documents",
                "query": "complete public search including query and exclude normalization, posting gathering, "
                         "stable length sort if applicable, merging, difference for AND NOT, full fresh result list",
                "block": "five complete identical calls retained then checked; previous results deleted before next timer",
                "excluded": "manifest/proposal checks, correctness, diagnostics, disk output and summary"},
            "statistics": "median, inclusive Q1/Q3, IQR; one block is one sample; quartiles are not confidence intervals",
            "memory": "not measured; CSV index_bytes and peak_memory_bytes remain empty",
            "real_corpus": "BGB (daten/real/bgb/dokumente, 2486 paragraphs, one document each); "
                           "delivered series 03 real part used the Kafka excerpt",
            "datasets": []}
    if pilot_reference is not None:
        info["pilot_reference"] = pilot_reference
    return info


def require_pilot(path):
    return messlauf03.require_pilot(path, PARAMETERS, code_hashes())


def timing_run(output, plan, pilot, background=messlauf03.PLANNED_BACKGROUND, pilot_reference=None):
    info = metadata(plan, output, pilot, background, pilot_reference)
    directory, raw, prepared, index, queries, description = validate_dataset()
    info["datasets"].append(description)
    context = {"run_id": info["run_id"], "git_commit": info["git_commit"], "seed": plan.seed,
               **{field: description[field] for field in ("dataset_id", "document_count", "text_bytes", "token_count")}}

    def check(value, expected):
        assert value == expected, "Vorbereitungsphase verändert den Korpus"
    rows = []
    for phase, algorithm, operation, expected in (
            ("load", "corpus_loader", lambda: load_corpus(directory), raw),
            ("preparation", "tokenizer", lambda: prepare_corpus(raw), prepared),
            ("build", "inverted_index", lambda: build_inverted_index(prepared), index)):
        rows.extend(measure_phase(operation, lambda value: check(value, expected), plan,
                                  phase=phase, context={**context, "algorithm": algorithm}))
    operations = {
        "direct_boolean": lambda q: search_direct_boolean(prepared, q.terms, q.operator, q.exclude),
        "and_input_order": lambda q: search_index_boolean(index, q.terms, q.operator, "input_order", q.exclude),
        "and_shortest_first": lambda q: search_index_boolean(index, q.terms, q.operator, "shortest_first", q.exclude),
        "and_galloping": lambda q: search_index_boolean(index, q.terms, q.operator, "galloping", q.exclude),
        "or_input_order": lambda q: search_index_boolean(index, q.terms, q.operator, "input_order"),
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
            "decision": "Manifest, Anfragevorschläge, Treffer und Diagnosen korrekt; Parameter für den Finallauf gesperrt",
            "pilot_is_not_final_measurement": True})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
