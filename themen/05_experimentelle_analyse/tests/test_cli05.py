"""Gesamt-CLI anhand handberechneter Treffer und echter Prozessaufrufe."""

import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from experimentelle_analyse.cli import main


ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "daten/beispiele/d0_d5"


def run_cli(*arguments, cwd=ROOT):
    return subprocess.run(
        [sys.executable, "-m", "experimentelle_analyse", *map(str, arguments)],
        cwd=cwd, text=True, capture_output=True, check=False,
    )


@pytest.mark.parametrize("method", ["direct", "index"])
@pytest.mark.parametrize("kind,query,tokens,expected", [
    ("word", "FEHLER!", ["fehler"], ["D0.txt", "D2.txt"]),
    ("and", "Verbindung, SERVER Verbindung", ["verbindung", "server"],
     ["D0.txt", "D2.txt", "D3.txt"]),
    ("or", "Fehler a", ["fehler", "a"], ["D0.txt", "D2.txt", "D5.txt"]),
    ("phrase", "VERBINDUNG zum Server", ["verbindung", "zum", "server"],
     {"D0.txt": [3], "D2.txt": [0]}),
    ("phrase", "a a", ["a", "a"], {"D5.txt": [0, 1]}),
])
def test_all_search_kinds_have_complete_expected_results(method, kind, query, tokens, expected):
    completed = run_cli("search", "--corpus", CORPUS, "--kind", kind,
                        "--method", method, "--query", query)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "kind": kind, "method": method, "variant": "basic", "query": query,
        "normalized_tokens": tokens, "matches": expected,
    }
    assert completed.stderr == ""
    assert len(completed.stdout.splitlines()) == 1


def test_shortest_first_is_available_for_index_and():
    completed = run_cli("search", "--corpus", CORPUS, "--kind", "and", "--method", "index",
                        "--query", "Verbindung Server", "--variant", "shortest_first")
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["matches"] == ["D0.txt", "D2.txt", "D3.txt"]
    assert result["variant"] == "shortest_first"


@pytest.mark.parametrize("kind,method", [
    ("and", "direct"), ("or", "direct"), ("or", "index"),
    ("word", "index"), ("phrase", "index"),
])
def test_inapplicable_shortest_variant_is_a_clear_input_error(kind, method):
    completed = run_cli("search", "--corpus", CORPUS, "--kind", kind,
                        "--method", method, "--query", "a", "--variant", "shortest_first")
    assert completed.returncode == 2
    assert "ausschließlich" in completed.stderr
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr


@pytest.mark.parametrize("kind", ["word", "and", "or", "phrase"])
@pytest.mark.parametrize("query", ["", "! _ - \n"])
def test_tokenless_query_is_rejected_for_every_kind(kind, query):
    completed = run_cli("search", "--corpus", CORPUS, "--kind", kind, "--query", query)
    assert completed.returncode == 2
    assert "mindestens ein Token" in completed.stderr
    assert completed.stdout == ""


def test_word_query_requires_one_complete_token():
    completed = run_cli("search", "--corpus", CORPUS, "--kind", "word", "--query", "a a")
    assert completed.returncode == 2
    assert "genau ein Token" in completed.stderr
    assert completed.stdout == ""


def test_boolean_query_treats_operator_text_as_an_ordinary_token():
    completed = run_cli("search", "--corpus", CORPUS, "--kind", "and",
                        "--query", "Verbindung AND Server")
    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert result["normalized_tokens"] == ["verbindung", "and", "server"]
    assert result["matches"] == []


@pytest.mark.parametrize("kind,expected", [("word", []), ("and", []), ("or", []), ("phrase", {})])
def test_valid_unknown_query_has_no_matches(kind, expected):
    completed = run_cli("search", "--corpus", CORPUS, "--kind", kind,
                        "--query", "niemalsvorhanden")
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["matches"] == expected


def test_missing_corpus_and_invalid_utf8_produce_exit_two(tmp_path):
    missing = run_cli("search", "--corpus", tmp_path / "missing", "--kind", "word", "--query", "a")
    assert missing.returncode == 2
    assert "existiert nicht" in missing.stderr
    assert missing.stdout == ""
    (tmp_path / "bad.txt").write_bytes(b"\xff")
    invalid = run_cli("search", "--corpus", tmp_path, "--kind", "word", "--query", "a")
    assert invalid.returncode == 2
    assert "UTF-8" in invalid.stderr
    assert invalid.stdout == ""


def test_installed_command_works_outside_repository(tmp_path):
    completed = run_cli("search", "--corpus", CORPUS, "--kind", "word", "--query", "Fehler", cwd=tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["matches"] == ["D0.txt", "D2.txt"]


@pytest.mark.parametrize("command,module_name,function_name,source_option", [
    ("run", "pipeline", "run_experiment", "--config"),
    ("generate", "datasets", "generate_from_config", "--config"),
    ("analyse", "analysis", "analyse", "--input"),
    ("verify", "verify", "verify_run", "--input"),
])
def test_command_dispatch_passes_paths_and_separates_progress(
    monkeypatch, capsys, tmp_path, command, module_name, function_name, source_option,
):
    module = ModuleType(f"experimentelle_analyse.{module_name}")
    calls = []

    def target(*arguments):
        calls.append(arguments)
        print("Fortschritt")
        return {"command": command, "count": 7}

    setattr(module, function_name, target)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    source = tmp_path / "source"
    output = tmp_path / "output"
    arguments = [command, source_option, str(source)]
    if command != "verify":
        arguments += ["--output", str(output)]
    assert main(arguments) == 0
    expected_calls = [(source,)] if command == "verify" else [(source, output)]
    assert calls == expected_calls
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"command": command, "count": 7}
    assert captured.err == "Fortschritt\n"


def test_commands_are_lazy_and_search_does_not_load_measurement_modules():
    script = """import sys
from experimentelle_analyse.cli import main
main(['search', '--corpus', sys.argv[1], '--kind', 'word', '--query', 'Fehler'])
assert all('experimentelle_analyse.' + name not in sys.modules
           for name in ('pipeline', 'analysis', 'verify', 'datasets'))
"""
    completed = subprocess.run([sys.executable, "-c", script, str(CORPUS)],
                               cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("arguments", [[], ["invalid"], ["search"], ["run"], ["analyse"], ["verify"], ["generate"]])
def test_missing_options_and_unknown_commands_are_parser_errors(arguments):
    completed = run_cli(*arguments)
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "usage:" in completed.stderr


def test_verification_failure_is_not_reported_as_success(monkeypatch, tmp_path, capsys):
    module = ModuleType("experimentelle_analyse.verify")

    def reject(_path):
        raise AssertionError("Rohdaten beschädigt")

    module.verify_run = reject
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with pytest.raises(SystemExit) as failure:
        main(["verify", "--input", str(tmp_path)])
    assert failure.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Rohdaten beschädigt" in captured.err
