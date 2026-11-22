"""Strenge Verträge für Versuchsdefinitionen und Integer-Rohwerte."""
import csv
import math
from pathlib import Path

from gemeinsam.messung import CSV_FIELDS


def validate_config(config):
    required = {"schema_version", "seed", "warmups", "repeats", "block_size", "memory_repeats", "datasets", "q_values"}
    if not isinstance(config, dict) or not required <= config.keys():
        raise ValueError("Versuchsdefinition: Pflichtfelder fehlen")
    allowed = required | {"total_repeats", "sequence_block_size", "pilot_directory", "mode"}
    if config.keys() - allowed:
        raise ValueError(f"Unbekannte Konfigurationsfelder: {sorted(config.keys()-allowed)}")
    if "pilot_directory" in config and (not isinstance(config["pilot_directory"],str) or not config["pilot_directory"]):
        raise ValueError("pilot_directory muss eine nichtleere Zeichenkette sein")
    if "mode" in config and config["mode"] not in ("pilot","main"):
        raise ValueError("mode muss pilot oder main sein")
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ValueError("schema_version muss 1 sein")
    for field, minimum in (("seed",0),("warmups",0),("repeats",2),("block_size",1),
                           ("memory_repeats",2),("total_repeats",2),("sequence_block_size",1)):
        value = config.get(field, {"total_repeats":5,"sequence_block_size":50}.get(field))
        if type(value) is not int or value < minimum:
            raise ValueError(f"{field}: ganze Zahl >= {minimum} erforderlich")
    datasets = config["datasets"]
    if not isinstance(datasets,list) or not datasets or any(not isinstance(d,dict) or not isinstance(d.get("id"),str) or not d["id"] for d in datasets):
        raise ValueError("datasets: nichtleere Liste mit eindeutigen IDs erforderlich")
    if len({d["id"] for d in datasets}) != len(datasets):
        raise ValueError("Doppelte Datensatzkennung")
    for d in datasets:
        if not d["id"].replace("_", "").replace("-", "").isalnum():
            raise ValueError("Datensatz-ID muss aus Buchstaben/Ziffern/_/- bestehen")
        if d.get("kind") not in ("synthetic", "real"):
            raise ValueError("Ungültiger Datensatztyp")
    qs = config["q_values"]
    if not isinstance(qs,list) or not qs or any(type(q) is not int or q < 0 for q in qs) or qs != sorted(set(qs)):
        raise ValueError("q_values: sortierte eindeutige nichtnegative ganze Zahlen erforderlich")
    return config


def read_csv(path, fields=CSV_FIELDS):
    with Path(path).open(encoding="utf-8",newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(fields):
            raise ValueError(f"Falsche Felder/Einheiten in {path}")
        rows = list(reader)
        if any(None in r or any(v is None for v in r.values()) for r in rows):
            raise ValueError("Beschädigte CSV-Zeile")
        return rows


def integer(value, name, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f"{name}: Integer erforderlich")
    text = str(value)
    if not text.isdecimal():
        raise ValueError(f"{name}: Integer erforderlich")
    number = int(text)
    if number < minimum:
        raise ValueError(f"{name}: zu klein")
    return number


def check_derived(value, expected, name):
    try:
        number = float(value)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{name}: ungültige Einheit/Zahl") from error
    if not math.isfinite(number) or not math.isclose(number, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError(f"{name}: inkonsistente Ableitung/Einheit")


FLOW_FIELDS = ("run_id","dataset_id","profile_id","algorithm","repeat","order_index",
               "query_count","elapsed_ns","unit","result_digest","correct")
BATCH_FIELDS = ("run_id","dataset_id","profile_id","algorithm","repeat","order_index",
                "query_count","elapsed_ns","ns_per_query","unit","correct")


def write_csv(path, rows, fields):
    path = Path(path)
    with path.open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
