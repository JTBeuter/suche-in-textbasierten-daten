"""Realkorpus BGB: Archiv, Prüfsummen, Umwandlungsregeln und unabhängige Erwartungen.

Die Erwartungswerte im Manifest stammen aus ``daten/real/bgb/berechne_erwartungen.py``
(eigene Tokenisierung ohne Import aus ``gemeinsam``). Hier werden sie gegen die
produktive Aufbereitung und die öffentlichen Such-APIs geprüft. Zusätzlich
tokenisiert eine dritte, kleine Implementierung (``itertools.groupby``) jeden
Paragraphen. Alles läuft ohne Netzwerk.
"""

import hashlib
import importlib.util
import itertools
import json
import re
import sys
import unicodedata
from pathlib import Path

import pytest

from boolesche_suche import search_direct_boolean, search_index_boolean
from direkte_suche import search_direct_substring, search_direct_word
from gemeinsam import load_corpus, normalize_query, prepare_corpus
from invertierter_index import build_inverted_index, search_index_word
from positionsindex import build_positional_index, search_direct_phrase, search_index_phrase

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "daten" / "real" / "bgb"
DOCS = DATA / "dokumente"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _list_hash(values: list[str]) -> str:
    return _sha256("\n".join(values).encode("utf-8"))


def _positions_hash(matches: dict[str, list[int]]) -> str:
    return _list_hash([f"{d}\t{','.join(map(str, s))}" for d, s in sorted(matches.items())])


def _groupby_tokens(text: str) -> list[str]:
    """Dritte, eigenständige Umsetzung der Tokenregel für die Gegenprobe."""
    folded = unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).casefold())

    def is_token_char(char: str) -> bool:
        category = unicodedata.category(char)
        return category in ("Lu", "Ll", "Lt", "Lm", "Lo", "Nd")

    return ["".join(group) for keep, group in itertools.groupby(folded, is_token_char) if keep]


@pytest.fixture(scope="module")
def manifest():
    return json.loads((DATA / "manifest.json").read_bytes().decode("utf-8"))


@pytest.fixture(scope="module")
def suggestions():
    return json.loads((DATA / "anfragevorschlaege.json").read_bytes().decode("utf-8"))


@pytest.fixture(scope="module")
def raw():
    return load_corpus(DOCS)


@pytest.fixture(scope="module")
def corpus(raw):
    return prepare_corpus(raw)


@pytest.fixture(scope="module")
def index(corpus):
    return build_inverted_index(corpus)


@pytest.fixture(scope="module")
def positional(corpus):
    return build_positional_index(corpus)


@pytest.fixture(scope="module")
def converter():
    spec = importlib.util.spec_from_file_location("bgb_erzeuge_korpus", DATA / "erzeuge_korpus.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses benötigen den Moduleintrag
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def test_archive_retrieval_record_and_law_status(manifest):
    archive = (DATA / manifest["source_file"]).read_bytes()
    record = json.loads((DATA / manifest["retrieval_record"]).read_bytes().decode("utf-8"))
    assert manifest["dataset_id"] == "bgb-gesetze-im-internet-v1"
    assert len(archive) == manifest["source_bytes"] == record["bytes"]
    assert _sha256(archive) == manifest["source_sha256"] == record["sha256"]
    assert manifest["retrieved_at"] == record["retrieved_at"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d", manifest["retrieved_at"])
    assert manifest["http_last_modified"] == record["http_headers"]["last-modified"]
    assert manifest["http_etag"] == record["http_headers"].get("etag")
    assert manifest["source_xml"]["xml_is_nfc"] is True
    status = manifest["law_status"]
    assert status["jurabk"] == "BGB" and status["ausfertigung_datum"] == "1896-08-18"
    assert [s["standtyp"] for s in status["standangaben"]] == ["Neuf", "Stand"]
    assert manifest["rights"]["norm_url"] == "https://www.gesetze-im-internet.de/urhg/__5.html"


def test_document_files_match_manifest_checksums(manifest):
    entries = manifest["documents"]
    names = sorted(path.name for path in DOCS.iterdir())
    assert len(entries) == manifest["counts"]["documents"] == len(names) == 2486
    assert [entry["document_id"] for entry in entries] == names
    canonical = ""
    for entry in entries:
        data = (DOCS / entry["document_id"]).read_bytes()
        assert entry["source_path"] == entry["document_id"]
        assert len(data) == entry["bytes"]
        assert _sha256(data) == entry["sha256"]
        canonical += f"{entry['sha256']}  {entry['document_id']}\n"
    assert _sha256(canonical.encode("utf-8")) == manifest["corpus_sha256"]
    assert sum(entry["bytes"] for entry in entries) == manifest["counts"]["raw_bytes"]


def test_file_names_follow_law_order_and_format(manifest):
    names = [entry["document_id"] for entry in manifest["documents"]]
    assert all(a.encode() < b.encode() for a, b in zip(names, names[1:]))
    for entry in manifest["documents"]:
        number, suffix = re.fullmatch(r"§ (\d{1,4})([a-z]*)", entry["paragraph"]).groups()
        assert entry["document_id"] == f"bgb_{int(number):04d}{suffix}.txt"
    assert names[:3] == ["bgb_0001.txt", "bgb_0002.txt", "bgb_0007.txt"]
    assert "bgb_0312.txt" in names and "bgb_0312a.txt" in names
    assert names.index("bgb_0312.txt") < names.index("bgb_0312a.txt") < names.index("bgb_0313.txt")
    assert names[-1] == "bgb_2385.txt"


def test_format_no_footnotes_no_repealed_paragraphs(manifest, raw):
    excluded = manifest["excluded_paragraphs"]
    assert manifest["counts"]["excluded_repealed"] == 39
    assert manifest["counts"]["excluded_without_normtext"] == 1
    assert [e["paragraph"] for e in excluded if e["reason"] == "ohne_normtext"] == ["§ 651"]
    present = {entry["paragraph"] for entry in manifest["documents"]}
    assert not present & {e["paragraph"] for e in excluded}
    assert all(e["title"] == "(weggefallen)" for e in manifest["collective_entries"])
    for document in raw:
        text = document.raw_text
        assert text.endswith("\n") and not text.endswith("\n\n")
        assert "\r" not in text and not text.startswith("\ufeff")
        assert unicodedata.is_normalized("NFC", text)
        lines = text[:-1].split("\n")
        assert all(line and line == " ".join(line.split()) for line in lines)
        assert lines[0] != "(weggefallen)" and lines != ["(weggefallen)"]
        assert "Amtlicher Hinweis" not in text and "+++" not in text
    by_id = {document.document_id: document.raw_text for document in raw}
    assert by_id["bgb_0001.txt"] == (
        "Beginn der Rechtsfähigkeit\n"
        "Die Rechtsfähigkeit des Menschen beginnt mit der Vollendung der Geburt.\n")
    # § 14 hat eine Fußnote (amtlicher Hinweis), die nicht übernommen wird.
    assert "Umsetzung der eingangs" not in by_id["bgb_0014.txt"]
    # Listenpunkte stehen mit Nummer auf eigener Zeile, nichts wird verklebt.
    assert "\n3. die nach den Artikeln 24, 25 und 32" in by_id["bgb_0055a.txt"]


def test_offline_regeneration_is_byte_identical(converter, manifest, tmp_path):
    archive = (DATA / manifest["source_file"]).read_bytes()
    result = converter.wandle_um(archive)
    target = tmp_path / "dokumente"
    converter.schreibe_dokumente(result.dokumente, target)
    regenerated = sorted(path.name for path in target.iterdir())
    assert regenerated == [entry["document_id"] for entry in manifest["documents"]]
    for name in regenerated:
        assert (target / name).read_bytes() == (DOCS / name).read_bytes(), name
    assert [d.paragraph for d in result.dokumente] == [e["paragraph"] for e in manifest["documents"]]
    assert list(result.ausgeschlossen) == manifest["excluded_paragraphs"]
    assert result.zaehlung["documents"] == manifest["counts"]["documents"]


def test_production_tokens_match_independent_tokenization(manifest, raw, corpus, index):
    expected = manifest["independent_expectations"]
    assert expected["corpus_sha256"] == manifest["corpus_sha256"]
    assert [d.document_id for d in corpus] == [e["document_id"] for e in manifest["documents"]]
    for document in corpus:
        assert list(document.tokens) == _groupby_tokens(document.raw_text), document.document_id
    assert len(corpus) == expected["document_count"] == 2486
    assert sum(len(d.tokens) for d in corpus) == expected["token_count"]
    assert len(index) == expected["vocabulary_size"]
    assert sum(len(index[term]) for term in index) == expected["posting_count"]
    assert list(corpus[0].tokens[:20]) == expected["prefix_tokens_bgb_0001"]
    assert expected["secondary_check"]["documents_with_difference"] == 0
    bands = {"df > 1000": 0, "df 100-1000": 0, "df 10-99": 0, "df 2-9": 0, "df 1": 0}
    for term in index:
        df = len(index[term])
        bands["df > 1000" if df > 1000 else "df 100-1000" if df >= 100 else
              "df 10-99" if df >= 10 else "df 2-9" if df >= 2 else "df 1"] += 1
    assert bands == expected["df_distribution"]
    comparison = manifest["production_comparison"]
    assert comparison["corpus_sha256"] == manifest["corpus_sha256"]
    assert comparison["all_equal"] is True and comparison["failed_checks"] == []


def _assert_ids(entry: dict, result: list[str]) -> None:
    if "document_ids" in entry:
        assert result == entry["document_ids"], entry["query"]
    else:
        assert len(result) == entry["document_ids_count"], entry["query"]
        assert _list_hash(result) == entry["document_ids_sha256"], entry["query"]
        assert result[:5] == entry["document_ids_first5"]


def test_word_expectations_direct_and_index(manifest, corpus, index, positional):
    for entry in manifest["independent_expectations"]["words"]:
        assert normalize_query(entry["query"]) == (entry["term"],)
        direct = search_direct_word(corpus, entry["query"])
        assert direct == search_index_word(index, entry["query"])
        assert len(direct) == entry["df"]
        _assert_ids(entry, direct)
        postings = positional.get(entry["term"], {})
        assert sum(len(p) for p in postings.values()) == entry["cf"]
        if direct:
            assert postings[entry["first_document"]][0] == entry["first_position"]
            assert direct[-1] == entry["last_document"]
    words = {e["query"]: e for e in manifest["independent_expectations"]["words"]}
    assert words["Maßgabe"]["df"] == words["MASSGABE"]["df"] == 80
    assert words["Server"]["df"] == words["Unauffindbar"]["df"] == 0
    assert words["Erbschaftskauf"]["document_ids"] == ["bgb_2385.txt"]


def _assert_phrase(entry: dict, result: dict[str, list[int]]) -> None:
    assert len(result) == entry["document_count"], entry["query"]
    assert sum(map(len, result.values())) == entry["match_count"], entry["query"]
    assert _positions_hash(result) == entry["positions_sha256"], entry["query"]
    if "positions" in entry:
        assert result == entry["positions"], entry["query"]


def test_phrase_expectations_direct_and_index(manifest, suggestions, corpus, positional):
    # Direkter Scan nur für die Manifestphrasen (Laufzeit), Positionsindex für alle.
    for entry in manifest["independent_expectations"]["phrases"]:
        terms = normalize_query(entry["query"], "phrase")
        assert list(terms) == entry["terms"]
        _assert_phrase(entry, search_direct_phrase(corpus, terms))
        _assert_phrase(entry, search_index_phrase(positional, terms))
    for entry in suggestions["reihe_04_phrasensuche"] + [
            e for e in suggestions["reihe_05_profile"] if "positions_sha256" in e]:
        terms = normalize_query(entry["query"], "phrase")
        assert list(terms) == entry["terms"]
        _assert_phrase(entry, search_index_phrase(positional, terms))
    by_query = {e["query"]: e for e in manifest["independent_expectations"]["phrases"]}
    assert by_query["Beginn der Rechtsfähigkeit"]["positions"] == {"bgb_0001.txt": [0]}
    assert by_query["Maßgabe nach"]["document_count"] == 0


def test_boolean_and_profile_suggestions(suggestions, corpus, index):
    entries = suggestions["reihe_03_boolesche_suche"] + [
        e for e in suggestions["reihe_05_profile"] if e.get("kind") in ("and", "or")]
    for entry in entries:
        operator = "OR" if entry["kind"] == "or" else "AND"
        results = [search_direct_boolean(corpus, entry["query"], operator),
                   search_index_boolean(index, entry["query"], operator)]
        if operator == "AND":
            results.append(search_index_boolean(index, entry["query"], operator, "shortest_first"))
        for result in results:
            if entry["kind"] == "and_not":
                excluded = set(search_index_word(index, entry["exclude"]))
                result = [d for d in result if d not in excluded]
            assert len(result) == entry["hit_count"], entry["query"]
            _assert_ids(entry, result)


def test_series_01_02_suggestions(suggestions, raw, corpus):
    for entry in suggestions["reihe_01_direkte_suche"]:
        hits = search_direct_word(corpus, entry["query"])
        _assert_ids(entry, hits)
        scanned = 0
        for document in corpus:
            tokens = document.tokens
            scanned += tokens.index(entry["term"]) + 1 if entry["term"] in tokens else len(tokens)
        assert scanned == entry["scanned_tokens_direct"]
        if entry["query"] in ("Vertrag", "Fehler", "Server"):  # Auswahl wegen Laufzeit
            assert len(search_direct_substring(raw, entry["query"])) == entry["substring_hit_count"]
    for entry in suggestions["reihe_02_index_teilmengen"]:
        subset = corpus[:entry["D"]]
        sub_index = build_inverted_index(subset)
        assert subset[-1].document_id == entry["last_document_id"]
        assert sum(len(d.tokens) for d in subset) == entry["N"]
        assert len(sub_index) == entry["V"]
        assert sum(len(sub_index[t]) for t in sub_index) == entry["P"]
