"""Abbildungen ausschließlich aus geprüften Rohwert-Zusammenfassungen erzeugen."""

from pathlib import Path
import hashlib
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[4]
RESULTS = ROOT / "ergebnisse/messungen/04_positionsindex_phrasensuche"
OUTPUT = ROOT / "ergebnisse/abbildungen"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    summary = json.loads((RESULTS / "summary.json").read_text())
    memory = json.loads((RESULTS / "memory.json").read_text())
    lookup = {(s["dataset_id"], s["algorithm"], s["phase"], s["query_id"]): s for s in summary}
    colors = {"direct_phrase": "#32689c", "positional_phrase": "#b45c32"}
    labels = {"direct_phrase": "Direkter Scan", "positional_phrase": "Positionsindex"}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    generated = []

    def save(figure, name):
        figure.tight_layout()
        for extension in ("png", "svg"):
            target = OUTPUT / f"{name}.{extension}"
            figure.savefig(target, dpi=160)
            generated.append({"path": target.relative_to(ROOT).as_posix(), "sha256": sha(target)})
        plt.close(figure)

    lengths = [1, 2, 3, 5]
    figure, axes = plt.subplots(1, 3, figsize=(11.6, 3.8), sharey=True)
    for axis, group, title in zip(axes, ("frequent", "rare", "repeated"),
                                 ("Häufig: 2.000 Starts", "Selten: 2 Starts", "Wiederholt: 1.200–400 Starts")):
        for algorithm in colors:
            rows = [lookup[("phrase_h200", algorithm, "query", f"{group}_k{m}")] for m in lengths]
            medians = [s["median_ms"] * 1_000 for s in rows]
            axis.errorbar(lengths, medians,
                          yerr=[[v - s["q1_ms"] * 1_000 for v, s in zip(medians, rows)],
                                [s["q3_ms"] * 1_000 - v for v, s in zip(medians, rows)]],
                          marker="o", capsize=3, color=colors[algorithm], label=labels[algorithm])
        axis.set(title=title, xlabel="Phrasenlänge m", xticks=lengths, yscale="log")
        axis.grid(alpha=.25, which="both")
    axes[0].set_ylabel("Zeit je vollständiger Anfrage [µs, logarithmisch]")
    axes[-1].legend(fontsize=8)
    figure.suptitle("D = 200, N = 100.000; Median und Q1–Q3 aus 20 Blöcken mit je 5 Anfragen")
    save(figure, "04_phrasenlaenge")

    figure, axes = plt.subplots(1, 2, figsize=(9.5, 3.8))
    hvalues = [0, 20, 200]
    for algorithm in colors:
        values = [lookup[(f"phrase_h{h:03d}", algorithm, "query", "result_size_k5")] for h in hvalues]
        axes[0].plot(hvalues, [v["median_ms"] * 1_000 for v in values], marker="o",
                     color=colors[algorithm], label=labels[algorithm])
    axes[0].set(xlabel="Trefferdokumente / Starts H", ylabel="Medianzeit je Anfrage [µs]",
                title="m = 5, gleiche Einzelworthäufigkeiten", xticks=hvalues)
    axes[0].grid(alpha=.25)
    axes[0].legend(fontsize=8)
    selected = [next(item for item in memory["summary"] if item["dataset_id"] == "phrase_h200"
                     and item["algorithm"] == algorithm) for algorithm in ("inverted_index", "positional_index")]
    axes[1].bar([-.17, .83], [s["median_retained_traced_bytes"] / 1_048_576 for s in selected],
                width=.34, color="#32689c", label="Gehalten")
    axes[1].bar([.17, 1.17], [s["median_peak_traced_bytes"] / 1_048_576 for s in selected],
                width=.34, color="#b45c32", label="Zusätzlicher Peak")
    axes[1].set(xticks=[0, 1], xticklabels=["Dokumentindex", "Positionsindex"],
                ylabel="Zusätzliche Python-Allokationen [MiB]", title="Getrennte Tracemalloc-Prozesse, 3 Builds")
    axes[1].legend(fontsize=8)
    axes[1].grid(axis="y", alpha=.25)
    save(figure, "04_ergebnisgroesse_speicher")

    manifest = {"source": {name: sha(RESULTS / name) for name in
                           ("raw.csv", "summary.json", "memory.csv", "memory.json")},
                "renderer_path": Path(__file__).relative_to(ROOT).as_posix(),
                "renderer_sha256": sha(Path(__file__)), "matplotlib_version": matplotlib.__version__,
                "figures": generated,
                "limits": "H variation also changes token order and merge progress; IQR is not a confidence interval; memory is not RSS."}
    (RESULTS / "plot_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(generated)} Abbildungsdateien mit Quellen-/Renderer-SHA geschrieben.")


if __name__ == "__main__":
    main()
