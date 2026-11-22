#!/usr/bin/env python3
"""Reihe 03 BGB: nur gespeicherte, geprüfte Werte auswerten; keine erneute Laufzeitmessung."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


def load_sibling(name):
    """Lädt ein Skript dieses Ordners unter eindeutigem Namen (Reihe 03 hat gleichnamige Skripte)."""
    label = f"reihe03bgb_{name}"
    if label not in sys.modules:
        spec = importlib.util.spec_from_file_location(label, Path(__file__).resolve().with_name(f"{name}.py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[label] = module
        spec.loader.exec_module(module)
    return sys.modules[label]


run = load_sibling("run")
verify_results = load_sibling("verify_results")

AND_VARIANTS = ("and_input_order", "and_shortest_first", "and_galloping")


def comparisons(summary, metadata):
    """Je Anfrage: Median/Quartile/IQR aller zulässigen Verfahren, Verhältnisse und Vergleichszähler."""
    lookup = {(item["algorithm"], item["query_id"]): item for item in summary if item["phase"] == "query"}
    rows = []
    for query in metadata["datasets"][0]["queries"]:
        row = {key: query[key] for key in ("query_id", "query_type", "operator", "terms", "normalized_terms",
                                           "exclude", "normalized_exclude", "effective_term_count",
                                           "posting_lengths_input_order", "exclude_posting_length", "hit_count",
                                           "purpose")}
        row["direct_visited_tokens"] = query["direct_diagnostics"]["visited_tokens"]
        algorithms = ["direct_boolean", *(AND_VARIANTS if query["operator"] == "AND" else ("or_input_order",))]
        for algorithm in algorithms:
            item = lookup[algorithm, query["query_id"]]
            for field in ("median_ms", "q1_ms", "q3_ms", "iqr_ms"):
                row[f"{algorithm}_{field}"] = item[field]
            row["sample_count"] = item["sample_count"]
            if algorithm != "direct_boolean":
                diagnostics = query["diagnostics"][algorithm]
                row[f"{algorithm}_id_comparisons"] = diagnostics.get("total_id_comparisons",
                                                                     diagnostics["id_comparisons"])
        baseline = "and_input_order" if query["operator"] == "AND" else "or_input_order"
        row["direct_over_index_ratio"] = row["direct_boolean_median_ms"] / row[f"{baseline}_median_ms"]
        if query["operator"] == "AND":
            row["input_over_shortest_ratio"] = row["and_input_order_median_ms"] / row["and_shortest_first_median_ms"]
            row["shortest_over_galloping_ratio"] = row["and_shortest_first_median_ms"] / row["and_galloping_median_ms"]
        rows.append(row)
    return rows


def number(value, digits=2):
    """Deutsche Schreibweise: Tausenderpunkt, Dezimalkomma."""
    text = f"{value:,.{digits}f}"
    return text.replace(",", " ").replace(".", ",").replace(" ", ".")


def micro(row, algorithm):
    return (f"{number(row[f'{algorithm}_median_ms'] * 1000)} "
            f"({number(row[f'{algorithm}_iqr_ms'] * 1000)})")


def label(row):
    text = f" {row['operator']} ".join(row["terms"])
    if row["exclude"] is not None:
        text += f" AND NOT {row['exclude']}"
    return text


def report(rows, metadata, source):
    plan = metadata["measurement_plan"]
    lines = ["# Beobachtete Ergebnisse der Reihe 03 auf dem BGB (Realteil)", ""]
    if metadata["run_id"] == "03_bgb_pilot":
        lines += ["**Pilotlauf.** Diese Werte belegen nur, dass die Pipeline funktioniert. Sie sind keine "
                  "Ergebnisse und werden nicht interpretiert.", ""]
    lines += [f"Mediane und Interquartilsabstände (IQR) in Mikrosekunden pro vollständiger Anfrage aus "
              f"{plan['repeats']} Blöcken mit je {plan['query_block_size']} Anfragen. Gemessen werden die "
              "öffentlichen Funktionen inklusive Normalisierung, Postingzugriff, Sortierung und vollständiger "
              "Ergebnisliste. Verhältnisse über 1 beschreiben einen beobachteten Medianvorteil des jeweils "
              "zweiten Verfahrens. Es ist kein Signifikanztest. Vergleiche sind relationale Kennungsvergleiche "
              "aus getrennten Diagnoseläufen außerhalb der Timer, bei AND NOT einschließlich der Differenz.", "",
              "## AND und AND NOT", "",
              "| Anfrage | Listenlängen | Treffer | direkt µs (IQR) | input_order µs (IQR) | shortest_first µs (IQR) "
              "| galloping µs (IQR) | input/shortest | shortest/galloping | Vergleiche input/shortest/galloping |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in (row for row in rows if row["operator"] == "AND"):
        lengths = "/".join(number(value, 0) for value in row["posting_lengths_input_order"])
        if row["exclude_posting_length"] is not None:
            lengths += f", NOT {number(row['exclude_posting_length'], 0)}"
        lines.append(
            f"| {label(row)} | {lengths} | {number(row['hit_count'], 0)} | {micro(row, 'direct_boolean')} | "
            f"{micro(row, 'and_input_order')} | {micro(row, 'and_shortest_first')} | {micro(row, 'and_galloping')} | "
            f"{number(row['input_over_shortest_ratio'], 3)} | {number(row['shortest_over_galloping_ratio'], 3)} | "
            f"{number(row['and_input_order_id_comparisons'], 0)}/{number(row['and_shortest_first_id_comparisons'], 0)}/"
            f"{number(row['and_galloping_id_comparisons'], 0)} |")
    lines += ["", "## OR", "",
              "| Anfrage | Listenlängen | Treffer | direkt µs (IQR) | input_order µs (IQR) | direkt/Index | Vergleiche |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in (row for row in rows if row["operator"] == "OR"):
        lengths = "/".join(number(value, 0) for value in row["posting_lengths_input_order"])
        lines.append(f"| {label(row)} | {lengths} | {number(row['hit_count'], 0)} | {micro(row, 'direct_boolean')} | "
                     f"{micro(row, 'or_input_order')} | {number(row['direct_over_index_ratio'], 3)} | "
                     f"{number(row['or_input_order_id_comparisons'], 0)} |")
    dataset = metadata["datasets"][0]
    lines += ["", f"Korpus: BGB, {number(dataset['document_count'], 0)} Paragraphen als Dokumente, "
              f"N = {number(dataset['token_count'], 0)} Tokens, Wortschatz {number(dataset['vocabulary_size'], 0)}. "
              "Erwartungen stammen aus `daten/real/bgb/anfragevorschlaege.json` und einer eigenen "
              "Regex-Tokenisierung und wurden vor dem ersten Timer mit der direkten Referenz geprüft. "
              "Zweck jeder Anfrage, Einzelzähler und Trefferlisten stehen in `comparisons.json` und `metadata.json`. "
              "Betriebssystem-Caches, Python-Allokation und gewöhnliche Hintergrundlast sind Grenzen.", "",
              f"Quelle: `{source}`. Gemessener Git-Ausgangspunkt: `{metadata['git_commit']}`, "
              f"uncommittierte Änderungen vorhanden: `{metadata['git_dirty']}`, "
              f"PYTHONHASHSEED: `{metadata['environment']['python_hash_seed']}`, "
              f"Hintergrundlast: {metadata['background_load']}. "
              "Exakte Quellenstände mit SHA-256 sind unter `code_source/` archiviert."]
    return "\n".join(lines) + "\n"


def analyse(directory, output, *, check_active_code=True):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    verify_results.verify_directory(directory, check_active_code=check_active_code)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    rows = comparisons(summary, metadata)
    run.write_json(output / "comparisons.json", rows)
    (output / "auswertung.md").write_text(report(rows, metadata, f"{run.messlauf03.display(directory)}/raw.csv"),
                                          encoding="utf-8")
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
