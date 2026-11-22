"""Reihe 03b: Pflanzplan, Galloping-Diagnose, Blockgrenzen, Sperren und Rohwert-Audit."""

import copy
import csv
import importlib.util
import json
from pathlib import Path
import random
import shutil
import sys

import pytest

from gemeinsam import load_corpus, prepare_corpus
from gemeinsam.messung import MeasurementPlan
from boolesche_suche import intersect_galloping, intersect_sorted


EXPERIMENTS = Path(__file__).resolve().parents[1]
GALLOPING = EXPERIMENTS / "galloping"
ROOT = EXPERIMENTS.parents[2]
PILOT = ROOT / "ergebnisse/messungen/03b_pilot"


@pytest.fixture(scope="module")
def modules():
    # Eindeutige Modulnamen: Reihe 03 besitzt gleichnamige Skripte run/verify_results/analyse.
    for directory in (GALLOPING, EXPERIMENTS):
        if str(directory) not in sys.path:
            sys.path.append(str(directory))
    result = {}
    for name, path in (("run", GALLOPING / "run.py"), ("verify_results", GALLOPING / "verify_results.py"),
                       ("analyse", GALLOPING / "analyse.py"), ("render", GALLOPING / "plots/render.py")):
        label = f"reihe03b_{name}"
        if label not in sys.modules:
            spec = importlib.util.spec_from_file_location(label, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[label] = module
            spec.loader.exec_module(module)
        result[name] = sys.modules[label]
    import galloping_generator
    import boolean_diagnostics
    import messlauf03  # noqa: F401  (von run geladen, hier für Tests über sys.modules)
    result["generator"] = galloping_generator
    result["diagnostics"] = boolean_diagnostics
    return result


def test_membership_plan_matches_agreed_design(modules):
    generator = modules["generator"]
    plan = generator.membership_plan()
    assert generator.STAGES == (10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000)
    ids = generator.identifiers(10_000)
    assert ids[0] == "d00000.txt" and ids[-1] == "d09999.txt" and list(ids) == sorted(ids)
    for stage, df in enumerate(generator.STAGES):
        long = plan[generator.long_word(stage)]
        spread = plan[generator.short_word("verteilt", stage)]
        start = plan[generator.short_word("anfang", stage)]
        assert len(long) == df == len(set(long)) and list(long) == sorted(long)
        # Lange Liste gleichmäßig über alle Dokumente: Abstand D/df.
        assert long == tuple(ids[i * 10_000 // df] for i in range(df))
        assert len(spread) == len(start) == 10
        assert set(spread) <= set(long) and set(start) <= set(long)
        assert start == long[:10]
        positions = [long.index(identifier) for identifier in spread]
        assert positions[-1] == df - 1  # Zwei-Zeiger muss bis zum Ende der langen Liste laufen.
        gaps = {b - a for a, b in zip([-1, *positions], positions)}
        assert max(gaps) - min(gaps) <= 1  # gleichmäßig verteilt
    words = [*plan, *(f"f{i:03d}" for i in range(generator.FILLER_WORDS))]
    assert len(set(words)) == len(words) and all(len(word) == 4 and word.isascii() for word in words)


@pytest.mark.parametrize("kwargs", [{"document_count": 5}, {"stages": (20, 10)}, {"stages": (5,)},
                                    {"stages": (10, 10)}, {"document_count": True}])
def test_membership_plan_rejects_invalid_parameters(modules, kwargs):
    with pytest.raises((ValueError, TypeError)):
        modules["generator"].membership_plan(**{"document_count": 100, "stages": (10, 50, 100), **kwargs})


def test_small_generated_corpus_is_deterministic_and_matches_plan(modules, tmp_path):
    generator, run = modules["generator"], modules["run"]
    options = {"document_count": 200, "stages": (10, 50, 200), "seed": 17}
    left = generator.generate_corpus(tmp_path / "left", **options)
    right = generator.generate_corpus(tmp_path / "right", **options)
    assert left.file_sha256 == right.file_sha256 and left.expected_tokens == right.expected_tokens
    prepared = prepare_corpus(load_corpus(left.root))
    assert {doc.document_id: doc.tokens for doc in prepared} == left.expected_tokens
    assert all(len(tokens) == 100 for tokens in left.expected_tokens.values())
    postings = run.independent_postings(left.expected_tokens)
    assert all(postings[word] == ids for word, ids in left.membership.items())
    with pytest.raises(ValueError, match="leer"):
        generator.generate_corpus(left.root, **options)


@pytest.mark.parametrize("seed", [3, 29, 20261006])
def test_galloping_diagnostic_result_and_counts(modules, seed):
    diagnostics = modules["diagnostics"]
    rng = random.Random(seed)
    universe = [f"d{i:05d}.txt" for i in range(3000)]
    for _ in range(300):
        left = sorted(rng.sample(universe, rng.randrange(0, 30)))
        right = sorted(rng.sample(universe, rng.choice([0, 1, 10, 300, 3000])))
        result, counts = diagnostics.galloping_diagnostic(left, right)
        assert result == intersect_galloping(left, right) == intersect_sorted(left, right)
        assert counts["id_comparisons"] == (counts["gallop_probes"] + counts["binary_search_steps"]
                                            + counts["equality_checks"])
        assert counts["examined_short_ids"] <= min(len(left), len(right))


def test_diagnostics_for_design_cases(modules):
    diagnostics, generator = modules["diagnostics"], modules["generator"]
    plan = generator.membership_plan()
    stage = generator.STAGES.index(10_000)
    long, spread = plan[generator.long_word(stage)], plan[generator.short_word("verteilt", stage)]
    _, two_pointer, _ = diagnostics.merge_diagnostic(spread, long, "AND")
    _, galloping = diagnostics.galloping_diagnostic(spread, long)
    assert two_pointer == 19_990  # 10 Treffer mit ==, 9.990 Fehlschläge mit == und <.
    assert galloping["id_comparisons"] < 300
    start = plan[generator.short_word("anfang", stage)]
    assert diagnostics.merge_diagnostic(start, long, "AND")[1] == 10
    assert diagnostics.galloping_diagnostic(start, long)[1]["id_comparisons"] == 20
    full = diagnostics.diagnose_postings_galloping({"v": spread, "l": long}, ("v", "l"))
    assert full["ordered_terms"] == ["v", "l"] and full["result_ids"] == list(spread)
    assert full["merge_input_lengths"] == [[10, 10_000]] and full["intermediate_lengths"] == [10, 10]
    empty = diagnostics.diagnose_postings_galloping({"v": spread}, ("v", "fehlt"))
    assert empty["ordered_terms"] == ["fehlt", "v"] and empty["id_comparisons"] == 0


def test_queries_short_word_first_and_expected_hits(modules):
    run, generator = modules["run"], modules["generator"]
    queries = run.make_queries(generator.membership_plan())
    assert len(queries) == 20 and len({query.query_id for query in queries}) == 20
    for query in queries:
        assert query.terms[0].startswith("v" if query.case == "verteilt" else "a")
        assert query.terms[1].startswith("l") and len(query.expected_ids) == 10
    assert queries[0].query_id == "verteilt_df00010" and queries[-1].query_id == "anfang_df10000"


def test_measurement_blocks_random_order_checked_and_released(modules, monkeypatch):
    run = modules["run"]
    clock = iter(range(0, 10_000_000, 1000))
    monkeypatch.setattr(run, "perf_counter_ns", lambda: next(clock))
    query = run.GallopingQuery
    queries = [query("a", ("a000", "l000"), "anfang", 0, 10, ("d1.txt",)),
               query("b", ("v000", "l000"), "verteilt", 0, 10, ("d2.txt",))]
    calls = []

    def operation(name):
        def search(terms):
            calls.append((name, terms))
            return ["d1.txt"] if terms[0] == "a000" else ["d2.txt"]
        return search
    operations = {name: operation(name) for name in run.ALGORITHMS}
    plan = MeasurementPlan(warmups=1, repeats=3, query_block_size=4, seed=7)
    rows = run.measure_comparison(operations, queries, plan, {})
    assert len(rows) == 3 * 4 and len(calls) == 4 * 4 * 4
    assert all(row["elapsed_ns"] == 1000 and row["query_ms"] == .00025 for row in rows)
    assert all(sorted(row["order_index"] for row in rows if row["repeat"] == i) == list(range(4)) for i in range(3))
    again = run.measure_comparison(operations, queries, plan, {})
    assert [(r["repeat"], r["algorithm"], r["query_id"], r["order_index"]) for r in rows] == \
        [(r["repeat"], r["algorithm"], r["query_id"], r["order_index"]) for r in again]
    with pytest.raises(AssertionError, match="falsche"):
        run.measure_comparison({"and_galloping": lambda terms: []}, queries[:1], plan, {})
    events = []

    class Observed(list):
        def __del__(self):
            events.append("destroy")

    def tick():
        events.append("clock")
        return len(events) * 1000
    monkeypatch.setattr(run, "perf_counter_ns", tick)
    run.measure_comparison({"and_galloping": lambda terms: Observed(["d1.txt"])}, queries[:1],
                           MeasurementPlan(warmups=0, repeats=2, query_block_size=1), {})
    assert events == ["clock", "clock", "destroy", "clock", "clock", "destroy"]


def test_final_requires_pilot_with_same_parameters_code_and_hashseed(modules, tmp_path, monkeypatch):
    run = modules["run"]
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    path = tmp_path / "decision.json"
    with pytest.raises(SystemExit, match="Zuerst"):
        run.require_pilot(path)
    decision = {"pilot_correct": False, "locked_parameters": run.PARAMETERS}
    path.write_text(json.dumps(decision))
    with pytest.raises(SystemExit, match="Erfolgreicher"):
        run.require_pilot(path)
    decision.update(pilot_correct=True, method_code_sha256={"x": "y"}, python_hash_seed="0")
    path.write_text(json.dumps(decision))
    with pytest.raises(SystemExit, match="Messcode"):
        run.require_pilot(path)
    monkeypatch.setattr(run, "code_hashes", lambda: {"x": "y"})
    assert run.require_pilot(path)["pilot_decision_sha256"] == run.sha(path)
    decision["python_hash_seed"] = "random"
    path.write_text(json.dumps(decision))
    with pytest.raises(SystemExit, match="PYTHONHASHSEED"):
        run.require_pilot(path)


def test_output_names_and_overwrite_refusal(modules, tmp_path, monkeypatch):
    lauf = sys.modules["messlauf03"]
    monkeypatch.setattr(lauf, "MESSUNGEN", tmp_path)
    for name in ("", ".", "..", "a/b", "../x"):
        with pytest.raises(SystemExit, match="Ordnername"):
            lauf.directory_name(name)
    final = lauf.directory_name("final")
    final.mkdir()
    (final / "raw.csv").write_text("alt\n")
    # Ein nicht leerer Finalordner wird nie überschrieben, auch nicht mit --replace-pilot.
    for replace in (False, True):
        with pytest.raises(SystemExit, match="nicht überschrieben"):
            lauf.prepare_output(final, pilot=False, replace_pilot=replace)
    assert (final / "raw.csv").read_text() == "alt\n"
    pilot = lauf.directory_name("pilot")
    pilot.mkdir()
    (pilot / "raw.csv").write_text("alt\n")
    with pytest.raises(SystemExit, match="--replace-pilot"):
        lauf.prepare_output(pilot, pilot=True, replace_pilot=False)
    lauf.prepare_output(pilot, pilot=True, replace_pilot=True)
    assert list(pilot.iterdir()) == []
    lauf.prepare_output(lauf.directory_name("neu"), pilot=False, replace_pilot=False)
    assert (tmp_path / "neu").is_dir()
    with pytest.raises(SystemExit, match="anderer Ordnername"):
        lauf.pilot_directory("final", final)


def test_main_refuses_before_any_work(modules, monkeypatch, tmp_path):
    run = modules["run"]
    lauf = sys.modules["messlauf03"]
    monkeypatch.setattr(lauf, "MESSUNGEN", tmp_path)
    monkeypatch.setattr(run, "timing_run", lambda *args, **kwargs: pytest.fail("Messung darf nicht starten"))
    monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    with pytest.raises(SystemExit, match="PYTHONHASHSEED=0"):
        run.main([])
    with pytest.raises(SystemExit, match="PYTHONHASHSEED=0"):
        run.main(["--pilot"])
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    with pytest.raises(SystemExit, match="Zuerst"):
        run.main([])
    with pytest.raises(SystemExit, match="anderer Ordnername"):
        run.main(["--ausgabe", "x", "--pilot-ordner", "x"])
    with pytest.raises(SystemExit):
        run.main(["--replace-pilot"])
    (tmp_path / "03b_galloping").mkdir()
    (tmp_path / "03b_galloping" / "raw.csv").write_text("alt\n")
    with pytest.raises(SystemExit, match="nicht überschrieben"):
        run.main([])
    assert list(tmp_path.iterdir()) == [tmp_path / "03b_galloping"]


@pytest.fixture(scope="module")
def pilot_copy(tmp_path_factory, modules):
    if not (PILOT / "metadata.json").exists():
        pytest.skip("Pilot 03b noch nicht ausgeführt")
    target = tmp_path_factory.mktemp("pilot03b") / "03b_pilot"
    shutil.copytree(PILOT, target)
    return target


def test_existing_pilot_verifies_and_rejects_tampering(modules, pilot_copy, tmp_path, monkeypatch):
    verifier = modules["verify_results"]
    rows, groups, files = verifier.verify_directory(pilot_copy, check_active_code=False)
    assert (rows, groups, files) == (3 * (3 + 40), 43, 10_000)
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
    # Neuberechnung lief oben vollständig. Hier liefert sie den unveränderten Datensatz,
    # damit der Vergleich mit manipulierten Metadaten ohne zweite Korpuserzeugung prüfbar ist.
    monkeypatch.setattr(verifier, "recompute_dataset", lambda _: copy.deepcopy(metadata["datasets"][0]))
    assert verifier.verify_corpus(metadata) == 10_000
    changed_metadata = copy.deepcopy(metadata)
    changed_metadata["datasets"][0]["queries"][0]["diagnostics"]["and_galloping"]["id_comparisons"] += 1
    with pytest.raises(AssertionError, match="Diagnose"):
        verifier.verify_corpus(changed_metadata)
    changed_metadata = copy.deepcopy(metadata)
    changed_metadata["datasets"][0]["files"][0]["sha256"] = "0" * 64
    with pytest.raises(AssertionError):
        verifier.verify_corpus(changed_metadata)
    corrupt = tmp_path / "corrupt"
    shutil.copytree(pilot_copy, corrupt)
    source = corrupt / "code_source/themen/03_boolesche_mehrwortsuche/src/boolesche_suche/lists.py"
    source.write_text(source.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Quelltextarchiv"):
        verifier.verify_directory(corrupt, check_active_code=False)


def test_analysis_and_plot_from_pilot_copy_write_only_to_temporary_paths(modules, pilot_copy, tmp_path, monkeypatch):
    # Die vollständige Prüfung des Pilots läuft im vorherigen Test; hier nur Aufruf belegen.
    verified = []
    monkeypatch.setattr(modules["verify_results"], "verify_directory",
                        lambda directory, **options: verified.append((Path(directory), options)))
    rows = modules["analyse"].analyse(pilot_copy, tmp_path / "analyse", check_active_code=False)
    assert len(rows) == 20
    assert all(row["two_pointer_over_galloping_ratio"] == row["two_pointer_median_ms"] / row["galloping_median_ms"]
               for row in rows)
    report = (tmp_path / "analyse/auswertung.md").read_text(encoding="utf-8")
    assert "Pilotlauf" in report and ";" not in report
    stored = json.loads((tmp_path / "analyse/comparisons.json").read_text(encoding="utf-8"))
    assert stored == rows
    outputs = modules["render"].render(pilot_copy, tmp_path / "abbildungen", check_active_code=False)
    assert [Path(item["path"]).name for item in outputs] == list(modules["render"].FIGURE_NAMES)
    manifest = json.loads((pilot_copy / "plot_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["values"]) == 40 and manifest["measurement_unchanged"] is True
    with pytest.raises(SystemExit, match="nicht überschrieben"):
        modules["render"].render(pilot_copy, tmp_path / "abbildungen", check_active_code=False)
    assert verified == [(pilot_copy.resolve(), {"check_active_code": False})] * 2
