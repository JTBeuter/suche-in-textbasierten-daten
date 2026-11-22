"""CLI-Erweiterung um --variant galloping und --exclude über beide Einstiege."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]


def invoke(*args, integrated=False):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    module = "direkte_suche" if integrated else "boolesche_suche"
    options = ["--boolean"] if integrated else []
    return subprocess.run([sys.executable, "-m", module, *options, *args], cwd=ROOT,
                          env=environment, capture_output=True, text=True)


@pytest.mark.parametrize("integrated", [False, True])
def test_galloping_variant_output_has_unchanged_fields(integrated):
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--terms", "Verbindung", "Server", "VERBINDUNG!",
                    "--operator", "AND", "--variant", "galloping", integrated=integrated)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        '{"mode": "boolean", "method": "index", "operator": "AND", "variant": "galloping", '
        '"terms": ["Verbindung", "Server", "VERBINDUNG!"], "normalized_terms": ["verbindung", "server"], '
        '"original_term_count": 3, "effective_term_count": 2, "matches": ["D0.txt", "D2.txt", "D3.txt"]}\n'
    )


@pytest.mark.parametrize("integrated", [False, True])
@pytest.mark.parametrize("method,variant", [("direct", "input_order"), ("index", "input_order"),
                                            ("index", "shortest_first"), ("index", "galloping")])
def test_exclude_outputs_raw_and_normalized_word(integrated, method, variant):
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--terms", "Verbindung", "--exclude", "SERVER!",
                    "--operator", "AND", "--method", method, "--variant", variant, integrated=integrated)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "mode": "boolean", "method": method, "operator": "AND", "variant": variant,
        "terms": ["Verbindung"], "normalized_terms": ["verbindung"],
        "original_term_count": 1, "effective_term_count": 1,
        "exclude": "SERVER!", "normalized_exclude": "server", "matches": ["D1.txt"],
    }
    assert list(json.loads(result.stdout))[-3:] == ["exclude", "normalized_exclude", "matches"]


@pytest.mark.parametrize("terms,exclude,expected", [
    (["verbindung", "zum"], "fehler", []),
    (["Verbindung", "Server"], "Fehler", ["D3.txt"]),
    (["Fehler"], "Fehler", []),
    (["Verbindung"], "unbekannt", ["D0.txt", "D1.txt", "D2.txt", "D3.txt"]),
])
def test_exclude_examples_both_methods(terms, exclude, expected):
    for method in ("direct", "index"):
        result = invoke("--corpus", "daten/beispiele/d0_d5", "--terms", *terms, "--exclude", exclude,
                        "--operator", "AND", "--method", method)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["matches"] == expected


@pytest.mark.parametrize("options,message", [
    (["--terms", "a", "--operator", "OR", "--exclude", "Fehler"], "--exclude ist ausschließlich"),
    (["--terms", "a", "--operator", "OR", "--variant", "galloping"], "OR unterstützt ausschließlich"),
    (["--terms", "a", "--operator", "AND", "--method", "direct", "--variant", "galloping"], "direkte Referenz"),
    (["--terms", "a", "--operator", "AND", "--exclude", "Fehler Server"], "genau ein"),
    (["--terms", "a", "--operator", "AND", "--exclude", ""], "exclude"),
    (["--terms", "a", "--operator", "AND", "--exclude", "E-Mail"], "genau ein"),
    (["--terms", "a", "--operator", "AND", "--variant", "gallop"], "invalid choice"),
])
@pytest.mark.parametrize("integrated", [False, True])
def test_new_option_errors_are_explained_without_traceback(options, message, integrated):
    result = invoke("--corpus", "daten/beispiele/d0_d5", *options, integrated=integrated)
    assert result.returncode == 2
    assert result.stdout == ""
    assert message in result.stderr
    assert "Traceback" not in result.stderr


def test_operator_word_in_terms_stays_a_search_word():
    # Kein Abfrageparser: ein geschriebenes AND/NOT ist ein gewöhnliches Suchwort.
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--terms", "Verbindung", "AND", "NOT", "Server",
                    "--operator", "AND", "--variant", "galloping")
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["normalized_terms"] == ["verbindung", "and", "not", "server"]
    assert output["matches"] == []
