"""Enge Paketkompatibilität bei unveränderten historischen Suchmessungen."""

import ast
import hashlib
from pathlib import Path
import tomllib
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
VERIFIER = Path("themen/03_boolesche_mehrwortsuche/experimente/verify_results.py")
FINAL03 = ROOT / "ergebnisse/messungen/03_boolesche_mehrwortsuche"


@pytest.fixture
def compatibility(tmp_path):
    # Load only the narrowly scoped audit function, without sibling experiment
    # imports, sys.path changes or timing operations.
    source = ast.parse((ROOT / VERIFIER).read_text())
    function = next(node for node in source.body if isinstance(node, ast.FunctionDef)
                    and node.name == "verify_active_source")
    environment = {"Path": Path, "ROOT": tmp_path, "ast": ast, "tomllib": tomllib,
                   "sha": lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(VERIFIER), "exec"), environment)
    for relative in (Path("pyproject.toml"), VERIFIER):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    return SimpleNamespace(root=tmp_path, verify=environment["verify_active_source"])


def archived_sha(relative):
    return hashlib.sha256((FINAL03 / "code_source" / relative).read_bytes()).hexdigest()


def test_only_additive_packaging_and_documented_audit_change_allowed(compatibility):
    for relative in ("pyproject.toml", VERIFIER.as_posix()):
        compatibility.verify(FINAL03, relative, archived_sha(relative))


@pytest.mark.parametrize("before,after", [
    ('requires-python = ">=3.11"', 'requires-python = ">=3.12"'),
    ('dependencies = []', 'dependencies = ["external-search-service"]'),
    ('version = "0.1.0"', 'version = "0.2.0"'),
    ('gemeinsam = "gemeinsam/src/gemeinsam"', 'gemeinsam = "other"'),
])
def test_historical_packaging_rejects_other_changes(compatibility, before, after):
    path = compatibility.root / "pyproject.toml"
    text = path.read_text()
    assert before in text
    path.write_text(text.replace(before, after, 1))
    with pytest.raises(AssertionError):
        compatibility.verify(FINAL03, "pyproject.toml", archived_sha("pyproject.toml"))


def test_historical_verifier_rejects_weakened_result_checks(compatibility):
    path = compatibility.root / VERIFIER
    text = path.read_text()
    assert 'assert row["correct"] == "True"' in text
    path.write_text(text.replace('assert row["correct"] == "True"', 'assert True', 1))
    with pytest.raises(AssertionError, match="historischer Verifier"):
        compatibility.verify(FINAL03, VERIFIER.as_posix(), archived_sha(VERIFIER))


def test_nonconfiguration_active_sources_remain_strict(compatibility):
    relative = "themen/03_boolesche_mehrwortsuche/src/boolesche_suche/search.py"
    target = compatibility.root / relative
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / relative).read_bytes() + b"\n# changed\n")
    with pytest.raises(AssertionError, match="aktiver Code geändert"):
        compatibility.verify(FINAL03, relative, archived_sha(relative))


def test_original_algorithms_data_and_recorded_chapter_baselines_are_preserved():
    import json

    before = json.loads((ROOT / "doku/pruefberichte/artefakte_04/anfangszustand.json").read_text())
    protected_prefixes = ("gemeinsam/", "daten/",
                          "themen/01_textaufbereitung_direkte_suche/src/",
                          "themen/02_invertierter_index_einzelwortsuche/src/")
    # Die spätere Zitierkorrektur in Commit 8cae849 ändert keinen Algorithmus.
    # Die alten Themenkapitel samt chapter_preservation.json wurden am 14.10.2026
    # bewusst gelöscht (doku/entscheidungen.md), ihr Hashvergleich entfällt.
    for relative, expected in before["files_sha256_before"].items():
        if relative.startswith(protected_prefixes):
            assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    # Thema 03 wurde am 14.10.2026 bewusst um Galloping Search und AND NOT erweitert
    # (Gesamtplan 2.3). Byteidentisch bleibt deshalb nur, was Thema 04 tatsächlich nutzt:
    # die Zwei-Zeiger-Funktionen in lists.py, AST-genau gegen die in Reihe 04
    # archivierte und im Anfangszustand gehashte Fassung.
    lists = "themen/03_boolesche_mehrwortsuche/src/boolesche_suche/lists.py"
    archived = ROOT / "ergebnisse/messungen/04_positionsindex_phrasensuche/code_source" / lists
    assert hashlib.sha256(archived.read_bytes()).hexdigest() == before["files_sha256_before"][lists]

    def functions(path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return {node.name: ast.dump(node) for node in tree.body if isinstance(node, ast.FunctionDef)}
    old_functions, new_functions = functions(archived), functions(ROOT / lists)
    for name in ("intersect_sorted", "union_sorted"):
        assert new_functions[name] == old_functions[name], name
