"""Reihe 02, BGB-Realteil: Erwartungen, Ausgabeschutz, Pilotsperre und Prüfung."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
import types

import pytest


EXPERIMENTS = Path(__file__).resolve().parents[1]
ROOT = EXPERIMENTS.parents[2]


@pytest.fixture(scope="module")
def module():
    label = "experiment02_bgb_lauf_test"
    spec = importlib.util.spec_from_file_location(label, EXPERIMENTS / "bgb_lauf.py")
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[label] = loaded
    spec.loader.exec_module(loaded)
    yield loaded
    sys.modules.pop(label, None)


@pytest.fixture(scope="module")
def reference(module):
    return module.bgb_reference()


def _tree_sha(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob("*")) if path.is_file()}


def test_series02_helpers_are_loaded_from_series02_files(module, monkeypatch):
    # Ein fremdes generator/memory-Modul im Cache darf run.py der Reihe 02 nicht beeinflussen.
    foreign = types.ModuleType("generator")
    monkeypatch.setitem(sys.modules, "generator", foreign)
    for name in ("experiment02_bgb_generator", "experiment02_bgb_memory", "experiment02_bgb_run"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    run02, memory02 = module._load_series02()
    assert Path(run02.__file__) == EXPERIMENTS / "run.py" and Path(memory02.__file__) == EXPERIMENTS / "memory.py"
    assert Path(sys.modules[run02.generate_corpus.__module__].__file__) == EXPERIMENTS / "generator.py"
    assert sys.modules["generator"] is foreign
    assert module.MEMORY_FIELDS == run02.MEMORY_FIELDS


def test_reference_matches_manifest_and_proposals(module, reference):
    source = reference["source"]
    assert (source["document_count"], source["token_count"], source["vocabulary_size"], source["posting_count"]) == (
        2486, 213718, 11398, 133909)
    assert [(subset["document_count"], subset["token_count"], subset["vocabulary_size"], subset["posting_count"])
            for subset in reference["subsets"]] == [
        (250, 16899, 2577, 11077), (500, 44221, 4699, 26529), (1000, 103733, 7750, 61468),
        (1500, 135600, 8975, 83782), (2000, 183132, 10595, 112759), (2486, 213718, 11398, 133909)]
    queries = {query["query_id"]: query for query in reference["queries"]}
    assert {key: (value["document_frequency"], value["occurrences"]) for key, value in queries.items()} == {
        "beginn": (52, 63), "der": (2280, 11486), "erbschaftskauf": (1, 1), "server": (0, 0),
        "fehler": (5, 10), "verbindung": (16, 21), "unauffindbar": (0, 0)}
    assert queries["erbschaftskauf"]["expected_ids"] == ["bgb_2385.txt"]
    assert queries["erbschaftskauf"]["first_position"] == 9
    assert queries["der"]["direct_visited_tokens"] == 37889
    assert queries["server"]["direct_visited_tokens"] == 213718
    assert reference["ranks"][0] == {"rank": 1, "term": "der", "cf": 11486, "df": 2280}
    # Wortschatz wächst langsamer als N.
    assert all(later["vocabulary_size"] / later["token_count"] < earlier["vocabulary_size"] / earlier["token_count"]
               for earlier, later in zip(reference["subsets"], reference["subsets"][1:]))


def test_reference_rejects_other_data_state(module, monkeypatch):
    monkeypatch.setitem(module.PARAMETERS, "corpus_sha256", "0" * 64)
    with pytest.raises(AssertionError, match="anderen Datenstand"):
        module.bgb_reference()


def test_prepared_corpus_must_equal_independent_tokens(module, reference):
    # Der passende Fall läuft in jedem Pilot- und Hauptlauf vor der Messung.
    changed = dict(reference, tokens={**reference["tokens"], "bgb_0001.txt": ("anders",)})
    with pytest.raises(AssertionError, match="unabhängigen Tokenisierung"):
        module.prepared_corpus(changed)


def test_heaps_fit_recovers_exact_power_law(module):
    fit = module.heaps_fit([(n, 3 * n ** 0.6) for n in (100, 1000, 10_000, 100_000)])
    assert math.isclose(fit["beta"], 0.6) and math.isclose(fit["k"], 3)


def test_existing_results_are_never_overwritten(module, tmp_path, monkeypatch):
    delivered = ROOT / "ergebnisse/messungen/02_invertierter_index"
    before = _tree_sha(delivered)
    with pytest.raises(SystemExit, match="nicht überschrieben"):
        module.main(["--ausgabe", "02_invertierter_index"])
    assert _tree_sha(delivered) == before
    monkeypatch.setattr(module, "MESSUNGEN", tmp_path)
    for invalid in ("", "..", "a/b", "../02_bgb"):
        with pytest.raises(SystemExit, match="Ungültiger Ordnername"):
            module.target_directory(invalid)
    (tmp_path / "belegt").mkdir()
    (tmp_path / "belegt" / "x").write_text("alt", encoding="utf-8")
    with pytest.raises(SystemExit, match="nicht leer"):
        module.target_directory("belegt")


def test_final_requires_matching_pilot_lock(module, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "MESSUNGEN", tmp_path)
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    with pytest.raises(SystemExit, match="Zuerst --pilot"):
        module.main(["--ausgabe", "02_bgb", "--pilot-ordner", "02_bgb_pilot"])
    assert not (tmp_path / "02_bgb").exists()
    path = tmp_path / "02_bgb_pilot" / "pilot_decision.json"
    path.parent.mkdir()
    decision = {"pilot_correct": True, "locked_parameters": module.PARAMETERS,
                "method_code_sha256": module.code_hashes(), "python_hash_seed": "0"}
    path.write_text(json.dumps(decision), encoding="utf-8")
    assert module.require_pilot(path)["pilot_correct"] is True
    for field, value, message in (("pilot_correct", False, "Erfolgreicher"),
                                  ("locked_parameters", {}, "Erfolgreicher"),
                                  ("method_code_sha256", {"x": "y"}, "Messcode"),
                                  ("python_hash_seed", "random", "PYTHONHASHSEED")):
        path.write_text(json.dumps({**decision, field: value}), encoding="utf-8")
        with pytest.raises(SystemExit, match=message):
            module.require_pilot(path)


def test_saved_pilot_verifies_and_tampering_is_rejected(module, tmp_path, monkeypatch):
    directory = ROOT / "ergebnisse/messungen/02_bgb_pilot"
    if not (directory / "metadata.json").is_file():
        pytest.skip("Pilot 02_bgb_pilot nicht vorhanden")
    result = module.verify_directory(directory, archive_only=True)
    assert (result["rows"], result["groups"], result["memory_rows"]) == (60, 20, 18)
    copy = tmp_path / "02_bgb_pilot"
    shutil.copytree(directory, copy)
    raw = copy / "raw.csv"
    with raw.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[-1]["elapsed_ns"] = str(int(rows[-1]["elapsed_ns"]) + 1)
    with raw.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(module, "bgb_reference", lambda: pytest.fail("Rohwertfehler muss vor der Neuberechnung auffallen"))
    with pytest.raises(AssertionError):
        module.verify_directory(copy, archive_only=True)
