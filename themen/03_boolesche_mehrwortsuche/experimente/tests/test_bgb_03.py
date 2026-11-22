"""Reihe 03 BGB (Realteil): Anfrageauswahl, unabhängige Erwartungen, Blöcke, Sperren, Audit."""

import copy
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

from gemeinsam.messung import MeasurementPlan


EXPERIMENTS = Path(__file__).resolve().parents[1]
BGB = EXPERIMENTS / "bgb"
ROOT = EXPERIMENTS.parents[2]
PILOT = ROOT / "ergebnisse/messungen/03_bgb_pilot"


@pytest.fixture(scope="module")
def modules():
    # Eindeutige Modulnamen: Reihe 03 besitzt gleichnamige Skripte run/verify_results/analyse.
    for directory in (BGB, EXPERIMENTS):
        if str(directory) not in sys.path:
            sys.path.append(str(directory))
    result = {}
    for name in ("run", "verify_results", "analyse"):
        label = f"reihe03bgb_{name}"
        if label not in sys.modules:
            spec = importlib.util.spec_from_file_location(label, BGB / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[label] = module
            spec.loader.exec_module(module)
        result[name] = sys.modules[label]
    import boolean_diagnostics
    import messlauf03
    result["diagnostics"], result["lauf"] = boolean_diagnostics, messlauf03
    return result


@pytest.fixture(scope="module")
def validated(modules):
    return modules["run"].validate_dataset()


def test_query_plan_covers_agreed_questions(modules):
    plan = {query["query_id"]: query for query in modules["run"].QUERY_PLAN}
    assert len(plan) == len(modules["run"].QUERY_PLAN) == 15
    # Reihenfolge: dieselben Wörter mit kurzer bzw. langer Liste vorn (k=2 und k=5).
    assert plan["and_k2_selten_vorn"]["terms"] == plan["and_k2_haeufig_vorn"]["terms"][::-1]
    assert sorted(plan["and_k5_selten_vorn"]["terms"]) == sorted(plan["and_k5_selten_hinten"]["terms"])
    assert {len(query["terms"]) for query in plan.values() if query["operator"] == "AND"} == {2, 3, 5}
    assert sum(query["operator"] == "OR" for query in plan.values()) == 3
    assert [query["query_id"] for query in plan.values() if query["exclude"]] == ["and_not_k2"]


def test_expectations_from_manifest_and_proposals(modules, validated):
    *_, queries, dataset = validated
    by_id = {query["query_id"]: query for query in dataset["queries"]}
    expected = {
        "and_k2_selten_vorn": ([16, 2280], 15), "and_k2_haeufig_vorn": ([2280, 16], 15),
        "and_k2_extrem": ([1, 2280], 1), "and_k2_aehnlich": ([79, 82], 66),
        "and_k2_mittel": ([188, 77], 14), "and_k3_mittel": ([215, 145, 165], 5),
        "and_k5_mittel": ([188, 77, 165, 215, 145], 0),
        "and_k5_selten_vorn": ([16, 2280, 2177, 1844, 1243], 12),
        "and_k5_selten_hinten": ([1243, 1844, 2177, 2280, 16], 12),
        "and_k5_haeufig": ([2280, 2177, 1844, 1243, 1391], 674), "and_leer_vorhanden": ([79, 139], 0),
        "or_k2_mittel": ([188, 77], 251), "or_k3_mittel": ([215, 145, 165], 420),
        "or_k5_haeufig": ([2280, 2177, 1844, 1243, 1391], 2463), "and_not_k2": ([188, 77], 9),
    }
    assert {key: (value["posting_lengths_input_order"], value["hit_count"]) for key, value in by_id.items()} == expected
    assert by_id["and_not_k2"]["exclude_posting_length"] == 106
    assert by_id["and_not_k2"]["expected_ids"] == ["bgb_0179.txt", "bgb_0309.txt", "bgb_0314.txt", "bgb_0325.txt",
                                                   "bgb_0346.txt", "bgb_0437.txt", "bgb_0634.txt", "bgb_0648a.txt",
                                                   "bgb_0651i.txt"]
    assert by_id["and_k2_extrem"]["expected_ids"] == ["bgb_2385.txt"]
    assert by_id["and_k5_selten_hinten"]["proposal"]["proposal_match"] == "permutation"
    assert all(value["proposal"]["proposal_match"] == "exact" for key, value in by_id.items()
               if key != "and_k5_selten_hinten")
    assert dataset["document_count"] == 2486 and dataset["token_count"] == 213_718
    assert dataset["corpus_sha256"] == modules["run"].PARAMETERS["corpus_sha256"]
    # Galloping spart bei großem Längenverhältnis Vergleiche, bei ähnlichen Längen nicht.
    extreme = by_id["and_k2_extrem"]["diagnostics"]
    assert extreme["and_galloping"]["id_comparisons"] < extreme["and_shortest_first"]["id_comparisons"] / 100
    similar = by_id["and_k2_aehnlich"]["diagnostics"]
    assert similar["and_galloping"]["id_comparisons"] > similar["and_shortest_first"]["id_comparisons"]
    assert by_id["and_not_k2"]["diagnostics"]["and_galloping"]["difference_input_lengths"] == [14, 106]


def test_changed_proposal_or_corpus_is_detected(modules, monkeypatch, tmp_path):
    run = modules["run"]
    proposals = json.loads((ROOT / run.PARAMETERS["proposals"]).read_text(encoding="utf-8"))
    entry = next(item for item in proposals["reihe_03_boolesche_suche"] if item["kind"] == "and_not")
    entry["document_ids"] = entry["document_ids"][1:]
    changed = tmp_path / "vorschlaege.json"
    changed.write_text(json.dumps(proposals, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setitem(run.PARAMETERS, "proposals", str(changed))
    with pytest.raises(AssertionError, match="and_not_k2"):
        run.bgb_fixture()
    monkeypatch.setitem(run.PARAMETERS, "proposals", "daten/real/bgb/anfragevorschlaege.json")
    monkeypatch.setitem(run.PARAMETERS, "token_count", 1)
    with pytest.raises(AssertionError, match="Kennzahlen"):
        run.bgb_fixture()


def test_find_proposal_requires_same_kind_terms_and_exclude(modules):
    run = modules["run"]
    proposals = [{"kind": "and", "terms": ["a", "b"]}, {"kind": "and_not", "terms": ["a", "b"], "exclude_term": "c"}]
    assert run.find_proposal(proposals, "and", ("a", "b"), None) == (proposals[0], "exact")
    assert run.find_proposal(proposals, "and", ("b", "a"), None) == (proposals[0], "permutation")
    assert run.find_proposal(proposals, "and_not", ("a", "b"), "c")[0] is proposals[1]
    for kind, terms, exclude in (("or", ("a", "b"), None), ("and_not", ("a", "b"), "d"), ("and", ("a",), None)):
        with pytest.raises(AssertionError, match="kein Anfragevorschlag"):
            run.find_proposal(proposals, kind, terms, exclude)


def test_and_not_diagnostics(modules):
    diagnostics = modules["diagnostics"]
    result, comparisons, _ = diagnostics.difference_diagnostic(["a", "c", "e"], ["b", "c", "d"])
    assert result == ["a", "e"] and comparisons == 7  # a/b ==,<; c/b ==,<; c/c ==; e/d ==,<
    tokens = {"x.txt": ("alpha", "beta", "gamma", "rest"), "y.txt": ("alpha", "beta", "rest")}
    direct = diagnostics.diagnose_direct_exclude(tokens, ("alpha", "beta"), "gamma")
    assert direct == {"visited_tokens": 3 + 3, "result_ids": ["y.txt"]}


def test_measurement_eligibility_order_and_release(modules, monkeypatch):
    run = modules["run"]
    clock = iter(range(0, 10_000_000, 1000))
    monkeypatch.setattr(run, "perf_counter_ns", lambda: next(clock))
    queries = [run.RealQuery("a", ("x", "y"), "AND", None, ("d1.txt",)),
               run.RealQuery("o", ("x", "y"), "OR", None, ("d1.txt", "d2.txt")),
               run.RealQuery("n", ("x",), "AND", "y", ())]
    calls = []

    def operation(name):
        def search(query):
            calls.append((name, query.query_id))
            return list(query.expected_ids)
        return search
    operations = {name: operation(name) for name in run.ALGORITHMS}
    plan = MeasurementPlan(warmups=1, repeats=3, query_block_size=2, seed=7)
    rows = run.measure_comparison(operations, queries, plan, {})
    # direkt 3 Anfragen, je AND-Variante 2 (AND und AND NOT), OR 1: 10 Blöcke je Wiederholung.
    assert len(rows) == 3 * 10 and len(calls) == 4 * 10 * 2
    assert {(row["algorithm"], row["query_id"]) for row in rows} == {
        ("direct_boolean", "a"), ("direct_boolean", "o"), ("direct_boolean", "n"), ("or_input_order", "o"),
        *((name, query) for name in ("and_input_order", "and_shortest_first", "and_galloping") for query in "an")}
    assert {row["query_type"] for row in rows if row["query_id"] == "n"} == {"and_not"}
    assert json.loads(queries[2].text) == {"terms": ["x"], "operator": "AND", "exclude": "y"}
    again = run.measure_comparison(operations, queries, plan, {})
    assert [(r["repeat"], r["algorithm"], r["query_id"], r["order_index"]) for r in rows] == \
        [(r["repeat"], r["algorithm"], r["query_id"], r["order_index"]) for r in again]
    with pytest.raises(AssertionError, match="falsche"):
        run.measure_comparison({"direct_boolean": lambda query: ["falsch.txt"]}, queries[:1], plan, {})
    events = []

    class Observed(list):
        def __del__(self):
            events.append("destroy")

    def tick():
        events.append("clock")
        return len(events)
    monkeypatch.setattr(run, "perf_counter_ns", tick)
    run.measure_comparison({"direct_boolean": lambda query: Observed(["d1.txt"])}, queries[:1],
                           MeasurementPlan(warmups=0, repeats=2, query_block_size=1), {})
    assert events == ["clock", "clock", "destroy", "clock", "clock", "destroy"]


def test_main_refuses_before_any_work(modules, monkeypatch, tmp_path):
    run, lauf = modules["run"], modules["lauf"]
    monkeypatch.setattr(lauf, "MESSUNGEN", tmp_path)
    monkeypatch.setattr(run, "timing_run", lambda *args, **kwargs: pytest.fail("Messung darf nicht starten"))
    monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    for arguments in ([], ["--pilot"]):
        with pytest.raises(SystemExit, match="PYTHONHASHSEED=0"):
            run.main(arguments)
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    with pytest.raises(SystemExit, match="Zuerst"):
        run.main([])
    with pytest.raises(SystemExit, match="anderer Ordnername"):
        run.main(["--ausgabe", "x", "--pilot-ordner", "x"])
    with pytest.raises(SystemExit, match="Ordnername"):
        run.main(["--ausgabe", "../03_boolesche_mehrwortsuche"])
    (tmp_path / "03_bgb").mkdir()
    (tmp_path / "03_bgb" / "raw.csv").write_text("alt\n")
    with pytest.raises(SystemExit, match="nicht überschrieben"):
        run.main([])
    with pytest.raises(SystemExit):
        run.main(["--replace-pilot"])
    assert (tmp_path / "03_bgb" / "raw.csv").read_text() == "alt\n"
    decision = {"pilot_correct": True, "locked_parameters": run.PARAMETERS, "method_code_sha256": run.code_hashes(),
                "python_hash_seed": "0"}
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "pilot_decision.json").write_text(json.dumps(decision))
    started = []
    monkeypatch.setattr(run, "timing_run", lambda *args, **kwargs: started.append((args, kwargs)))
    run.main(["--ausgabe", "neu", "--pilot-ordner", "p", "--hintergrundlast", "ruhig"])
    (output, plan, pilot, background, reference), _ = started[0]
    assert output == tmp_path / "neu" and pilot is False and background == "ruhig"
    assert plan == MeasurementPlan(query_block_size=5)
    assert reference["pilot_decision_sha256"] == run.sha(tmp_path / "p" / "pilot_decision.json")


@pytest.fixture(scope="module")
def pilot_copy(tmp_path_factory, modules):
    if not (PILOT / "metadata.json").exists():
        pytest.skip("Pilot 03_bgb noch nicht ausgeführt")
    target = tmp_path_factory.mktemp("pilot03bgb") / "03_bgb_pilot"
    shutil.copytree(PILOT, target)
    return target


def test_existing_pilot_verifies_and_rejects_tampering(modules, pilot_copy, tmp_path, monkeypatch):
    verifier = modules["verify_results"]
    rows, groups, documents = verifier.verify_directory(pilot_copy, check_active_code=False)
    assert (rows, groups, documents) == (3 * (3 + 54), 57, 2486)
    with (pilot_copy / "raw.csv").open(encoding="utf-8", newline="") as handle:
        raw = list(csv.DictReader(handle))
    summary = json.loads((pilot_copy / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((pilot_copy / "metadata.json").read_text(encoding="utf-8"))
    changed = copy.deepcopy(raw)
    changed[-1]["elapsed_ns"] = str(int(changed[-1]["elapsed_ns"]) + 1)
    with pytest.raises(AssertionError):
        verifier.verify_data(changed, summary, metadata)
    swapped = copy.deepcopy(raw)
    queries = [row for row in swapped if row["phase"] == "query"]
    queries[0]["order_index"], queries[1]["order_index"] = queries[1]["order_index"], queries[0]["order_index"]
    with pytest.raises(AssertionError):
        verifier.verify_data(swapped, summary, metadata)
    changed_summary = copy.deepcopy(summary)
    changed_summary[0]["median_ms"] += 1e-9
    with pytest.raises(AssertionError):
        verifier.verify_data(raw, changed_summary, metadata)
    monkeypatch.setattr(verifier, "recompute_dataset", lambda _: copy.deepcopy(metadata["datasets"][0]))
    assert verifier.verify_corpus(metadata) == 2486
    changed_metadata = copy.deepcopy(metadata)
    changed_metadata["datasets"][0]["queries"][0]["diagnostics"]["and_galloping"]["id_comparisons"] += 1
    with pytest.raises(AssertionError, match="Diagnose"):
        verifier.verify_corpus(changed_metadata)
    corrupt = tmp_path / "corrupt"
    shutil.copytree(pilot_copy, corrupt)
    source = corrupt / "code_source/themen/03_boolesche_mehrwortsuche/src/boolesche_suche/search.py"
    source.write_text(source.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Quelltextarchiv"):
        verifier.verify_directory(corrupt, check_active_code=False)


def test_analysis_from_pilot_copy_writes_only_to_temporary_path(modules, pilot_copy, tmp_path, monkeypatch):
    verified = []
    monkeypatch.setattr(modules["verify_results"], "verify_directory",
                        lambda directory, **options: verified.append((Path(directory), options)))
    rows = modules["analyse"].analyse(pilot_copy, tmp_path, check_active_code=False)
    assert verified == [(pilot_copy.resolve(), {"check_active_code": False})]
    assert len(rows) == 15
    by_id = {row["query_id"]: row for row in rows}
    row = by_id["and_k2_extrem"]
    assert row["shortest_over_galloping_ratio"] == row["and_shortest_first_median_ms"] / row["and_galloping_median_ms"]
    assert "and_galloping_median_ms" not in by_id["or_k5_haeufig"]
    report = (tmp_path / "auswertung.md").read_text(encoding="utf-8")
    assert "Pilotlauf" in report and "Vertrag AND Schadensersatz AND NOT Verbraucher" in report
    assert json.loads((tmp_path / "comparisons.json").read_text(encoding="utf-8")) == rows
