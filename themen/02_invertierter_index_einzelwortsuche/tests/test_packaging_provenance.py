"""Actual historical verifier must allow additions and reject changed evidence."""

import importlib.util
import json
from pathlib import Path
import re
import tomllib

import pytest


ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = Path("doku/pruefberichte/artefakte_02/pyproject_vorstufe01.toml")
EXPECTED_HASH = json.loads(
    (ROOT / "ergebnisse/messungen/01_direkte_suche/metadata.json").read_text(encoding="utf-8")
)["code_sha256"]["pyproject.toml"]
CLI_SOURCE = Path("themen/01_textaufbereitung_direkte_suche/src/direkte_suche/__main__.py")
CLI_ARCHIVE = Path("doku/pruefberichte/artefakte_02/cli_vorstufe01.py")
EXPECTED_CLI_HASH = json.loads(
    (ROOT / "ergebnisse/messungen/01_direkte_suche/metadata.json").read_text(encoding="utf-8")
)["code_sha256"][CLI_SOURCE.as_posix()]


@pytest.fixture
def verifier_fixture(tmp_path, monkeypatch):
    script = ROOT / "themen/01_textaufbereitung_direkte_suche/experimente/verify_results.py"
    spec = importlib.util.spec_from_file_location("historical_results_verifier", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    archive = tmp_path / ARCHIVE
    archive.parent.mkdir(parents=True)
    archive.write_bytes((ROOT / ARCHIVE).read_bytes())
    current = tmp_path / "pyproject.toml"
    current.write_bytes((ROOT / "pyproject.toml").read_bytes())
    return module, current, archive


def test_real_additive_packaging_extension_preserves_historical_evidence(verifier_fixture):
    verifier, _, _ = verifier_fixture
    verifier.verify_packaging_extension(EXPECTED_HASH)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            'direkte_suche = "themen/01_textaufbereitung_direkte_suche/src/direkte_suche"',
            'direkte_suche = "themen/02_invertierter_index_einzelwortsuche/src/invertierter_index"',
        ),
        ('dependencies = []', 'dependencies = ["another-search-service"]'),
        ('addopts = "-ra"', 'addopts = "-ra --ignore=themen/01_textaufbereitung_direkte_suche"'),
    ],
    ids=["old-package-mapping-changed", "dependencies-changed", "test-configuration-changed"],
)
def test_changes_beyond_additions_are_rejected(verifier_fixture, before, after):
    verifier, current, _ = verifier_fixture
    content = current.read_text(encoding="utf-8")
    assert before in content
    current.write_text(content.replace(before, after, 1), encoding="utf-8")
    with pytest.raises(AssertionError):
        verifier.verify_packaging_extension(EXPECTED_HASH)


def test_removing_historical_package_is_rejected_after_additive_extensions(verifier_fixture):
    verifier, current, _ = verifier_fixture
    content = current.read_text(encoding="utf-8")
    packages = tomllib.loads(content)["tool"]["setuptools"]["packages"]
    assert "direkte_suche" in packages
    changed = [package for package in packages if package != "direkte_suche"]
    old_assignment = f"packages = {json.dumps(packages)}"
    assert old_assignment in content
    current.write_text(content.replace(old_assignment, f"packages = {json.dumps(changed)}", 1), encoding="utf-8")
    with pytest.raises(AssertionError):
        verifier.verify_packaging_extension(EXPECTED_HASH)


def test_testpaths_type_change_cannot_pass_substring_membership(verifier_fixture):
    verifier, current, _ = verifier_fixture
    content = current.read_text(encoding="utf-8")
    # Both previous paths occur as substrings, but this is one invalid path.
    old_paths = (
        "themen/01_textaufbereitung_direkte_suche/tests"
        "themen/01_textaufbereitung_direkte_suche/experimente/tests"
    )
    changed, replacements = re.subn(r"testpaths = \[[^\n]+\]", f'testpaths = "{old_paths}"', content)
    assert replacements == 1
    current.write_text(changed, encoding="utf-8")
    with pytest.raises(AssertionError):
        verifier.verify_packaging_extension(EXPECTED_HASH)


def test_archive_tampering_is_rejected_even_if_toml_meaning_is_unchanged(verifier_fixture):
    verifier, _, archive = verifier_fixture
    archive.write_bytes(archive.read_bytes() + b"\n# changed archive\n")
    with pytest.raises(AssertionError, match="gemessene Paketkonfiguration"):
        verifier.verify_packaging_extension(EXPECTED_HASH)


@pytest.fixture
def cli_verifier_fixture(verifier_fixture):
    verifier, _, _ = verifier_fixture
    current = verifier.ROOT / CLI_SOURCE
    archive = verifier.ROOT / CLI_ARCHIVE
    current.parent.mkdir(parents=True)
    current.write_bytes((ROOT / CLI_SOURCE).read_bytes())
    archive.write_bytes((ROOT / CLI_ARCHIVE).read_bytes())
    boolean_archive = verifier.ROOT / "doku/pruefberichte/artefakte_03/cli_vorstufe02.py"
    boolean_archive.parent.mkdir(parents=True, exist_ok=True)
    boolean_archive.write_bytes((ROOT / "doku/pruefberichte/artefakte_03/cli_vorstufe02.py").read_bytes())
    return verifier, current, archive


def test_actual_cli_index_addition_preserves_historical_branches(cli_verifier_fixture):
    verifier, _, _ = cli_verifier_fixture
    verifier.verify_cli_extension(EXPECTED_CLI_HASH)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("matches = search_direct_word(prepare_corpus(raw_corpus), args.query)", "matches = []"),
        ("matches = search_direct_substring(raw_corpus, args.query)", "matches = []"),
        ('default="word"', 'default="substring"'),
    ],
    ids=["word-branch-changed", "substring-branch-changed", "default-mode-changed"],
)
def test_cli_extension_rejects_changes_to_existing_behavior(cli_verifier_fixture, before, after):
    verifier, current, _ = cli_verifier_fixture
    content = current.read_text(encoding="utf-8")
    assert before in content
    current.write_text(content.replace(before, after, 1), encoding="utf-8")
    with pytest.raises(AssertionError, match="bestehende CLI-Semantik"):
        verifier.verify_cli_extension(EXPECTED_CLI_HASH)


def test_cli_archive_tampering_is_rejected_even_if_ast_is_unchanged(cli_verifier_fixture):
    verifier, _, archive = cli_verifier_fixture
    archive.write_bytes(archive.read_bytes() + b"\n# changed CLI archive\n")
    with pytest.raises(AssertionError, match="gemessener CLI-Quelltext"):
        verifier.verify_cli_extension(EXPECTED_CLI_HASH)
