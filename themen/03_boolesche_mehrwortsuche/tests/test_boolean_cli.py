"""Beide CLI-Einstiege tatsächlich aus Repository und fremdem Verzeichnis."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]


def invoke(*args, cwd=ROOT, integrated=False):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    module = "direkte_suche" if integrated else "boolesche_suche"
    options = ["--boolean"] if integrated else []
    return subprocess.run([sys.executable, "-m", module, *options, *args], cwd=cwd,
                          env=environment, capture_output=True, text=True)


@pytest.mark.parametrize("integrated", [False, True])
@pytest.mark.parametrize("method,variant", [("direct", "input_order"), ("index", "input_order"), ("index", "shortest_first")])
def test_both_entry_points_known_and_query(integrated, method, variant):
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--terms", "Verbindung", "Server", "VERBINDUNG!",
                    "--operator", "AND", "--method", method, "--variant", variant, integrated=integrated)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "mode": "boolean", "method": method, "operator": "AND", "variant": variant,
        "terms": ["Verbindung", "Server", "VERBINDUNG!"], "normalized_terms": ["verbindung", "server"],
        "original_term_count": 3, "effective_term_count": 2, "matches": ["D0.txt", "D2.txt", "D3.txt"],
    }


@pytest.mark.parametrize("integrated", [False, True])
def test_installed_entry_point_outside_repository(tmp_path, integrated):
    result = invoke("--corpus", str(ROOT / "daten/beispiele/d0_d5"), "--terms", "Fehler", "a",
                    "--operator", "OR", integrated=integrated, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["matches"] == ["D0.txt", "D2.txt", "D5.txt"]


@pytest.mark.parametrize("options", [
    ["--terms", "", "--operator", "AND"],
    ["--terms", "Fehler Server", "--operator", "AND"],
    ["--terms", "a", "--operator", "NOT"],
    ["--terms", "a", "--operator", "OR", "--variant", "shortest_first"],
    ["--terms", "a", "--operator", "AND", "--method", "direct", "--variant", "shortest_first"],
    ["--terms", "--operator", "AND"],
])
@pytest.mark.parametrize("integrated", [False, True])
def test_errors_are_explained_without_traceback(options, integrated):
    result = invoke("--corpus", "daten/beispiele/d0_d5", *options, integrated=integrated)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr
    assert "Traceback" not in result.stderr


def test_empty_corpus_and_missing_path(tmp_path):
    options = ("--terms", "Server", "--operator", "AND")
    good = invoke("--corpus", str(tmp_path), *options)
    assert good.returncode == 0, good.stderr
    assert json.loads(good.stdout)["matches"] == []
    bad = invoke("--corpus", str(tmp_path / "missing"), *options)
    assert bad.returncode == 2
    assert "existiert nicht" in bad.stderr
    assert "Traceback" not in bad.stderr


def test_import_does_not_execute_search_or_experiment(tmp_path):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-c", "import boolesche_suche; import boolesche_suche.__main__"],
                            cwd=tmp_path, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert list(tmp_path.iterdir()) == []
