"""Pinned real prose: archive, exact extraction and fixed independent expectations."""

import hashlib
import json
from pathlib import Path

from gemeinsam import load_corpus, prepare_corpus
from direkte_suche import search_direct_word

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "daten" / "real" / "kafka_verwandlung"


def test_archived_source_and_exact_excerpt():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    archive = (DATA / manifest["source_file"]).read_bytes()
    assert len(archive) == manifest["source_bytes"] == 145983
    assert hashlib.sha256(archive).hexdigest() == manifest["source_sha256"]
    source = archive.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    selection = manifest["selection"]
    assert source.count(selection["start_inclusive"]) == 1
    assert source.count(selection["end_exclusive"]) == 1
    start = source.index(selection["start_inclusive"])
    end = source.index(selection["end_exclusive"], start)
    expected = (source[start:end].strip() + "\n").encode("utf-8")
    entry = manifest["documents"][0]
    actual = (DATA / entry["source_path"]).read_bytes()
    assert actual == expected
    assert len(actual) == entry["bytes"] == 8495
    assert hashlib.sha256(actual).hexdigest() == entry["sha256"]
    assert len(actual.decode("utf-8").strip().split("\n\n")) == 8


def test_real_preparation_and_manually_fixed_positions():
    raw = load_corpus(DATA)
    assert len(raw) == 1
    prepared = prepare_corpus(raw)
    doc = prepared[0]
    assert doc.document_id == doc.source_path == "01_anfang.txt"
    assert doc.raw_text == raw[0].raw_text
    assert len(doc.tokens) == 1271
    assert doc.tokens[:20] == (
        "als", "gregor", "samsa", "eines", "morgens", "aus", "unruhigen",
        "träumen", "erwachte", "fand", "er", "sich", "in", "seinem", "bett",
        "zu", "einem", "ungeheueren", "ungeziefer", "verwandelt",
    )
    expectations = {
        "Gregor": [1, 785, 845, 901, 919, 976, 1039, 1060, 1061, 1078, 1079, 1089, 1102, 1141, 1147],
        "Fenster": [172],
        "Unauffindbar": [],
    }
    for query, positions in expectations.items():
        actual = [i for i, token in enumerate(doc.tokens) if token == query.lower()]
        assert actual == positions
        assert search_direct_word(prepared, query) == (["01_anfang.txt"] if positions else [])
