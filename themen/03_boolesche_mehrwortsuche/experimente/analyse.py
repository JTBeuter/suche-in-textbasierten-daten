#!/usr/bin/env python3
"""Nur gespeicherte Werte auswerten; keine erneute Laufzeitmessung."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from run import ROOT, write_json
from verify_results import verify_directory


def comparisons(summary, metadata):
    lookup = {(item["dataset_id"], item["algorithm"], item["query_id"]): item
              for item in summary if item["phase"] == "query"}
    result = []
    for dataset in metadata["datasets"]:
        for query in dataset["queries"]:
            direct = lookup[dataset["dataset_id"], "direct_boolean", query["query_id"]]
            baseline_name = "and_input_order" if query["operator"] == "AND" else "or_input_order"
            baseline = lookup[dataset["dataset_id"], baseline_name, query["query_id"]]
            row = {"dataset_id": dataset["dataset_id"], "query_id": query["query_id"],
                   "operator": query["operator"], "group": query["group"], "order": query["order"],
                   "original_term_count": query["original_term_count"], "effective_term_count": query["effective_term_count"],
                   "posting_lengths": query["posting_lengths_input_order"], "hit_count": query["hit_count"],
                   "direct_median_ms": direct["median_ms"], "direct_iqr_ms": direct["iqr_ms"],
                   "input_order_median_ms": baseline["median_ms"], "input_order_iqr_ms": baseline["iqr_ms"],
                   "direct_over_index_ratio": direct["median_ms"] / baseline["median_ms"]}
            if query["operator"] == "AND":
                optimized = lookup[dataset["dataset_id"], "and_shortest_first", query["query_id"]]
                row.update(shortest_first_median_ms=optimized["median_ms"], shortest_first_iqr_ms=optimized["iqr_ms"],
                           input_over_shortest_ratio=baseline["median_ms"] / optimized["median_ms"],
                           input_comparisons=query["diagnostics"]["input_order"]["id_comparisons"],
                           shortest_comparisons=query["diagnostics"]["shortest_first"]["id_comparisons"])
            result.append(row)
    return result


def plot_svg(path, rows):
    selected = [row for row in rows if row["dataset_id"] == "boolean_controlled" and row["operator"] == "AND"
                and row["effective_term_count"] == 5 and row["order"] == "forward"]
    width, height = 940, 430
    left, top, bottom = 78, 58, 330
    plot_width = width - left - 25
    maximum = max(max(row["input_order_median_ms"], row["shortest_first_median_ms"]) * 1000 for row in selected) * 1.1
    content = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
               '<rect width="100%" height="100%" fill="white"/>',
               '<g font-family="sans-serif" font-size="13" fill="#222">',
               '<text x="78" y="25" font-size="18">AND: fünf Begriffe in ursprünglicher Reihenfolge</text>',
               '<text x="18" y="52">µs / Anfrage</text>']
    for i in range(5):
        value = maximum * i / 4
        y = bottom - (bottom - top) * i / 4
        content += [f'<line x1="{left}" y1="{y}" x2="{width - 25}" y2="{y}" stroke="#ddd"/>',
                    f'<text x="{left - 10}" y="{y + 4}" text-anchor="end">{value:.0f}</text>']
    labels = {"rare": "selten", "frequent": "häufig", "mixed": "gemischt", "unknown": "unbekannt",
              "disjoint": "disjunkt", "high_overlap": "hohe Überl.", "low_overlap": "geringe Überl."}
    spacing = plot_width / len(selected)
    for i, row in enumerate(selected):
        center = left + spacing * (i + .5)
        for offset, field, color in ((-27, "input_order_median_ms", "#476b9e"), (4, "shortest_first_median_ms", "#c17935")):
            bar_height = row[field] * 1000 / maximum * (bottom - top)
            content.append(f'<rect x="{center + offset}" y="{bottom - bar_height}" width="24" height="{bar_height}" fill="{color}"/>')
        content.append(f'<text x="{center}" y="{bottom + 23}" text-anchor="middle">{html.escape(labels[row["group"]])}</text>')
    content += ['<rect x="80" y="378" width="14" height="14" fill="#476b9e"/><text x="103" y="390">input_order</text>',
                '<rect x="230" y="378" width="14" height="14" fill="#c17935"/><text x="253" y="390">shortest_first</text>',
                '<text x="80" y="417" font-size="11">Median aus 20 Blöcken à 5 vollständigen Anfragen; Planungsaufwand enthalten; Quelle: 03_boolesche_mehrwortsuche/raw.csv.</text>',
                '</g></svg>']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(content) + "\n", encoding="utf-8")


def report(rows, metadata):
    selected = [row for row in rows if row["dataset_id"] == "boolean_controlled" and row["operator"] == "AND"
                and row["effective_term_count"] == 5 and row["order"] == "forward"]
    lines = ["# Beobachtete Ergebnisse der Untersuchung 03", "",
             "Die Tabelle zeigt Mediane und Interquartilsabstände (IQR) in Mikrosekunden pro vollständiger Anfrage. "
             "Das Verhältnis input/shortest > 1 beschreibt einen beobachteten Medianvorteil der Sortierung. "
             "Es ist kein Signifikanztest. Verglichen werden derselbe Korpus und dieselben Begriffe.", "",
             "| Anfragegruppe, k=5 vorwärts | Postinglängen | Treffer | direkte Suche µs (IQR) | input_order µs (IQR) | shortest_first µs (IQR) | input/shortest | Diagnose Vergleiche input/shortest |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in selected:
        lines.append(f"| {row['group']} | {row['posting_lengths']} | {row['hit_count']} | "
            f"{row['direct_median_ms'] * 1000:.2f} ({row['direct_iqr_ms'] * 1000:.2f}) | "
            f"{row['input_order_median_ms'] * 1000:.2f} ({row['input_order_iqr_ms'] * 1000:.2f}) | "
            f"{row['shortest_first_median_ms'] * 1000:.2f} ({row['shortest_first_iqr_ms'] * 1000:.2f}) | "
            f"{row['input_over_shortest_ratio']:.3f} | {row['input_comparisons']}/{row['shortest_comparisons']} |")
    lines += ["", "Alle k=2/3/5, umgekehrten Anfragen, OR-Vergleiche, Duplikatfälle und realen Anfragen stehen in "
              "`comparisons.json`; Streuungen und Einzelwerte in `summary.json` und `raw.csv`. "
              "Die vollständigen IDs, Längen, Zwischenresultate und Diagnosezähler stehen in `metadata.json`.", "",
              "Die Häufigkeitsgruppen ändern bei gleichem N=100000 die Postingverteilung. Die Reihenfolge wird "
              "durch Vorwärts-/Rückwärtspermutation exakt derselben Begriffe isoliert. k wird durch vorab definierte "
              "Präfixe auf demselben Korpus variiert; dabei kann auch die Schnittmenge schrumpfen. Daher folgt daraus "
              "kein von Häufigkeiten und Überschneidung unabhängiger universeller k-Effekt.", "",
              "Der unveränderte Kafka-Auszug umfasst ein Dokument und 1271 Tokens. Er bestätigt Aufbereitung "
              "und Semantik an echter Prosa, trägt aber keine belastbare Skalierungs- oder Verteilungsanalyse. "
              "Die synthetische Textlänge ist konstant; Positionen und Füllwörter bleiben bei sämtlichen "
              "Anfragen gleich. Betriebssystem-Caches, Python-Allokation und gewöhnliche Hintergrundlast "
              "sind Grenzen. Laufzeiten enthalten die vollständige Materialisierung. Speicher und "
              "Amortisation des Gesamtprojekts werden hier nicht untersucht.", "",
              f"Gemessener Git-Ausgangspunkt: `{metadata['git_commit']}`; "
              f"uncommittierte Änderungen vorhanden: `{metadata['git_dirty']}`. "
              "Exakte Quellenstände mit SHA-256 sind unter `code_source/` archiviert."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-only", action="store_true")
    args = parser.parse_args()
    directory = ROOT / "ergebnisse/messungen/03_boolesche_mehrwortsuche"
    verify_directory(directory, check_active_code=not args.archive_only)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    rows = comparisons(summary, metadata)
    write_json(directory / "comparisons.json", rows)
    (directory / "auswertung.md").write_text(report(rows, metadata), encoding="utf-8")
    plot_svg(ROOT / "ergebnisse/abbildungen/03_and_reihenfolge.svg", rows)
    print("Vergleichstabelle und SVG aus geprüften Rohwerten erzeugt.")


if __name__ == "__main__":
    main()
