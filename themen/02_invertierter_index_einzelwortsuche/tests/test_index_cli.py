"""Exercise the installed CLI without an implicit local import path."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]


def invoke(*arguments, cwd=ROOT, module="invertierter_index"):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_documented_index_cli_from_repository():
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--query", "Fehler")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "mode": "word", "query": "Fehler", "matches": ["D0.txt", "D2.txt"],
    }
    assert result.stderr == ""


def test_index_cli_uses_shared_raw_query_normalization():
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--query", "FEHLER!")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["matches"] == ["D0.txt", "D2.txt"]


def test_installed_index_package_is_usable_outside_repository(tmp_path):
    result = invoke("--corpus", str(ROOT / "daten/beispiele/d0_d5"), "--query", "Fehler", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["matches"] == ["D0.txt", "D2.txt"]


def test_index_cli_unknown_word_has_successful_empty_result():
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--query", "abwesend")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["matches"] == []


@pytest.mark.parametrize("query", ["", "...!", "Fehler Server", "E-Mail"])
def test_invalid_word_query_has_clear_cli_error(query):
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--query", query)
    assert result.returncode == 2
    assert result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


def test_missing_corpus_has_clear_cli_error(tmp_path):
    result = invoke("--corpus", str(tmp_path / "missing"), "--query", "Fehler")
    assert result.returncode == 2
    assert "existiert nicht" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


def test_invalid_utf8_corpus_has_clear_cli_error(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"\xff")
    result = invoke("--corpus", str(tmp_path), "--query", "Fehler")
    assert result.returncode == 2
    assert "UTF-8" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


def test_empty_corpus_is_valid_cli_input(tmp_path):
    result = invoke("--corpus", str(tmp_path), "--query", "Fehler")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["matches"] == []


@pytest.mark.parametrize(
    ("query", "matches"),
    [
        ("FEHLER!", ["D0.txt", "D2.txt"]),
        ("a", ["D5.txt"]),
        ("bei", ["D0.txt"]),
        ("der", ["D0.txt"]),
        ("ohne", ["D1.txt", "D3.txt"]),
        ("server", ["D0.txt", "D2.txt", "D3.txt"]),
        ("serverfehler", ["D1.txt"]),
        ("verbindung", ["D0.txt", "D1.txt", "D2.txt", "D3.txt"]),
        ("zum", ["D0.txt", "D2.txt"]),
        ("abwesend", []),
    ],
)
def test_established_cli_index_mode_agrees_with_index_entry_and_word_reference(query, matches):
    arguments = ("--corpus", "daten/beispiele/d0_d5", "--query", query)
    standalone = invoke(*arguments)
    integrated = invoke(*arguments, "--mode", "index", module="direkte_suche")
    reference = invoke(*arguments, module="direkte_suche")
    for result, mode in ((standalone, "word"), (integrated, "index"), (reference, "word")):
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert json.loads(result.stdout) == {"mode": mode, "query": query, "matches": matches}


@pytest.mark.parametrize("failure", ["multiword", "invalid-utf8"])
def test_established_cli_index_mode_preserves_shared_input_errors(tmp_path, failure):
    if failure == "invalid-utf8":
        (tmp_path / "a.txt").write_bytes(b"\xff")
        corpus, query, message = str(tmp_path), "Fehler", "UTF-8"
    else:
        corpus, query, message = "daten/beispiele/d0_d5", "Fehler Server", "genau ein Token"
    result = invoke("--corpus", corpus, "--query", query, "--mode", "index", module="direkte_suche")
    assert result.returncode == 2
    assert message in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
