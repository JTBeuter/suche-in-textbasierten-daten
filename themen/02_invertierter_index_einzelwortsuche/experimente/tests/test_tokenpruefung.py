"""Zusatzmessung 02b: Datensätze, Kopie ohne Tokenprüfung, Ausgabeschutz und Prüfung."""

from __future__ import annotations

import ast
import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from gemeinsam import CorpusError, PreparedDocument, RawDocument, prepare_corpus
from invertierter_index import build_inverted_index


EXPERIMENTS = Path(__file__).resolve().parents[1]
ROOT = EXPERIMENTS.parents[2]


@pytest.fixture
def module(monkeypatch):
    label = "experiment02b_tokenpruefung_test"
    spec = importlib.util.spec_from_file_location(label, EXPERIMENTS / "tokenpruefung.py")
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, label, loaded)
    spec.loader.exec_module(loaded)
    return loaded


def _sources(module):
    production = Path(module.index_module.__file__).read_text(encoding="utf-8")
    return production, (EXPERIMENTS / "tokenpruefung.py").read_text(encoding="utf-8")


def _tree_sha(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob("*")) if path.is_file()}


def test_datasets_are_exactly_the_v_series_of_run02(module):
    # PARAMETERS aus run.py ohne Import lesen: kein Namenskonflikt mit generator/memory anderer Themen.
    tree = ast.parse((EXPERIMENTS / "run.py").read_text(encoding="utf-8"))
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "PARAMETERS" for target in node.targets))
    entries = dict(zip((key.value for key in assignment.value.keys), assignment.value.values))
    recipes = ast.literal_eval(entries["datasets"])
    v_series = [{key: value for key, value in recipe.items() if key != "series"}
                for recipe in recipes if "V" in recipe["series"]]
    assert sorted(v_series, key=lambda recipe: recipe["base_vocabulary"]) == module.PARAMETERS["datasets"]
    assert ast.literal_eval(entries["seed"]) == module.PARAMETERS["seed"]
    assert set(module.PARAMETERS["variant_order"]) == {recipe["dataset_id"] for recipe in v_series}
    assert all(sorted(order) == sorted(module.VARIANTS) for order in module.PARAMETERS["variant_order"].values())
    assert module.reference_datasets()["v10000"]["vocabulary_size"] == 10_002


def test_copy_equals_production_without_exactly_the_token_check(module):
    production, own = _sources(module)
    module.copy_matches_production(production, own)
    changed_copy = own.replace("immutable = {token: tuple(sorted(ids))", "immutable = {token: tuple(ids)", 1)
    assert changed_copy != own
    with pytest.raises(AssertionError, match="Kopie weicht"):
        module.copy_matches_production(production, changed_copy)
    changed_production = production.replace("if document.document_id in identifiers:",
                                            "if document.document_id in identifiers and False:", 1)
    assert changed_production != production
    with pytest.raises(AssertionError, match="Kopie weicht"):
        module.copy_matches_production(changed_production, own)
    weaker_check = production.replace("if tokenize(token) != (token,):", "if not token:", 1)
    assert weaker_check != production
    with pytest.raises(AssertionError, match="Tokenprüfung hat sich verändert"):
        module.copy_matches_production(weaker_check, own)


def test_variants_identical_and_copy_skips_only_the_token_contract(module):
    prepared = prepare_corpus((RawDocument("b.txt", "b.txt", "Straße Fehler fehler"),
                               RawDocument("a.txt", "a.txt", "Fehler Verbindung"),
                               RawDocument("c.txt", "c.txt", "")))
    public, without = build_inverted_index(prepared), module.build_ohne_tokenpruefung(iter(prepared))
    assert type(without) is type(public)
    assert dict(without) == dict(public) == {"strasse": ("b.txt",), "fehler": ("a.txt", "b.txt"),
                                             "verbindung": ("a.txt",)}
    assert list(without) == list(public)
    invalid = (PreparedDocument("x.txt", "x.txt", "A B", ("A B",)),)
    with pytest.raises(CorpusError, match="normalisiertes"):
        build_inverted_index(invalid)
    assert dict(module.build_ohne_tokenpruefung(invalid)) == {"A B": ("x.txt",)}
    for faulty in ("text", [object()], [prepared[0], prepared[0]]):
        with pytest.raises(CorpusError):
            module.build_ohne_tokenpruefung(faulty)


def test_existing_results_are_never_overwritten(module, tmp_path, monkeypatch):
    delivered = ROOT / "ergebnisse/messungen/02_invertierter_index"
    before = _tree_sha(delivered)
    with pytest.raises(SystemExit, match="nicht überschrieben"):
        module.main(["--ausgabe", "02_invertierter_index"])
    with pytest.raises(SystemExit, match="nicht überschrieben"):
        module.main(["--pilot", "--ausgabe", "02_pilot"])
    assert _tree_sha(delivered) == before
    monkeypatch.setattr(module, "MESSUNGEN", tmp_path)
    for invalid in ("", "..", "a/b", "../02b"):
        with pytest.raises(SystemExit, match="Ungültiger Ordnername"):
            module.target_directory(invalid)
    (tmp_path / "belegt").mkdir()
    (tmp_path / "belegt" / "x").write_text("alt", encoding="utf-8")
    with pytest.raises(SystemExit, match="nicht leer"):
        module.target_directory("belegt")
    (tmp_path / "leer").mkdir()
    assert module.target_directory("leer") == tmp_path / "leer"


def test_final_requires_matching_pilot_lock(module, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "MESSUNGEN", tmp_path)
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    with pytest.raises(SystemExit, match="Zuerst --pilot"):
        module.main(["--ausgabe", "02b_tokenpruefung", "--pilot-ordner", "02b_pilot"])
    assert not (tmp_path / "02b_tokenpruefung").exists()
    path = tmp_path / "02b_pilot" / "pilot_decision.json"
    path.parent.mkdir()
    decision = {"pilot_correct": True, "locked_parameters": module.PARAMETERS,
                "method_code_sha256": module.code_hashes(), "python_hash_seed": "0"}
    path.write_text(json.dumps(decision), encoding="utf-8")
    assert module.require_pilot(path)["python_hash_seed"] == "0"
    for field, value, message in (("pilot_correct", False, "Erfolgreicher"),
                                  ("locked_parameters", {}, "Erfolgreicher"),
                                  ("method_code_sha256", {"x": "y"}, "Messcode"),
                                  ("python_hash_seed", "random", "PYTHONHASHSEED")):
        path.write_text(json.dumps({**decision, field: value}), encoding="utf-8")
        with pytest.raises(SystemExit, match=message):
            module.require_pilot(path)


def test_dataset_preparation_rejects_corpus_differing_from_run02(module, tmp_path):
    # Der passende Fall ist im Pipelinetest abgedeckt.
    reference = copy.deepcopy(module.reference_datasets())
    recipe = module.PARAMETERS["datasets"][0]
    reference["v100"]["corpus_sha256"] = "0" * 64
    with pytest.raises(AssertionError, match="byteidentisch"):
        module.prepare_dataset(recipe, tmp_path / "anders", reference)


def test_pilot_pipeline_with_test_clock_verifies_and_detects_tampering(module, tmp_path, monkeypatch):
    """Ersatzuhr: prüft nur die Pipeline; diese Werte sind keine Messergebnisse."""
    import gemeinsam.messung as measurement
    counter = iter(range(0, 10**12, 1_000_000))
    monkeypatch.setattr(measurement, "perf_counter_ns", lambda: next(counter))
    monkeypatch.setattr(module, "MESSUNGEN", tmp_path)
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    output = module.run(module.argparse.Namespace(pilot=True, ausgabe="02b_test", pilot_ordner="unbenutzt",
                                                  hintergrundlast="pytest-Ersatzuhr"))
    assert output == tmp_path / "02b_test"
    result = module.verify_directory(output)
    assert result["rows"] == 3 * 2 * 3 and result["groups"] == 6 and result["changed_sources"] == []
    evaluation = json.loads((output / "auswertung.json").read_text(encoding="utf-8"))
    assert [entry["dataset_id"] for entry in evaluation["results"]] == ["v100", "n100000", "v10000"]
    assert all(entry["share"] == 0.0 for entry in evaluation["results"])  # Ersatzuhr: gleiche Blockdauer
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["environment"]["python_hash_seed"] == "0" and metadata["environment"]["python_hash_seed_set"] is True
    reference = module.reference_datasets()
    for dataset in metadata["datasets"]:
        stored = reference[dataset["dataset_id"]]
        assert dataset["corpus_sha256"] == stored["corpus_sha256"]
        assert dataset["token_checks"] == {"tokenize_calls": stored["vocabulary_size"],
                                           "checked_tokens_lookups": stored["posting_count"]}
    assert [dataset["vocabulary_size"] for dataset in metadata["datasets"]] == [102, 1002, 10002]
    with pytest.raises(SystemExit, match="nicht leer"):
        module.run(module.argparse.Namespace(pilot=True, ausgabe="02b_test", pilot_ordner="unbenutzt",
                                             hintergrundlast="pytest"))
    raw = output / "raw.csv"
    with raw.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["elapsed_ns"] = str(int(rows[0]["elapsed_ns"]) + 1)
    with raw.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(AssertionError):
        module.verify_directory(output)
