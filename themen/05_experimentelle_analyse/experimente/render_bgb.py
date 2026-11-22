#!/usr/bin/env python3
"""Publikationsdiagramme für BGB-Läufe der Reihe 05 aus geprüften Modellen.

Aufruf aus der Repositorywurzel nach ``experimentelle_analyse analyse``:

    .venv/bin/python themen/05_experimentelle_analyse/experimente/render_bgb.py \
        --input ergebnisse/messungen/05_bgb --analysis ergebnisse/abbildungen/05_bgb

Mediane als Linien, Q1 bis Q3 als halbtransparente Bänder statt Fehlerbalken,
deutsche Beschriftung. Die Bilder und ``render_manifest.json`` entstehen neu im
Auswertungsordner. Vorhandene Dateien werden nicht überschrieben, Rohwerte und
Auswertungsdateien werden nur gelesen. Es wird nichts kopiert.
"""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import ticker

from experimentelle_analyse.provenance import sha_file, write_json
from experimentelle_analyse.verify import verify_run

PROFILE = {'word_missing': 'Fehlendes Wort', 'word_frequent': 'Häufiges Wort',
           'word_rare': 'Seltenes Wort', 'and_present3': 'AND mit drei Wörtern',
           'or_present3': 'OR mit drei Wörtern', 'phrase_present3': 'Phrase aus drei Wörtern'}
BLAU, ROT, GRAU = '#1769aa', '#c14c29', '#555555'
NAMEN = ('05_bgb_gesamtkosten_baender', '05_bgb_amortisation_baender')
FORMATE = ('png', 'svg', 'pdf')
# Kleine Schrift für 6,3 Zoll Satzbreite, damit 100 und 1.000 nicht überlappen.
STIL = {'font.size': 7.5, 'axes.labelsize': 7.5, 'axes.titlesize': 7.5,
        'xtick.labelsize': 6.5, 'ytick.labelsize': 6.5, 'legend.fontsize': 7}


def deutsche_zahl(wert, _position=None):
    """Achsenbeschriftung ohne Exponenten: 1.000 statt 10^3, echtes Minuszeichen."""
    if wert == 0:
        return '0'
    if abs(wert) >= 1 and float(wert).is_integer():
        text = f'{abs(int(wert)):,}'.replace(',', '.')
    else:
        text = f'{abs(wert):g}'.replace('.', ',')
    return ('−' if wert < 0 else '') + text


def anfrage_achse(ax):
    """Symmetrisch logarithmische x-Achse, damit q = 0 sichtbar bleibt."""
    ax.set(xscale='symlog', xlim=(0, None), xlabel='Anzahl der Anfragen q')
    ax.xaxis.set_major_locator(ticker.FixedLocator([0, 1, 10, 100, 1000]))
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(deutsche_zahl))
    ax.xaxis.set_minor_locator(ticker.NullLocator())


def anfrage_text(query):
    """Anfrage wie in der Arbeit: Operator zwischen den Wörtern, Phrase in Anführungszeichen."""
    if query['kind'] in ('and', 'or'):
        return f' {query["kind"].upper()} '.join(query['text'].split())
    return f'„{query["text"]}“'


def titel(profile, query):
    return f'{PROFILE[profile]}\n{anfrage_text(query)}'


def lade_geprueft(run, analysis, archive_only):
    """Lauf prüfen und Auswertungsdateien an genau diesen Rohwertstand binden."""
    verify_run(run, archive_only=archive_only)
    lineage = json.loads((analysis / 'plot_manifest.json').read_text(encoding='utf-8'))
    for name, digest in lineage['input_sha256'].items():
        if sha_file(run / name) != digest:
            raise ValueError('Auswertung stammt aus einem anderen Rohwertstand')
    for name in ('models.json', 'amortisation.json'):
        if name not in lineage['output_sha256'] or sha_file(analysis / name) != lineage['output_sha256'][name]:
            raise ValueError(f'{name} fehlt oder ist beschädigt')
    meta = json.loads((run / 'metadata.json').read_text(encoding='utf-8'))
    models = json.loads((analysis / 'models.json').read_text(encoding='utf-8'))
    table = json.loads((analysis / 'amortisation.json').read_text(encoding='utf-8'))
    return meta, models, table


def render_gesamtkosten(models, table, queries, repeats):
    fig, axes = plt.subplots(2, 3, figsize=(6.3, 4.5), layout='constrained')
    for ax, profile in zip(axes.flat, PROFILE):
        model = models[profile]
        observations = model['observations']
        x = [o['query_count'] for o in observations]
        for key, label, color in (('direct_ns', 'Direkte Suche', BLAU), ('index_ns', 'Indexsuche', ROT)):
            ax.plot(x, [o[key]['median'] / 1e6 for o in observations], color=color,
                    linewidth=1.2, marker='o', markersize=2.2, label=f'{label} (Median)')
            ax.fill_between(x, [o[key]['q1'] / 1e6 for o in observations],
                            [o[key]['q3'] / 1e6 for o in observations],
                            color=color, alpha=.18, linewidth=0, label=f'{label} (Q1–Q3)')
        markiere_amortisation(ax, table[profile], oben=True)
        ax.set(yscale='log', title=titel(profile, queries[model['query_id']]))
        # Auch bei schmalem Wertebereich (Aufbereitung dominiert) beschriftete Marken.
        ax.yaxis.set_major_locator(ticker.LogLocator(base=10, subs=(1, 2, 3, 5)))
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(deutsche_zahl))
        ax.yaxis.set_minor_locator(ticker.NullLocator())
        anfrage_achse(ax)
        ax.grid(alpha=.2, which='major')
    for ax in axes[:, 0]:
        ax.set_ylabel('Gesamtzeit [ms]')
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside lower center', ncol=2, fontsize=7, frameon=False,
               title=f'Bänder: Q1–Q3 aus {repeats} Wiederholungen. Gestrichelt: aufgerundetes q* des Modells.',
               title_fontsize=7)
    return fig


def render_amortisation(models, table, queries, repeats):
    fig, axes = plt.subplots(2, 3, figsize=(6.3, 4.6), layout='constrained')
    for ax, profile in zip(axes.flat, PROFILE):
        model = models[profile]
        observations = model['observations']
        x = [o['query_count'] for o in observations]
        ax.axhline(0, color='black', linewidth=.8)
        ax.fill_between(x, [o['paired_saving_ns']['q1'] / 1e6 for o in observations],
                        [o['paired_saving_ns']['q3'] / 1e6 for o in observations],
                        color=BLAU, alpha=.18, linewidth=0, label=f'Q1–Q3 der {repeats} Paare')
        ax.plot(x, [o['paired_saving_ns']['median'] / 1e6 for o in observations], color=BLAU,
                linewidth=1.2, marker='o', markersize=2.2, label='Median der Differenz')
        markiere_amortisation(ax, table[profile], oben=False)
        ax.set_yscale('symlog', linthresh=1)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(deutsche_zahl))
        ax.yaxis.set_minor_locator(ticker.NullLocator())
        ax.set(title=titel(profile, queries[model['query_id']]))
        anfrage_achse(ax)
        ax.grid(alpha=.2)
    for ax in axes[:, 0]:
        ax.set_ylabel(r'$T_{\mathrm{direkt}}-T_{\mathrm{index}}$ [ms]')
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside lower center', ncol=3, fontsize=7, frameon=False,
               title='Über der Nulllinie spart der Index Zeit, darunter ist die direkte Suche schneller.',
               title_fontsize=7)
    return fig


def markiere_amortisation(ax, row, oben):
    """Senkrechte Linie bei ⌈q*⌉ oder Hinweis „nie“, wie in der Tabelle aus Abschnitt 3.6.

    Beschriftung rechts der Linie: oben bei den Gesamtkosten (dort sind die
    Kurven nahe q* niedrig), unten bei der Differenz (rechts von q* positiv).
    """
    if row['amortisation'] == 'nie':
        ax.text(.03, .97, 'Modell: nie', transform=ax.transAxes, color=GRAU, fontsize=6.5, va='top')
        return
    q = row['q_stern_aufgerundet']
    ax.axvline(q, color=GRAU, linestyle='--', linewidth=.9)
    ax.text(q * 1.12, .97 if oben else .03, f'⌈q*⌉ = {deutsche_zahl(q)}', transform=ax.get_xaxis_transform(),
            color=GRAU, fontsize=6.5, va='top' if oben else 'bottom', ha='left',
            bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': .8, 'pad': 1})


def render(run, analysis, *, archive_only=False):
    run, analysis = Path(run), Path(analysis)
    targets = [analysis / f'{name}.{ext}' for name in NAMEN for ext in FORMATE] + [analysis / 'render_manifest.json']
    existing = [path.name for path in targets if path.exists()]
    if existing:
        raise ValueError(f'{existing[0]} existiert bereits; vorhandene Diagramme werden nicht überschrieben')
    meta, models, table = lade_geprueft(run, analysis, archive_only)
    if len(meta['datasets']) != 1:
        raise ValueError('render_bgb erwartet genau einen Realdatensatz je Lauf')
    dataset = meta['datasets'][0]
    queries = {query['id']: query for query in dataset['queries']}
    models = {model['profile_id']: model for model in models if model['dataset_id'] == dataset['id']}
    table = {row['profile_id']: row for row in table if row['dataset_id'] == dataset['id']}
    if set(models) != set(PROFILE) or set(table) != set(PROFILE):
        raise ValueError('Es werden genau die sechs Profile erwartet')
    repeats = meta['config'].get('total_repeats', 5)
    outputs = {}
    with matplotlib.rc_context(STIL):
        figures = (render_gesamtkosten(models, table, queries, repeats),
                   render_amortisation(models, table, queries, repeats))
    for name, figure in zip(NAMEN, figures):
        for ext in FORMATE:
            path = analysis / f'{name}.{ext}'
            figure.savefig(path, dpi=220)
            outputs[path.name] = sha_file(path)
        plt.close(figure)
    inputs = {f'{run.name}/{name}': sha_file(run / name) for name in ('metadata.json', 'totals.csv', 'batches.csv', 'raw.csv')}
    inputs.update({f'{analysis.name}/{name}': sha_file(analysis / name)
                   for name in ('models.json', 'amortisation.json', 'plot_manifest.json')})
    write_json(analysis / 'render_manifest.json', {
        'run_id': meta['run_id'], 'dataset_id': dataset['id'], 'input_sha256': inputs,
        'output_sha256': outputs, 'renderer_source': 'themen/05_experimentelle_analyse/experimente/render_bgb.py',
        'renderer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'matplotlib_version': matplotlib.__version__, 'verification': 'archive_only' if archive_only else 'strict',
        'darstellung': 'Mediane als Linien, Q1 bis Q3 als Bänder (inklusive Quartile, keine Konfidenzintervalle), '
                       'senkrechte Linie bei aufgerundetem q* des Modells, symlog für q ab 0'})
    print(f'{len(outputs)} Bilddateien und render_manifest.json in {analysis} geschrieben, Rohwerte unverändert.')
    return outputs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--input', type=Path, required=True, help='geprüfter Messlauf, z. B. ergebnisse/messungen/05_bgb')
    parser.add_argument('--analysis', type=Path, required=True, help='Ausgabe von analyse, z. B. ergebnisse/abbildungen/05_bgb')
    parser.add_argument('--archive-only', action='store_true',
                        help='aktive Quellen dürfen abweichen; Archiv, Rohwerte und Daten bleiben geprüft')
    args = parser.parse_args()
    render(args.input, args.analysis, archive_only=args.archive_only)
