#!/usr/bin/env python3
"""Gespeicherten Lauf der Reihe 05 prüfen, wahlweise im Archivmodus.

Gleiche Prüfung wie ``python -m experimentelle_analyse verify``. Der Schalter
``--archive-only`` (analog zu den Reihen 03/04) lässt veränderte aktive Quellen
zu: Statt „aktive Quelle == Messfassung“ werden die archivierten Quellen unter
``code_source/`` gegen die gespeicherten Hashes geprüft. Rohwerte, Statistik,
Daten, Reihenfolgen, Speicherprozesse und die Suchwiederholung mit dem aktiven
Code bleiben vollständig geprüft. Die Ausgabe nennt die abweichenden Dateien.
"""
import argparse
import json
from pathlib import Path

from experimentelle_analyse.verify import verify_run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--input', required=True, type=Path, help='Messverzeichnis, z. B. ergebnisse/messungen/05_pilot')
    parser.add_argument('--archive-only', action='store_true',
                        help='aktive Quellen dürfen abweichen; Archiv, Rohwerte und Daten bleiben geprüft')
    args = parser.parse_args(argv)
    try:
        result = verify_run(args.input, archive_only=args.archive_only)
    except (ValueError, OSError, AssertionError) as error:
        parser.error(str(error) or type(error).__name__)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
