"""Abbildung für Abschnitt 4.2: Wörterbuch mit Dokumentfrequenz und Postinglisten.

Die Inhalte werden nicht von Hand eingetragen, sondern mit dem Projektcode aus
dem Beispielkorpus daten/beispiele/d0_d5 berechnet (load_corpus,
prepare_corpus, build_inverted_index). Ausgabe: 42_woerterbuch_postings.pdf
und .png neben diesem Skript. Korpusdateien, verwendete Projektmodule,
Ausgaben und Skript werden mit SHA-256 im gemeinsamen Plotmanifest
arbeit_plot_manifest.json festgehalten (Eintrag dieses Skripts).

Aufruf aus der Repositorywurzel:
    .venv/bin/python ergebnisse/abbildungen_arbeit/42_woerterbuch_postings.py
"""

import hashlib
import inspect
import json
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402

from gemeinsam import load_corpus, prepare_corpus, tokenize  # noqa: E402
from invertierter_index import build_inverted_index  # noqa: E402

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parents[1]
KORPUS = WURZEL / "daten" / "beispiele" / "d0_d5"
ZIEL = HIER / "42_woerterbuch_postings"
MANIFEST = HIER / "arbeit_plot_manifest.json"

BLAU = "#1f6aa5"
BLAU_HELL = "#dce8f4"
GRAU = "#555555"

plt.rcParams.update({
    "font.size": 9,
    "pdf.fonttype": 42,
    "svg.fonttype": "none",
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


def kurz(kennung: str) -> str:
    """D0.txt -> D0, wie im Text der Arbeit."""
    return kennung.removesuffix(".txt")


def main() -> None:
    index = build_inverted_index(prepare_corpus(load_corpus(KORPUS)))
    # Das dict hat keine zugesagte Reihenfolge, für die Darstellung alphabetisch.
    eintraege = [(term, index[term]) for term in sorted(index)]
    postings_gesamt = sum(len(liste) for _, liste in eintraege)
    assert len(eintraege) == 9 and postings_gesamt == 17, (len(eintraege), postings_gesamt)

    zeile = 0.22          # Zeilenhöhe in Zoll
    kopf = 0.28
    breite = 4.1
    hoehe = kopf + zeile * len(eintraege) + 0.06
    fig = plt.figure(figsize=(breite, hoehe))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, breite)
    ax.set_ylim(0, hoehe)
    ax.axis("off")

    x_term, w_term = 0.04, 1.15
    x_df, w_df = x_term + w_term, 0.36
    x_liste, w_zelle = x_df + w_df + 0.45, 0.45
    h = zeile * 0.78

    y_kopf = hoehe - kopf / 2
    ax.text(x_term + w_term / 2, y_kopf, "Term", ha="center", va="center", weight="bold")
    ax.text(x_df + w_df / 2, y_kopf, "df", ha="center", va="center", weight="bold",
            style="italic")
    ax.text(x_liste, y_kopf, "Postingliste",
            ha="left", va="center", weight="bold")

    for nummer, (term, liste) in enumerate(eintraege):
        y = hoehe - kopf - zeile * (nummer + 0.5)
        unten = y - h / 2
        ax.add_patch(Rectangle((x_term, unten), w_term, h, facecolor=BLAU_HELL,
                               edgecolor=BLAU, linewidth=0.8))
        ax.add_patch(Rectangle((x_df, unten), w_df, h, facecolor=BLAU_HELL,
                               edgecolor=BLAU, linewidth=0.8))
        ax.text(x_term + 0.08, y, term, ha="left", va="center", family="DejaVu Sans Mono")
        ax.text(x_df + w_df / 2, y, str(len(liste)), ha="center", va="center")
        ax.add_patch(FancyArrowPatch((x_df + w_df + 0.05, y), (x_liste - 0.04, y),
                                     arrowstyle="-|>", mutation_scale=8,
                                     color=GRAU, linewidth=0.8))
        for spalte, kennung in enumerate(liste):
            x = x_liste + spalte * w_zelle
            ax.add_patch(Rectangle((x, unten), w_zelle, h, facecolor="white",
                                   edgecolor=GRAU, linewidth=0.8))
            ax.text(x + w_zelle / 2, y, kurz(kennung), ha="center", va="center")

    for endung in ("pdf", "png"):
        fig.savefig(ZIEL.with_suffix(f".{endung}"), dpi=300,
                    metadata={"CreationDate": None} if endung == "pdf" else None)
    plt.close(fig)

    korpusdateien = sorted(KORPUS.rglob("*.txt"))
    # Korpus, Tokenisierung und Index bestimmen den Inhalt der Abbildung.
    module = sorted({Path(inspect.getsourcefile(f)).resolve()
                     for f in (load_corpus, prepare_corpus, tokenize, build_inverted_index)})
    schreibe_manifest(korpusdateien + module,
                      [ZIEL.with_suffix(".pdf"), ZIEL.with_suffix(".png")])


if __name__ == "__main__":
    main()
