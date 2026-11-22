"""Gesamt-CLI: --variant galloping und --exclude (AND NOT) aus Thema 03."""

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "daten/beispiele/d0_d5"


def run_cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "experimentelle_analyse", *map(str, arguments)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )


@pytest.mark.parametrize("arguments,expected", [
    (("--kind", "and", "--method", "index", "--query", "Verbindung Server", "--variant", "shortest_first"),
     '{"kind": "and", "method": "index", "variant": "shortest_first", "query": "Verbindung Server", '
     '"normalized_tokens": ["verbindung", "server"], "matches": ["D0.txt", "D2.txt", "D3.txt"]}\n'),
    (("--kind", "and", "--method", "direct", "--query", "Verbindung zum"),
     '{"kind": "and", "method": "direct", "variant": "basic", "query": "Verbindung zum", '
     '"normalized_tokens": ["verbindung", "zum"], "matches": ["D0.txt", "D2.txt"]}\n'),
])
def test_output_without_new_options_is_byte_identical_to_previous_version(arguments, expected):
    # Erwartete Zeilen stammen aus der Fassung vor der Erweiterung (Commit 7bc4f9a).
    completed = run_cli("search", "--corpus", CORPUS, *arguments)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == expected
    assert completed.stderr == ""


def test_galloping_is_available_for_index_and():
    completed = run_cli("search", "--corpus", CORPUS, "--kind", "and", "--method", "index",
                        "--query", "Verbindung Server Fehler", "--variant", "galloping")
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "kind": "and", "method": "index", "variant": "galloping", "query": "Verbindung Server Fehler",
        "normalized_tokens": ["verbindung", "server", "fehler"], "matches": ["D0.txt", "D2.txt"],
    }


@pytest.mark.parametrize("kind,method", [
    ("and", "direct"), ("or", "direct"), ("or", "index"), ("word", "index"), ("phrase", "index"),
])
def test_inapplicable_galloping_variant_is_a_clear_input_error(kind, method):
    completed = run_cli("search", "--corpus", CORPUS, "--kind", kind, "--method", method,
                        "--query", "a", "--variant", "galloping")
    assert completed.returncode == 2
    assert "galloping ist ausschließlich für --kind and --method index zulässig." in completed.stderr
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr


@pytest.mark.parametrize("method,variant", [
    ("direct", "basic"), ("index", "basic"), ("index", "shortest_first"), ("index", "galloping"),
])
@pytest.mark.parametrize("query,exclude,normalized,expected", [
    ("Verbindung", "SERVER!", "server", ["D1.txt"]),
    ("verbindung zum", "fehler", "fehler", []),
    ("Verbindung, Server", "Fehler", "fehler", ["D3.txt"]),
    ("Fehler", "fehler", "fehler", []),
    ("Verbindung", "unbekannt", "unbekannt", ["D0.txt", "D1.txt", "D2.txt", "D3.txt"]),
])
def test_exclude_for_and_with_both_methods(method, variant, query, exclude, normalized, expected):
    completed = run_cli("search", "--corpus", CORPUS, "--kind", "and", "--method", method,
                        "--query", query, "--variant", variant, "--exclude", exclude)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert list(result) == ["kind", "method", "variant", "query", "normalized_tokens",
                            "exclude", "normalized_exclude", "matches"]
    assert result["exclude"] == exclude and result["normalized_exclude"] == normalized
    assert result["variant"] == variant
    assert result["matches"] == expected


@pytest.mark.parametrize("kind", ["word", "or", "phrase"])
@pytest.mark.parametrize("method", ["direct", "index"])
def test_exclude_outside_and_is_rejected(kind, method):
    completed = run_cli("search", "--corpus", CORPUS, "--kind", kind, "--method", method,
                        "--query", "Verbindung", "--exclude", "Server")
    assert completed.returncode == 2
    assert "--exclude ist ausschließlich für --kind and zulässig." in completed.stderr
    assert completed.stdout == ""


@pytest.mark.parametrize("exclude", ["", "Fehler Server", "E-Mail", "..."])
def test_exclude_must_be_exactly_one_word(exclude):
    completed = run_cli("search", "--corpus", CORPUS, "--kind", "and", "--query", "Verbindung",
                        "--exclude", exclude)
    assert completed.returncode == 2
    assert "exclude muss genau ein Wort ergeben." in completed.stderr
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr


def test_written_not_stays_an_ordinary_search_word():
    completed = run_cli("search", "--corpus", CORPUS, "--kind", "and", "--query", "Verbindung NOT Server")
    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert result["normalized_tokens"] == ["verbindung", "not", "server"]
    assert result["matches"] == []
    assert "exclude" not in result
