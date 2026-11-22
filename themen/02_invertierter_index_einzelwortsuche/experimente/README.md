# Untersuchung 02

Aus der Repositorywurzel nach `.venv/bin/python -m pip install -e .`:

```sh
.venv/bin/python -m pytest themen/02_invertierter_index_einzelwortsuche/experimente/tests
PYTHONHASHSEED=0 .venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/run.py --pilot
.venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/verify_results.py --pilot
PYTHONHASHSEED=0 .venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/run.py
.venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/verify_results.py
```

Der Pilot prüft alle Korpora mit einem Warmup und drei gemessenen Wiederholungen und sperrt Parameter und gemessenen Code. Der finale Lauf verlangt diese unveränderte Freigabe und verwendet fünf Warmups und 20 Wiederholungen. Je Anfrage werden zehn Aufrufe als ein Messblock behandelt. Projekt-Tests und PDF-Builds sollen während Zeitmessungen ruhen. `PYTHONHASHSEED=0` macht auch die Hashiteration reproduzierbar; der tatsächlich gesetzte Wert steht in den Softwaremetadaten.

Die N-Reihe verwendet 10.000/100.000/1.000.000 Tokens, je 1.000 pro Dokument, also 10/100/1.000 Dokumente. Der Grundwortschatz umfasst 1.000 Wörter. Die V-Reihe verwendet 100/1.000/10.000 Grundwörter bei N=100.000 und D=100. Jedes Grundwort wird auf einer zufälligen freien Position garantiert; zusätzlich werden Fehler und Verbindung gepflanzt. Der erreichte Wortschatz ist daher 102/1.002/10.002. Die mittlere Stufe ist ein gemeinsamer Datenpunkt beider Reihen. Die Häufigkeit von Fehler ist N/100, df(Fehler)=D, Verbindung hat ein Vorkommen am Ende der ersten Datei, Unauffindbar fehlt. Der zusätzliche reale Kafka-Auszug und sein Manifest stammen unverändert aus Thema 01.

`generator.py` berechnet unabhängige Erwartungen direkt aus dem Pflanzplan. Ganze generierte Tokenfolgen, alle Postinglisten und Treffer werden vor den Messungen geprüft. Beim Realtext gelten dessen handgeprüfter Tokenanfang, Tokenzahl, Datei-Hashes und alle Positionen der Versuchswörter. Die gesamten Realtext-Tokens sind nicht unabhängig handverifiziert. Die direkten besuchten Tokens werden außerhalb der Messgrenzen aus der ersten Trefferposition je Dokument berechnet und in den Metadaten gespeichert.

`run.py` übernimmt `MeasurementPlan`, `QuerySpec`, `measure_phase` und das CSV-/Statistikschema aus `gemeinsam.messung`. Ein lokaler transparenter Treiber mischt zusätzlich alle sechs vollständigen (Verfahren, Anfrage)-Blöcke pro Wiederholung mit festem Seed. Auswahl, Zufall und Ergebnisprüfungen liegen außerhalb des Timers. Beide öffentlichen Suchfunktionen erhalten dieselben Rohtexte; Normalisierung, Ergebnismaterialisierung und Block-Schleifenaufwand sind enthalten. Laden und Korpusaufbereitung werden hier nicht erneut gemessen.

Nach dem Zeitlauf startet ein eigener Python-Prozess den Speicherlauf. Der Tracer startet je Build erst nach Laden und Aufbereitung. `memory.csv` hat ein eigenes Schema: Lauf/Datensatz, N/D/V/P, Wiederholung sowie bleibende und maximale zusätzliche Tracemalloc-Bytes und exklusiven Indexobjektspeicher. Der letztere zählt Indexobjekt, Proxy, Wörterbuch, Tupel und Strings jeweils einmal; bereits im Korpus existierende Token-/Kennungsstrings werden nach Objektidentität ausgenommen. Beide Maße sind Python-Speichermaße, keine RSS-Werte. Die drei Speicherwiederholungen sind keine Zeitmessungen; die Speicherfelder der Zeit-CSV bleiben leer.

`raw.csv`, `summary.json`, `metadata.json`, `memory.csv`, `memory.json` und Snapshots der gemessenen Quellen liegen unter `ergebnisse/messungen/02_invertierter_index/`, Pilotdaten unter `02_pilot/`. Die finale Auswertung erzeugt PNG/SVG-Abbildungen mit Präfix `02_`. `verify_results.py` prüft Schema, Einheiten, Leerfelder, Seed-Reihenfolgen, Mediane/Quartile, separate Speicherwerte, byteidentische Korpusrekonstruktion, erreichte Parameter, Trefferzahlen und Quelltext-Hashes. Nach bewusst später geändertem Code prüft `--archive-only` weiterhin die gemessenen Snapshots; dieser Modus behauptet keinen identischen aktuellen Codezustand.

Die N-Reihe verändert zugleich D und P bei fester Dokumentlänge. Die V-Reihe verändert zugleich V und P, da andere Wörter in mehr unterschiedlichen Dokumenten auftreten. Beide sind kontrollierte Verteilungsversuche und keine isolierte kausale Schätzung eines einzigen Parameters. Desktoplast, warme Datenstrukturen, Python-Objektverwaltung und Blockaufwand begrenzen die Übertragbarkeit.

## Zusatzmessung 02b: Anteil der Tokenprüfung am Indexaufbau

In der V-Reihe steigt die Aufbauzeit bei gleichem N von 4,7 auf 80,7 ms. `build_inverted_index` prüft jedes verschiedene Token einmal mit der zentralen Tokenisierung (`tokenize(token) == (token,)`) und führt dazu je Posting eine Abfrage im Set `checked_tokens` aus. `tokenpruefung.py` misst auf den drei V-Datensätzen `v100`, `n100000` und `v10000` (N=100.000, D=100, Seed 20261006) (a) die öffentliche Funktion und (b) die messinterne Kopie `build_ohne_tokenpruefung`, der genau diese Prüfung fehlt. Der Produktionscode bleibt unverändert.

```sh
.venv/bin/python -m pytest themen/02_invertierter_index_einzelwortsuche/experimente/tests/test_tokenpruefung.py -q
PYTHONHASHSEED=0 .venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/tokenpruefung.py --pilot --ausgabe 02b_pilot
.venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/tokenpruefung.py --pruefen 02b_pilot
PYTHONHASHSEED=0 .venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/tokenpruefung.py --ausgabe 02b_tokenpruefung --pilot-ordner 02b_pilot
.venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/tokenpruefung.py --pruefen 02b_tokenpruefung
```

Vor jeder Messung gilt: Die Generatorparameter stimmen mit den gespeicherten V-Datensätzen der Reihe 02 überein, die erzeugten Korpora sind byteidentisch (Korpus-SHA-256 aus `02_invertierter_index/metadata.json`), V und P stimmen, und beide Varianten liefern denselben Index wie die unabhängigen Sollpostings, einschließlich Schlüsselreihenfolge. Ein AST-Vergleich sichert, dass die Kopie der Produktionsfunktion ohne genau die Tokenprüfung entspricht; ändert sich `build_inverted_index`, bricht der Lauf ab.

Messplan wie Reihe 02: `measure_phase`, `perf_counter_ns`, Pilot ein Warmup und drei Wiederholungen, Hauptlauf fünf Warmups und 20 Wiederholungen je Variante und Datensatz. Die Reihenfolge der Varianten wechselt je Datensatz (`v100` a,b; `n100000` b,a; `v10000` a,b). Beide Varianten werden in getrennten Blöcken gemessen; Wiederholungen sind daher nicht gepaart.

Ausgabe in neue Ordner (Standard `02b_pilot`, `02b_tokenpruefung`); ein vorhandener nicht-leerer Ordner bricht vor der Messung ab. Der Pilot sperrt Parameter, Code-SHA-256 und `PYTHONHASHSEED` in `pilot_decision.json`; der Hauptlauf verlangt Gleichheit. `raw.csv` folgt `CSV_FIELDS` (Phase `build`, Algorithmus `inverted_index` bzw. `inverted_index_ohne_tokenpruefung`), `summary.json` enthält Median und inklusive Quartile, `auswertung.json` je Datensatz Median und IQR beider Varianten, die Differenz und den Anteil `(Median a − Median b) / Median a`. Der Anteil ist ein Verhältnis von Medianen, kein Konfidenzintervall. `--pruefen NAME` rechnet Statistik und Auswertung nach, prüft Reihenfolge, Korpus-Hashes gegen Reihe 02, Quellarchiv, AST-Kopie und Pilotsperre; `--archive-only` lässt später geänderte aktive Quellen zu.

## Realteil BGB (02_bgb)

`bgb_lauf.py` misst ausschließlich den realen BGB-Korpus (`daten/real/bgb/dokumente/`, 2.486 Paragraphen, ein Paragraph je Dokument). Die synthetischen Reihen und die gelieferten Ergebnisse unter `02_invertierter_index/` bleiben unverändert; `run.py` wird nicht geändert.

```sh
.venv/bin/python -m pytest themen/02_invertierter_index_einzelwortsuche/experimente/tests/test_bgb_lauf.py -q
PYTHONHASHSEED=0 .venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/bgb_lauf.py --pilot --ausgabe 02_bgb_pilot
.venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/bgb_lauf.py --pruefen 02_bgb_pilot
PYTHONHASHSEED=0 .venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/bgb_lauf.py --ausgabe 02_bgb --pilot-ordner 02_bgb_pilot
.venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/bgb_lauf.py --pruefen 02_bgb
```

Teil 1 misst die Aufbauzeit von `build_inverted_index` für die ersten k Paragraphen in Kennungsordnung (= Gesetzesreihenfolge). Die Werte werden vor der Messung aus einer unabhängigen Regex-Tokenisierung berechnet und gegen `anfragevorschlaege.json` (`reihe_02_index_teilmengen`) geprüft:

| Datensatz | D | N | V | P | letzte Kennung |
|---|---:|---:|---:|---:|---|
| `bgb_d0250` | 250 | 16.899 | 2.577 | 11.077 | `bgb_0241a.txt` |
| `bgb_d0500` | 500 | 44.221 | 4.699 | 26.529 | `bgb_0439.txt` |
| `bgb_d1000` | 1.000 | 103.733 | 7.750 | 61.468 | `bgb_0721.txt` |
| `bgb_d1500` | 1.500 | 135.600 | 8.975 | 83.782 | `bgb_1210.txt` |
| `bgb_d2000` | 2.000 | 183.132 | 10.595 | 112.759 | `bgb_1838.txt` |
| `bgb_d2486` | 2.486 | 213.718 | 11.398 | 133.909 | `bgb_2385.txt` |

Teil 2 vergleicht auf dem ganzen BGB `search_direct_word` und `search_index_word` mit dem Treiber `measure_comparison` aus `run.py`: alle 14 Blöcke (Verfahren × Anfrage) werden je Wiederholung mit festem Seed gemischt. Die Anfragen stammen aus den Reihen 01b (Beginn, der, Erbschaftskauf, Server) und 02 (Fehler, Verbindung, Unauffindbar). Ihre Erwartungen (df/cf, Trefferlisten, erste Position) stehen in `manifest.json` unter `independent_expectations.words`:

| `query_id` | df | cf | erster Treffer | Tokenvergleiche direkt |
|---|---:|---:|---|---:|
| `beginn` | 52 | 63 | `bgb_0001.txt`, Position 0 | 208.860 |
| `der` | 2.280 | 11.486 | `bgb_0001.txt`, Position 1 | 37.889 |
| `erbschaftskauf` | 1 | 1 | `bgb_2385.txt`, Position 9 | 213.615 |
| `server` | 0 | 0 | – | 213.718 |
| `fehler` | 5 | 10 | `bgb_0524.txt`, Position 9 | 213.201 |
| `verbindung` | 16 | 21 | `bgb_0307.txt`, Position 126 | 212.244 |
| `unauffindbar` | 0 | 0 | – | 213.718 |

Teil 3 startet nach dem Zeitlauf einen eigenen Python-Prozess mit `memory.profile_index` der Reihe 02: drei neue Builds je Teilmenge, gehaltener und Spitzen-Tracemalloc-Speicher sowie exklusiver Objektgraph (`memory.csv`, `memory.json`).

Messplan wie Reihe 02 (Pilot 1/3, Hauptlauf 5/20, Abfrageblöcke mit zehn Aufrufen). CLI wie bei 01b: `--pilot`, `--ausgabe NAME` (Standard `02_bgb_pilot`/`02_bgb`), `--pilot-ordner NAME`, `--hintergrundlast TEXT`; ein vorhandener nicht-leerer Ordner bricht ab; der Pilot sperrt Parameter, Code-SHA-256 und `PYTHONHASHSEED`. `auswertung.json` enthält je Teilmenge D/N/V/P, V/N, Aufbau-Median und IQR, µs je Posting und Speichermediane, die Heaps-Anpassung `V = K · N^β` (kleinste Quadrate über die sechs geschachtelten Teilmengen, nur beschreibend), je Anfrage die Mediane beider Verfahren und ihr Verhältnis sowie die Rang-Häufigkeit des ganzen BGB (Zipf, Gleichstand nach Term). Der Hauptlauf schreibt `abbildungen/02_bgb_teilmengen.{png,svg}` in seinen Ordner. `--pruefen NAME` rechnet Statistik, Reihenfolge, Speicherzusammenfassung und Auswertung nach und prüft BGB-Dateien, Tokens, Teilmengen und Treffer erneut. Grenzen: Die Teilmengen sind geschachtelte Präfixe in Gesetzesreihenfolge, keine Zufallsstichproben; die Paragraphen sind sehr ungleich lang (8 bis 1.168 Tokens).
