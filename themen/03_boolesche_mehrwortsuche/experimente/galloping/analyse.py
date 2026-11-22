#!/usr/bin/env python3
"""Reihe 03b: nur gespeicherte, geprüfte Werte auswerten; keine erneute Laufzeitmessung."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


def load_sibling(name):
    """Lädt ein Skript dieses Ordners unter eindeutigem Namen (Reihe 03 hat gleichnamige Skripte)."""
    label = f"reihe03b_{name}"
    if label not in sys.modules:
        spec = importlib.util.spec_from_file_location(label, Path(__file__).resolve().with_name(f"{name}.py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[label] = module
        spec.loader.exec_module(module)
    return sys.modules[label]


run = load_sibling("run")
verify_results = load_sibling("verify_results")

CASE_LABELS = {"verteilt": "kurze Liste verteilt", "anfang": "kurze Liste am Anfang"}


def comparisons(summary, metadata):
    """Je Fall und Stufe: Median, Quartile, IQR beider Verfahren und Diagnosezähler."""
    lookup = {(item["algorithm"], item["query_id"]): item for item in summary if item["phase"] == "query"}
    dataset = metadata["datasets"][0]
    rows = []
    for query in dataset["queries"]:
        two_pointer = lookup["and_shortest_first", query["query_id"]]
        galloping = lookup["and_galloping", query["query_id"]]
        diagnostics = query["diagnostics"]
        rows.append({
            "query_id": query["query_id"], "case": query["case"], "stage": query["stage"],
            "long_document_frequency": query["long_document_frequency"],
            "posting_lengths": query["posting_lengths_input_order"], "hit_count": query["hit_count"],
            "two_pointer_median_ms": two_pointer["median_ms"], "two_pointer_q1_ms": two_pointer["q1_ms"],
            "two_pointer_q3_ms": two_pointer["q3_ms"], "two_pointer_iqr_ms": two_pointer["iqr_ms"],
            "galloping_median_ms": galloping["median_ms"], "galloping_q1_ms": galloping["q1_ms"],
            "galloping_q3_ms": galloping["q3_ms"], "galloping_iqr_ms": galloping["iqr_ms"],
            "two_pointer_over_galloping_ratio": two_pointer["median_ms"] / galloping["median_ms"],
            "sample_count": two_pointer["sample_count"],
            "two_pointer_id_comparisons": diagnostics["and_shortest_first"]["id_comparisons"],
            "two_pointer_pointer_advances": diagnostics["and_shortest_first"]["pointer_advances"],
            "galloping_id_comparisons": diagnostics["and_galloping"]["id_comparisons"],
            "galloping_probes": diagnostics["and_galloping"]["gallop_probes"],
            "galloping_binary_search_steps": diagnostics["and_galloping"]["binary_search_steps"],
            "galloping_equality_checks": diagnostics["and_galloping"]["equality_checks"],
        })
    order = {case: position for position, case in enumerate(run.CASES)}
    return sorted(rows, key=lambda row: (order[row["case"]], row["long_document_frequency"]))


def number(value, digits=2):
    """Deutsche Schreibweise: Tausenderpunkt, Dezimalkomma."""
    text = f"{value:,.{digits}f}"
    return text.replace(",", " ").replace(".", ",").replace(" ", ".")


def report(rows, metadata, source):
    plan = metadata["measurement_plan"]
    pilot = metadata["run_id"] == "03b_pilot"
    lines = ["# Beobachtete Ergebnisse der Reihe 03b (Galloping Search gegen Zwei-Zeiger)", ""]
    if pilot:
        lines += ["**Pilotlauf.** Diese Werte belegen nur, dass die Pipeline funktioniert. Sie sind keine "
                  "Ergebnisse und werden nicht interpretiert.", ""]
    lines += [f"Mediane und Interquartilsabstände (IQR) in Mikrosekunden pro vollständiger Anfrage aus "
              f"{plan['repeats']} Blöcken mit je {plan['query_block_size']} Anfragen. Beide Verfahren laufen über "
              "`search_index_boolean` mit AND, kurzes Wort zuerst, und sortieren die Listen stabil nach Länge. "
              "Ein Verhältnis Zwei-Zeiger/Galloping über 1 beschreibt einen beobachteten Medianvorteil der "
              "Galloping Search, unter 1 einen Nachteil. Es ist kein Signifikanztest. Die Vergleichszahlen "
              "stammen aus getrennten Diagnoseläufen außerhalb der Timer.", ""]
    for case in run.CASES:
        lines += [f"## Fall „{case}“: {CASE_LABELS[case]}", "",
                  "| df lange Liste | Zwei-Zeiger µs (IQR) | Galloping µs (IQR) | Zwei-Zeiger/Galloping | "
                  "Vergleiche Zwei-Zeiger | Vergleiche Galloping |",
                  "| ---: | ---: | ---: | ---: | ---: | ---: |"]
        for row in (row for row in rows if row["case"] == case):
            lines.append(
                f"| {number(row['long_document_frequency'], 0)} | "
                f"{number(row['two_pointer_median_ms'] * 1000)} ({number(row['two_pointer_iqr_ms'] * 1000)}) | "
                f"{number(row['galloping_median_ms'] * 1000)} ({number(row['galloping_iqr_ms'] * 1000)}) | "
                f"{number(row['two_pointer_over_galloping_ratio'], 3)} | "
                f"{number(row['two_pointer_id_comparisons'], 0)} | {number(row['galloping_id_comparisons'], 0)} |")
        lines.append("")
    dataset = metadata["datasets"][0]
    lines += ["Vergleiche sind relationale Kennungsvergleiche: beim Zwei-Zeiger-Verfahren `==` und bei "
              "Ungleichheit zusätzlich `<`, bei der Galloping Search Proben der Sprungphase, "
              "Binärsuchschritte und die abschließende Gleichheitsprüfung. Einzelzähler stehen in "
              "`comparisons.json` und `metadata.json`.", "",
              f"Korpus: {number(dataset['document_count'], 0)} erzeugte Dokumente mit je "
              f"{metadata['parameters']['synthetic']['tokens_per_document']} Tokens "
              f"(N = {number(dataset['token_count'], 0)}), kurze Liste immer "
              f"{metadata['parameters']['short_document_frequency']} Dokumente und Teilmenge der langen Liste. "
              "Die direkte Suche diente nur der Trefferprüfung vor dem ersten Timer und wurde nicht gemessen. "
              "Betriebssystem-Caches, Python-Allokation und gewöhnliche Hintergrundlast sind Grenzen. "
              "Laufzeiten enthalten Normalisierung, Postingzugriff, Sortierung und die vollständige Ergebnisliste.", "",
              f"Quelle: `{source}`. Gemessener Git-Ausgangspunkt: `{metadata['git_commit']}`, "
              f"uncommittierte Änderungen vorhanden: `{metadata['git_dirty']}`, "
              f"PYTHONHASHSEED: `{metadata['environment']['python_hash_seed']}`. "
              "Exakte Quellenstände mit SHA-256 sind unter `code_source/` archiviert."]
    return "\n".join(lines) + "\n"


def analyse(directory, output, *, check_active_code=True):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    verify_results.verify_directory(directory, check_active_code=check_active_code)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    rows = comparisons(summary, metadata)
    run.write_json(output / "comparisons.json", rows)
    source = directory.relative_to(run.ROOT).as_posix() if directory.is_relative_to(run.ROOT) else directory.name
    (output / "auswertung.md").write_text(report(rows, metadata, f"{source}/raw.csv"), encoding="utf-8")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-only", action="store_true")
    parser.add_argument("--eingabe", metavar="NAME", default=run.STANDARD_FINAL,
                        help=f"Messordner unter ergebnisse/messungen (Standard {run.STANDARD_FINAL}); Ausgabe ebendort")
    args = parser.parse_args(argv)
    directory = run.messlauf03.directory_name(args.eingabe)
    analyse(directory, directory, check_active_code=not args.archive_only)
    print("comparisons.json und auswertung.md aus geprüften Rohwerten erzeugt.")


if __name__ == "__main__":
    main()
