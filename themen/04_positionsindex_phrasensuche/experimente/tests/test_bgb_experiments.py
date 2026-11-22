"""BGB-Realteil der Reihe 04: Auswahl, Datenprüfung, Pilotsperre und Prüfer.

Der Kleinkorpus unten hat handgezählte Erwartungen und ersetzt im Test den
BGB-Datenpfad; er ist kein Messergebnis. Nur der erste Test liest den echten
BGB-Korpus.
"""

import copy
import csv
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


PREFIX = "themen.04_positionsindex_phrasensuche.experimente"


@pytest.fixture
def modules():
    return {name: importlib.import_module(f"{PREFIX}.{name}")
            for name in ("run", "run_bgb", "verify_bgb", "verify_results", "memory")}


def test_real_bgb_selection_matches_manifest_and_independent_oracle(modules):
    run_bgb = modules["run_bgb"]
    root, tokens, queries, fixture = run_bgb.bgb_fixture()
    assert root == run_bgb.ROOT / "daten/real/bgb/dokumente"
    assert len(tokens) == 2486 and sum(map(len, tokens.values())) == 213718
    counts = {query.query_id: (len(query.expected), sum(map(len, query.expected.values()))) for query in queries}
    assert counts == {
        "bgb_frequent_k2": (57, 64), "bgb_frequent_k3": (62, 85), "bgb_frequent_k4": (82, 85),
        "bgb_frequent_k5": (35, 35), "bgb_rare_k2": (1, 1), "bgb_rare_k3": (1, 1), "bgb_rare_k4": (1, 1),
        "bgb_rare_k5": (2, 2), "bgb_common_words_k2": (32, 34), "bgb_wrong_order_k2": (0, 0),
        "bgb_wrong_order_k3": (0, 0), "bgb_missing_k3": (0, 0),
    }
    for group in ("bgb_frequent", "bgb_rare"):
        assert sorted(len(query.tokens) for query in queries if query.group == group) == [2, 3, 4, 5]
    by_id = {query.query_id: query for query in queries}
    assert by_id["bgb_rare_k3"].expected == {"bgb_0001.txt": [0]}
    assert by_id["bgb_frequent_k2"].tokens == ("nach", "massgabe")
    selection = {entry["query_id"]: entry for entry in fixture["query_selection"]}
    assert min(selection["bgb_common_words_k2"]["df_terms"]) > 2000
    assert selection["bgb_missing_k3"]["df_terms"][-1] == 0
    assert sum(entry["also_in_manifest_phrases"] for entry in selection.values()) == 6


# ---------------------------------------------------------------- Kleinkorpus

TEXTS = {
    "bgb_0001.txt": "Beginn der Rechtsfähigkeit\nNach Maßgabe der die Regel.\n",
    "bgb_0002.txt": "Die Regel gilt nach Maßgabe, nach MASSGABE der die Frist.\n",
    "bgb_0003.txt": "Maßgabe allein; der Rest gilt.\n",
}
# Von Hand gezählt: Tokens je Dokument 8/10/5, V=11, P=19.
FAKE_QUERIES = [
    ("fake_k2", "nach Maßgabe", "fake", ["nach", "massgabe"], [2, 3], {"bgb_0001.txt": [3], "bgb_0002.txt": [3, 5]}),
    ("fake_words_k2", "der die", "fake_words", ["der", "die"], [3, 2], {"bgb_0001.txt": [5], "bgb_0002.txt": [7]}),
    ("fake_k3", "Beginn der Rechtsfähigkeit", "fake", ["beginn", "der", "rechtsfähigkeit"], [1, 3, 1],
     {"bgb_0001.txt": [0]}),
    ("fake_wrong_order_k2", "Regel nach", "fake_wrong_order", ["regel", "nach"], [2, 2], {}),
    ("fake_missing_k2", "zum Server", "fake_missing", ["zum", "server"], [0, 0], {}),
]


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _entry(text, terms, df_terms, positions):
    lines = [f"{identifier}\t{','.join(map(str, starts))}" for identifier, starts in sorted(positions.items())]
    return {"query": text, "note": "Test", "terms": terms, "df_terms": df_terms, "document_count": len(positions),
            "match_count": sum(map(len, positions.values())),
            "positions_sha256": _sha("\n".join(lines).encode("utf-8")), "positions": positions}


def write_fake_bgb(base):
    folder = base / "daten/real/bgb"
    (folder / "dokumente").mkdir(parents=True)
    documents = []
    for name, text in sorted(TEXTS.items()):
        payload = text.encode("utf-8")
        (folder / "dokumente" / name).write_bytes(payload)
        documents.append({"document_id": name, "source_path": name, "bytes": len(payload), "sha256": _sha(payload)})
    corpus = _sha("".join(f"{entry['sha256']}  {entry['document_id']}\n" for entry in documents).encode("utf-8"))
    entries = [_entry(text, terms, df, positions) for _, text, _, terms, df, positions in FAKE_QUERIES]
    manifest = {"dataset_id": "fake-bgb-v1", "corpus_root": "dokumente", "corpus_sha256": corpus,
                "retrieved_at": "2026-10-14T00:00:00+02:00", "documents": documents,
                "independent_expectations": {
                    "dataset_id": "fake-bgb-v1", "corpus_sha256": corpus, "document_count": 3, "token_count": 23,
                    "vocabulary_size": 11, "posting_count": 19, "first_document_id": "bgb_0001.txt",
                    "prefix_tokens_bgb_0001": ["beginn", "der", "rechtsfähigkeit"], "phrases": [entries[0]]}}
    proposals = {"dataset_id": "fake-bgb-v1", "corpus_sha256": corpus, "method": "test",
                 "reihe_04_phrasensuche": entries}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (folder / "anfragevorschlaege.json").write_text(json.dumps(proposals, ensure_ascii=False), encoding="utf-8")
    return corpus


@pytest.fixture
def fake(modules, monkeypatch, tmp_path):
    """Kleinkorpus statt BGB, Ergebnisordner im temporären Verzeichnis."""
    run_bgb = modules["run_bgb"]
    base = tmp_path / "repo"
    corpus = write_fake_bgb(base)
    parameters = copy.deepcopy(run_bgb.PARAMETERS)
    parameters["real"].update({"dataset": "fake-bgb-v1", "corpus_sha256": corpus, "document_count": 3,
                               "token_count": 23, "vocabulary_size": 11, "posting_count": 19})
    parameters["queries"] = [{"query_id": query_id, "text": text, "group": group, "phrase_length": len(terms),
                              "document_count": len(positions), "match_count": sum(map(len, positions.values()))}
                             for query_id, text, group, terms, _, positions in FAKE_QUERIES]
    monkeypatch.setattr(run_bgb, "PARAMETERS", parameters)
    monkeypatch.setattr(run_bgb, "DATA_ROOT", base)
    monkeypatch.setattr(run_bgb, "MESSUNGEN", tmp_path / "messungen")
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    return SimpleNamespace(base=base, folder=base / "daten/real/bgb", messungen=tmp_path / "messungen",
                           parameters=parameters)


def _edit_json(path, change):
    value = json.loads(path.read_text(encoding="utf-8"))
    change(value)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_fixture_checks_multiple_documents_and_every_expectation(modules, fake):
    run_bgb = modules["run_bgb"]
    root, tokens, queries, fixture = run_bgb.bgb_fixture()
    assert root == fake.folder / "dokumente"
    assert [len(sequence) for sequence in tokens.values()] == [8, 10, 5]
    assert {query.query_id: query.expected for query in queries} == {
        query_id: positions for query_id, _, _, _, _, positions in FAKE_QUERIES}
    assert queries[0].text == "nach Maßgabe" and queries[0].tokens == ("nach", "massgabe")
    assert fixture["statistics"] == {"document_count": 3, "token_count": 23, "vocabulary_size": 11, "posting_count": 19}


@pytest.mark.parametrize("damage,message", [
    (lambda f: _edit_json(f.folder / "anfragevorschlaege.json",
                          lambda v: v["reihe_04_phrasensuche"][1]["positions"].update({"bgb_0002.txt": [6]})),
     "Startpositionen"),
    (lambda f: _edit_json(f.folder / "manifest.json",
                          lambda v: v["independent_expectations"]["phrases"][0].update({"match_count": 4})),
     "widersprechen"),
    (lambda f: f.parameters["queries"][0].update({"match_count": 4}), "Startzahl"),
    (lambda f: (f.folder / "dokumente/bgb_0004.txt").write_text("neu\n", encoding="utf-8"), "andere Dateien"),
    (lambda f: (f.folder / "dokumente/bgb_0003.txt").write_text("Maßgabe allein; der Rest galt.\n", encoding="utf-8"),
     "weicht vom Manifest ab"),
])
def test_fixture_rejects_changed_data_or_expectations(modules, fake, damage, message):
    damage(fake)
    with pytest.raises(AssertionError, match=message):
        modules["run_bgb"].bgb_fixture()


def test_target_directory_never_overwrites(modules, fake):
    run_bgb = modules["run_bgb"]
    for name in ("", ".", "..", "a/b", "../04_bgb"):
        with pytest.raises(SystemExit, match="Ordnername"):
            run_bgb.target_directory(name)
    (fake.messungen / "voll").mkdir(parents=True)
    (fake.messungen / "voll" / "raw.csv").write_text("x\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="nicht leer"):
        run_bgb.target_directory("voll")
    (fake.messungen / "leer").mkdir()
    assert run_bgb.target_directory("leer") == fake.messungen / "leer"
    with pytest.raises(SystemExit, match="nicht leer"):
        run_bgb.main(["--pilot", "--ausgabe", "voll"])


def _in_process_workers(modules, monkeypatch):
    """Speicherworker im Testprozess (Kleinkorpus); eigene Kennung je Worker statt PID."""
    memory, run = modules["memory"], modules["run"]
    pids = iter(range(70001, 70100))
    current = {}

    def fake_run(command, cwd, check):
        arguments = dict(zip(command[2::2], command[3::2]))
        current["pid"] = next(pids)
        memory.worker(arguments["--metadata"], arguments["--dataset"], arguments["--algorithm"],
                      Path(arguments["--output"]))

    monkeypatch.setattr(memory, "os", SimpleNamespace(getpid=lambda: current["pid"]))
    monkeypatch.setattr(run, "subprocess", SimpleNamespace(run=fake_run, check_output=subprocess.check_output))


def test_pilot_and_final_end_to_end_with_lock_and_memory(modules, fake, monkeypatch):
    run_bgb, verify = modules["run_bgb"], modules["verify_bgb"]
    _in_process_workers(modules, monkeypatch)
    with pytest.raises(SystemExit, match="Zuerst --pilot"):
        run_bgb.main(["--ausgabe", "f0", "--pilot-ordner", "p"])
    run_bgb.main(["--pilot", "--ausgabe", "p"])
    pilot = fake.messungen / "p"
    decision = json.loads((pilot / "pilot_decision.json").read_text(encoding="utf-8"))
    assert decision["pilot_correct"] and decision["python_hash_seed"] == "0"
    assert decision["verified_counts"] == {"raw_rows": 36, "summary_groups": 12, "files": 3, "memory_rows": 6}
    metadata = json.loads((pilot / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["series"] == "04_bgb" and metadata["run_kind"] == "pilot" and metadata["run_id"] == "p"
    assert metadata["measurement_plan"] == run_bgb.PARAMETERS["pilot_plan"]
    assert (pilot / "code_source/themen/04_positionsindex_phrasensuche/experimente/run_bgb.py").is_file()
    assert verify.verify_directory(pilot) == (36, 12, 3, 6)
    with pytest.raises(SystemExit, match="anderer Ordnername"):
        run_bgb.main(["--ausgabe", "p2", "--pilot-ordner", "p2"])
    run_bgb.main(["--ausgabe", "f", "--pilot-ordner", "p", "--hintergrundlast", "Test: Kleinkorpus"])
    final = fake.messungen / "f"
    metadata = json.loads((final / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["run_kind"] == "final" and metadata["background_load"] == "Test: Kleinkorpus"
    assert metadata["pilot_directory"].endswith("/p")
    assert verify.verify_directory(final) == (240, 12, 3, 6)
    verify.main(["--eingabe", "f"])


def test_final_gates_hash_seed_code_data_parameters_and_memory(modules, fake, monkeypatch):
    run_bgb = modules["run_bgb"]
    _in_process_workers(modules, monkeypatch)
    run_bgb.main(["--pilot", "--ausgabe", "p"])
    path = fake.messungen / "p" / "pilot_decision.json"
    assert run_bgb.require_pilot(path)["pilot_correct"] is True
    monkeypatch.setenv("PYTHONHASHSEED", "1")
    with pytest.raises(SystemExit, match="PYTHONHASHSEED"):
        run_bgb.require_pilot(path)
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    real_hashes = run_bgb.code_hashes
    monkeypatch.setattr(run_bgb, "code_hashes", lambda: {**real_hashes(), "neu.py": "0"})
    with pytest.raises(SystemExit, match="Messcode"):
        run_bgb.require_pilot(path)
    monkeypatch.setattr(run_bgb, "code_hashes", real_hashes)
    original = path.read_text(encoding="utf-8")
    _edit_json(path, lambda value: value["locked_parameters"].update({"memory_repeats": 4}))
    with pytest.raises(SystemExit, match="Parameter"):
        run_bgb.require_pilot(path)
    path.write_text(original, encoding="utf-8")
    _edit_json(fake.folder / "anfragevorschlaege.json", lambda value: value.update({"method": "anders"}))
    with pytest.raises(SystemExit, match="Datenstand"):
        run_bgb.require_pilot(path)
    _edit_json(fake.folder / "anfragevorschlaege.json", lambda value: value.update({"method": "test"}))
    (fake.messungen / "p" / "memory.json").rename(fake.messungen / "p" / "memory.weg")
    with pytest.raises(SystemExit, match="Speicherlauf"):
        run_bgb.require_pilot(path)


def test_verifier_detects_timing_statistics_metadata_archive_and_data_tampering(modules, fake, monkeypatch):
    run_bgb, verify, results = modules["run_bgb"], modules["verify_bgb"], modules["verify_results"]
    _in_process_workers(modules, monkeypatch)
    run_bgb.main(["--pilot", "--ausgabe", "p"])
    directory = fake.messungen / "p"
    with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    results.verify_timing_rows(rows, summary, metadata)
    bad = copy.deepcopy(rows)
    bad[0]["elapsed_ns"] = str(int(bad[0]["elapsed_ns"]) + 1)
    with pytest.raises(AssertionError):
        results.verify_timing_rows(bad, summary, metadata)
    bad = copy.deepcopy(rows)
    next(row for row in bad if row["phase"] == "query")["hit_count"] = "987"
    with pytest.raises(AssertionError):
        results.verify_timing_rows(bad, summary, metadata)
    bad = copy.deepcopy(summary)
    bad[0]["median_ms"] += .01
    with pytest.raises(AssertionError):
        results.verify_timing_rows(rows, bad, metadata)
    bad = copy.deepcopy(metadata)
    bad["datasets"][0]["queries"][0]["expected_positions"]["bgb_0002.txt"] = [3]
    with pytest.raises(AssertionError, match="Neuberechnung"):
        verify.verify_corpus(bad)
    bad = copy.deepcopy(metadata)
    bad["datasets"][0]["queries"][0]["position_count"] = 4
    with pytest.raises(AssertionError):
        verify.verify_contract(directory, bad)
    bad = copy.deepcopy(metadata)
    bad["measurement_plan"]["repeats"] = 20
    with pytest.raises(AssertionError, match="Messplan"):
        verify.verify_contract(directory, bad)
    archived = directory / "code_source/themen/04_positionsindex_phrasensuche/experimente/run_bgb.py"
    archived.write_bytes(archived.read_bytes() + b"\n")
    with pytest.raises(AssertionError, match="Quelltextarchiv"):
        verify.verify_directory(directory)
    archived.write_bytes(archived.read_bytes()[:-1])
    assert verify.verify_directory(directory)[0] == 36
    (fake.folder / "dokumente/bgb_0003.txt").write_text("Maßgabe allein; der Rest galt.\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Manifest"):
        verify.verify_directory(directory)


def test_memory_worker_selects_series_from_metadata(modules):
    memory, run, run_bgb = modules["memory"], modules["run"], modules["run_bgb"]
    assert memory.series_source({}) is run
    assert memory.series_source({"series": "04_bgb"}) is run_bgb


def test_old_runner_refuses_nonempty_delivered_targets(modules, monkeypatch, tmp_path):
    run = modules["run"]
    delivered = tmp_path / "ergebnisse/messungen/04_pilot"
    delivered.mkdir(parents=True)
    (delivered / "raw.csv").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(run, "ROOT", tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("darf nicht messen")

    monkeypatch.setattr(run, "timing_run", forbidden)
    monkeypatch.setattr(sys, "argv", ["run.py", "--pilot"])
    with pytest.raises(SystemExit, match="nicht leer"):
        run.main()
