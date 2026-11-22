# Reihe 03b: Galloping Search gegen Zwei-Zeiger

Die Reihe misst, ab welchem Längenverhältnis der galoppierende Schnitt (`search_index_boolean(..., "AND", "galloping")`, intern `intersect_galloping`) gegenüber dem Zwei-Zeiger-Schnitt mit kürzester Liste zuerst (`search_index_boolean(..., "AND", "shortest_first")`, intern `intersect_sorted`) Zeit spart. Beide Verfahren laufen über die öffentliche Funktion. Normalisieren, Postings sammeln, stabiles Sortieren nach Länge und die vollständige sortierte Ergebnisliste gehören zur Abfragezeit. Die Reihe ist eigenständig und nicht direkt mit Reihe 03 (1.000 Dokumente) vergleichbar.

## Versuchsplan (abgestimmt am 14.10.2026, im Pilot gesperrt)

| Größe | Wert |
| --- | --- |
| Korpus | 10.000 erzeugte Dokumente `d00000.txt` bis `d09999.txt` (feste Breite), je 100 Tokens, N = 1.000.000 |
| Tokens | alle Anfrage- und Fülltokens vier ASCII-Zeichen (`l000`, `v000`, `a000`, `f000` bis `f049`), Großschreibung und Satzzeichen in den Dateien |
| Anfrage | AND, k = 2, kurzes Wort zuerst, dann langes Wort |
| Lange Liste | 10 Stufen df = 10, 20, 50, 100, 200, 500, 1.000, 2.000, 5.000, 10.000, je eigenes Wort `l000` bis `l009`, gleichmäßig über alle Dokumente (Dokument i·10.000/df) |
| Fall „verteilt“ (Hauptfall) | kurzes Wort `v000` bis `v009` mit df = 10, Teilmenge der langen Liste an den Stellen (j+1)·df/10−1, j = 0 bis 9. Der letzte Eintrag der langen Liste gehört dazu, das Zwei-Zeiger-Verfahren läuft also die ganze lange Liste ab |
| Fall „anfang“ (Gegenprobe) | kurzes Wort `a000` bis `a009` mit df = 10 = die ersten 10 Einträge der langen Liste, das Zwei-Zeiger-Verfahren endet früh |
| Verfahren | nur `and_shortest_first` (Zwei-Zeiger) und `and_galloping` |
| Direkte Suche | nur Trefferprüfung vor dem ersten Timer, nicht gemessen |
| Pilot | 1 Warmup, 3 Wiederholungen, Blöcke mit 5 Aufrufen |
| Final | 5 Warmups, 20 Wiederholungen, Blöcke mit 5 vollständigen Aufrufen, `PYTHONHASHSEED=0` |

Die 40 Blöcke aus Verfahren und Anfrage werden je Wiederholung mit festem Seed gemischt. Ergebnisse eines Blocks werden vor dem nächsten Timer freigegeben. Laden, Aufbereitung und Indexaufbau werden mit dem gemeinsamen `measure_phase` getrennt gemessen. Zeitmessung mit `time.perf_counter_ns`, Rohschema `gemeinsam.messung.CSV_FIELDS`, Speicherfelder bleiben leer.

Vor dem ersten Timer werden alle Tokenfolgen gegen den Pflanzplan, der Index gegen unabhängig gebildete Postings und jede Anfrage über die direkte Suche und beide Indexvarianten gegen die Mengenoracle des Plans geprüft. Die Diagnose läuft getrennt über eigene Nachbildungen in `../boolean_diagnostics.py`: Zwei-Zeiger zählt `==` und bei Ungleichheit zusätzlich `<` (`diagnose_postings`), die Galloping Search zählt Proben der Sprungphase, Binärsuchschritte und Gleichheitsprüfungen (`diagnose_postings_galloping`). Diese Zähler sind keine Zeitmessungen.

## Befehle

Aus dem Repository-Verzeichnis.

```sh
# Pilot (sperrt Parameter, Messcode und PYTHONHASHSEED)
PYTHONHASHSEED=0 .venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/galloping/run.py --pilot
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/galloping/verify_results.py --eingabe 03b_pilot

# Finallauf (nur auf ruhiger Maschine)
PYTHONHASHSEED=0 .venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/galloping/run.py \
    --ausgabe 03b_galloping --pilot-ordner 03b_pilot --hintergrundlast "TEXT"
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/galloping/verify_results.py --eingabe 03b_galloping
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/galloping/analyse.py --eingabe 03b_galloping
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/galloping/plots/render.py --eingabe 03b_galloping
```

Laufkonvention wie die neue Reihe 01 (gemeinsamer Code in `../messlauf03.py`, auch für den BGB-Realteil der Reihe 03): `--ausgabe NAME` wählt einen neuen Ordner unter `ergebnisse/messungen` (Standard `03b_pilot` bzw. `03b_galloping`), `--pilot-ordner NAME` den Pilot für den Finallauf (Standard `03b_pilot`), `--hintergrundlast TEXT` landet in `metadata.json`. Ein nicht leerer Ordner wird nie überschrieben, ein Pilot nur mit `--pilot --replace-pilot` bewusst ersetzt. Pilot und Finallauf verlangen `PYTHONHASHSEED=0`. Der Finallauf bricht ab, wenn der Pilot fehlt oder Parameter, Messcode oder Hashseed seit dem Pilot abweichen. Der gebundene Messcode umfasst `gemeinsam/src/gemeinsam/*.py`, die Pakete `invertierter_index` und `boolesche_suche`, alle `*.py` dieses Ordners, `../boolean_diagnostics.py`, `../messlauf03.py`, `gemeinsam/__init__.py`, `pyproject.toml` und `requirements-dev.txt`. Ändert sich eine dieser Dateien vor dem Finallauf, muss der Pilot neu laufen (neuer Name mit `--ausgabe` oder `--replace-pilot`).

Ausgabe je Lauf: `raw.csv`, `summary.json` (Median, Q1, Q3, IQR, Minimum, Maximum), `metadata.json` (Parameter, Plan, Umgebung mit `PYTHONHASHSEED`, Git-Stand, Dateimanifest mit SHA-256 aller 10.000 Dateien, Anfragen, Postinglängen, Diagnosen) und `code_source/` mit den gebundenen Quellständen. Der Pilot schreibt zusätzlich `pilot_decision.json`, der Finallauf verweist mit SHA-256 auf diese Datei. `verify_results.py --pilot` ist eine Kurzform für `--eingabe 03b_pilot`.

`verify_results.py` prüft Schema, alle Blockzeiten, die Statistik, die gemischte Reihenfolge inklusive Warmups, Quellarchive und den aktiven Code. Es erzeugt den Korpus neu, vergleicht alle Dateihashes und wiederholt sämtliche Prüfungen und Diagnosen. `--archive-only` erlaubt spätere Codeänderungen und prüft weiterhin Archive, Rohwerte und Daten. `analyse.py` schreibt `comparisons.json` und `auswertung.md` (Median, IQR, Verhältnis Zwei-Zeiger/Galloping, Vergleichszahlen je Stufe und Fall). `plots/render.py` (Matplotlib 3.10.1, Entwicklungswerkzeug) erzeugt `ergebnisse/abbildungen/03b_galloping.{png,svg,pdf}`: Liniendiagramm mit logarithmischer x-Achse (df der langen Liste) und logarithmischer y-Achse (Median pro Anfrage in µs), zwei Verfahren mal zwei Fälle, Q1 bis Q3 als halbtransparente Bänder. Vorhandene Abbildungen werden nur mit `--replace` ersetzt. `plot_manifest.json` und `plot_source/render.py` binden Eingaben, Quelle und Ausgaben an SHA-256. Beide Skripte lesen `--eingabe NAME` (Standard `03b_galloping`), `render.py` zusätzlich `--figure-dir`. Die Tests rufen die Funktionen nur mit temporären Kopien des Pilots auf.

Tests: `themen/03_boolesche_mehrwortsuche/experimente/tests/test_galloping_03b.py`.
