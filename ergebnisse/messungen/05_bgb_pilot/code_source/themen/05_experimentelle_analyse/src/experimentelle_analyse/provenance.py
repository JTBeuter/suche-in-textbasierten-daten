"""Quellarchive, Paket-/Hardwarestand und atomare JSON-Ausgaben."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import unicodedata


ROOT = Path(__file__).resolve().parents[4]
# Nur unter Linux vorhanden; macOS/Windows verwenden platform.processor().
CPUINFO = Path("/proc/cpuinfo")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+"\n", encoding="utf-8")
    temporary.replace(path)


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    files = list((ROOT / "gemeinsam/src").rglob("*.py"))
    for topic in (ROOT / "themen").iterdir():
        files += list((topic / "src").rglob("*.py"))
    files += [ROOT / "pyproject.toml", ROOT / "requirements-lock.txt"]
    return {p.relative_to(ROOT).as_posix(): sha_file(p) for p in sorted(files)}


def archive_sources(output, hashes):
    for name, digest in hashes.items():
        target = Path(output) / "code_source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = (ROOT / name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != digest:
            raise RuntimeError("Quellfassung während Archivierung verändert")
        target.write_bytes(payload)


def background_load(label):
    """Momentaufnahme der Hintergrundlast, nur zwischen Zeitintervallen aufgerufen.

    Lastmittel (1/5/15 min) und die fünf Prozesse mit dem höchsten CPU-Anteil
    (nur Kurzname, keine Argumente). ``pcpu`` von ps ist die CPU-Zeit geteilt
    durch die Laufzeit seit Prozessstart, kein Momentanwert. Fehlende Werkzeuge ergeben None statt
    eines Abbruchs; die Angabe beschreibt die Messumgebung, sie korrigiert nichts.
    """
    snapshot = {"label": label, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                "logical_cpus": os.cpu_count(), "loadavg_1_5_15": None, "top_cpu_processes": None}
    try:
        snapshot["loadavg_1_5_15"] = [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        pass
    try:
        output = subprocess.run(["ps", "-eo", "pid=,pcpu=,comm=", "--sort=-pcpu"], capture_output=True,
                                text=True, timeout=10, check=True).stdout.splitlines()
        processes = []
        for line in output[:5]:
            pid, pcpu, command = line.split(None, 2)
            processes.append({"pid": int(pid), "cpu_percent": float(pcpu), "command": command.strip()})
        snapshot["top_cpu_processes"] = processes
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return snapshot


def environment():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    clock = time.get_clock_info("perf_counter")
    cpu = platform.processor()
    if CPUINFO.is_file():
        cpu = next((line.split(":",1)[1].strip() for line in CPUINFO.read_text().splitlines()
                    if line.startswith("model name")), cpu)
    return {"recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
        "git_status": git("status", "--porcelain"), "python": sys.version,
        "python_executable": sys.executable, "unicode_version": unicodedata.unidata_version,
        "os": platform.platform(), "machine": platform.machine(), "cpu": cpu,
        "logical_cpus": os.cpu_count(), "pythonhashseed": os.environ.get("PYTHONHASHSEED", "unset"),
        "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        "clock": {"implementation": clock.implementation,"monotonic":clock.monotonic,
                  "resolution_seconds":clock.resolution,"unit":"ns"}}
