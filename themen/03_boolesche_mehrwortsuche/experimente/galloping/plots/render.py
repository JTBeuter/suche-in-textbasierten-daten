#!/usr/bin/env python3
"""Reihe 03b: Matplotlib-Liniendiagramm aus geprüften Rohwerten; keine Zeitmessung."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, LogLocator, NullLocator  # noqa: E402


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
FIGURE_NAMES = ("03b_galloping.png", "03b_galloping.svg", "03b_galloping.pdf")
# Zwei-Zeiger in derselben Farbe wie „Kürzeste Liste zuerst“ in Abbildung 03; beide
# Farben mit dem Palettenprüfer des dataviz-Leitfadens geprüft (CVD ΔE 24,9).
COLORS = {"and_shortest_first": "#c17935", "and_galloping": "#2a78d6"}
METHOD_LABELS = {"and_shortest_first": "Zwei-Zeiger", "and_galloping": "Galloping Search"}
CASE_STYLES = {"verteilt": ("-", "o", "kurze Liste verteilt"), "anfang": ("--", "s", "kurze Liste am Anfang")}


def load_experiment(name):
    """Skripte der Reihe 03b unter eindeutigem Namen (Reihe 03 hat gleichnamige Skripte)."""
    label = f"reihe03b_{name}"
    if label not in sys.modules:
        spec = importlib.util.spec_from_file_location(label, HERE.parent / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[label] = module
        spec.loader.exec_module(module)
    return sys.modules[label]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def german(value):
    return f"{value:,.0f}".replace(",", ".")


def render(directory, figure_dir, *, check_active_code=True, replace=False):
    directory, figure_dir = Path(directory).resolve(), Path(figure_dir).resolve()
    targets = [figure_dir / name for name in FIGURE_NAMES]
    existing = [path for path in targets if path.exists()]
    if existing and not replace:
        raise SystemExit("Abbildung existiert bereits, nicht überschrieben: "
                         + ", ".join(path.name for path in existing) + " (bewusst ersetzen mit --replace)")
    verify_results = load_experiment("verify_results")
    run = load_experiment("run")
    verify_results.verify_directory(directory, check_active_code=check_active_code)
    inputs = {name: sha(directory / name) for name in ("raw.csv", "summary.json", "metadata.json")}
    source_sha = sha(__file__)
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    plan = metadata["measurement_plan"]
    queries = metadata["datasets"][0]["queries"]
    lookup = {(item["algorithm"], item["query_id"]): item for item in summary if item["phase"] == "query"}

    figure, axis = plt.subplots(figsize=(8.2, 4.8), layout="constrained")
    plotted = []
    for case in run.CASES:
        style, marker, case_label = CASE_STYLES[case]
        selected = sorted((query for query in queries if query["case"] == case),
                          key=lambda query: query["long_document_frequency"])
        x = [query["long_document_frequency"] for query in selected]
        for algorithm in ("and_shortest_first", "and_galloping"):
            values = [lookup[algorithm, query["query_id"]] for query in selected]
            medians = [item["median_ms"] * 1000 for item in values]
            q1 = [item["q1_ms"] * 1000 for item in values]
            q3 = [item["q3_ms"] * 1000 for item in values]
            color = COLORS[algorithm]
            axis.fill_between(x, q1, q3, color=color, alpha=.16, linewidth=0)
            axis.plot(x, medians, linestyle=style, marker=marker, markersize=5, linewidth=1.6, color=color,
                      markeredgecolor="white", markeredgewidth=.8,
                      label=f"{METHOD_LABELS[algorithm]}, {case_label}")
            plotted += [{"algorithm": algorithm, "case": case, "query_id": query["query_id"],
                         "long_document_frequency": query["long_document_frequency"],
                         "median_us": median, "q1_us": low, "q3_us": high}
                        for query, median, low, high in zip(selected, medians, q1, q3)]
    stages = sorted({query["long_document_frequency"] for query in queries})
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.xaxis.set_major_locator(FixedLocator(stages))
    axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _: german(value)))
    axis.xaxis.set_minor_locator(NullLocator())
    axis.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
    axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: german(value)))
    axis.yaxis.set_minor_locator(NullLocator())
    axis.set_xlabel("Dokumentfrequenz der langen Liste (logarithmisch), kurze Liste immer 10 Dokumente")
    axis.set_ylabel("Median pro vollständiger Anfrage in µs (logarithmisch)")
    axis.set_title("AND mit zwei Wörtern: Galloping Search und Zwei-Zeiger-Verfahren")
    axis.grid(which="major", color="#d9d9d6", linewidth=.6, linestyle="-")
    axis.set_axisbelow(True)
    for spine in ("top", "right"):
        axis.spines[spine].set_visible(False)
    axis.legend(loc="upper left", frameon=False)
    run_name = "Pilotlauf" if metadata["run_id"] == "03b_pilot" else "Finalmessung"
    source = directory.relative_to(ROOT).as_posix() if directory.is_relative_to(ROOT) else directory.name
    figure.text(.01, -.06, f"{run_name}. Mediane aus {plan['repeats']} Blöcken mit je {plan['query_block_size']} "
                "Anfragen. Bänder zeigen Q1 bis Q3 und sind keine Konfidenzintervalle.\n"
                f"Quelle: {source}/raw.csv", fontsize=8, color="#52514e")
    figure_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for path in targets:
        options = {"dpi": 200} if path.suffix == ".png" else {}
        if path.suffix == ".pdf":
            options["metadata"] = {"CreationDate": None, "ModDate": None}
        elif path.suffix == ".svg":
            options["metadata"] = {"Date": None}
        figure.savefig(path, bbox_inches="tight", **options)
        outputs.append({"path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
                        "sha256": sha(path)})
    plt.close(figure)
    assert inputs == {name: sha(directory / name) for name in inputs}, "Messartefakte während Plot geändert"
    assert sha(__file__) == source_sha, "Plotquelle während Rendering geändert"
    archived = directory / "plot_source/render.py"
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_bytes(Path(__file__).read_bytes())
    manifest = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "renderer": "Matplotlib",
                "matplotlib_version": matplotlib.__version__, "python": sys.version,
                "source_path": Path(__file__).resolve().relative_to(ROOT).as_posix(), "source_sha256": source_sha,
                "source_archive": "plot_source/render.py", "input_sha256": inputs, "outputs": outputs,
                "values": plotted, "axes": {"x": "long-list document frequency, logarithmic",
                                            "y": "median query time in microseconds, logarithmic"},
                "bands": "inclusive Q1 to Q3 as translucent bands, not confidence intervals",
                "query_count": len(queries), "measurement_unchanged": True}
    (directory / "plot_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
    return outputs


def main(argv=None):
    run = load_experiment("run")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-only", action="store_true")
    parser.add_argument("--eingabe", metavar="NAME", default=run.STANDARD_FINAL,
                        help=f"Messordner unter ergebnisse/messungen (Standard {run.STANDARD_FINAL})")
    parser.add_argument("--figure-dir", type=Path, default=ROOT / "ergebnisse/abbildungen")
    parser.add_argument("--replace", action="store_true", help="vorhandene 03b-Abbildungen bewusst ersetzen")
    args = parser.parse_args(argv)
    render(run.messlauf03.directory_name(args.eingabe), args.figure_dir,
           check_active_code=not args.archive_only, replace=args.replace)
    print("Matplotlib-PNG/SVG/PDF mit Q1-Q3-Bändern und eigenem Quell-/Inputmanifest gespeichert.")


if __name__ == "__main__":
    main()
