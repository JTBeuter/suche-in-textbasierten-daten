"""Abbildung für Abschnitt 5.3: Reihe 03b, Galloping Search gegen Zwei-Zeiger-Verfahren.

Druckfassung für die Arbeit. Gezeichnet werden dieselben Messwerte wie in
ergebnisse/abbildungen/03b_galloping.*, aber ohne Titel und Fußzeile und mit
Schrift in 9 pt bei der eingebundenen Breite. Die Abbildung ist so groß wie
\\textwidth (16 cm), damit LaTeX sie nicht verkleinert.

Eingaben (nur gelesen): ergebnisse/messungen/03b_galloping/summary.json für
Mediane und Quartile, comparisons.json für Fall und Listenlänge. Stimmen
Mediane oder Quartile beider Dateien nicht überein, bricht das Skript ab.
Ausgabe: 03b_galloping_arbeit.pdf und .png neben diesem Skript. Eingaben,
Ausgaben und Skript werden mit SHA-256 im gemeinsamen Plotmanifest
arbeit_plot_manifest.json festgehalten (Eintrag dieses Skripts).

Aufruf aus der Repositorywurzel:
    .venv/bin/python ergebnisse/abbildungen_arbeit/03b_galloping_arbeit.py
"""

import hashlib
import json
import math
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parents[1]
MESSUNG = WURZEL / "ergebnisse" / "messungen" / "03b_galloping"
ZIEL = HIER / "03b_galloping_arbeit"
MANIFEST = HIER / "arbeit_plot_manifest.json"

# Dieselben Farben wie in den übrigen Abbildungen von Kapitel 5
# (ergebnisse/abbildungen_arbeit/render_eval_figures.py): Blau für das einfache Verfahren, Rot für das
# beschleunigte.
BLAU, ROT = "#1769aa", "#c14c29"
VERFAHREN = {
    # Algorithmus in summary.json: (Feldpräfix in comparisons.json, Name, Farbe)
    "and_shortest_first": ("two_pointer", "Zwei-Zeiger-Verfahren", BLAU),
    "and_galloping": ("galloping", "Galloping Search", ROT),
}
FAELLE = {
    # Fall: (Linienstil, Marker, Beschriftung)
    "verteilt": ("-", "o", "kurze Liste verteilt"),
    "anfang": ("--", "s", "kurze Liste am Anfang"),
}
BREITE_ZOLL = 16 / 2.54  # \textwidth der Arbeit
HOEHE_ZOLL = 2.75
TOLERANZ_MS = 1e-12

plt.rcParams.update({
    "font.size": 9,
    "axes.labelsize": 9,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "pdf.fonttype": 42,
})


def sha256(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


def relativ(pfad: Path) -> str:
    return pfad.resolve().relative_to(WURZEL).as_posix()


def schreibe_manifest(eingaben: list[Path], ausgaben: list[Path]) -> None:
    """Aktualisiert nur den Eintrag dieses Skripts im gemeinsamen Plotmanifest."""
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except FileNotFoundError:
        manifest = {}
    manifest["zweck"] = ("Herkunft der eigens für die Arbeit gezeichneten Abbildungen "
                         "unter ergebnisse/abbildungen_arbeit/, die kein anderes Plotmanifest erfasst")
    skripte = manifest.setdefault("skripte", {})
    skript = Path(__file__).resolve()
    skripte[relativ(skript)] = {
        "skript_sha256": sha256(skript),
        "matplotlib_version": matplotlib.__version__,
        "python_version": sys.version.split()[0],
        "eingaben_sha256": {relativ(p): sha256(p) for p in eingaben},
        "ausgaben_sha256": {relativ(p): sha256(p) for p in ausgaben},
    }
    manifest["skripte"] = dict(sorted(skripte.items()))
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def deutsche_zahl(wert, _position=None) -> str:
    """1.000 statt 1000 oder 10^3, wie in den übrigen Abbildungen."""
    return f"{wert:,.0f}".replace(",", ".")


def lade_werte():
    """Liefert je (Algorithmus, Fall) die nach Listenlänge sortierten Punkte."""
    summary = json.loads((MESSUNG / "summary.json").read_text(encoding="utf-8"))
    vergleiche = json.loads((MESSUNG / "comparisons.json").read_text(encoding="utf-8"))
    abfragen = {(e["algorithm"], e["query_id"]): e for e in summary if e["phase"] == "query"}

    werte = {(a, f): [] for a in VERFAHREN for f in FAELLE}
    fehler = []
    for zeile in vergleiche:
        fall = zeile["case"]
        laenge = zeile["long_document_frequency"]
        if zeile["posting_lengths"] != [10, laenge]:
            fehler.append(f"{zeile['query_id']}: unerwartete Listenlängen {zeile['posting_lengths']}")
        for algorithmus, (praefix, _, _) in VERFAHREN.items():
            eintrag = abfragen.pop((algorithmus, zeile["query_id"]))
            for feld in ("median", "q1", "q3"):
                aus_summary = eintrag[f"{feld}_ms"]
                aus_vergleich = zeile[f"{praefix}_{feld}_ms"]
                if not math.isclose(aus_summary, aus_vergleich, rel_tol=0, abs_tol=TOLERANZ_MS):
                    fehler.append(f"{zeile['query_id']} {algorithmus} {feld}: "
                                  f"summary {aus_summary} gegen comparisons {aus_vergleich}")
            werte[algorithmus, fall].append(
                (laenge, eintrag["median_ms"] * 1000, eintrag["q1_ms"] * 1000, eintrag["q3_ms"] * 1000))
    if abfragen:
        fehler.append(f"Abfragen ohne Vergleichszeile: {sorted(abfragen)}")
    for schluessel, punkte in werte.items():
        if len(punkte) != 10:
            fehler.append(f"{schluessel}: {len(punkte)} statt 10 Stufen")
        punkte.sort()
    if fehler:
        sys.exit("Abbruch, Messdateien widersprechen sich:\n" + "\n".join(fehler))
    return werte


def zeichne(werte) -> None:
    fig, ax = plt.subplots(figsize=(BREITE_ZOLL, HOEHE_ZOLL), layout="constrained")
    for fall, (stil, marker, fall_text) in FAELLE.items():
        for algorithmus, (_, name, farbe) in VERFAHREN.items():
            punkte = werte[algorithmus, fall]
            x = [p[0] for p in punkte]
            ax.fill_between(x, [p[2] for p in punkte], [p[3] for p in punkte],
                            color=farbe, alpha=.18, linewidth=0)
            ax.plot(x, [p[1] for p in punkte], linestyle=stil, marker=marker, markersize=4,
                    linewidth=1.3, color=farbe, markeredgecolor="white", markeredgewidth=.6,
                    label=f"{name}, {fall_text}")

    stufen = sorted({p[0] for punkte in werte.values() for p in punkte})
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_locator(FixedLocator(stufen))
    ax.xaxis.set_major_formatter(FuncFormatter(deutsche_zahl))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_locator(FixedLocator([10, 20, 50, 100, 200, 500, 1000, 2000]))
    ax.yaxis.set_major_formatter(FuncFormatter(deutsche_zahl))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_ylim(10, 2500)
    ax.set_xlabel("Listenlänge der langen Postingliste")
    ax.set_ylabel("Abfragezeit [µs]")
    ax.grid(which="major", alpha=.2)
    ax.set_axisbelow(True)
    for seite in ("top", "right"):
        ax.spines[seite].set_visible(False)
    ax.legend(loc="upper left", frameon=False, handlelength=2.6, borderaxespad=.2)

    fig.savefig(ZIEL.with_suffix(".pdf"), metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(ZIEL.with_suffix(".png"), dpi=220)
    plt.close(fig)


def main() -> None:
    eingaben = {name: sha256(MESSUNG / name) for name in ("summary.json", "comparisons.json")}
    werte = lade_werte()
    zeichne(werte)
    if eingaben != {name: sha256(MESSUNG / name) for name in eingaben}:
        sys.exit("Abbruch, Messdateien wurden während des Zeichnens geändert")
    schreibe_manifest([MESSUNG / name for name in eingaben],
                      [ZIEL.with_suffix(".pdf"), ZIEL.with_suffix(".png")])
    for name, wert in eingaben.items():
        print(f"{name}: sha256 {wert}")
    for (algorithmus, fall), punkte in werte.items():
        print(f"{VERFAHREN[algorithmus][1]}, {fall}: Median {punkte[0][1]:.1f} bis {punkte[-1][1]:.1f} µs")
    print(f"Mediane und Quartile stimmen mit comparisons.json überein. Ausgabe: {ZIEL.name}.pdf/.png")


if __name__ == "__main__":
    main()
