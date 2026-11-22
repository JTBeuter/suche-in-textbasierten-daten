"""Gemeinsame Messgrenzen und CSV-Schema für Themen 01 bis 05.

Abfragen schließen das Erzeugen der vollständigen Trefferliste ein.
Korrektheitsprüfungen und Dateiausgabe liegen außerhalb der Zeitintervalle.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import csv
from pathlib import Path
import random
from statistics import median, quantiles
from time import perf_counter_ns
from typing import Any


CSV_FIELDS = (
    "run_id", "git_commit", "seed", "dataset_id", "document_count", "text_bytes",
    "token_count", "algorithm", "phase", "query_id", "query_type", "query_text",
    "repeat", "order_index", "block_size", "elapsed_ns", "load_ms",
    "preparation_ms", "build_ms", "query_ms", "index_bytes", "peak_memory_bytes",
    "hit_count", "correct",
)


@dataclass(frozen=True)
class MeasurementPlan:
    warmups: int = 5
    repeats: int = 20
    query_block_size: int = 10
    seed: int = 20261006

    def __post_init__(self) -> None:
        for name in ("warmups", "repeats", "query_block_size"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} muss eine ganze Zahl sein")
        if self.warmups < 0 or self.repeats < 2 or self.query_block_size < 1:
            raise ValueError("warmups >= 0, repeats >= 2 und query_block_size >= 1 erforderlich")


@dataclass(frozen=True)
class QuerySpec:
    query_id: str
    text: str
    query_type: str
    expected_ids: tuple[str, ...]


def _checked_block(
    operation: Callable[[], Any],
    validate: Callable[[Any], None],
    block_size: int,
) -> int:
    start = perf_counter_ns()
    results = [operation() for _ in range(block_size)]
    elapsed = perf_counter_ns() - start
    for result in results:
        validate(result)
    return elapsed


def measure_phase(
    operation: Callable[[], Any],
    validate: Callable[[Any], None],
    plan: MeasurementPlan,
    *,
    phase: str,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Zeitmessung eines ganzen Lade-, Aufbereitungs- oder Aufbauschritts."""
    if phase not in {"load", "preparation", "build"}:
        raise ValueError("phase muss load, preparation oder build sein")
    for _ in range(plan.warmups):
        _checked_block(operation, validate, 1)
    rows = []
    for repeat in range(plan.repeats):
        elapsed = _checked_block(operation, validate, 1)
        rows.append({
            **context, "phase": phase, "repeat": repeat, "block_size": 1,
            "elapsed_ns": elapsed, f"{phase}_ms": elapsed / 1_000_000,
            "correct": True,
        })
    return rows


def measure_queries(
    search: Callable[[str], list[str]],
    queries: Sequence[QuerySpec],
    plan: MeasurementPlan,
    *,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Messe alle Anfragen in pro Wiederholung deterministisch gemischter Folge.

    search ist die öffentliche Abfragefunktion: Anfrageaufbereitung gehört
    deshalb zum Intervall. Ein Block enthält query_block_size gleiche Anfragen;
    query_ms enthält die Blockzeit geteilt durch die Anzahl der Anfragen.
    """
    if len({query.query_id for query in queries}) != len(queries):
        raise ValueError("query_id muss eindeutig sein")
    rng = random.Random(plan.seed)
    rows = []
    for iteration in range(-plan.warmups, plan.repeats):
        order = list(queries)
        rng.shuffle(order)
        for order_index, query in enumerate(order):
            expected = list(query.expected_ids)

            def validate(result: Any) -> None:
                if result != expected:
                    raise AssertionError(
                        f"{query.query_id}: erwartet {expected!r}, erhalten {result!r}"
                    )

            elapsed = _checked_block(
                lambda: search(query.text), validate, plan.query_block_size,
            )
            if iteration >= 0:
                rows.append({
                    **context, "phase": "query", "query_id": query.query_id,
                    "query_type": query.query_type, "query_text": query.text,
                    "repeat": iteration, "order_index": order_index,
                    "block_size": plan.query_block_size, "elapsed_ns": elapsed,
                    "query_ms": elapsed / 1_000_000 / plan.query_block_size,
                    "hit_count": len(expected), "correct": True,
                })
    return rows


def write_measurements(path: str | Path, rows: Sequence[dict[str, Any]]) -> None:
    """Nicht zutreffende Felder bleiben leer, insbesondere Index-/Speicherwerte."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def summarize_measurements(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Median und inklusive Quartile (statistics.quantiles, method='inclusive')."""
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["dataset_id"], row["algorithm"], row["phase"], row.get("query_id", ""))
        groups.setdefault(key, []).append(row)
    summary = []
    for key, values in sorted(groups.items()):
        phase = key[2]
        numbers = [float(row[f"{phase}_ms"]) for row in values]
        if len(numbers) < 2:
            raise ValueError("mindestens zwei Messungen pro Gruppe erforderlich")
        q1, _, q3 = quantiles(numbers, n=4, method="inclusive")
        summary.append({
            "dataset_id": key[0], "algorithm": key[1], "phase": phase,
            "query_id": key[3], "query_type": values[0].get("query_type", ""),
            "token_count": values[0]["token_count"], "sample_count": len(values),
            "median_ms": median(numbers), "q1_ms": q1, "q3_ms": q3,
            "iqr_ms": q3 - q1, "minimum_ms": min(numbers), "maximum_ms": max(numbers),
        })
    return summary
