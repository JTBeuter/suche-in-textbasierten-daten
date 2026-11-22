import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]


def invoke(*arguments, cwd=ROOT):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, "-m", "direkte_suche", *arguments],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_documented_cli_works_from_repository_without_hidden_pythonpath():
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--query", "Fehler")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"mode": "word", "query": "Fehler", "matches": ["D0.txt", "D2.txt"]}
    assert result.stderr == ""


def test_substring_cli_exposes_the_semantic_difference():
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--query", "Fehler", "--mode", "substring")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["matches"] == ["D0.txt", "D1.txt", "D2.txt"]


def test_installed_package_is_usable_outside_repository(tmp_path):
    result = invoke("--corpus", str(ROOT / "daten/beispiele/d0_d5"), "--query", "Fehler", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["matches"] == ["D0.txt", "D2.txt"]


def test_invalid_query_is_a_clear_nonzero_cli_error():
    result = invoke("--corpus", "daten/beispiele/d0_d5", "--query", "Fehler Server")
    assert result.returncode == 2
    assert "genau ein Token" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


def test_invalid_corpus_is_a_clear_nonzero_cli_error(tmp_path):
    result = invoke("--corpus", str(tmp_path / "missing"), "--query", "Fehler")
    assert result.returncode == 2
    assert "existiert nicht" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
