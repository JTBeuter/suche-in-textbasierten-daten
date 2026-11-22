#!/usr/bin/env python3
"""Publikationsdiagramme aus geprüften Modellen, mit zulässigem Q>=0."""
import argparse
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from experimentelle_analyse.provenance import ROOT, sha_file, write_json
from experimentelle_analyse.verify import verify_run

LABELS={'word_missing':'Fehlendes Wort','word_frequent':'Häufiges Wort','word_rare':'Seltenes Wort',
        'and_present3':'AND (3 Wörter)','or_present3':'OR (3 Wörter)','phrase_present3':'Phrase (3 Tokens)'}


def render(run,output,archive_only=False):
    verify_run(run,archive_only=archive_only)
    lineage=json.loads((output/'plot_manifest.json').read_text())
    for name,digest in lineage['input_sha256'].items():
        if sha_file(run/name)!=digest:
            raise ValueError('Diagrammdaten stammen aus einem anderen Lauf')
    for name in ('models.json','summary.json'):
        if sha_file(output/name)!=lineage['output_sha256'][name]:
            raise ValueError('Abgeleitete Modelle/Zusammenfassung beschädigt')
    models=json.loads((output/'models.json').read_text())
    for chart in ('gesamtkosten','amortisation'):
        fig,axes=plt.subplots(2,3,figsize=(11,6),layout='constrained')
        for ax,profile in zip(axes.flat,LABELS):
            if chart=='gesamtkosten':
                m=next(m for m in models if m['dataset_kind']=='synthetic' and m['profile_id']==profile)
                observations=m['observations']
                for key,label,color in (('direct_ns','Direkt','#1769aa'),('index_ns','Index','#c14c29')):
                    ax.errorbar([o['query_count'] for o in observations],
                        [o[key]['median']/1e6 for o in observations],
                        yerr=[[(o[key]['median']-o[key]['q1'])/1e6 for o in observations],
                              [(o[key]['q3']-o[key]['median'])/1e6 for o in observations]],
                        label=label,color=color,marker='.',linewidth=1,capsize=2)
                ax.set_yscale('log')
                ax.set_ylabel('Gesamtzeit [ms]')
            else:
                for m in [m for m in models if m['profile_id']==profile]:
                    obs=m['observations'];x=[o['query_count'] for o in obs]
                    label='Erzeugt (N=10.000)' if m['dataset_kind']=='synthetic' else 'Kafka (N=1.271)'
                    ax.plot(x,[o['paired_saving_ns']['median']/1e6 for o in obs],marker='.',linewidth=1,label=label)
                    ax.fill_between(x,[o['paired_saving_ns']['q1']/1e6 for o in obs],
                        [o['paired_saving_ns']['q3']/1e6 for o in obs],alpha=.15)
                ax.axhline(0,color='black',linewidth=.6)
                ax.set_yscale('symlog',linthresh=1)
                ax.set_ylabel('Direkt − Index [ms]')
            ax.set_xscale('symlog',linthresh=1)
            ax.set_xlim(left=0)
            ax.set_xlabel('Abfragen Q (symlog)')
            ax.set_title(LABELS[profile])
            ax.grid(alpha=.2)
        axes.flat[0].legend(fontsize=8)
        for ext in ('png','svg','pdf'):
            fig.savefig(output/f'05_{chart}.{ext}',dpi=180)
        plt.close(fig)
    lineage['initial_renderer_sha256']=lineage.get('initial_renderer_sha256',lineage['renderer_sha256'])
    lineage['renderer_sha256']=sha_file(Path(__file__))
    lineage['renderer_source']='themen/05_experimentelle_analyse/experimente/render.py'
    lineage['q_axis_domain']='Q>=0; symlog lower bound0; signed savings on y'
    lineage['output_sha256']={name:sha_file(output/name) for name in lineage['output_sha256']}
    write_json(output/'plot_manifest.json',lineage)
    print('Zwei Diagramme (PNG/SVG/PDF) und Bildmanifest aktualisiert; Rohwerte unverändert.')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=ROOT/'ergebnisse/messungen/05_experimentelle_analyse')
    p.add_argument('--output',type=Path,default=ROOT/'ergebnisse/abbildungen/05')
    p.add_argument('--archive-only',action='store_true',help='aktive Quellen dürfen abweichen; Archiv bleibt geprüft')
    a=p.parse_args();render(a.input,a.output,a.archive_only)
