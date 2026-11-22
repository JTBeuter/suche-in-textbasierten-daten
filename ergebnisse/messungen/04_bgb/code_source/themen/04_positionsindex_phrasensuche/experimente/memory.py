#!/usr/bin/env python3
"""Ein Profilingprozess erzeugt genau eine Indexart auf genau einem Korpus."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import tracemalloc

from invertierter_index import build_inverted_index
from positionsindex import build_positional_index


def profile_index(prepared, expected, *, algorithm, repeats=3):
    if algorithm not in ("inverted_index", "positional_index"):
        raise ValueError("unknown index algorithm")
    if tracemalloc.is_tracing():
        raise RuntimeError("profiling requires inactive tracer")
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
        raise ValueError("positive repeat count required")
    builder = build_inverted_index if algorithm == "inverted_index" else build_positional_index
    rows = []
    for repeat in range(repeats):
        gc.collect()
        tracemalloc.start()
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        try:
            index = builder(prepared)
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        observed = dict(index) if algorithm == "inverted_index" else {token: dict(docs) for token, docs in index.items()}
        assert observed == expected, "profiling build violates independent oracle"
        retained, additional_peak = current - before, peak - before
        assert retained > 0 and additional_peak >= retained
        rows.append({"repeat": repeat, "worker_pid": os.getpid(), "retained_traced_bytes": retained,
                     "peak_traced_bytes": additional_peak, "transient_peak_bytes": additional_peak - retained})
        del index, observed
    return rows


def series_source(info):
    """Datenquelle des Laufs: gelieferte Reihe 04 oder BGB-Realteil (Metadatenfeld series)."""
    # Import orchestration only after module definitions; it does not create an index.
    if __package__:
        from . import run, run_bgb
    else:
        import run
        import run_bgb
    return run_bgb if info.get("series") == run_bgb.SERIES else run


def worker(metadata_path, dataset_id, algorithm, output):
    info = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    source = series_source(info)
    PARAMETERS, write_json = source.PARAMETERS, source.write_json
    assert info["parameters"] == PARAMETERS and info["code_sha256"] == source.code_hashes()
    expected_dataset = next(item for item in info["datasets"] if item["dataset_id"] == dataset_id)
    started = datetime.now(timezone.utc).isoformat()
    with TemporaryDirectory(prefix="textsuche-04-memory-") as temporary:
        for identifier, directory, tokens, queries, extra in source.datasets(temporary):
            if identifier != dataset_id:
                continue
            prepared, postings, positions, dataset = source.describe_dataset(identifier, directory, tokens, queries, extra)
            assert dataset == expected_dataset, "memory and time corpus mismatch"
            expected = postings if algorithm == "inverted_index" else positions
            if algorithm == "inverted_index":
                del positions
            else:
                del postings
            profiles = profile_index(prepared, expected, algorithm=algorithm, repeats=PARAMETERS["memory_repeats"])
            rows = [{"run_id": info["run_id"], "dataset_id": identifier, "algorithm": algorithm,
                     **{field: dataset[field] for field in ("document_count", "token_count", "vocabulary_size", "posting_count")},
                     **profile} for profile in profiles]
            break
        else:
            raise ValueError("unknown dataset")
    assert info["code_sha256"] == source.code_hashes()
    write_json(output, {"dataset_id": dataset_id, "algorithm": algorithm, "worker_pid": os.getpid(),
        "started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_sha256": info["code_sha256"], "rows": rows})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--algorithm", required=True, choices=("inverted_index", "positional_index"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    worker(args.metadata, args.dataset, args.algorithm, args.output)


if __name__ == "__main__":
    main()
