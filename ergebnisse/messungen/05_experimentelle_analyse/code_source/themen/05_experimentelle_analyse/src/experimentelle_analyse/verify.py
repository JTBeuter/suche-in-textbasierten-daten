"""Rohwertaudit: keine stillen Ausschlüsse, vollständige Zuordnung und Orakel."""
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory

from gemeinsam import load_corpus, prepare_corpus
from gemeinsam.messung import CSV_FIELDS
from .datasets import build_datasets
from .operations import BUILDERS, result_hash, search_operation, validate_result, variants
from .pipeline import q_grid, select_profiles
from .provenance import sha_file, source_hashes
from .schema import BATCH_FIELDS, FLOW_FIELDS, check_derived, integer, read_csv, validate_config


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_rows(meta, rows, batches, totals, memory, checks):
    """Auch auf kleinen handberechenbaren Rohdaten ohne Timer ausführbar."""
    config=validate_config(meta["config"])
    require(meta.get("status")=="complete","Messlauf ist nicht vollständig korrekt abgeschlossen")
    datasets={d["id"]:d for d in meta["datasets"]}
    require(len(datasets)==len(meta["datasets"])==len(config["datasets"]),"Datensätze inkonsistent")
    require({k:d["kind"] for k,d in datasets.items()}=={d["id"]:d["kind"] for d in config["datasets"]},"Konfiguration/Datensatzzuordnung inkonsistent")
    query_lookup={d["id"]:{q["id"]:q for q in d["queries"]} for d in datasets.values()}
    expected=set()
    for ds in datasets.values():
        require(len(query_lookup[ds["id"]])==len(ds["queries"]),"Doppelte Query-ID")
        for p in ds["profiles"]:
            qs=p.get("q_values")
            require(isinstance(qs,list) and bool(qs) and all(type(q) is int and q>=0 for q in qs) and qs==sorted(set(qs)),"Ungültiger Q-Bereich")
            require(set(config["q_values"])<=set(qs),"Feste Q-Stützstellen fehlen")
        for phase,algorithm in (("load","common"),("preparation","common"),("build","inverted_index"),("build","positional_index")):
            expected.add((ds["id"],algorithm,phase,""))
        for q in ds["queries"]:
            for a in variants(q["kind"]):
                expected.add((ds["id"],a,"query",q["id"]))
    groups=defaultdict(list)
    for r in rows:
        ds=datasets.get(r["dataset_id"])
        require(ds is not None,"Unbekannte Datensatzzuordnung")
        require(r["run_id"]==meta["run_id"] and r["git_commit"]==meta["environment"]["git_commit"],"Run/Git-Zuordnung inkonsistent")
        for field in ("document_count","token_count","text_bytes"):
            require(integer(r[field],field)==ds[field],"Datensatzumfang inkonsistent")
        require(integer(r["seed"],"seed")==config["seed"],"Falscher Reihenfolgen-Seed")
        phase=r["phase"]
        require(phase in ("load","preparation","build","query"),"Ungültige Messphase")
        elapsed=integer(r["elapsed_ns"],"elapsed_ns",1)
        count=integer(r["block_size"],"block_size",1)
        require(count==(config["block_size"] if phase=="query" else 1),"Falsche Blockgröße")
        require(r["correct"]=="True","Nicht korrektheitsgesicherter Rohwert")
        check_derived(r[phase+"_ms"],elapsed/1e6/count,phase+"_ms")
        for p in ("load","preparation","build","query"):
            if p!=phase:
                require(r[p+"_ms"]=="","Nicht zutreffende Zeitfelder müssen leer sein")
        require(r["index_bytes"]==r["peak_memory_bytes"]=="","Profilingwerte im Zeitlauf unzulässig")
        key=(ds["id"],r["algorithm"],phase,r["query_id"])
        require(key in expected,"Falsche Query-/Algorithmuszuordnung")
        if phase=="query":
            q=query_lookup[ds["id"]][r["query_id"]]
            require(r["query_text"]==q["text"] and r["query_type"]==q["kind"],"Querytext/Suchart inkonsistent")
            require(integer(r["hit_count"],"hit_count")==q["hit_count"],"Falsche Ergebnisgröße")
        else:
            require(all(r[k]=="" for k in ("query_id","query_type","query_text","hit_count")),"Queryfelder in Aufbauphase")
        integer(r["order_index"],"order_index")
        groups[key].append(integer(r["repeat"],"repeat"))
    require(set(groups)==expected,"Fehlende Rohwertgruppen")
    for repeats in groups.values():
        require(sorted(repeats)==list(range(config["repeats"])),"Fehlende/doppelte/unzulässige Wiederholung")
    # Plan tatsächlich aufgezeichneter Reihenfolgen rekonstruieren.
    for ds in datasets.values():
        rng=random.Random(config["seed"])
        phases=[("load","common"),("preparation","common"),("build","inverted_index"),("build","positional_index")]
        tasks=[(q["id"],a) for q in ds["queries"] for a in variants(q["kind"])]
        own=[r for r in rows if r["dataset_id"]==ds["id"]]
        for repeat in range(-config["warmups"],config["repeats"]):
            order=list(phases);rng.shuffle(order)
            if repeat>=0:
                observed=sorted((r for r in own if r["phase"]!="query" and int(r["repeat"])==repeat),key=lambda r:int(r["order_index"]))
                require([int(r["order_index"]) for r in observed]==list(range(len(order))),"Ordnungsindexfolge inkonsistent")
                require([(r["phase"],r["algorithm"]) for r in observed]==order,"Aufbau-Reihenfolge inkonsistent")
            order=list(tasks);rng.shuffle(order)
            if repeat>=0:
                observed=sorted((r for r in own if r["phase"]=="query" and int(r["repeat"])==repeat),key=lambda r:int(r["order_index"]))
                require([int(r["order_index"]) for r in observed]==list(range(len(order))),"Ordnungsindexfolge inkonsistent")
                require([(r["query_id"],r["algorithm"]) for r in observed]==order,"Query-Reihenfolge inkonsistent")
        for profile in ds["profiles"]:
            for repeat in range(-config["warmups"],config["repeats"]):
                order=["direct",profile["algorithm"]];rng.shuffle(order)
                if repeat>=0:
                    observed=sorted((r for r in batches if r["dataset_id"]==ds["id"] and r["profile_id"]==profile["id"] and int(r["repeat"])==repeat),key=lambda r:int(r["order_index"]))
                    require([int(r["order_index"]) for r in observed]==list(range(len(order))),"Ordnungsindexfolge inkonsistent")
                    require([r["algorithm"] for r in observed]==order,"Profilblock-Reihenfolge inkonsistent")
        for profile in ds["profiles"]:
            tasks=[(q,a) for q in profile["q_values"] for a in ("direct",profile["algorithm"])]
            for repeat in range(-1,config.get("total_repeats",5)):
                order=list(tasks);rng.shuffle(order)
                if repeat>=0:
                    observed=sorted((r for r in totals if r["dataset_id"]==ds["id"] and r["profile_id"]==profile["id"] and int(r["repeat"])==repeat),key=lambda r:int(r["order_index"]))
                    require([int(r["order_index"]) for r in observed]==list(range(len(order))),"Ordnungsindexfolge inkonsistent")
                    require([(int(r["query_count"]),r["algorithm"]) for r in observed]==order,"Gesamtfolge-Reihenfolge inkonsistent")
    for data,is_total in ((batches,False),(totals,True)):
        expected_flow=set()
        for ds in datasets.values():
            for p in ds["profiles"]:
                qs=p["q_values"] if is_total else [config.get("sequence_block_size",50)]
                for q in qs:
                    for a in ("direct",p["algorithm"]):
                        expected_flow.add((ds["id"],p["id"],a,q))
        grouped=defaultdict(list)
        for r in data:
            key=(r["dataset_id"],r["profile_id"],r["algorithm"],integer(r["query_count"],"query_count"))
            require(key in expected_flow,"Ungültige Profilfolgezuordnung")
            require(r["run_id"]==meta["run_id"] and r["unit"]=="ns" and r["correct"]=="True","Profilfolge: falsche Einheit/Status")
            elapsed=integer(r["elapsed_ns"],"elapsed_ns",1)
            integer(r["order_index"],"order_index")
            if is_total:
                ds=datasets[key[0]]
                p=next(p for p in ds["profiles"] if p["id"]==key[1])
                q=query_lookup[ds["id"]][p["query_id"]]
                require(r["result_digest"]==result_hash(q["expected"]),"Profilfolge: Ergebnishash inkonsistent")
            else:
                check_derived(r["ns_per_query"],elapsed/key[3],"ns_per_query")
            grouped[key].append(integer(r["repeat"],"repeat"))
        require(set(grouped)==expected_flow,"Fehlende Profilfolgen")
        n=config.get("total_repeats",5) if is_total else config["repeats"]
        require(all(sorted(v)==list(range(n)) for v in grouped.values()),"Falsche Profilwiederholungen")
    check_map={(c["dataset_id"],c["query_id"],c["algorithm"]):c for c in checks}
    require(len(check_map)==len(checks)==sum(len(variants(q["kind"])) for d in datasets.values() for q in d["queries"]),"Korrektheitsledger unvollständig")
    for ds in datasets.values():
        for q in ds["queries"]:
            for a in variants(q["kind"]):
                c=check_map.get((ds["id"],q["id"],a))
                require(c is not None and c["result_sha256"]==result_hash(q["expected"]),"Korrektheitsnachweis inkonsistent")
                require(c["hit_count"]==q["hit_count"] and c["position_count"]==q["position_count"],"Korrektheitsgrößen inkonsistent")
                require(c["validated_calls"]==1+config["block_size"]*(config["repeats"]+config["warmups"]),"Validierungsanzahl inkonsistent")
    memory_groups=defaultdict(list)
    for r in memory:
        require(r["run_id"]==meta["run_id"] and r["unit"]=="bytes","Falsche Speichereinheit/Run")
        key=(r["dataset_id"],r["algorithm"])
        require(key[0] in datasets and key[1] in BUILDERS,"Falsche Speicherzuordnung")
        held=integer(r["retained_traced_bytes"],"retained",1)
        peak=integer(r["peak_traced_bytes"],"peak",held)
        require(integer(r["transient_peak_bytes"],"transient")==peak-held,"Peaküberhang inkonsistent")
        integer(r["worker_pid"],"worker_pid",1)
        memory_groups[key].append(integer(r["repeat"],"repeat"))
    require(set(memory_groups)=={(d,a) for d in datasets for a in BUILDERS},"Fehlende Indexspeichermessung")
    require(all(sorted(v)==list(range(config["memory_repeats"])) for v in memory_groups.values()),"Speicherwiederholungen inkonsistent")

    pilot=None
    if meta["config"].get("pilot_directory"):
        from .provenance import ROOT
        pilot=json.loads((ROOT/meta["config"]["pilot_directory"]/"metadata.json").read_text())
        require(pilot["status"]=="complete" and pilot["run_id"]==meta["pilot_run_id"],"Pilotzuordnung ungültig")
    for ds in meta["datasets"]:
        for p in ds["profiles"]:
            own=[{**r,"elapsed_ns":int(r["elapsed_ns"]),"query_count":int(r["query_count"])} for r in batches if r["dataset_id"]==ds["id"] and r["profile_id"]==p["id"]]
            kind=next(q["kind"] for q in ds["queries"] if q["id"]==p["query_id"])
            name="positional_index" if kind=="phrase" else "inverted_index"
            build=[{**r,"elapsed_ns":int(r["elapsed_ns"])} for r in rows if r["dataset_id"]==ds["id"] and r["phase"]=="build" and r["algorithm"]==name]
            grid,model=q_grid(p,own,build,meta["config"])
            require(model==p["calibration_model"],"Kalibrierungsmodell widerspricht Rohwerten")
            if pilot:
                prior=next(d for d in pilot["datasets"] if d["id"]==ds["id"])
                grid=next(profile["q_values"] for profile in prior["profiles"] if profile["id"]==p["id"])
            require(grid==p["q_values"],"Kalibrierungsregel/Q-Auswahl inkonsistent")


def _verify_run(directory):
    directory=Path(directory)
    meta=json.loads((directory/"metadata.json").read_text())
    require(meta.get("schema_version")==1,"Metadatenschema unzulässig")
    rows=read_csv(directory/"raw.csv",CSV_FIELDS)
    batches=read_csv(directory/"batches.csv",BATCH_FIELDS)
    totals=read_csv(directory/"totals.csv",FLOW_FIELDS)
    memory=json.loads((directory/"memory.json").read_text())
    checks=json.loads((directory/"correctness.json").read_text())
    verify_rows(meta,rows,batches,totals,memory,checks)
    require(meta["code_sha256"]==source_hashes(),"Aktiver Quellcode weicht von Messfassung ab")
    for name,digest in meta["code_sha256"].items():
        require(sha_file(directory/"code_source"/name)==digest,"Quellarchiv beschädigt")
    with TemporaryDirectory(prefix="textsuche-05-verify-") as temporary:
        reproduced=build_datasets(meta["config"],Path(temporary))
        for ds in reproduced:
            stored=next(d for d in meta["datasets"] if d["id"]==ds["id"])
            require(ds["manifest"]==stored["manifest"] and ds["queries"]==stored["queries"],"Generator/Query-Reproduktion abweichend")
            require(json.loads((directory/"datasets"/ds["id"]/"manifest.json").read_text())==ds["manifest"],"Gespeichertes Manifest inkonsistent")
            qpath=directory/"datasets"/ds["id"]/"queries.json"
            require(sha_file(qpath)==ds["manifest"]["queries_sha256"],"Querydatei beschädigt")
            root=directory/stored["root"]
            corpus=prepare_corpus(load_corpus(root))
            require({d.document_id:list(d.tokens) for d in corpus}==stored["manifest"]["expected_tokens"],"Tokenplan/Korpus inkonsistent")
            for f in ds["manifest"]["files"]:
                require(sha_file(root/f["document_id"])==f["sha256"],"Korpusdatei beschädigt")
            for q in ds["queries"]:
                idx=BUILDERS["positional_index" if q["kind"]=="phrase" else "inverted_index"](corpus)
                for a in variants(q["kind"]):
                    validate_result(search_operation(corpus,idx,q,a),q,corpus)
            require([{k:p[k] for k in ("id","query_id","algorithm")} for p in stored["profiles"]]==select_profiles(ds["queries"]),"Abfragemodell wechselt Query")
    end=datetime.fromisoformat(meta["timing_completed_at_utc"])
    processes=[]
    all_memory=[]
    for ds in meta["datasets"]:
        for a in BUILDERS:
            worker=json.loads((directory/f"memory_{ds['id']}_{a}.json").read_text())
            start=datetime.fromisoformat(worker["started_at_utc"])
            finish=datetime.fromisoformat(worker["completed_at_utc"])
            require(start>=end and finish>=start,"Profiling und Zeitmessung überlappen")
            require(worker["dataset_id"]==ds["id"] and worker["algorithm"]==a and worker["code_sha256"]==meta["code_sha256"],"Profilingprozess inkonsistent")
            require(all(r["worker_pid"]==worker["worker_pid"] for r in worker["rows"]),"Prozesszuordnung inkonsistent")
            processes.append((start,finish))
            all_memory.extend(worker["rows"])
    require(all_memory==memory,"Speicherzusammenfassung inkonsistent")
    require(all(processes[i][1]<=processes[i+1][0] for i in range(len(processes)-1)),"Speicherprozesse überlappen")
    return {"status":"verified","raw_rows":len(rows),"batch_rows":len(batches),"total_rows":len(totals),"memory_rows":len(memory)}


def verify_run(directory):
    try:
        return _verify_run(directory)
    except (KeyError, TypeError, StopIteration) as error:
        raise ValueError(f"Beschädigte Messmetadaten oder fehlende Zuordnung: {error}") from error
