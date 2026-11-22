"""Isolierte Indexallokationen auf bereits vorbereitetem Korpus."""
import argparse
from datetime import datetime, timezone
import gc
import json
import os
from pathlib import Path
import tracemalloc

from gemeinsam import load_corpus, prepare_corpus
from .operations import BUILDERS, index_oracle, validate_index
from .provenance import source_hashes, write_json


def worker(metadata_path, dataset_id, algorithm, output):
    path=Path(metadata_path)
    meta=json.loads(path.read_text())
    if algorithm not in BUILDERS or source_hashes()!=meta["code_sha256"]:
        raise ValueError("Speicherprozess: Algorithmus/Quellfassung inkonsistent")
    ds=next(d for d in meta["datasets"] if d["id"]==dataset_id)
    manifest=ds["manifest"]
    expected={doc:tuple(tokens) for doc,tokens in manifest["expected_tokens"].items()}
    corpus=prepare_corpus(load_corpus(path.parent/ds["root"]))
    if {d.document_id:d.tokens for d in corpus}!=expected:
        raise AssertionError("Profilingdaten stimmen nicht mit Tokenplan überein")
    oracle=index_oracle(expected,algorithm=="positional_index")
    rows=[]
    started=datetime.now(timezone.utc).isoformat()
    for repeat in range(meta["config"]["memory_repeats"]):
        gc.collect()
        tracemalloc.start()
        before,_=tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        try:
            index=BUILDERS[algorithm](corpus)
            current,peak=tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        validate_index(index,oracle,algorithm=="positional_index")
        retained=current-before
        extra_peak=peak-before
        if retained<=0 or extra_peak<retained:
            raise AssertionError("Unzulässige Tracerwerte")
        rows.append({"run_id":meta["run_id"],"dataset_id":dataset_id,"algorithm":algorithm,"repeat":repeat,
            "worker_pid":os.getpid(),"retained_traced_bytes":retained,"peak_traced_bytes":extra_peak,
            "transient_peak_bytes":extra_peak-retained,"unit":"bytes"})
        del index
    write_json(output,{"dataset_id":dataset_id,"algorithm":algorithm,"worker_pid":os.getpid(),
        "started_at_utc":started,"completed_at_utc":datetime.now(timezone.utc).isoformat(),
        "code_sha256":source_hashes(),"rows":rows})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--metadata",required=True)
    parser.add_argument("--dataset",required=True)
    parser.add_argument("--algorithm",choices=tuple(BUILDERS),required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    worker(args.metadata,args.dataset,args.algorithm,args.output)


if __name__=="__main__":
    main()
