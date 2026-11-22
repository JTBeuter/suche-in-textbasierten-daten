"""BGB-Realteil der Reihe 05: Mehrdokumentprüfung, feste Profile, Abschnitt 3.6.

Die kleine Sammlung ``kleine_sammlung`` ist von Hand berechnet: Tokens,
Häufigkeiten, Treffer und Hashformeln stehen als Literale im Test und nicht
als Ausgabe des Produktivcodes. Das echte BGB wird zusätzlich gegen die
unabhängig berechneten Werte aus ``daten/real/bgb`` geprüft.
"""

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil

import pytest

from experimentelle_analyse import pipeline, provenance
from experimentelle_analyse.analysis import AMORTISATION_FIELDS, amortisation_rows, analyse
from experimentelle_analyse.costs import amortisation_3_6
from experimentelle_analyse.datasets import build_datasets, verify_real_snapshot
from experimentelle_analyse.schema import read_csv, validate_config
from experimentelle_analyse.verify import verify_run


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENTE = ROOT / "themen/05_experimentelle_analyse/experimente"
SPEC = importlib.util.spec_from_file_location("render_bgb05", EXPERIMENTE / "render_bgb.py")
RENDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDER)

TEXTE = {
    "a.txt": "Der Gläubiger setzt dem Schuldner eine Frist.\n",
    "b.txt": "Der Mieter zahlt die Miete im Sinne des Vertrags.\n",
    "c.txt": "Im Sinne des Gesetzes haftet der Vermieter, nicht der Mieter.\n",
}
PROFILANFRAGEN = [
    {"kind": "word", "category": "missing", "text": "Server"},
    {"kind": "word", "category": "frequent", "text": "der"},
    {"kind": "word", "category": "rare", "text": "Frist"},
    {"kind": "and", "category": "present", "text": "Gläubiger Schuldner Frist"},
    {"kind": "or", "category": "present", "text": "Mieter Vermieter Miete"},
    {"kind": "phrase", "category": "present", "text": "im Sinne des"},
]


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def kleine_sammlung(root):
    """Drei Dokumente im Manifestformat des BGB, alle Erwartungen von Hand."""
    (root / "dokumente").mkdir(parents=True)
    (root / "quelle").mkdir()
    archiv = b"unveraenderliches Testarchiv"
    (root / "quelle/archiv.bin").write_bytes(archiv)
    dokumente = []
    for name, text in TEXTE.items():
        payload = text.encode("utf-8")
        (root / "dokumente" / name).write_bytes(payload)
        dokumente.append({"document_id": name, "source_path": name, "bytes": len(payload), "sha256": sha(payload)})
    korpus = sha("".join(f"{d['sha256']}  {d['document_id']}\n" for d in dokumente).encode("utf-8"))
    sinne = sha("b.txt\t5\nc.txt\t0".encode("utf-8"))
    manifest = {
        "dataset_id": "kleine-sammlung-v1", "corpus_root": "dokumente",
        "source_file": "quelle/archiv.bin", "source_bytes": len(archiv), "source_sha256": sha(archiv),
        "documents": dokumente, "corpus_sha256": korpus,
        "independent_expectations": {
            "corpus_sha256": korpus, "document_count": 3, "token_count": 26, "vocabulary_size": 19,
            "posting_count": 25, "positional_posting_count": 26,
            "first_document_id": "a.txt", "last_document_id": "c.txt",
            "prefix_tokens_a": ["der", "gläubiger", "setzt"],
            "words": [
                {"query": "der", "term": "der", "df": 3, "cf": 4, "first_document": "a.txt",
                 "first_position": 0, "last_document": "c.txt", "document_ids": ["a.txt", "b.txt", "c.txt"]},
                {"query": "Frist", "term": "frist", "df": 1, "cf": 1, "first_document": "a.txt",
                 "first_position": 6, "last_document": "a.txt", "document_ids": ["a.txt"]},
                {"query": "Server", "term": "server", "df": 0, "cf": 0, "document_ids": []},
            ],
            "phrases": [{"query": "im Sinne des", "terms": ["im", "sinne", "des"], "df_terms": [2, 2, 2],
                         "document_count": 2, "match_count": 2, "positions_sha256": sinne,
                         "positions": {"b.txt": [5], "c.txt": [0]}}],
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    vorschlaege = {"corpus_sha256": korpus, "reihe_05_profile": [
        {"kind": "and", "terms": ["gläubiger", "schuldner", "frist"], "df": [1, 1, 1],
         "hit_count": 1, "document_ids": ["a.txt"]},
        {"kind": "or", "terms": ["mieter", "vermieter", "miete"], "df": [2, 1, 1],
         "hit_count": 2, "document_ids": ["b.txt", "c.txt"]},
    ]}
    (root / "anfragevorschlaege.json").write_text(json.dumps(vorschlaege, ensure_ascii=False), encoding="utf-8")
    return root


def sammlung_config(root, **changes):
    config = {"schema_version": 1, "mode": "pilot", "seed": 17, "warmups": 0, "repeats": 2, "block_size": 1,
              "memory_repeats": 2, "total_repeats": 2, "sequence_block_size": 2,
              "amortisation_table": "abschnitt_3_6", "q_values": [0, 1, 2],
              "datasets": [{"id": "klein", "kind": "real", "path": str(root), "queries": deepcopy(PROFILANFRAGEN)}]}
    config.update(changes)
    return config


def test_small_collection_is_checked_document_by_document(tmp_path):
    manifest, tokens = verify_real_snapshot(kleine_sammlung(tmp_path / "quelle"))
    assert manifest["dataset_id"] == "kleine-sammlung-v1"
    assert tokens == {
        "a.txt": ("der", "gläubiger", "setzt", "dem", "schuldner", "eine", "frist"),
        "b.txt": ("der", "mieter", "zahlt", "die", "miete", "im", "sinne", "des", "vertrags"),
        "c.txt": ("im", "sinne", "des", "gesetzes", "haftet", "der", "vermieter", "nicht", "der", "mieter"),
    }


@pytest.mark.parametrize("schaden", [
    "zusatzdokument", "dokument", "archiv", "korpushash", "tokenzahl", "praefix",
    "wortliste", "phrasenstarts", "vorschlagshash",
])
def test_small_collection_rejects_damage(tmp_path, schaden):
    root = kleine_sammlung(tmp_path / "quelle")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    erwartung = manifest["independent_expectations"]
    if schaden == "zusatzdokument":
        (root / "dokumente/d.txt").write_text("undokumentiert\n", encoding="utf-8")
    elif schaden == "dokument":
        (root / "dokumente/b.txt").write_text("Der Mieter zahlt.\n", encoding="utf-8")
    elif schaden == "archiv":
        (root / "quelle/archiv.bin").write_bytes("verändert".encode("utf-8"))
    elif schaden == "korpushash":
        manifest["corpus_sha256"] = "0" * 64
    elif schaden == "tokenzahl":
        erwartung["token_count"] = 27
    elif schaden == "praefix":
        erwartung["prefix_tokens_a"] = ["die", "gläubiger"]
    elif schaden == "wortliste":
        erwartung["words"][0]["document_ids"] = ["a.txt", "b.txt"]
    elif schaden == "phrasenstarts":
        erwartung["phrases"][0]["positions"] = {"b.txt": [5], "c.txt": [1]}
    if schaden != "vorschlagshash":
        (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ValueError):
            verify_real_snapshot(root)
    else:
        vorschlaege = json.loads((root / "anfragevorschlaege.json").read_text(encoding="utf-8"))
        vorschlaege["reihe_05_profile"][1]["document_ids"] = ["b.txt"]
        (root / "anfragevorschlaege.json").write_text(json.dumps(vorschlaege, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ValueError, match="independent expectation"):
            build_datasets(sammlung_config(root), tmp_path / "daten")


def test_fixed_profile_queries_get_oracle_results_and_crosschecks(tmp_path):
    root = kleine_sammlung(tmp_path / "quelle")
    dataset, = build_datasets(sammlung_config(root), tmp_path / "daten")
    assert dataset["root"] == tmp_path / "daten/klein/corpus/dokumente"
    queries = {query["id"]: query for query in dataset["queries"]}
    assert {key: (value["expected"], value["cf"], value["df"]) for key, value in queries.items()} == {
        "klein:word:missing:k1": ([], [0], [0]),
        "klein:word:frequent:k1": (["a.txt", "b.txt", "c.txt"], [4], [3]),
        "klein:word:rare:k1": (["a.txt"], [1], [1]),
        "klein:and:present:k3": (["a.txt"], [1, 1, 1], [1, 1, 1]),
        "klein:or:present:k3": (["b.txt", "c.txt"], [2, 1, 1], [2, 1, 1]),
        "klein:phrase:present:k3": ({"b.txt": [5], "c.txt": [0]}, [2, 2, 2], [2, 2, 2]),
    }
    assert queries["klein:phrase:present:k3"]["position_count"] == 2
    manifest = dataset["manifest"]
    assert manifest["query_generator_version"] == "05-queries-fixed-v1"
    assert manifest["document_count"] == 3 and manifest["total_tokens"] == 26
    assert manifest["corpus_root"] == "dokumente"
    assert set(manifest["snapshot_files"]) == {"manifest.json", "quelle/archiv.bin", "anfragevorschlaege.json"}
    assert manifest["conversion_check"] is None
    sources = {entry["query_id"]: entry["sources"] for entry in manifest["query_crosschecks"]}
    assert sources["klein:and:present:k3"] == ["anfragevorschlaege:reihe_05_profile"]
    assert sources["klein:phrase:present:k3"] == ["manifest:independent_expectations.phrases"]
    profiles = pipeline.select_profiles(dataset["queries"])
    assert [(p["id"], p["query_id"], p["algorithm"]) for p in profiles] == [
        ("word_missing", "klein:word:missing:k1", "index"),
        ("word_frequent", "klein:word:frequent:k1", "index"),
        ("word_rare", "klein:word:rare:k1", "index"),
        ("and_present3", "klein:and:present:k3", "index_shortest"),
        ("or_present3", "klein:or:present:k3", "index"),
        ("phrase_present3", "klein:phrase:present:k3", "index"),
    ]


@pytest.mark.parametrize("change", ["no_queries", "missing_has_hits", "unknown_kind", "extra_key",
                                    "boolean_duplicate", "no_independent_record", "synthetic_queries"])
def test_fixed_query_definition_errors_fail_before_output(tmp_path, change):
    root = kleine_sammlung(tmp_path / "quelle")
    config = sammlung_config(root)
    queries = config["datasets"][0]["queries"]
    if change == "no_queries":
        del config["datasets"][0]["queries"]
    elif change == "missing_has_hits":
        queries[0]["text"] = "Mieter"
    elif change == "unknown_kind":
        queries[0]["kind"] = "regex"
    elif change == "extra_key":
        queries[0]["note"] = "zusätzlich"
    elif change == "boolean_duplicate":
        queries[3]["text"] = "Frist Frist Gläubiger"
    elif change == "no_independent_record":
        queries[2]["text"] = "Vertrags"
    else:
        config["datasets"] = [{"id": "s", "kind": "synthetic", "documents": 2, "length": 100,
                               "vocabulary": 32, "queries": deepcopy(PROFILANFRAGEN)}]
    with pytest.raises(ValueError):
        build_datasets(config, tmp_path / "daten")


def test_real_bgb_profiles_match_manifest_and_suggestions(tmp_path):
    """Echtes BGB: 2.486 Dokumente, Offline-Neuerzeugung, sechs feste Profilanfragen."""
    config = json.loads((EXPERIMENTE / "bgb_pilot.json").read_text(encoding="utf-8"))
    before = {path.relative_to(ROOT / "daten/real/bgb").as_posix(): sha(path.read_bytes())
              for path in (ROOT / "daten/real/bgb").rglob("*") if path.is_file()}
    dataset, = build_datasets(config, tmp_path)
    manifest = dataset["manifest"]
    assert (manifest["document_count"], manifest["total_tokens"], manifest["actual_vocabulary"],
            manifest["raw_bytes"]) == (2486, 213718, 11398, 1587032)
    assert manifest["source_summary"]["corpus_sha256"] == "dc1641fd49dfa45270a1865f454abd64cf7cf94d79b37af9657ff97d7602eadf"
    assert manifest["conversion_check"] is not None
    observed = {query["id"]: (query["terms"], query["hit_count"], query["position_count"]) for query in dataset["queries"]}
    assert observed == {
        "bgb:word:missing:k1": (["server"], 0, None),
        "bgb:word:frequent:k1": (["der"], 2280, None),
        "bgb:word:rare:k1": (["verbindung"], 16, None),
        "bgb:and:present:k3": (["gläubiger", "schuldner", "frist"], 5, None),
        "bgb:or:present:k3": (["mieter", "vermieter", "miete"], 105, None),
        "bgb:phrase:present:k3": (["im", "sinne", "des"], 62, 85),
    }
    rare = next(query for query in dataset["queries"] if query["category"] == "rare")
    assert rare["cf"] == [21]
    conjunction = next(query for query in dataset["queries"] if query["kind"] == "and")
    assert conjunction["expected"] == ["bgb_0204.txt", "bgb_0264.txt", "bgb_0281.txt", "bgb_0323.txt", "bgb_0415.txt"]
    assert all(entry["sources"] for entry in manifest["query_crosschecks"])
    after = {path.relative_to(ROOT / "daten/real/bgb").as_posix(): sha(path.read_bytes())
             for path in (ROOT / "daten/real/bgb").rglob("*") if path.is_file()}
    assert after == before


def test_bgb_configs_bind_pilot_and_main_with_unchanged_grid():
    pilot = json.loads((EXPERIMENTE / "bgb_pilot.json").read_text(encoding="utf-8"))
    main = json.loads((EXPERIMENTE / "bgb_main.json").read_text(encoding="utf-8"))
    old = json.loads((EXPERIMENTE / "main.json").read_text(encoding="utf-8"))
    for config in (pilot, main):
        assert validate_config(config) == config
        assert [dataset["id"] for dataset in config["datasets"]] == ["bgb"]
        assert config["q_values"] == old["q_values"]
        assert config["amortisation_table"] == "abschnitt_3_6"
    assert pipeline.semantic_config(pilot) == pipeline.semantic_config(main)
    assert (pilot["mode"], main["mode"], main["pilot_directory"]) == ("pilot", "main", "ergebnisse/messungen/05_bgb_pilot")
    assert (main["warmups"], main["repeats"], main["total_repeats"]) == (old["warmups"], old["repeats"], old["total_repeats"])


@pytest.mark.parametrize("value", ["abschnitt_3_5", True, 1])
def test_unknown_amortisation_table_is_rejected(value):
    config = json.loads((EXPERIMENTE / "bgb_pilot.json").read_text(encoding="utf-8"))
    config["amortisation_table"] = value
    with pytest.raises(ValueError):
        validate_config(config)


@pytest.mark.parametrize("aufbau,direkt,index,erwartet", [
    (60000, 20000, 10000, (6.0, 6, True, 6)),
    (70000, 10000, 2000, (8.75, 9, False, 9)),
    (1, 3, 2, (1.0, 1, True, 1)),
    (5000, 2000, 2000, (None, None, False, "nie")),
    (5000, 2000, 2500, (None, None, False, "nie")),
])
def test_section_3_6_quantities_are_hand_calculated(aufbau, direkt, index, erwartet):
    values = amortisation_3_6(aufbau, direkt, index)
    assert (values["q_stern"], values["q_stern_aufgerundet"], values["gleichstand_bei_q_stern"],
            values["amortisation"]) == erwartet
    assert (values["t_aufbau_ns"], values["t_direkt_ns"], values["t_index_ns"]) == (aufbau, direkt, index)
    assert values["differenz_ns"] == direkt - index


def test_section_3_6_rejects_negative_times():
    with pytest.raises(ValueError):
        amortisation_3_6(-1, 2, 1)


def test_amortisation_rows_take_model_medians_and_tested_stages():
    meta = {"datasets": [{"id": "d", "queries": [{"id": "q", "text": "Wort"}]}]}
    observations = [{"query_count": count, "index_cheaper_repeats": positive, "repeats": 3,
                     "paired_saving_ns": {"median": saving}}
                    for count, positive, saving in ((0, 0, -60000), (6, 3, 2000), (7, 1, -500), (9, 3, 30000), (10, 3, 40000))]
    model = {"dataset_id": "d", "profile_id": "p", "query_id": "q", "index_algorithm": "index",
             "build_index_ns": 60000.0, "query_direct_ns": 20000.0, "query_index_ns": 10000.0,
             "has_advantage": True, "first_cheaper_q": 7, "observations": observations}
    row, = amortisation_rows(meta, [model])
    assert (row["q_stern"], row["q_stern_aufgerundet"], row["amortisation"], row["first_cheaper_q_strict"]) == (6.0, 6, 6, 7)
    assert (row["first_stage_all_pairs_positive"], row["median_saving_ns_there"], row["positive_pairs_there"]) == (6, 2000, 3)
    assert row["from_stage_all_higher_all_pairs_positive"] == 9
    model.update(query_index_ns=25000.0, has_advantage=False, first_cheaper_q=None,
                 observations=[{**o, "index_cheaper_repeats": 0} for o in observations])
    row, = amortisation_rows(meta, [model])
    assert (row["amortisation"], row["q_stern"], row["first_stage_all_pairs_positive"],
            row["from_stage_all_higher_all_pairs_positive"]) == ("nie", None, None, None)


def test_main_run_requires_hash_seed_zero_before_any_output(tmp_path, monkeypatch):
    config = json.loads((EXPERIMENTE / "bgb_main.json").read_text(encoding="utf-8"))
    path = tmp_path / "main.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("PYTHONHASHSEED", "1")
    with pytest.raises(ValueError, match="PYTHONHASHSEED=0"):
        pipeline.run_experiment(path, tmp_path / "ziel")
    monkeypatch.delenv("PYTHONHASHSEED")
    with pytest.raises(ValueError, match="PYTHONHASHSEED=0"):
        pipeline.run_experiment(path, tmp_path / "ziel")
    assert not (tmp_path / "ziel").exists()


def test_background_load_snapshot_names_short_commands_only(monkeypatch):
    snapshot = provenance.background_load("probe")
    assert snapshot["label"] == "probe" and snapshot["logical_cpus"] == os.cpu_count()
    if snapshot["loadavg_1_5_15"] is not None:
        assert len(snapshot["loadavg_1_5_15"]) == 3
    for process in snapshot["top_cpu_processes"] or []:
        assert set(process) == {"pid", "cpu_percent", "command"}
        assert "/" not in process["command"] or len(process["command"]) <= 15

    def missing(*_args, **_kwargs):
        raise OSError("kein ps")

    monkeypatch.setattr(provenance.subprocess, "run", missing)
    assert provenance.background_load("ohne")["top_cpu_processes"] is None


def test_small_collection_end_to_end_run_verify_analyse_and_render(tmp_path, monkeypatch):
    """Vollständiger Kurzlauf: Messung, strenge Prüfung, Abschnitt 3.6, Bänderdiagramme."""
    root = kleine_sammlung(tmp_path / "quelle")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(sammlung_config(root), ensure_ascii=False), encoding="utf-8")
    run = tmp_path / "lauf"
    result = pipeline.run_experiment(config_path, run)
    assert result["memory_rows"] == 4
    meta = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    assert meta["status"] == "complete" and meta["datasets"][0]["root"] == "datasets/klein/corpus/dokumente"
    labels = [entry["label"] for entry in meta["background_load"]]
    assert labels[0] == "vor_messung" and labels[-2:] == ["nach_zeitmessung", "nach_speichermessung"]
    assert sum(label.endswith(":nach_gesamtablaeufen") for label in labels) == 6
    assert verify_run(run)["status"] == "verified"
    with pytest.raises(ValueError, match="Messziel muss leer sein"):
        pipeline.run_experiment(config_path, run)

    analysis = tmp_path / "auswertung"
    analyse(run, analysis)
    table = json.loads((analysis / "amortisation.json").read_text(encoding="utf-8"))
    models = json.loads((analysis / "models.json").read_text(encoding="utf-8"))
    assert [row["profile_id"] for row in table] == [model["profile_id"] for model in models]
    for row, model in zip(table, models):
        assert row["t_aufbau_ns"] == model["build_index_ns"]
        assert (row["t_direkt_ns"], row["t_index_ns"]) == (model["query_direct_ns"], model["query_index_ns"])
        if model["delta_t_ns"] > 0:
            assert row["q_stern"] == pytest.approx(model["equality_q"])
        else:
            assert row["amortisation"] == "nie"
    csv_rows = read_csv(analysis / "amortisation.csv", AMORTISATION_FIELDS)
    assert len(csv_rows) == 6 and all(";" not in value for row in csv_rows for value in row.values())
    lineage = json.loads((analysis / "plot_manifest.json").read_text(encoding="utf-8"))
    assert {"amortisation.json", "amortisation.csv"} <= set(lineage["output_sha256"])
    with pytest.raises(ValueError, match="nicht überschrieben"):
        analyse(run, analysis)

    outputs = RENDER.render(run, analysis)
    assert set(outputs) == {f"{name}.{ext}" for name in RENDER.NAMEN for ext in RENDER.FORMATE}
    manifest = json.loads((analysis / "render_manifest.json").read_text(encoding="utf-8"))
    assert manifest["output_sha256"] == outputs and manifest["verification"] == "strict"
    with pytest.raises(ValueError, match="nicht überschrieben"):
        RENDER.render(run, analysis)

    # Archivmodus: nur der Vergleich mit dem aktiven Code entfällt, das Archiv bleibt geprüft.
    from experimentelle_analyse import verify as verify_module
    changed = {**meta["code_sha256"], "themen/neu.py": "0" * 64}
    monkeypatch.setattr(verify_module, "source_hashes", lambda: changed)
    with pytest.raises(ValueError, match="Aktiver Quellcode"):
        verify_run(run)
    archived = verify_run(run, archive_only=True)
    assert archived["status"] == "verified_archive_only"
    assert archived["active_source_differences"] == ["themen/neu.py"]
    damaged = next((run / "code_source").rglob("*.py"))
    damaged.write_bytes(damaged.read_bytes() + b"\n# beschaedigt\n")
    with pytest.raises(ValueError, match="Quellarchiv beschädigt"):
        verify_run(run, archive_only=True)


def test_render_refuses_analysis_of_another_run(tmp_path):
    # Bildmanifest des Hauptlaufs, Rohwerte des Pilots: keine Diagramme.
    analysis = tmp_path / "auswertung"
    analysis.mkdir()
    shutil.copyfile(ROOT / "ergebnisse/abbildungen/05/plot_manifest.json", analysis / "plot_manifest.json")
    with pytest.raises(ValueError, match="anderen Rohwertstand"):
        RENDER.render(ROOT / "ergebnisse/messungen/05_pilot", analysis, archive_only=True)
    assert sorted(path.name for path in analysis.iterdir()) == ["plot_manifest.json"]
