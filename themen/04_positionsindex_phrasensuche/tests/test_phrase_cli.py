"""Installierte CLI, ohne PYTHONPATH, mit gültigen und fehlerhaften Dateien."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]


def invoke(*arguments, cwd=ROOT):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, "-m", "positionsindex", *arguments],
        cwd=cwd, env=environment, text=True, capture_output=True, check=False,
    )


@pytest.mark.parametrize("method", ["direct", "index"])
def test_documented_phrase_cli(method):
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--phrase", "Verbindung zum Server", "--method", method)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "mode": "phrase", "method": method, "phrase": "Verbindung zum Server",
        "normalized_tokens": ["verbindung", "zum", "server"],
        "matches": {"D0.txt": [3], "D2.txt": [0]},
    }


@pytest.mark.parametrize("method", ["direct", "index"])
@pytest.mark.parametrize(
    ("phrase", "expected"),
    [("a a", {"D5.txt": [0, 1]}), ("SERVER. FEHLER!", {"D2.txt": [2]}), ("unbekannt", {})],
)
def test_cli_overlap_sentence_punctuation_and_unknown_phrase(method, phrase, expected):
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--phrase", phrase, "--method", method)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["matches"] == expected


def test_installed_cli_works_outside_repository(tmp_path):
    result = invoke("--corpus", str(ROOT / "daten/beispiele/d0_d5"), "--phrase", "a a", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["matches"] == {"D5.txt": [0, 1]}


@pytest.mark.parametrize("phrase", ["", " ", "...!", "_—!\n"])
def test_invalid_phrase_has_explained_error_and_no_output(phrase):
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--phrase", phrase)
    assert result.returncode == 2
    assert "mindestens ein Token" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("method", ["direct", "index"])
def test_cli_missing_corpus_is_an_error(tmp_path, method):
    result = invoke("--corpus", str(tmp_path / "missing"), "--phrase", "a", "--method", method)
    assert result.returncode == 2
    assert "existiert nicht" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("method", ["direct", "index"])
def test_invalid_utf8_does_not_produce_a_partial_result(tmp_path, method):
    (tmp_path / "a.txt").write_text("a a", encoding="utf-8")
    (tmp_path / "b.txt").write_bytes(b"\xff")
    result = invoke("--corpus", str(tmp_path), "--phrase", "a", "--method", method)
    assert result.returncode == 2
    assert "UTF-8" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("method", ["direct", "index"])
def test_empty_corpus_successfully_returns_empty_mapping(tmp_path, method):
    result = invoke("--corpus", str(tmp_path), "--phrase", "a a", "--method", method)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["matches"] == {}


def test_unicode_cli_uses_the_shared_normalization(tmp_path):
    (tmp_path / "unicode.txt").write_text("Straße STRASSE Äpfel A\u0308pfel", encoding="utf-8")
    for phrase, expected in (("STRAẞE STRASSE", [0]), ("A\u0308PFEL äpfel", [2])):
        result = invoke("--corpus", str(tmp_path), "--phrase", phrase)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["matches"] == {"unicode.txt": expected}


def test_invalid_method_is_rejected_by_parser():
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--phrase", "a", "--method", "other")
    assert result.returncode == 2
    assert result.stderr
    assert result.stdout == ""
