#!/usr/bin/env python3
"""Standard-Matplotlib-Abbildung aus geprüften Rohwerten; keine Zeitmessung."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[4]
DIRECTORY = ROOT / "ergebnisse/messungen/03_boolesche_mehrwortsuche"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-only", action="store_true")
    args = parser.parse_args()
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / "verify_results.py")]
    if args.archive_only:
        command.append("--archive-only")
    subprocess.run(command, cwd=ROOT, check=True)
    inputs = {name: sha(DIRECTORY / name) for name in ("raw.csv", "summary.json", "metadata.json")}
    source_sha = sha(__file__)
    metadata = json.loads((DIRECTORY / "metadata.json").read_text(encoding="utf-8"))
    summary = json.loads((DIRECTORY / "summary.json").read_text(encoding="utf-8"))
    dataset = next(item for item in metadata["datasets"] if item["dataset_id"] == "boolean_controlled")
    queries = [item for item in dataset["queries"] if item["operator"] == "AND" and item["effective_term_count"] == 5
               and item["order"] == "forward"]
    labels = {"rare": "selten", "frequent": "häufig", "mixed": "gemischt", "unknown": "unbekannt",
              "disjoint": "disjunkt", "high_overlap": "hohe\nÜberschneidung", "low_overlap": "geringe\nÜberschneidung"}
    lookup = {(item["algorithm"], item["query_id"]): item for item in summary if item["dataset_id"] == dataset["dataset_id"] and item["phase"] == "query"}
    figure, axis = plt.subplots(figsize=(10.5, 4.8), layout="constrained")
    width = .34
    plotted = []
    for algorithm, shift, color, label in (("and_input_order", -width / 2, "#476b9e", "Eingabereihenfolge"),
                                           ("and_shortest_first", width / 2, "#c17935", "Kürzeste Liste zuerst")):
        values = [lookup[algorithm, query["query_id"]] for query in queries]
        medians = [item["median_ms"] * 1000 for item in values]
        errors = [[(item["median_ms"] - item["q1_ms"]) * 1000 for item in values],
                  [(item["q3_ms"] - item["median_ms"]) * 1000 for item in values]]
        axis.bar([i + shift for i in range(len(queries))], medians, width=width, color=color, label=label,
                 yerr=errors, capsize=3, error_kw={"elinewidth": 1, "capthick": 1})
        plotted += [{"algorithm": algorithm, "query_id": query["query_id"], "median_us": item["median_ms"] * 1000,
                     "q1_us": item["q1_ms"] * 1000, "q3_us": item["q3_ms"] * 1000}
                    for query, item in zip(queries, values)]
    axis.set_xticks(range(len(queries)), [labels[query["group"]] for query in queries])
    axis.set_ylabel("Zeit pro vollständiger Anfrage (µs)")
    axis.set_xlabel("Kontrollierte Verteilung; k=5, ursprüngliche Begriffreihenfolge")
    axis.set_title("AND-Suche: Reihenfolge und vollständiger Planungsaufwand")
    axis.set_ylim(bottom=0)
    axis.grid(axis="y", alpha=.25)
    axis.set_axisbelow(True)
    axis.legend(loc="upper right")
    figure.text(.01, -.035, "Mediane; Fehlerbalken Q1 bis Q3. 20 Blöcke à 5 Anfragen.\n"
                "Quelle: ergebnisse/messungen/03_boolesche_mehrwortsuche/raw.csv; IQR ist kein Konfidenzintervall.", fontsize=8)
    outputs = []
    for name in ("03_and_reihenfolge.png", "03_and_reihenfolge_matplotlib.svg"):
        path = ROOT / "ergebnisse/abbildungen" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(path, dpi=180, bbox_inches="tight")
        outputs.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)})
    plt.close(figure)
    assert inputs == {name: sha(DIRECTORY / name) for name in inputs}, "Messartefakte während Plot geändert"
    assert sha(__file__) == source_sha, "Plotquelle während Rendering geändert"
    archived = DIRECTORY / "plot_source/render.py"
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_bytes(Path(__file__).read_bytes())
    manifest = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "renderer": "Matplotlib",
                "matplotlib_version": matplotlib.__version__, "python": sys.version,
                "source_path": Path(__file__).resolve().relative_to(ROOT).as_posix(), "source_sha256": source_sha,
                "source_archive": "plot_source/render.py", "input_sha256": inputs, "outputs": outputs,
                "values": plotted, "error_bars": "inclusive Q1 to Q3, not confidence intervals",
                "query_count": len(queries), "measurement_unchanged": True}
    (DIRECTORY / "plot_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Matplotlib-PNG/SVG mit Quartilbalken und eigenem Quell-/Inputmanifest gespeichert.")


if __name__ == "__main__":
    main()
