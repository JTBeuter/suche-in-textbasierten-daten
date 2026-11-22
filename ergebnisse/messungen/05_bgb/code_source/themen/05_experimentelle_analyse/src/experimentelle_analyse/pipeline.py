"""Korrektheitsgesicherte Phasen und tatsächlich gemessene Gesamtabläufe."""
from datetime import datetime, timezone
from fractions import Fraction
import gc
import json
import os
from pathlib import Path
import random
from statistics import median
import subprocess
import sys
from time import perf_counter_ns
import traceback

from gemeinsam import load_corpus, prepare_corpus
from gemeinsam.messung import write_measurements
from .costs import cheaper_range
from .operations import BUILDERS, index_oracle, result_hash, search_operation, validate_index, validate_result, variants
from .provenance import ROOT, archive_sources, background_load, environment, source_hashes, write_json
from .schema import BATCH_FIELDS, FLOW_FIELDS, validate_config, write_csv


def timed(operation, count, validate):
    """GC nur im Timer deaktiviert; jedes materialisierte Ergebnis danach prüfen."""
    enabled=gc.isenabled()
    gc.disable()
    try:
        start=perf_counter_ns()
        results=[operation() for _ in range(count)]
        elapsed=perf_counter_ns()-start
    finally:
        if enabled:
            gc.enable()
        else:
            gc.disable()
    for result in results:
        validate(result)
    return elapsed


def select_profiles(queries):
    profiles=[]
    for category in ("missing","frequent","rare"):
        candidates=[q for q in queries if q["kind"]=="word" and q["category"]==category]
        if not candidates:
            raise ValueError(f"Pflichtprofil word/{category} fehlt")
        profiles.append({"id":"word_"+category,"query_id":candidates[0]["id"],"algorithm":"index"})
    for kind in ("and","or","phrase"):
        candidates=[q for q in queries if q["kind"]==kind and q["hit_count"]>0 and q["length"]==3]
        if not candidates:
            raise ValueError(f"Pflichtprofil {kind}/Länge3 mit Treffern fehlt")
        profiles.append({"id":kind+"_present3","query_id":candidates[0]["id"],
                         "algorithm":"index_shortest" if kind=="and" else "index"})
    return profiles


def require_hash_seed(config):
    """Hauptläufe nur mit PYTHONHASHSEED=0 (dokumentierte Konvention); vor jeder Ausgabe."""
    if config.get("mode")=="main" and os.environ.get("PYTHONHASHSEED")!="0":
        raise ValueError("Hauptlauf erfordert PYTHONHASHSEED=0")


def semantic_config(config):
    return {k:v for k,v in config.items() if k not in {"mode","pilot_directory","warmups","repeats","total_repeats"}}


def q_grid(profile, batches, build_rows, config):
    """Vorab definierte Kalibrierregel; keine Auswahl nach gewünschten Befunden."""
    direct=median([Fraction(r["elapsed_ns"],r["query_count"]) for r in batches if r["algorithm"]=="direct"])
    indexed=median([Fraction(r["elapsed_ns"],r["query_count"]) for r in batches if r["algorithm"]==profile["algorithm"]])
    build=median([r["elapsed_ns"] for r in build_rows])
    model=cheaper_range(build,direct-indexed)
    q=model["first_cheaper_q"]
    values=set(config["q_values"])
    if q is not None and 1 <= q <= 5000:
        values.update((max(0,q//2),max(0,q-1),q,min(5000,q+1),min(5000,2*q)))
    return sorted(values), model


def run_experiment(config_path, output):
    from .datasets import build_datasets
    config=validate_config(json.loads(Path(config_path).read_text(encoding="utf-8")))
    require_hash_seed(config)
    output=Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Messziel muss leer sein; vorhandene Läufe werden nicht überschrieben")
    output.mkdir(parents=True,exist_ok=True)
    hashes=source_hashes()
    archive_sources(output,hashes)
    env=environment()
    pilot=None
    if config.get("pilot_directory"):
        from .verify import verify_run
        pilot_dir=ROOT/config["pilot_directory"]
        verify_run(pilot_dir)
        pilot=json.loads((pilot_dir/"metadata.json").read_text())
        if pilot["code_sha256"]!=hashes or semantic_config(pilot["config"])!=semantic_config(config):
            raise ValueError("Pilotbindung verletzt: Code/Versuchsparameter verändert")
    meta={"schema_version":1,"status":"running","run_id":"05_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"),
          "config":config,"environment":env,"code_sha256":hashes,"datasets":[],
          "measurement_boundaries":{"query":"prepared corpus -> raw query normalisation -> all materialised matches; block list included",
              "total":"loaded raw corpus in memory -> prepare -> optional build -> Q identical complete profile queries; materialised results retained until post-timer validation",
              "load":"cached local files, not cold disk","gc":"disabled only inside timer, previous state restored; gc.collect once per dataset",
              "cache":"in-process warmed interpreter/allocator; no CPU isolation; no concurrent project benchmark/test/build",
              "memory":"separate worker per dataset/index; tracer starts after preparation, no alternate production index built"},
          "pilot_run_id":None if pilot is None else pilot["run_id"],"exclusions":[],
          # Momentaufnahmen nur zwischen Zeitintervallen; beschreiben, korrigieren nichts.
          "background_load":[background_load("vor_messung")]}
    rows,batches,flows,checks=[],[],[],[]
    def save():
        write_measurements(output/"raw.csv",rows)
        write_csv(output/"batches.csv",batches,BATCH_FIELDS)
        write_csv(output/"totals.csv",flows,FLOW_FIELDS)
        write_json(output/"metadata.json",meta)
        write_json(output/"correctness.json",checks)
    try:
        datasets=build_datasets(config,output/"datasets")
        for ds in datasets:
            raw=load_corpus(ds["root"])
            corpus=prepare_corpus(raw)
            tokens=ds["expected_tokens"]
            if {d.document_id:d.tokens for d in corpus}!=tokens:
                raise AssertionError(f"{ds['id']}: vollständige Tokenfolge falsch")
            queries=ds["queries"]
            profiles=select_profiles(queries)
            desc={"id":ds["id"],"kind":ds["kind"],"root":os.path.relpath(Path(ds["root"]).resolve(),output.resolve()),
                  "manifest":ds["manifest"],"queries":queries,"profiles":profiles,
                  "document_count":len(corpus),"token_count":sum(len(d.tokens) for d in corpus),
                  "text_bytes":sum(len(d.raw_text.encode()) for d in raw),
                  "vocabulary_size":len({t for d in corpus for t in d.tokens})}
            meta["datasets"].append(desc)
            context={"run_id":meta["run_id"],"git_commit":env["git_commit"],"seed":config["seed"],
                "dataset_id":ds["id"],**{k:desc[k] for k in ("document_count","token_count","text_bytes")}}
            oracles={name:index_oracle(tokens,name=="positional_index") for name in BUILDERS}
            indexes={name:builder(corpus) for name,builder in BUILDERS.items()}
            for name,index in indexes.items():
                validate_index(index,oracles[name],name=="positional_index")
            for q in queries:
                index=indexes["positional_index" if q["kind"]=="phrase" else "inverted_index"]
                for algorithm in variants(q["kind"]):
                    validate_result(search_operation(corpus,index,q,algorithm),q,corpus)
                    checks.append({"dataset_id":ds["id"],"query_id":q["id"],"algorithm":algorithm,
                        "result_sha256":result_hash(q["expected"]),"hit_count":q["hit_count"],
                        "position_count":q["position_count"],"validated_calls":1+config["block_size"]*(config["warmups"]+config["repeats"])})
            rng=random.Random(config["seed"])
            gc.collect()
            phase_operations=[("load","common",lambda:load_corpus(ds["root"]),lambda value: value==raw or (_ for _ in ()).throw(AssertionError("Raw corpus differs"))),
                ("preparation","common",lambda:prepare_corpus(raw),lambda value:value==corpus or (_ for _ in ()).throw(AssertionError("Prepared corpus differs")))]
            for name,builder in BUILDERS.items():
                phase_operations.append(("build",name,lambda b=builder:b(corpus),
                    lambda value,n=name:validate_index(value,oracles[n],n=="positional_index")))
            tasks=[(q,a) for q in queries for a in variants(q["kind"])]
            for repeat in range(-config["warmups"],config["repeats"]):
                order=list(phase_operations);rng.shuffle(order)
                for order_i,(phase,algorithm,operation,validator) in enumerate(order):
                    elapsed=timed(operation,1,validator)
                    if repeat>=0:
                        rows.append({**context,"phase":phase,"algorithm":algorithm,"repeat":repeat,
                            "order_index":order_i,"block_size":1,"elapsed_ns":elapsed,f"{phase}_ms":elapsed/1e6,"correct":True})
                order=list(tasks);rng.shuffle(order)
                for order_i,(q,algorithm) in enumerate(order):
                    index=indexes["positional_index" if q["kind"]=="phrase" else "inverted_index"]
                    elapsed=timed(lambda:search_operation(corpus,index,q,algorithm),config["block_size"],lambda value:validate_result(value,q,corpus))
                    if repeat>=0:
                        rows.append({**context,"phase":"query","algorithm":algorithm,"repeat":repeat,
                            "order_index":order_i,"block_size":config["block_size"],"elapsed_ns":elapsed,
                            "query_id":q["id"],"query_type":q["kind"],"query_text":q["text"],
                            "query_ms":elapsed/1e6/config["block_size"],"hit_count":q["hit_count"],"correct":True})
            meta["background_load"].append(background_load(f"{ds['id']}:nach_phasen_und_queryblocks"))
            by_query={q["id"]:q for q in queries}
            # Repräsentative Kosten werden als ganze, passende Profilblöcke gemessen.
            for profile in profiles:
                q=by_query[profile["query_id"]]
                index=indexes["positional_index" if q["kind"]=="phrase" else "inverted_index"]
                for repeat in range(-config["warmups"],config["repeats"]):
                    order=["direct",profile["algorithm"]];rng.shuffle(order)
                    for order_i,algorithm in enumerate(order):
                        count=config.get("sequence_block_size",50)
                        elapsed=timed(lambda:search_operation(corpus,index,q,algorithm),count,lambda value:validate_result(value,q,corpus))
                        if repeat>=0:
                            batches.append({"run_id":meta["run_id"],"dataset_id":ds["id"],"profile_id":profile["id"],
                                "algorithm":algorithm,"repeat":repeat,"order_index":order_i,"query_count":count,
                                "elapsed_ns":elapsed,"ns_per_query":elapsed/count,"unit":"ns","correct":True})
                own=[r for r in batches if r["dataset_id"]==ds["id"] and r["profile_id"]==profile["id"]]
                name="positional_index" if q["kind"]=="phrase" else "inverted_index"
                build_rows=[r for r in rows if r["dataset_id"]==ds["id"] and r["phase"]=="build" and r["algorithm"]==name]
                grid,model=q_grid(profile,own,build_rows,config)
                if pilot:
                    prior=next(d for d in pilot["datasets"] if d["id"]==ds["id"])
                    grid=next(p for p in prior["profiles"] if p["id"]==profile["id"])["q_values"]
                profile.update(q_values=grid,calibration_model=model)
            meta["background_load"].append(background_load(f"{ds['id']}:nach_profilblocks"))
            # Alternative Indizes werden vor den Gesamtabläufen freigegeben.
            del indexes,index,oracles
            for profile in profiles:
                q=by_query[profile["query_id"]]
                builder=BUILDERS["positional_index" if q["kind"]=="phrase" else "inverted_index"]
                positional=q["kind"]=="phrase"
                oracle=index_oracle(tokens,positional)
                def flow(algorithm,count):
                    prepared=prepare_corpus(raw)
                    idx=None if algorithm=="direct" else builder(prepared)
                    results=[search_operation(prepared,idx,q,algorithm) for _ in range(count)]
                    return prepared,idx,results
                def validate_flow(value):
                    prepared,idx,results=value
                    if {d.document_id:d.tokens for d in prepared}!=tokens:
                        raise AssertionError("Gesamtablauf: Aufbereitung falsch")
                    if idx is not None:
                        validate_index(idx,oracle,positional)
                    for result in results:
                        validate_result(result,q,prepared)
                tasks=[(count,a) for count in profile["q_values"] for a in ("direct",profile["algorithm"])]
                for repeat in range(-1,config.get("total_repeats",5)):
                    order=list(tasks);rng.shuffle(order)
                    for order_i,(count,algorithm) in enumerate(order):
                        elapsed=timed(lambda:flow(algorithm,count),1,validate_flow)
                        if repeat>=0:
                            flows.append({"run_id":meta["run_id"],"dataset_id":ds["id"],"profile_id":profile["id"],
                                "algorithm":algorithm,"repeat":repeat,"order_index":order_i,"query_count":count,
                                "elapsed_ns":elapsed,"unit":"ns","result_digest":result_hash(q["expected"]),"correct":True})
                meta["background_load"].append(background_load(f"{ds['id']}:{profile['id']}:nach_gesamtablaeufen"))
            save()
        meta["timing_completed_at_utc"]=datetime.now(timezone.utc).isoformat()
        meta["background_load"].append(background_load("nach_zeitmessung"))
        # Eigene Prozesse mit eigenem vorbereitetem Korpus, keine Zeitmessung parallel.
        memory=[]
        save()
        for ds in meta["datasets"]:
            for name in BUILDERS:
                target=output/f"memory_{ds['id']}_{name}.json"
                subprocess.run([sys.executable,"-m","experimentelle_analyse.memory","--metadata",str(output/"metadata.json"),
                    "--dataset",ds["id"],"--algorithm",name,"--output",str(target)],check=True,cwd=ROOT)
                memory.extend(json.loads(target.read_text())["rows"])
        write_json(output/"memory.json",memory)
        meta["background_load"].append(background_load("nach_speichermessung"))
        if source_hashes()!=hashes:
            raise RuntimeError("Quellcode während Messlauf verändert")
        meta["status"]="complete"
        meta["completed_at_utc"]=datetime.now(timezone.utc).isoformat()
        save()
    except BaseException as error:
        meta["status"]="failed"
        meta["error"]={"type":type(error).__name__,"message":str(error)}
        save()
        write_json(output/"failure.json",{"error":meta["error"],"traceback":traceback.format_exc(),"published_diagrams":False})
        raise
    return {"run_id":meta["run_id"],"raw_rows":len(rows),"batch_rows":len(batches),"total_rows":len(flows),"memory_rows":len(memory)}
