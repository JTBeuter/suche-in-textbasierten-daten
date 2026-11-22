"""Auswertung geprüfter Rohwerte; Modelle getrennt von gemessenen Summen."""
from collections import defaultdict
from fractions import Fraction
import json
from pathlib import Path
from statistics import median, quantiles

from gemeinsam.messung import summarize_measurements
from .costs import amortisation_3_6, cheaper_range
from .provenance import ROOT, sha_file, write_json
from .schema import AMORTISATION_TABLE, BATCH_FIELDS, FLOW_FIELDS, read_csv, write_csv


AMORTISATION_FIELDS = ("daten","profil","anfrage","t_aufbau_ms","t_direkt_ms","t_index_ms","q_stern",
                       "q_stern_aufgerundet","amortisation","erste_stufe_alle_paare_positiv",
                       "median_ersparnis_ms_dort","paare_positiv_dort","paare_dort",
                       "ab_stufe_alle_hoeheren_alle_paare_positiv")


def stats(values):
    if len(values)<2:
        raise ValueError("Mindestens zwei unabhängige Blockwiederholungen erforderlich")
    q1,_,q3=quantiles(values,n=4,method="inclusive")
    return {"samples":len(values),"median":float(median(values)),"q1":float(q1),"q3":float(q3),
            "iqr":float(q3-q1),"min":float(min(values)),"max":float(max(values))}


def calculate_models(meta, rows, batches, totals):
    models=[]
    for ds in meta["datasets"]:
        for profile in ds["profiles"]:
            own=[r for r in batches if r["dataset_id"]==ds["id"] and r["profile_id"]==profile["id"]]
            td=median([Fraction(int(r["elapsed_ns"]),int(r["query_count"])) for r in own if r["algorithm"]=="direct"])
            ti=median([Fraction(int(r["elapsed_ns"]),int(r["query_count"])) for r in own if r["algorithm"]==profile["algorithm"]])
            kind=next(q for q in ds["queries"] if q["id"]==profile["query_id"])["kind"]
            index="positional_index" if kind=="phrase" else "inverted_index"
            build=median([int(r["elapsed_ns"]) for r in rows if r["dataset_id"]==ds["id"] and r["phase"]=="build" and r["algorithm"]==index])
            prep=median([int(r["elapsed_ns"]) for r in rows if r["dataset_id"]==ds["id"] and r["phase"]=="preparation"])
            model={"dataset_id":ds["id"],"dataset_kind":ds["kind"],"profile_id":profile["id"],
                "query_id":profile["query_id"],"index_algorithm":profile["algorithm"],
                "preparation_direct_ns":float(prep),"preparation_index_ns":float(prep),
                "build_direct_ns":0,"build_index_ns":float(build),
                "query_direct_ns":float(td),"query_index_ns":float(ti),**cheaper_range(build,td-ti),
                "model_basis":f"median full {meta['config'].get('sequence_block_size',50)}-query profile blocks / query count; equal preparation; no sum presented as measured total",
                "observations":[]}
            own=[r for r in totals if r["dataset_id"]==ds["id"] and r["profile_id"]==profile["id"]]
            for count in profile["q_values"]:
                direct={int(r["repeat"]):int(r["elapsed_ns"]) for r in own if int(r["query_count"])==count and r["algorithm"]=="direct"}
                indexed={int(r["repeat"]):int(r["elapsed_ns"]) for r in own if int(r["query_count"])==count and r["algorithm"]==profile["algorithm"]}
                savings=[direct[i]-indexed[i] for i in sorted(direct)]
                model["observations"].append({"query_count":count,"direct_ns":stats(list(direct.values())),
                    "index_ns":stats(list(indexed.values())),"paired_saving_ns":stats(savings),
                    "predicted_saving_ns":float(count*(td-ti)-build),
                    "index_cheaper_repeats":sum(s>0 for s in savings),"repeats":len(savings)})
            observations=model["observations"]
            first=next((o for o in observations if o["paired_saving_ns"]["median"]>0),None)
            robust=next((o for o in observations if o["paired_saving_ns"]["q1"]>0),None)
            lower=max((o["query_count"] for o in observations if first and o["query_count"]<first["query_count"] and o["paired_saving_ns"]["median"]<=0),default=None)
            model["observed_first_median_advantage_q"]=None if first is None else first["query_count"]
            model["observed_transition_bracket"]=None if first is None else [lower,first["query_count"]]
            model["observed_first_positive_iqr_q"]=None if robust is None else robust["query_count"]
            model["observed_median_advantage_qs"]=[o["query_count"] for o in observations if o["paired_saving_ns"]["median"]>0]
            model["observed_all_repeats_advantage_qs"]=[o["query_count"] for o in observations if o["index_cheaper_repeats"]==o["repeats"]]
            models.append(model)
    return models


def amortisation_rows(meta, models):
    """Größen aus Abschnitt 3.6 je Modell: t_Aufbau, t_direkt, t_index, q*, ⌈q*⌉ oder nie.

    Die t-Werte sind dieselben Mediane wie im Modell (Profilblöcke, Aufbauphase).
    Beobachtet wird nur an den tatsächlich gemessenen Rasterstufen.
    """
    queries={(d["id"],q["id"]):q for d in meta["datasets"] for q in d["queries"]}
    rows=[]
    for model in models:
        values=amortisation_3_6(model["build_index_ns"],model["query_direct_ns"],model["query_index_ns"])
        observations=model["observations"]
        first=next((o for o in observations if o["index_cheaper_repeats"]==o["repeats"]),None)
        suffix=next((o["query_count"] for i,o in enumerate(observations)
                     if all(v["index_cheaper_repeats"]==v["repeats"] for v in observations[i:])),None)
        rows.append({"dataset_id":model["dataset_id"],"profile_id":model["profile_id"],
            "query_text":queries[(model["dataset_id"],model["query_id"])]["text"],
            "index_algorithm":model["index_algorithm"],**values,
            "first_cheaper_q_strict":model["first_cheaper_q"] if model["has_advantage"] else None,
            "first_stage_all_pairs_positive":None if first is None else first["query_count"],
            "median_saving_ns_there":None if first is None else first["paired_saving_ns"]["median"],
            "positive_pairs_there":None if first is None else first["index_cheaper_repeats"],
            "pairs_there":None if first is None else first["repeats"],
            "from_stage_all_higher_all_pairs_positive":suffix,
            "basis":"Mediane: Aufbauphase (t_Aufbau), Profilblöcke/Anfragezahl (t_direkt, t_index); gleiche Vorbereitung beider Seiten"})
    return rows


def write_amortisation(output_dir, rows):
    """JSON mit Nanosekunden und lesbare CSV in Millisekunden, „nie“ statt Platzhalterstrich."""
    write_json(output_dir/"amortisation.json",rows)
    def ms(value):
        return "" if value is None else f"{value/1e6:.6f}"
    write_csv(output_dir/"amortisation.csv",[{"daten":r["dataset_id"],"profil":r["profile_id"],"anfrage":r["query_text"],
        "t_aufbau_ms":ms(r["t_aufbau_ns"]),"t_direkt_ms":ms(r["t_direkt_ns"]),"t_index_ms":ms(r["t_index_ns"]),
        "q_stern":"" if r["q_stern"] is None else f"{r['q_stern']:.3f}",
        "q_stern_aufgerundet":"" if r["q_stern_aufgerundet"] is None else r["q_stern_aufgerundet"],
        "amortisation":r["amortisation"],
        "erste_stufe_alle_paare_positiv":"nie" if r["first_stage_all_pairs_positive"] is None else r["first_stage_all_pairs_positive"],
        "median_ersparnis_ms_dort":ms(r["median_saving_ns_there"]),
        "paare_positiv_dort":"" if r["positive_pairs_there"] is None else r["positive_pairs_there"],
        "paare_dort":"" if r["pairs_there"] is None else r["pairs_there"],
        "ab_stufe_alle_hoeheren_alle_paare_positiv":"nie" if r["from_stage_all_higher_all_pairs_positive"] is None
            else r["from_stage_all_higher_all_pairs_positive"]} for r in rows],AMORTISATION_FIELDS)


def analyse(input_dir, output_dir, *, archive_only=False):
    """Prüft den Lauf und schreibt Auswertungen; vorhandene Ausgaben werden nicht überschrieben."""
    from .verify import verify_run
    input_dir,output_dir=Path(input_dir),Path(output_dir)
    verification=verify_run(input_dir,archive_only=archive_only)  # Fehlerhafte Läufe erzeugen keine Diagramme.
    meta=json.loads((input_dir/"metadata.json").read_text())
    table=meta["config"].get("amortisation_table")==AMORTISATION_TABLE
    artifacts=["summary.json","models.json"]+(["amortisation.json","amortisation.csv"] if table else [])
    artifacts+=[f"05_{name}.{ext}" for name in ("gesamtkosten","amortisation") for ext in ("png","svg","pdf")]
    existing=[name for name in artifacts+["plot_manifest.json"] if (output_dir/name).exists()]
    if existing:
        raise ValueError(f"Auswertungsziel enthält bereits {existing[0]}; vorhandene Auswertungen werden nicht überschrieben")
    output_dir.mkdir(parents=True,exist_ok=True)
    rows=read_csv(input_dir/"raw.csv")
    batches=read_csv(input_dir/"batches.csv",BATCH_FIELDS)
    totals=read_csv(input_dir/"totals.csv",FLOW_FIELDS)
    converted=[]
    for r in rows:
        converted.append({**r,r["phase"]+"_ms":float(r[r["phase"]+"_ms"]),"token_count":int(r["token_count"])})
    summary=summarize_measurements(converted)
    models=calculate_models(meta,rows,batches,totals)
    write_json(output_dir/"summary.json",summary)
    write_json(output_dir/"models.json",models)
    if table:
        write_amortisation(output_dir,amortisation_rows(meta,models))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    profiles=[p["id"] for p in meta["datasets"][0]["profiles"]]
    fig,axes=plt.subplots(2,3,figsize=(11,6),layout="constrained")
    synthetic=[m for m in models if m["dataset_kind"]=="synthetic"] or [m for m in models if m["dataset_id"]==meta["datasets"][0]["id"]]
    for ax,profile in zip(axes.flat,profiles):
        m=next(m for m in synthetic if m["profile_id"]==profile)
        observations=m["observations"]
        qs=[o["query_count"] for o in observations]
        for key,label,color in (("direct_ns","Direkt","#1769aa"),("index_ns","Index","#c14c29")):
            med=[o[key]["median"]/1e6 for o in observations]
            errors=[[o[key]["iqr"]/2e6 for o in observations]]*2
            # Asymmetrische Quartile um den Median zeigen wirkliche Streuung.
            errors=[[max(0,(o[key]["median"]-o[key]["q1"])/1e6) for o in observations],
                    [max(0,(o[key]["q3"]-o[key]["median"])/1e6) for o in observations]]
            ax.errorbar(qs,med,yerr=errors,label=label,color=color,marker=".",linewidth=1,capsize=2)
        ax.set(xscale="symlog",yscale="log",xlabel="Abfragen Q (symlog)",ylabel="Gesamtzeit [ms]",title=profile)
        ax.grid(alpha=.2)
    axes.flat[0].legend(fontsize=8)
    for ext in ("png","svg","pdf"):
        fig.savefig(output_dir/("05_gesamtkosten."+ext),dpi=180)
    plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(11,6),layout="constrained")
    for ax,profile in zip(axes.flat,profiles):
        for m in [m for m in models if m["profile_id"]==profile]:
            obs=m["observations"]
            x=[o["query_count"] for o in obs]
            y=[o["paired_saving_ns"]["median"]/1e6 for o in obs]
            ax.plot(x,y,marker=".",label=m["dataset_id"])
            ax.fill_between(x,[o["paired_saving_ns"]["q1"]/1e6 for o in obs],[o["paired_saving_ns"]["q3"]/1e6 for o in obs],alpha=.15)
        ax.axhline(0,color="black",linewidth=.6)
        ax.set(xscale="symlog",yscale="symlog",xlabel="Abfragen Q (symlog)",ylabel="Direkt − Index [ms]",title=profile)
        ax.grid(alpha=.2)
    axes.flat[0].legend(fontsize=8)
    for ext in ("png","svg","pdf"):
        fig.savefig(output_dir/("05_amortisation."+ext),dpi=180)
    plt.close(fig)
    inputs={f:sha_file(input_dir/f) for f in ("raw.csv","batches.csv","totals.csv","metadata.json","memory.json","correctness.json")}
    write_json(output_dir/"plot_manifest.json",{"run_id":meta["run_id"],"verification":verification,"input_sha256":inputs,
        "renderer_sha256":sha_file(Path(__file__)),"output_sha256":{f:sha_file(output_dir/f) for f in artifacts},
        "scatter":"inclusive quartiles, not confidence intervals; no discarded samples"})
    return {"run_id":meta["run_id"],"groups":len(summary),"models":len(models),"output":str(output_dir)}
