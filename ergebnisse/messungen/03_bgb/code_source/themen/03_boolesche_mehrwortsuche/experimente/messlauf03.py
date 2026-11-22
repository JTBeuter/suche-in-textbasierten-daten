"""Gemeinsame Laufkonvention der Reihen 03b und 03_bgb (wie die neue Reihe 01).

Ergebnisordner sind einzelne Namen unter ergebnisse/messungen (`--ausgabe`),
der Finallauf verweist mit `--pilot-ordner` auf einen erfolgreichen Pilot,
`--hintergrundlast` landet in den Metadaten. Vorhandene nicht leere Ordner
werden nie überschrieben; nur ein Pilot darf mit `--replace-pilot` bewusst
ersetzt werden. Pilot und Finallauf verlangen PYTHONHASHSEED=0.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from time import get_clock_info
import unicodedata


ROOT = Path(__file__).resolve().parents[3]
MESSUNGEN = ROOT / "ergebnisse/messungen"
REQUIRED_HASH_SEED = "0"
PLANNED_BACKGROUND = (
    "planned protocol: no parallel project tests, PDF builds or other benchmark series; "
    "ordinary desktop background load; machine not isolated; not checked by the script"
)


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def display(path: Path) -> str:
    """Repositoryrelativer Pfad für Metadaten und Meldungen."""
    try:
        return Path(path).relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def python_hash_seed() -> str:
    return os.environ.get("PYTHONHASHSEED", "random")


def require_hash_seed() -> None:
    if python_hash_seed() != REQUIRED_HASH_SEED:
        raise SystemExit(f"Pilot und Finalmessung nur mit PYTHONHASHSEED=0 starten (aktuell {python_hash_seed()}).")


def directory_name(name: str) -> Path:
    """Genau ein Ordnername unter ergebnisse/messungen."""
    if not name or name in {".", ".."} or Path(name).name != name or "/" in name or "\\" in name:
        raise SystemExit(f"Ungültiger Ordnername {name!r}: genau ein Name unter ergebnisse/messungen erwartet.")
    return MESSUNGEN / name


def check_output(output: Path, *, pilot: bool, replace_pilot: bool) -> None:
    """Abbruch vor jeder Arbeit, wenn ein nicht leerer Ordner überschrieben würde."""
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        if not pilot:
            raise SystemExit(f"{display(output)} existiert und ist nicht leer; Ergebnisse werden nicht "
                             "überschrieben. Neuen Namen mit --ausgabe wählen.")
        if not replace_pilot or not output.is_dir():
            raise SystemExit(f"{display(output)} existiert und ist nicht leer; neuen Namen mit --ausgabe wählen "
                             "oder den Pilot bewusst mit --replace-pilot ersetzen.")


def prepare_output(output: Path, *, pilot: bool, replace_pilot: bool) -> None:
    check_output(output, pilot=pilot, replace_pilot=replace_pilot)
    if output.exists() and any(output.iterdir()):
        shutil.rmtree(output)  # nur Pilot mit ausdrücklichem --replace-pilot
    output.mkdir(parents=True, exist_ok=True)


def pilot_directory(name: str, output: Path) -> Path:
    directory = directory_name(name)
    if directory == output:
        raise SystemExit("--pilot-ordner muss ein anderer Ordnername unter ergebnisse/messungen sein.")
    return directory


def require_pilot(path: Path, parameters: dict, hashes: dict) -> dict:
    """Finallauf nur nach erfolgreichem Pilot mit gleichen Parametern, Code und Hashseed."""
    if not path.is_file():
        raise SystemExit("Zuerst run.py --pilot ausführen: Parameter werden erst nach erfolgreichem Pilot gesperrt.")
    decision = json.loads(path.read_text(encoding="utf-8"))
    if decision.get("pilot_correct") is not True or decision.get("locked_parameters") != parameters:
        raise SystemExit("Erfolgreicher Pilot mit unveränderten Parametern erforderlich; Pilot erneut ausführen.")
    if decision.get("method_code_sha256") != hashes:
        raise SystemExit("Messcode hat sich nach dem Pilot geändert; Pilot erneut ausführen "
                         "(neuer Name mit --ausgabe oder --replace-pilot).")
    if decision.get("python_hash_seed") != python_hash_seed():
        raise SystemExit("PYTHONHASHSEED weicht vom Pilot ab; mit demselben Wert wie im Pilot starten.")
    return {"pilot_decision_path": display(path), "pilot_decision_sha256": sha(path)}


def archive_sources(output: Path, hashes: dict) -> None:
    for relative, digest in hashes.items():
        payload = (ROOT / relative).read_bytes()
        if hashlib.sha256(payload).hexdigest() != digest:
            raise RuntimeError("Quellfassung während der Archivierung verändert")
        target = output / "code_source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def run_header(output: Path, pilot: bool, background: str) -> dict:
    """Git-Stand, Umgebung, Hashseed und Hintergrundlast für metadata.json."""
    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()
    cpu = platform.processor()
    if Path("/proc/cpuinfo").exists():
        cpu = next((line.partition(":")[2].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")), cpu)
    memory = "unknown"
    if Path("/proc/meminfo").exists():
        memory = next((line for line in Path("/proc/meminfo").read_text().splitlines()
                       if line.startswith("MemTotal:")), "unknown")
    return {"run_kind": "pilot" if pilot else "final", "output_directory": display(output),
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
            "git_status_at_start": git("status", "--porcelain"),
            "environment": {"python": sys.version, "python_executable": sys.executable,
                            "platform": platform.platform(), "machine": platform.machine(),
                            "implementation": platform.python_implementation(), "cpu_model": cpu,
                            "memory_total": memory, "logical_cpus": os.cpu_count(),
                            "python_hash_seed": python_hash_seed(),
                            "python_hash_seed_set": "PYTHONHASHSEED" in os.environ,
                            "unicode_database": unicodedata.unidata_version, "pytest": version("pytest")},
            "clock": vars(get_clock_info("perf_counter")),
            "background_load": background}


def add_run_options(parser, standard_pilot: str, standard_final: str) -> None:
    parser.add_argument("--pilot", action="store_true",
                        help="ein Warmup, drei Messungen; Parameter und Messcode für den Finallauf sperren")
    parser.add_argument("--ausgabe", metavar="NAME",
                        help=f"neuer Ordner unter ergebnisse/messungen (Standard {standard_pilot} bzw. {standard_final})")
    parser.add_argument("--pilot-ordner", metavar="NAME", default=standard_pilot,
                        help=f"Pilotordner mit pilot_decision.json für den Finallauf (Standard {standard_pilot})")
    parser.add_argument("--hintergrundlast", metavar="TEXT", default=PLANNED_BACKGROUND,
                        help="tatsächliche Hintergrundlast für die Metadaten")
    parser.add_argument("--replace-pilot", action="store_true",
                        help="nur mit --pilot: vorhandenen Pilotordner bewusst ersetzen")
