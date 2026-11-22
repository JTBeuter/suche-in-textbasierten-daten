#!/usr/bin/env python3
"""Lesbare Publikationsfassungen aus verifizierten, unveränderten Messarchiven.

Aufruf aus der Repositorywurzel: .venv/bin/python ergebnisse/abbildungen_arbeit/render_eval_figures.py
Die historischen Diagramme und Rohdaten werden nicht überschrieben.

Mit --kapitel5 entstehen ausschließlich die überarbeiteten Fassungen
unter neuen Dateinamen (02_indexaufbau_ueberarbeitet,
05_gesamtkosten_baender, 05_amortisation_beschriftet) und ein eigenes Manifest
plot_manifest_ueberarbeitet.json. Bestehende Ausgaben bleiben dabei unberührt.
"""
import hashlib
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import ticker

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
INPUTS: dict[str, str] = {}
GENERATED: dict[str, str] = {}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(relative):
    path = ROOT / relative
    INPUTS[relative] = sha(path)
    return json.loads(path.read_text())


def save(fig, name):
    for ext in ('png', 'pdf', 'svg'):
        path = OUTPUT / f'{name}.{ext}'
        fig.savefig(path, dpi=220)
        GENERATED[path.relative_to(ROOT).as_posix()] = sha(path)
    plt.close(fig)


def render_index(ausgabe='02_indexaufbau', titel_v='N und D konstant; P wächst mit V'):
    prefix = 'ergebnisse/messungen/02_invertierter_index/'
    meta = read(prefix + 'metadata.json')
    summary = read(prefix + 'summary.json')
    memory = read(prefix + 'memory.json')
    builds = {row['dataset_id']: row for row in summary if row['phase'] == 'build'}
    mem = {row['dataset_id']: row for row in memory['summary']}
    fig, axes = plt.subplots(2, 2, figsize=(6.3, 3.7), layout='constrained')
    for col, series, key, label in ((0, 'N', 'token_count', 'Tokenzahl N'),
                                   (1, 'V', 'vocabulary_size', 'Wortschatz V')):
        datasets = sorted((d for d in meta['datasets'] if series in d['series']),
                          key=lambda d: d[key])
        x = [d[key] for d in datasets]
        rows = [builds[d['dataset_id']] for d in datasets]
        axes[0, col].plot(x, [r['median_ms'] for r in rows], 'o-', color='#1769aa')
        axes[0, col].fill_between(x, [r['q1_ms'] for r in rows],
                                 [r['q3_ms'] for r in rows], alpha=.18)
        axes[0, col].set(ylabel='Aufbauzeit [ms]',
                        title='D und P wachsen mit N' if series == 'N' else titel_v)
        for field, name, color in (('retained_traced_bytes', 'Gehalten', '#1769aa'),
                                   ('peak_traced_bytes', 'Peak', '#c14c29'),
                                   ('exclusive_index_bytes', 'Objektgraph', '#427449')):
            axes[1, col].plot(x, [mem[d['dataset_id']]['median_' + field] / 1024
                                 for d in datasets], 'o-', label=name, color=color)
        axes[1, col].set(ylabel='Zusätzlicher Speicher [KiB]')
        axes[1, col].legend(fontsize=7, loc='upper left')
        for ax in axes[:, col]:
            ax.set(xscale='log', yscale='log', xlabel=label)
            ax.grid(alpha=.25, which='both')
    save(fig, ausgabe)


def render_phrases():
    rows = read('ergebnisse/messungen/04_positionsindex_phrasensuche/summary.json')
    lookup = {(r['dataset_id'], r['algorithm'], r['phase'], r['query_id']): r for r in rows}
    fig, axes = plt.subplots(1, 3, figsize=(6.3, 2.4), layout='constrained', sharey=True)
    lengths = [1, 2, 3, 5]
    for ax, group, title in zip(axes, ('frequent', 'rare', 'repeated'),
                               ('Häufig: z = 2.000', 'Selten: z = 2', 'Wiederholt: z = 1.200–400')):
        for algorithm, label, color in (('direct_phrase', 'Direkt', '#1769aa'),
                                        ('positional_phrase', 'Index', '#c14c29')):
            values = [lookup['phrase_h200', algorithm, 'query', f'{group}_k{m}'] for m in lengths]
            y = [r['median_ms'] * 1000 for r in values]
            ax.errorbar(lengths, y, yerr=[[v - r['q1_ms'] * 1000 for v, r in zip(y, values)],
                                         [r['q3_ms'] * 1000 - v for v, r in zip(y, values)]],
                        label=label, color=color, marker='o', capsize=2, markersize=3)
        ax.set(title=title, xlabel='Phrasenlänge m', xticks=lengths, yscale='log')
        ax.grid(alpha=.25, which='both')
    axes[0].set_ylabel('Zeit je Anfrage [µs]')
    axes[-1].legend(fontsize=7)
    save(fig, '04_phrasenlaenge')


def render_boolean():
    prefix = 'ergebnisse/messungen/03_boolesche_mehrwortsuche/'
    meta = read(prefix + 'metadata.json')
    summary = read(prefix + 'summary.json')
    data = next(d for d in meta['datasets'] if d['dataset_id'] == 'boolean_controlled')
    queries = [q for q in data['queries'] if q['operator'] == 'AND'
               and q['effective_term_count'] == 5 and q['order'] == 'forward']
    labels = {'rare': 'selten', 'frequent': 'häufig', 'mixed': 'gemischt',
              'unknown': 'unbekannt', 'disjoint': 'disjunkt',
              'high_overlap': 'hohe\nÜberschneidung', 'low_overlap': 'geringe\nÜberschneidung'}
    lookup = {(r['algorithm'], r['query_id']): r for r in summary
              if r['dataset_id'] == data['dataset_id'] and r['phase'] == 'query'}
    fig, ax = plt.subplots(figsize=(6.3, 2.5), layout='constrained')
    width = .34
    for algorithm, shift, color, label in (('and_input_order', -width / 2, '#1769aa', 'Eingabereihenfolge'),
                                          ('and_shortest_first', width / 2, '#c14c29', 'Kürzeste Liste zuerst')):
        rows = [lookup[algorithm, q['query_id']] for q in queries]
        ax.bar([i + shift for i in range(len(queries))], [r['median_ms'] * 1000 for r in rows],
               width=width, color=color, label=label, capsize=2,
               yerr=[[(r['median_ms'] - r['q1_ms']) * 1000 for r in rows],
                     [(r['q3_ms'] - r['median_ms']) * 1000 for r in rows]])
    ax.set(xticks=range(len(queries)), xticklabels=[labels[q['group']] for q in queries],
           ylabel='Zeit je Anfrage [µs]', xlabel='Kontrollierte Verteilung, k = 5', ylim=(0, None))
    ax.legend(fontsize=7)
    ax.grid(axis='y', alpha=.25)
    ax.set_axisbelow(True)
    save(fig, '03_and_reihenfolge')


def render_totals():
    prefix = 'ergebnisse/abbildungen/05/'
    lineage = read(prefix + 'plot_manifest.json')
    for name, digest in lineage['input_sha256'].items():
        path = ROOT / 'ergebnisse/messungen/05_experimentelle_analyse' / name
        if sha(path) != digest:
            raise ValueError(f'Geänderte Messgrundlage: {name}')
        INPUTS[path.relative_to(ROOT).as_posix()] = digest
    models = read(prefix + 'models.json')
    if INPUTS[prefix + 'models.json'] != lineage['output_sha256']['models.json']:
        raise ValueError('Kostenmodelle stimmen nicht mit dem historischen Bildmanifest überein')
    profiles = {'word_missing': 'Fehlendes Wort', 'word_frequent': 'Häufiges Wort',
                'word_rare': 'Seltenes Wort', 'and_present3': 'AND: drei Wörter',
                'or_present3': 'OR: drei Wörter', 'phrase_present3': 'Phrase: drei Tokens'}
    for chart in ('gesamtkosten', 'amortisation'):
        fig, axes = plt.subplots(2, 3, figsize=(6.3, 4.1), layout='constrained')
        for ax, profile in zip(axes.flat, profiles):
            if chart == 'gesamtkosten':
                model = next(m for m in models if m['dataset_kind'] == 'synthetic' and m['profile_id'] == profile)
                observations = model['observations']
                for key, label, color in (('direct_ns', 'Direkt', '#1769aa'),
                                          ('index_ns', 'Index', '#c14c29')):
                    ax.errorbar([o['query_count'] for o in observations],
                                [o[key]['median'] / 1e6 for o in observations],
                                yerr=[[(o[key]['median'] - o[key]['q1']) / 1e6 for o in observations],
                                      [(o[key]['q3'] - o[key]['median']) / 1e6 for o in observations]],
                                label=label, color=color, marker='.', linewidth=1, capsize=1)
                ax.set(yscale='log', ylabel='Gesamtzeit [ms]')
            else:
                for model in (m for m in models if m['profile_id'] == profile):
                    obs = model['observations']
                    x = [o['query_count'] for o in obs]
                    label = 'Erzeugt' if model['dataset_kind'] == 'synthetic' else 'Kafka'
                    ax.plot(x, [o['paired_saving_ns']['median'] / 1e6 for o in obs],
                            marker='.', linewidth=1, label=label)
                    ax.fill_between(x, [o['paired_saving_ns']['q1'] / 1e6 for o in obs],
                                    [o['paired_saving_ns']['q3'] / 1e6 for o in obs], alpha=.15)
                ax.axhline(0, color='black', linewidth=.6)
                ax.set_yscale('symlog', linthresh=1)
                ax.set_ylabel('Direkt − Index [ms]')
            ax.set(xscale='symlog', xlim=(0, None), xlabel='Abfragezahl q', title=profiles[profile])
            ax.grid(alpha=.2)
        axes.flat[0].legend(fontsize=7)
        save(fig, '05_' + chart)


KAPITEL5_PROFILE = {'word_missing': 'Fehlendes Wort', 'word_frequent': 'Häufiges Wort',
                    'word_rare': 'Seltenes Wort', 'and_present3': 'AND: drei Wörter',
                    'or_present3': 'OR: drei Wörter', 'phrase_present3': 'Phrase: drei Tokens'}
BLAU, ROT = '#1769aa', '#c14c29'


def deutsche_zahl(wert, _position=None):
    """Achsenbeschriftung ohne Exponenten: 1.000 statt 10^3, Minuszeichen statt Bindestrich."""
    if wert == 0:
        return '0'
    if abs(wert) >= 1 and float(wert).is_integer():
        text = f'{abs(int(wert)):,}'.replace(',', '.')
    else:
        text = f'{abs(wert):g}'.replace('.', ',')
    return ('\u2212' if wert < 0 else '') + text


def anfrage_achse(ax):
    """Gemeinsame x-Achse: symmetrisch logarithmisch, damit q = 0 sichtbar bleibt."""
    ax.set(xscale='symlog', xlim=(0, None), xlabel='Anzahl der Anfragen q')
    ax.xaxis.set_major_locator(ticker.FixedLocator([0, 1, 10, 100, 1000]))
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(deutsche_zahl))
    ax.xaxis.set_minor_locator(ticker.NullLocator())


def synthetische_modelle():
    """Kostenmodelle des synthetischen Korpus mit derselben Herkunftsprüfung wie render_totals."""
    prefix = 'ergebnisse/abbildungen/05/'
    lineage = read(prefix + 'plot_manifest.json')
    for name, digest in lineage['input_sha256'].items():
        path = ROOT / 'ergebnisse/messungen/05_experimentelle_analyse' / name
        if sha(path) != digest:
            raise ValueError(f'Geänderte Messgrundlage: {name}')
        INPUTS[path.relative_to(ROOT).as_posix()] = digest
    models = read(prefix + 'models.json')
    if INPUTS[prefix + 'models.json'] != lineage['output_sha256']['models.json']:
        raise ValueError('Kostenmodelle stimmen nicht mit dem historischen Bildmanifest überein')
    return {m['profile_id']: m for m in models if m['dataset_kind'] == 'synthetic'}


def render_gesamtkosten_baender(models):
    """Abbildung 5.5 neu: Mediane als Linien, Q1 bis Q3 als halbtransparente Bänder."""
    fig, axes = plt.subplots(2, 3, figsize=(6.3, 4.2), layout='constrained')
    for ax, profile in zip(axes.flat, KAPITEL5_PROFILE):
        observations = models[profile]['observations']
        x = [o['query_count'] for o in observations]
        for key, label, color in (('direct_ns', 'Direkte Suche', BLAU), ('index_ns', 'Index', ROT)):
            ax.plot(x, [o[key]['median'] / 1e6 for o in observations], color=color,
                    linewidth=1.2, marker='o', markersize=2.2, label=label + ' (Median)')
            ax.fill_between(x, [o[key]['q1'] / 1e6 for o in observations],
                            [o[key]['q3'] / 1e6 for o in observations],
                            color=color, alpha=.18, linewidth=0, label=label + ' (Q1–Q3)')
        ax.set(yscale='log', title=KAPITEL5_PROFILE[profile])
        ax.yaxis.set_major_locator(ticker.LogLocator(base=10, subs=(1, 2, 5)))
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(deutsche_zahl))
        ax.yaxis.set_minor_formatter(ticker.NullFormatter())
        anfrage_achse(ax)
        ax.grid(alpha=.2, which='major')
    for ax in axes[:, 0]:
        ax.set_ylabel('Gesamtzeit [ms]')
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside lower center', ncol=4, fontsize=7, frameon=False)
    save(fig, '05_gesamtkosten_baender')


def render_amortisation_beschriftet(models):
    """Abbildung 5.4 neu: gepaarte Differenz T_direkt − T_index mit Lesehilfe und Modell-q*."""
    fig, axes = plt.subplots(2, 3, figsize=(6.3, 4.4), layout='constrained')
    for ax, profile in zip(axes.flat, KAPITEL5_PROFILE):
        model = models[profile]
        obs = model['observations']
        x = [o['query_count'] for o in obs]
        ax.axhline(0, color='black', linewidth=.8)
        ax.fill_between(x, [o['paired_saving_ns']['q1'] / 1e6 for o in obs],
                        [o['paired_saving_ns']['q3'] / 1e6 for o in obs],
                        color=BLAU, alpha=.18, linewidth=0, label='Q1–Q3 der fünf Paare')
        ax.plot(x, [o['paired_saving_ns']['median'] / 1e6 for o in obs], color=BLAU,
                linewidth=1.2, marker='o', markersize=2.2, label='Median der Differenz')
        q_stern = model['equality_q']
        if model['delta_t_ns'] > 0 and q_stern > 0:
            ax.axvline(q_stern, color=ROT, linestyle='--', linewidth=1, label='q* aus dem Modell')
            text = f'q* ≈ {q_stern:.1f}'.replace('.', ',')
            # Bei AND liegen unten und rechts der Linie Messpunkte, dort links oben beschriften.
            links = profile == 'and_present3'
            ax.text(q_stern / 1.12 if links else q_stern * 1.12, .97 if links else .03, text,
                    transform=ax.get_xaxis_transform(), ha='right' if links else 'left',
                    color=ROT, fontsize=6.5, va='top' if links else 'bottom',
                    bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': .8, 'pad': 1})
        else:
            ax.text(.03, .97, 'Modell: nie', transform=ax.transAxes, color=ROT,
                    fontsize=6.5, va='top')
        ax.set_yscale('symlog', linthresh=1)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(deutsche_zahl))
        ax.yaxis.set_minor_locator(ticker.NullLocator())
        ax.set(title=KAPITEL5_PROFILE[profile])
        anfrage_achse(ax)
        ax.grid(alpha=.2)
    for ax in axes[:, 0]:
        ax.set_ylabel(r'$T_{\mathrm{direkt}}-T_{\mathrm{index}}$ [ms]')
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside lower center', ncol=3, fontsize=7, frameon=False,
               title='Über der Nulllinie spart der Index Zeit, darunter ist die direkte Suche schneller.',
               title_fontsize=7)
    save(fig, '05_amortisation_beschriftet')


def kapitel5():
    """Nur neue Dateien für Kapitel 5 erzeugen, eigenes Manifest, keine Altausgabe berühren."""
    neue_namen = ('02_indexaufbau_ueberarbeitet', '05_gesamtkosten_baender',
                  '05_amortisation_beschriftet')
    render_index('02_indexaufbau_ueberarbeitet', 'N und D fest, P wächst mit V')
    models = synthetische_modelle()
    render_gesamtkosten_baender(models)
    render_amortisation_beschriftet(models)
    manifest = {'input_sha256': INPUTS, 'output_sha256': GENERATED,
                'renderer_sha256': sha(Path(__file__)), 'matplotlib_version': matplotlib.__version__,
                'purpose': 'Überarbeitete Abbildungen für Kapitel 5: Reihe 02 ohne Semikolon im Titel, '
                           '5.4 und 5.5 nur synthetischer Korpus mit Bändern, Lesehilfe und q* aus models.json',
                'outputs': list(neue_namen), 'historical_archives_modified': False}
    (OUTPUT / 'plot_manifest_ueberarbeitet.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(f'{len(GENERATED)} neue Dateien für Kapitel 5 aus unveränderten Daten erstellt.')


if __name__ == '__main__':
    plt.rcParams.update({'font.size': 8, 'axes.titlesize': 8, 'axes.labelsize': 8,
                         'xtick.labelsize': 7, 'ytick.labelsize': 7,
                         'svg.hashsalt': 'textsuche-benjamin'})
    OUTPUT.mkdir(exist_ok=True)
    if '--kapitel5' in sys.argv[1:]:
        kapitel5()
        sys.exit(0)
    render_index()
    render_boolean()
    render_phrases()
    render_totals()
    manifest = {'input_sha256': INPUTS, 'output_sha256': GENERATED,
                'renderer_sha256': sha(Path(__file__)), 'matplotlib_version': matplotlib.__version__,
                'purpose': 'Lesbare Druckfassung; q=Anfragezahl, z=Phrasenstarts; unveränderte numerische Daten',
                'historical_archives_modified': False}
    (OUTPUT / 'plot_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(f'{len(GENERATED)} Publikationsdateien aus unveränderten Daten erstellt.')
