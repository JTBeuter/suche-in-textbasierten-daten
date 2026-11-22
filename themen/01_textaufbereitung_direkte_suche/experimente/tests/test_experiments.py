"""Unabhängige Generator-Fälle und Zusammenhang Rohwerte/Auswertung."""

import csv
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median, quantiles

import pytest

from gemeinsam import load_corpus, prepare_corpus
from gemeinsam.datengenerator import generate_corpus
from gemeinsam.messung import (
    MeasurementPlan, QuerySpec, measure_phase, measure_queries,
    summarize_measurements, write_measurements,
)
from direkte_suche import search_direct_word


def test_generator_known_tokens_and_exact_planted_hits(tmp_path):
    generated = generate_corpus(tmp_path / "corpus", 240, seed=7)
    # Handfestes Fixture aus dem festgelegten Zufallsstartwert; keine zentrale
    # Tokenisierung wird benutzt, um diese Tokenfolge zu erzeugen.
    assert generated.expected_tokens["doc00.txt"] == (
        "fehler", "wort0970", "wort0154", "wort0404", "wort0666", "wort0049",
        "wort0074", "wort0840", "wort0548", "wort0096", "wort0374", "verbindung",
    )
    raw = load_corpus(generated.root)
    prepared = prepare_corpus(raw)
    assert {document.document_id: document.tokens for document in prepared} == generated.expected_tokens
    assert generated.expected_occurrences == {"frequent": 20, "rare": 1, "missing": 0}
    assert search_direct_word(prepared, "Fehler") == [f"doc{number:02d}.txt" for number in range(20)]
    assert search_direct_word(prepared, "Verbindung") == ["doc00.txt"]
    assert search_direct_word(prepared, "Unauffindbar") == []
    assert sum(len(document.tokens) for document in prepared) == 240


def test_generator_reproducible_bytes_and_seed_changes_data(tmp_path):
    left = generate_corpus(tmp_path / "left", 10_000, seed=17)
    right = generate_corpus(tmp_path / "right", 10_000, seed=17)
    different = generate_corpus(tmp_path / "different", 10_000, seed=18)
    assert left.file_sha256 == right.file_sha256
    assert left.expected_tokens == right.expected_tokens
    assert left.file_sha256 != different.file_sha256
    assert left.expected_hits == right.expected_hits == different.expected_hits
    assert left.expected_occurrences == {"frequent": 100, "rare": 1, "missing": 0}


@pytest.mark.parametrize("total,documents", [(0, 20), (100, 0), (239, 20), (2020, 20)])
def test_generator_rejects_ambiguous_parameters(tmp_path, total, documents):
    with pytest.raises(ValueError):
        generate_corpus(tmp_path / "corpus", total, document_count=documents)


def test_generator_preserves_nonempty_destination(tmp_path):
    path = tmp_path / "existing"
    path.mkdir()
    (path / "keep.txt").write_text("nicht überschreiben")
    with pytest.raises(ValueError):
        generate_corpus(path, 240)
    assert (path / "keep.txt").read_text() == "nicht überschreiben"


def test_measurement_counts_and_summary_are_derived_from_raw(monkeypatch, tmp_path):
    import gemeinsam.messung as measurement
    # Uhrwerte sind ein Testdouble, keine Forschungs-Messwerte.
    timestamps = iter([0, 1_000_000, 10_000_000, 13_000_000, 20_000_000, 25_000_000,
                       30_000_000, 37_000_000, 40_000_000, 49_000_000])
    monkeypatch.setattr(measurement, "perf_counter_ns", lambda: next(timestamps))
    operations = []
    validation = []
    rows = measure_phase(lambda: operations.append(1) or ["D"], lambda value: validation.append(value),
                         MeasurementPlan(warmups=1, repeats=4), phase="load",
                         context={"dataset_id": "test", "algorithm": "direct_word", "token_count": 10})
    assert len(operations) == len(validation) == 5
    assert [row["load_ms"] for row in rows] == [3, 5, 7, 9]
    summary = summarize_measurements(rows)
    assert summary[0]["median_ms"] == 6
    assert summary[0]["q1_ms"] == 4.5
    assert summary[0]["q3_ms"] == 7.5
    assert summary[0]["iqr_ms"] == 3
    target = tmp_path / "raw.csv"
    write_measurements(target, rows)
    reloaded = list(csv.DictReader(target.open()))
    assert sum(float(row["load_ms"]) for row in reloaded) == 24
    assert all(row["build_ms"] == row["query_ms"] == row["index_bytes"] == row["peak_memory_bytes"] == "" for row in reloaded)


def test_query_blocks_order_and_all_results_are_validated(tmp_path):
    calls = []
    queries = [QuerySpec("a", "A", "present", ("a.txt",)), QuerySpec("b", "B", "missing", ())]
    plan = MeasurementPlan(warmups=1, repeats=3, query_block_size=4, seed=9)

    def search(text):
        calls.append(text)
        return ["a.txt"] if text == "A" else []

    context = {"dataset_id": "test", "algorithm": "direct_word", "token_count": 2}
    left = measure_queries(search, queries, plan, context=context)
    right = measure_queries(search, queries, plan, context=context)
    assert len(calls) == 2 * (1 + 3) * 2 * 4
    assert len(left) == len(right) == 6
    assert [(row["repeat"], row["query_id"], row["order_index"]) for row in left] == [
        (row["repeat"], row["query_id"], row["order_index"]) for row in right
    ]
    assert all(row["query_ms"] == row["elapsed_ns"] / 1_000_000 / 4 for row in left)
    faulty_count = 0

    def faulty_search(text):
        nonlocal faulty_count
        faulty_count += 1
        return ["wrong.txt"] if faulty_count == 2 else ["a.txt"]

    with pytest.raises(AssertionError):
        measure_queries(faulty_search, queries[:1], plan, context=context)


def test_rule_comparison_exact_expected_effects():
    script = Path(__file__).resolve().parents[1] / "run.py"
    spec = importlib.util.spec_from_file_location("experiment_run", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    comparison = module.rule_comparison()
    assert comparison["correct"] is True
    assert comparison["variants"]["casefold"]["hits"]["Straße"] == ["r0.txt", "r1.txt", "r2.txt"]
    assert comparison["variants"]["lower"]["hits"]["Straße"] == ["r0.txt", "r1.txt"]
    assert comparison["variants"]["lower"]["hits"]["STRASSE"] == ["r0.txt", "r2.txt"]


def test_saved_final_raw_values_and_summary_are_consistent():
    root = Path(__file__).resolve().parents[4]
    directory = root / "ergebnisse/messungen/01_direkte_suche"
    with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    assert len(rows) == 400
    assert len(summary) == 20
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["dataset_id"], row["phase"], row["query_id"]].append(row)
        assert row["correct"] == "True"
        assert row["build_ms"] == row["index_bytes"] == row["peak_memory_bytes"] == ""
        elapsed_ms = int(row["elapsed_ns"]) / 1_000_000 / int(row["block_size"])
        assert float(row[f"{row['phase']}_ms"]) == elapsed_ms
        if row["phase"] == "query":
            assert row["query_type"] == "word"
            assert int(row["block_size"]) == 10
            assert int(row["hit_count"]) == (
                0 if row["query_id"] == "missing" else
                20 if row["dataset_id"].startswith("generated_") and row["query_id"] == "frequent" else 1
            )
    for result in summary:
        group = grouped[result["dataset_id"], result["phase"], result["query_id"]]
        assert sorted(int(row["repeat"]) for row in group) == list(range(20))
        values = [float(row[f"{row['phase']}_ms"]) for row in group]
        q1, _, q3 = quantiles(values, n=4, method="inclusive")
        assert result["median_ms"] == median(values)
        assert result["q1_ms"] == q1 and result["q3_ms"] == q3
        assert result["iqr_ms"] == q3 - q1
    assert metadata["measurement_plan"] == {"warmups": 5, "repeats": 20, "query_block_size": 10, "seed": 20261006}
    correction = metadata.get("recording_correction")
    if correction:
        archive = root / correction["measured_run_source_archive"]
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == correction["run_script_sha256_measured"]


EXPERIMENTS = Path(__file__).resolve().parents[1]
ROOT = EXPERIMENTS.parents[2]


def _load(name, label):
    spec = importlib.util.spec_from_file_location(label, EXPERIMENTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run_module():
    return _load("run", "experiment01_run_ausgabe")


@pytest.fixture
def verifier():
    return _load("verify_results", "experiment01_verify_ausgabe")


def _tree_sha(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob("*")) if path.is_file()}


def test_target_directory_never_reuses_nonempty_or_invalid_names(run_module, tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "MESSUNGEN", tmp_path)
    assert run_module.target_directory("01b_pilot") == tmp_path / "01b_pilot"
    (tmp_path / "leer").mkdir()
    assert run_module.target_directory("leer") == tmp_path / "leer"
    (tmp_path / "belegt").mkdir()
    (tmp_path / "belegt" / "raw.csv").write_text("alt", encoding="utf-8")
    with pytest.raises(SystemExit, match="nicht leer"):
        run_module.target_directory("belegt")
    assert (tmp_path / "belegt" / "raw.csv").read_text(encoding="utf-8") == "alt"
    for invalid in ("", ".", "..", "a/b", "../01b", "a\\b"):
        with pytest.raises(SystemExit, match="Ungültiger Ordnername"):
            run_module.target_directory(invalid)


@pytest.mark.parametrize("arguments", [
    ["--ausgabe", "01_direkte_suche"],
    ["--pilot", "--ausgabe", "01_pilot"],
    ["--pilot", "--ausgabe", "01_direkte_suche"],
])
def test_delivered_series_01_are_refused_before_any_measurement(run_module, arguments):
    delivered = {name: _tree_sha(ROOT / "ergebnisse/messungen" / name) for name in ("01_direkte_suche", "01_pilot")}
    with pytest.raises(SystemExit, match="nicht überschrieben"):
        run_module.main(arguments)
    assert {name: _tree_sha(ROOT / "ergebnisse/messungen" / name) for name in delivered} == delivered


def test_final_requires_lock_from_new_pilot_directory(run_module, tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "MESSUNGEN", tmp_path)
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    with pytest.raises(SystemExit, match="Zuerst --pilot"):
        run_module.main(["--ausgabe", "01b_direkte_suche", "--pilot-ordner", "01b_pilot"])
    assert not (tmp_path / "01b_direkte_suche").exists()
    decision_path = tmp_path / "01b_pilot" / "pilot_decision.json"
    decision_path.parent.mkdir()
    decision = {"pilot_correct": True, "locked_parameters": run_module.PARAMETERS,
                "method_code_sha256": run_module.code_hashes(), "python_hash_seed": "0"}
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    assert run_module.require_pilot(decision_path)["python_hash_seed"] == "0"
    for field, value, message in (("pilot_correct", False, "Parameter"),
                                  ("locked_parameters", {}, "Parameter"),
                                  ("method_code_sha256", {"run.py": "alt"}, "Messcode"),
                                  ("python_hash_seed", "random", "PYTHONHASHSEED")):
        decision_path.write_text(json.dumps({**decision, field: value}), encoding="utf-8")
        with pytest.raises(SystemExit, match=message):
            run_module.require_pilot(decision_path)
    # Die gelieferte Kafka-Pilotsperre 01_pilot gilt nicht für den BGB-Lauf. 01b_pilot ist
    # seit dem Finallauf vom 14.10.2026 der BGB-Pilot, an den 01b_direkte_suche gebunden ist.
    delivered = ROOT / "ergebnisse/messungen/01_pilot/pilot_decision.json"
    if delivered.is_file():
        with pytest.raises(SystemExit, match="Parameter"):
            run_module.require_pilot(delivered)
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    with pytest.raises(SystemExit, match="anderer Ordnername"):
        run_module.main(["--ausgabe", "x", "--pilot-ordner", "../01b_pilot"])


@pytest.mark.parametrize("seed,expected_set", [("0", True), (None, False)])
def test_metadata_records_hash_seed_and_archives_measured_sources(run_module, tmp_path, monkeypatch, seed, expected_set):
    if seed is None:
        monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    else:
        monkeypatch.setenv("PYTHONHASHSEED", seed)
    output = tmp_path / "01x_pilot"
    metadata = run_module._metadata(MeasurementPlan(warmups=1, repeats=3), True, output, "Testlast")
    assert metadata["run_id"] == "01x_pilot" and metadata["run_kind"] == "pilot"
    assert metadata["environment"]["python_hash_seed"] == (seed or "random")
    assert metadata["environment"]["python_hash_seed_set"] is expected_set
    assert metadata["background_load"] == "Testlast"
    assert metadata["source_archive"] == "code_source/"
    assert "themen/01_textaufbereitung_direkte_suche/experimente/run.py" in metadata["code_sha256"]
    for relative, digest in metadata["code_sha256"].items():
        assert hashlib.sha256((output / "code_source" / relative).read_bytes()).hexdigest() == digest


def test_delivered_series_01_verify_only_in_archive_mode(verifier):
    directory = ROOT / "ergebnisse/messungen/01_direkte_suche"
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    run_script = "themen/01_textaufbereitung_direkte_suche/experimente/run.py"
    active = hashlib.sha256((ROOT / run_script).read_bytes()).hexdigest()
    if active == metadata["recording_correction"]["run_script_sha256_after_recording_correction"]:
        pytest.skip("aktives run.py entspricht noch dem korrigierten Stand")
    with pytest.raises(AssertionError, match="--archive-only"):
        verifier.verify_code(directory, metadata)
    notes = verifier.verify_code(directory, metadata, archive_only=True)
    assert any(note.startswith("Nur-Archiv-Modus") for note in notes)


def test_archive_only_still_rejects_damaged_measured_archive(verifier, tmp_path):
    directory = ROOT / "ergebnisse/messungen/01_direkte_suche"
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    damaged = tmp_path / "run_source_measured.py"
    damaged.write_bytes((directory / "run_source_measured.py").read_bytes() + b"\n# manipuliert\n")
    metadata["recording_correction"]["measured_run_source_archive"] = damaged.as_posix()
    with pytest.raises(AssertionError):
        verifier.verify_code(directory, metadata, archive_only=True)


def test_new_source_archive_strict_archive_only_and_tampering(verifier, tmp_path):
    relative = "gemeinsam/src/gemeinsam/messung.py"
    payload = (ROOT / relative).read_bytes()
    archived = tmp_path / "code_source" / relative
    archived.parent.mkdir(parents=True)
    archived.write_bytes(payload)
    metadata = {"source_archive": "code_source/", "code_sha256": {relative: hashlib.sha256(payload).hexdigest()}}
    assert verifier.verify_code(tmp_path, metadata) == ["1 archivierte Quell-SHA-256 geprüft."]
    changed = {**metadata, "code_sha256": {relative: hashlib.sha256(payload + b"#").hexdigest()}}
    archived.write_bytes(payload + b"#")
    with pytest.raises(AssertionError, match="aktiver Code"):
        verifier.verify_code(tmp_path, changed)
    assert any("Nur-Archiv-Modus" in note for note in verifier.verify_code(tmp_path, changed, archive_only=True))
    archived.write_bytes(payload + b"##")
    with pytest.raises(AssertionError, match="Quelltextarchiv beschädigt"):
        verifier.verify_code(tmp_path, changed, archive_only=True)


def test_verify_data_derives_counts_from_plan_and_rejects_tampering(verifier):
    for name in ("01_direkte_suche", "01_pilot"):
        directory = ROOT / "ergebnisse/messungen" / name
        with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        assert verifier.verify_data(rows, summary, metadata) == (20 * metadata["measurement_plan"]["repeats"], 20)
        rows[0]["elapsed_ns"] = str(int(rows[0]["elapsed_ns"]) + 1)
        with pytest.raises(AssertionError):
            verifier.verify_data(rows, summary, metadata)
        wrong_plan = {**metadata, "measurement_plan": {**metadata["measurement_plan"], "warmups": 0}}
        with pytest.raises(AssertionError, match="Messplan"):
            verifier.verify_data(rows, summary, wrong_plan)


@pytest.mark.parametrize("name,kind,repeats", [("01b_pilot", "pilot", 3), ("01b_direkte_suche", "final", 20)])
def test_new_bgb_runs_verify_when_present(verifier, name, kind, repeats):
    # Pilot und Finallauf der Neumessung vom 14.10.2026 mit BGB-Realteil.
    real = "real_bgb"
    directory = ROOT / "ergebnisse/messungen" / name
    if not (directory / "metadata.json").is_file():
        pytest.skip(f"Lauf {name} nicht vorhanden")
    with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["run_kind"] == kind
    assert {dataset["dataset_id"] for dataset in metadata["datasets"]} - verifier.GENERATED_IDS == {real}
    groups = 21
    assert verifier.verify_data(rows, summary, metadata) == (groups * repeats, groups)
    verifier.verify_code(directory, metadata, archive_only=True)
    verifier.verify_auxiliary(directory, metadata)
    verifier.verify_bgb(next(dataset for dataset in metadata["datasets"] if dataset["dataset_id"] == real))


def test_bgb_fixture_queries_and_multi_document_checks(run_module):
    fixture, tokens, queries = run_module.bgb_fixture()
    assert [(query.query_id, query.text, len(query.expected_ids)) for query in queries] == [
        ("early", "Beginn", 52), ("frequent", "der", 2280), ("rare", "Erbschaftskauf", 1), ("missing", "Server", 0)]
    assert queries[0].expected_ids[0] == "bgb_0001.txt" and queries[2].expected_ids == ("bgb_2385.txt",)
    assert fixture["queries"]["early"]["first_position"] == 0
    assert fixture["queries"]["rare"]["first_position"] == 9
    assert fixture["queries"]["frequent"]["scanned_tokens_direct"] == 37889
    assert fixture["queries"]["missing"]["scanned_tokens_direct"] == 213718
    assert len(tokens) == 2486 and sum(map(len, tokens.values())) == 213718
    assert run_module.canonical_corpus_sha256(
        {identifier: entry["sha256"] for identifier, entry in fixture["files"].items()}) == fixture["corpus_sha256"]
    # Manipulierte Erwartungen und Listen werden erkannt.
    frequent = fixture["queries"]["frequent"]
    with pytest.raises(AssertionError, match="Anzahl/Hash"):
        run_module.check_document_list(list(queries[1].expected_ids[1:]), frequent)
    with pytest.raises(AssertionError, match="unabhängigen Erwartung"):
        run_module.check_document_list(["bgb_0001.txt"], fixture["queries"]["rare"])
    from gemeinsam import RawDocument
    raw = [RawDocument("bgb_0001.txt", "bgb_0001.txt", "Beginn der Rechtsfähigkeit")]
    files = [{"document_id": "bgb_0001.txt", "bytes": 1, "sha256": "0" * 64}]
    with pytest.raises(AssertionError, match="Dokumentkennungen"):
        run_module._check_real_corpus(files, prepare_corpus(raw), fixture, tokens)


def test_independent_tokens_refuses_characters_outside_regex_equivalence(run_module):
    assert run_module.independent_tokens("Maßgabe, § 312a Abs. 1") == ("massgabe", "312a", "abs", "1")
    for text in ("x\u0301y", "Zahl ²", "Ⅻ"):
        with pytest.raises(AssertionError, match="Regex-Gegenprobe"):
            run_module.independent_tokens(text)
