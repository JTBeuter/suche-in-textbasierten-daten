"""Zusätzlicher Indexspeicher; Profiling ist vom Zeitlauf getrennt."""

from __future__ import annotations

from collections.abc import Mapping
import gc
import sys
import tracemalloc

from invertierter_index import build_inverted_index


def exclusive_index_bytes(index: Mapping, prepared) -> int:
    """Objektgraph einmal zählen; im Korpus existierende Strings ausnehmen.

    gc.get_referents erfasst auch das Wörterbuch hinter MappingProxyType.
    Berücksichtigt werden nur Mapping, dict, tuple und str, keine Interpreter-
    Typen/Module oder der vorbereitete Korpus. Kein RSS-/Allocator-Maß.
    """
    shared = {id(document.document_id) for document in prepared}
    shared.update(id(token) for document in prepared for token in document.tokens)
    seen: set[int] = set()

    def visit(value) -> int:
        identity = id(value)
        if identity in seen or identity in shared:
            return 0
        if not isinstance(value, (Mapping, tuple, str)):
            return 0
        seen.add(identity)
        size = sys.getsizeof(value)
        if isinstance(value, str):
            return size
        if isinstance(value, tuple):
            return size + sum(visit(item) for item in value)
        # Mapping proxies expose a backing dictionary through the GC API.
        referents = gc.get_referents(value)
        backing = [item for item in referents if isinstance(item, Mapping)]
        if not isinstance(value, dict) and backing:
            return size + sum(visit(item) for item in backing)
        return size + sum(visit(key) + visit(item) for key, item in value.items())

    return visit(index)


def profile_index(prepared, expected_index: dict, *, repeats: int = 3) -> list[dict]:
    """Drei neue Builds, jeweils Tracerstart erst nach existierender Aufbereitung.

    retained = current_after_build - current_before_build;
    peak = peak_since_reset - current_before_build. Prüfen/Deep-Size erst nach
    Tracerstop; keine dieser instrumentierten Zeiten geht in Laufzeit-CSV ein.
    """
    rows = []
    for repeat in range(repeats):
        gc.collect()
        tracemalloc.start()
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        try:
            index = build_inverted_index(prepared)
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        if dict(index) != expected_index:
            raise AssertionError("Profiling-Build verletzt unabhängige Posting-Erwartung")
        retained, additional_peak = current - before, peak - before
        if retained <= 0 or additional_peak < retained:
            raise AssertionError("nicht plausibler zusätzlicher Tracemalloc-Speicher")
        rows.append({"repeat": repeat, "retained_traced_bytes": retained,
                     "peak_traced_bytes": additional_peak,
                     "exclusive_index_bytes": exclusive_index_bytes(index, prepared)})
        del index
    return rows
