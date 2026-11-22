# Ausgeführte Untersuchung zu Thema 01

Aus dem Repositoryverzeichnis mit der installierten Umgebung:

```sh
.venv/bin/python -m pytest themen/01_textaufbereitung_direkte_suche/experimente/tests -q
```

## Neumessung der Reihe 01 (01b)

Die Reihe wird unter denselben Bedingungen wie die Reihen 02 bis 05 neu gemessen: `PYTHONHASHSEED=0`, keine parallelen Projekttests, PDF-Builds oder anderen Messreihen. Realkorpus der Neumessung ist das BGB (`daten/real/bgb/dokumente/`, 2.486 Paragraphen, ein Paragraph je Dokument); der Kafka-Auszug gehört nur noch zu den gelieferten Ergebnissen. Pilot und Hauptlauf schreiben in neue Ordner unter `ergebnisse/messungen/`:

Die Neumessung vom 14.10.2026 lief mit diesen Befehlen (Pilot `01b_pilot`, Hauptlauf `01b_direkte_suche`, beide mit BGB-Realteil):

```sh
PYTHONHASHSEED=0 .venv/bin/python themen/01_textaufbereitung_direkte_suche/experimente/run.py --pilot --ausgabe 01b_pilot --hintergrundlast "TEXT"
PYTHONHASHSEED=0 .venv/bin/python themen/01_textaufbereitung_direkte_suche/experimente/run.py --ausgabe 01b_direkte_suche --pilot-ordner 01b_pilot --hintergrundlast "TEXT"
.venv/bin/python themen/01_textaufbereitung_direkte_suche/experimente/verify_results.py --eingabe 01b_direkte_suche
```

Ein heute zuvor unter Last entstandener Pilot mit Kafka-Realteil wurde ersetzt und liegt nicht im Repository.

`--ausgabe NAME` wählt genau einen Ordnernamen unter `ergebnisse/messungen/` (Standard `01b_pilot2` mit `--pilot`, also der Name für einen künftigen neuen Pilot, sonst `01b_direkte_suche`). Existiert der Ordner und ist nicht leer, bricht das Skript vor jeder Messung ab; die gelieferten Ordner `01_pilot` und `01_direkte_suche` werden nie überschrieben. Der Pilot schreibt `pilot_decision.json` mit den gesperrten Parametern, den SHA-256 des gemessenen Codes und dem tatsächlichen `PYTHONHASHSEED`. Der Hauptlauf liest diese Datei aus `--pilot-ordner NAME` (Standard `01b_pilot2`, für den Lauf vom 14.10.2026 ausdrücklich `01b_pilot`) und bricht ab, wenn Parameter, Messcode oder Hashseed abweichen. Hat sich der Code nach dem Pilot geändert, ist ein neuer Pilot in einen neuen Ordner nötig, etwa `--pilot --ausgabe 01b_pilot2` und danach `--pilot-ordner 01b_pilot2`. `--hintergrundlast TEXT` hält die tatsächliche Hintergrundlast in den Metadaten fest; ohne Angabe steht dort das geplante Protokoll mit dem Hinweis, dass das Skript es nicht prüft.

Jeder neue Lauf archiviert alle gehashten Quellen unter `code_source/` und schreibt `PYTHONHASHSEED` (`random`, wenn nicht gesetzt) sowie `python_hash_seed_set` in die Metadaten. Der Hauptlauf legt seine Abbildungen ausschließlich unter `<ausgabe>/abbildungen/` ab; `ergebnisse/abbildungen/` bleibt unverändert.

### BGB-Realteil der Neumessung

Datensatz `real_bgb`, Korpushash `dc1641fd49dfa45270a1865f454abd64cf7cf94d79b37af9657ff97d7602eadf`, D=2.486, N=213.718. Vor der Messung prüft der Lauf alle 2.486 Dateien (Bytes, SHA-256, kanonischer Korpushash) gegen `daten/real/bgb/manifest.json`, vergleicht die produktive Aufbereitung Dokument für Dokument mit einer unabhängigen Regex-Tokenisierung, prüft D, N und die 13 Anfangstokens von `bgb_0001.txt` und für jede Anfrage cf, df, die vollständige Trefferliste (bei „der“ Anzahl, SHA-256 und Ränder), erstes Dokument mit Position und die Tokenvergleiche der direkten Suche gegen `daten/real/bgb/anfragevorschlaege.json`:

| `query_id` | Anfrage | df | cf | erster Treffer | Tokenvergleiche direkt |
|---|---|---:|---:|---|---:|
| `early` | Beginn | 52 | 63 | `bgb_0001.txt`, Position 0 | 208.860 |
| `frequent` | der | 2.280 | 11.486 | `bgb_0001.txt`, Position 1 | 37.889 |
| `rare` | Erbschaftskauf | 1 | 1 | `bgb_2385.txt`, Position 9 | 213.615 |
| `missing` | Server | 0 | 0 | – | 213.718 |

Die direkte Suche bricht nur innerhalb eines Dokuments ab und öffnet stets alle 2.486 Paragraphen. Der Realteil hat damit vier statt drei Anfragen: 21 Gruppen, im Hauptlauf 420 Rohwerte.

## Prüfung gespeicherter Ergebnisse

```sh
.venv/bin/python themen/01_textaufbereitung_direkte_suche/experimente/verify_results.py --archive-only
.venv/bin/python themen/01_textaufbereitung_direkte_suche/experimente/verify_results.py --eingabe 01_pilot --archive-only
.venv/bin/python themen/01_textaufbereitung_direkte_suche/experimente/verify_results.py --eingabe 01b_pilot
```

`verify_results.py` prüft die vorhandenen Rohwerte, das Schema und die Auswertung unabhängig mit `statistics`, rekonstruiert alle generierten Größen zur Prüfsummenprüfung und prüft den gemessenen Codezustand. Es führt keine Zeitmessung aus und ändert keine Repositorydatei. Ohne `--eingabe` prüft es die gelieferte Reihe `01_direkte_suche`. Wiederholungs- und Zeilenzahlen folgen aus dem gesperrten Messplan (Pilot 1/3, Hauptlauf 5/20) und der Zahl der Anfragen. Kafka-Läufe prüft es gegen `daten/real/kafka_verwandlung/`, BGB-Läufe gegen Manifest, Anfragevorschläge und die BGB-Dateien selbst.

Für die gelieferten Ordner `01_direkte_suche` und `01_pilot` ist nur das gemessene Skript als `run_source_measured.py` archiviert. Seit der Erweiterung um neue Zielordner weicht das aktive `run.py` davon ab; diese Ergebnisse bestehen deshalb nur noch mit `--archive-only`. Dieser Modus prüft das archivierte gemessene Skript weiterhin gegen beide aufgezeichneten Prüfsummen. Alle übrigen Quellen besitzen dort kein Archiv und werden wie bisher gegen den aktiven Stand geprüft. Neue Läufe prüfen ohne `--archive-only` Archiv und aktiven Code; mit `--archive-only` nur das Archiv.

Die drei generierten Korpora besitzen jeweils 20 gleich lange Dokumente und 10.000, 100.000 beziehungsweise 1.000.000 Tokens. Der Startwert ist 20261006; alle freien Positionen stammen aus `wort0000` bis `wort0999`. `Fehler` steht an Position 0 und jeder durch 100 teilbaren Position jedes Dokuments; `Verbindung` steht ausschließlich am Ende des ersten Dokuments. `Unauffindbar` ist ausgeschlossen. Der reale Korpus der gelieferten Reihe ist der dokumentierte Kafka-Auszug unter `daten/real/kafka_verwandlung/`, der der Neumessung das BGB (siehe oben).

Generierte Dateien liegen während der Ausführung in einem temporären Verzeichnis. Byteidentische Dateien lassen sich mit `gemeinsam.datengenerator.generate_corpus` und den gespeicherten Parametern erneut erzeugen. `metadata.json` hält je Datei Kennung, Byteanzahl und SHA-256 sowie eine SHA-256 über das kanonische Dateimanifest fest. Die generierten vollständigen Tokenfolgen und Treffer werden vor der Messung gegen den Pflanzplan geprüft; diese Erwartungen benötigen keine zentrale Tokenisierung. Der reale Auszug wird gegen seine unabhängig geprüften Tokens am Anfang, Gesamttokenzahl, Suchworthäufigkeiten, Treffer, Positionen und Prüfsumme geprüft.

`gemeinsam.messung` ist für spätere Verfahren wiederverwendbar:

- `MeasurementPlan`: Aufwärmläufe, Wiederholungen, Abfragen je Block und Seed.
- `measure_phase`: getrennte vollständige Lade-, Aufbereitungs- und
  Indexaufbauschritte mit einem Validator außerhalb des Zeitintervalls.
- `measure_queries`: öffentliche Abfragefunktion, feste `QuerySpec`-Erwartungen,
  deterministisch gemischte Anfragefolge und Blockzeiten.
- `write_measurements` und `summarize_measurements`: gemeinsames Rohwertschema
  und gruppierter Median mit inklusiven Quartilen.

Die finale Reihe verwendet 5 Aufwärmläufe und 20 Messwiederholungen. Eine Suchmessung enthält 10 gleiche vollständige Abfragen; `query_ms` ist die Blockzeit geteilt durch 10. `elapsed_ns` speichert die ungerundete ganzzahlige Blockdauer. Abfrageaufbereitung und die vollständige sortierte Trefferliste sind enthalten. Zeitmessung erfolgt mit `perf_counter_ns`. Korrektheitsprüfungen, Zählen, Ausgaben und Dateischreiben erfolgen außerhalb der Intervalle. Der Block selbst enthält Schleifen- und Listensammelaufwand; er wird bei späteren Algorithmen gleich angewandt.

`load_ms` umfasst Verzeichnissuche, Pfadsortierung, Lesen und UTF-8-Decodierung. `preparation_ms` umfasst die gesamte gemeinsame Aufbereitung. Aufbau- und Speicherfelder bleiben für direkte Suche leer. Der Korpus ist bereits vor den Zeitmessungen zur Prüfung gelesen; der Betriebssystemcache wird nicht geleert. Die Ladezeiten beschreiben daher wiederholtes Lesen bei warmem Cache. Die Messumgebung war nicht isoliert. Die Neumessung 01b vermeidet den parallelen Build und setzt `PYTHONHASHSEED=0`.

`query_type` bezeichnet die Suchsemantik und ist hier `word`. Die Häufigkeitsklasse steht in `query_id` und ausdrücklich als `query_frequency` in den Metadaten. Beim gespeicherten ersten Lauf wurden diese beschreibenden Felder nach der Messung vereinheitlicht. Alle Zeitwerte blieben unverändert; `recording_correction` dokumentiert die Anpassung und die Skriptprüfsummen. `run_source_measured.py` archiviert den dazu passenden Quellstand und dient als Prüfartefakt; zur erneuten Ausführung wird das reguläre Skript verwendet.

Pro finalem Datensatz entstehen 20 Lade-, 20 Aufbereitungs- und 60 Suchmesswerte, insgesamt 400 CSV-Zeilen. `summary.json` enthält daraus 20 Gruppen mit je 20 Werten. Die beschrifteten SVG- und PNG-Abbildungen des gelieferten Laufs liegen unter `ergebnisse/abbildungen/01_*`, die der Neumessung unter `ergebnisse/messungen/01b_direkte_suche/abbildungen/`. `rule_comparison.json` dokumentiert eine einzige Regeländerung: `casefold()` gegenüber `lower()` bei sonst gleicher NFC- und Tokenisierung. Für diesen Vergleich wird keine Laufzeitbehauptung abgeleitet.

