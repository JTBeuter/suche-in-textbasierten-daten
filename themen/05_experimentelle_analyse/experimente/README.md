# Versuchsdefinitionen für die Gesamtintegration

Aus dem Repository-Verzeichnis nach Installation gemäß Haupt-README:

```sh
.venv/bin/python -m experimentelle_analyse generate --config themen/05_experimentelle_analyse/experimente/pilot.json --output /tmp/textsuche05_daten
.venv/bin/python -m pytest themen/05_experimentelle_analyse/tests/test_datasets05.py -q
PYTHONHASHSEED=0 .venv/bin/python -m experimentelle_analyse run --config themen/05_experimentelle_analyse/experimente/pilot.json --output ergebnisse/messungen/05_pilot
PYTHONHASHSEED=0 .venv/bin/python -m experimentelle_analyse run --config themen/05_experimentelle_analyse/experimente/main.json --output ergebnisse/messungen/05_experimentelle_analyse
.venv/bin/python -m experimentelle_analyse verify --input ergebnisse/messungen/05_experimentelle_analyse --archive-only
.venv/bin/python -m experimentelle_analyse analyse --input ergebnisse/messungen/05_experimentelle_analyse --output ergebnisse/abbildungen/05
.venv/bin/python themen/05_experimentelle_analyse/experimente/render.py
```

Ein Zielverzeichnis für Datensätze muss neu sein. Wiederholte Erzeugung wird in einem anderen Verzeichnis ausgeführt; vorhandene Korpora werden nicht überschrieben. `generate` speichert Rohdateien, Manifest und Abfragen vor jeder Zeitmessung. Laufende Suchmessungen dürfen nicht mit anderen Projektmessungen, Tests oder Builds überlappen.

## Festgelegte Daten und Abfragen

Beide Konfigurationen verwenden denselben synthetischen Korpus `synthetic_10000`: D=20, L=500, N=10000, V=64, Seed=20261006. Der Generator `05-planted-v1` übernimmt den bekannten Pflanzplan aus Thema 04 mit angepasstem Füllwortschatz. Fünf häufige Marker `f000` bis `f004` stehen alle 50 Tokens zusammen. Fünf seltene Marker `s000` bis `s004` stehen ab 30 nur in den ersten zwei Dokumenten. Ab 20 steht sechsmal `r000`; dadurch sind sämtliche überlappenden Treffer für Phrasen bis Länge 5 bekannt. Fünf Marker `z000` bis `z004` stehen ab 40 in jedem Dokument. Die übrigen 48 Wörter `b000` bis `b047` werden gleichverteilt gezogen und auf freien Positionen mindestens einmal garantiert. Rohdateien enthalten Großschreibung und Punkte; die unabhängig geplanten Tokens bleiben kleingeschriebene ASCII-Wörter.

Der zweite Datensatz bleibt der bestehende reale Kafka-Auszug `daten/real/kafka_verwandlung` mit D=1, N=1271 und acht Absätzen. Archiv, Bereinigung, Quellfassung und Nutzungshinweise werden anhand des vorhandenen Manifests erneut geprüft. Der Download wird nicht wiederholt. Der Quellen- snapshot und das einzige Suchdokument bleiben byteidentisch. Eine erneute geprüfte Kopie einschließlich `quelle.pg` und Quellenmanifest liegt pro Lauf unter `<output>/datasets/kafka/corpus`, sodass der gespeicherte Lauf nicht vom ursprünglichen Korpuspfad abhängt.

Query-Erzeugung `05-queries-v1` ist deterministisch und verwendet keinen eigenen Seed. Synthetisch entstehen 46 und im Kafka-Auszug 40 Queries: Wortanfragen häufig/selten/fehlend; AND/OR jeweils 2, 3 und 5 Begriffe in vier Frequenzgruppen; Phrasenlängen 1, 2, 3 und 5 vorhanden/fehlend. Synthetisch kommen Wiederholungen und falsche Reihenfolgen hinzu; real ist `Gregor Gregor` mit den unabhängig festgelegten Starts 1060 und 1078 vorhanden. Häufige reale Wörter beziehungsweise Phrasen werden nach CF gewählt, seltene Phrasen nach kleinster positiver CF, mit lexikografischer Auflösung von Gleichständen. Die seltene reale Wortanfrage ist das bereits unabhängig geprüfte `Fenster` mit einer Position. IDs enthalten Datensatz, Suchtyp, Kategorie und Begriffslänge.

Jede Query enthält `id`, `kind`, `text`, `terms`, `category`, `length`, `cf`, `df`, `expected`, `hit_count` und `position_count`. CF und DF gelten je Begriff. `expected` enthält sortierte Dokument-IDs beziehungsweise sämtliche Startpositionen je Dokument. `position_count` ist nur bei Phrasen eine Zahl, ansonsten `null`; Dokumenttreffer sind immer über `hit_count` vergleichbar. Ein Begriff der Gruppe `missing` kann bei OR vorhandenem übrigen Vokabular weiterhin zu Dokumenttreffern führen. Die direkte Referenz verwendet ausschließlich Tupelmitgliedschaft und Tupelschnitte des unabhängigen Tokenplans, keine produktive Suche und keinen Index.

## Messumfang und Pilotentscheidung

`pilot.json` enthält einen Aufwärmlauf, drei Wiederholungen, fünf Anfragen je Suchblock, drei isolierte Speicherwiederholungen und drei vollständige Gesamtkostenwiederholungen. `main.json` enthält fünf Aufwärmläufe, zwanzig Wiederholungen, fünf Anfragen je Suchblock und fünf Gesamtkostenwiederholungen. Ein zum Gesamtkostenprofil passender separater Suchblock hat in beiden Fällen 50 Anfragen. Bei Änderungen der Messdefinition muss ein neuer Pilot vor dem Hauptlauf erfolgen.

Die feste Q-Liste ist 0, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000. Die im Pipeline-Quellstand festgelegte Funktion `q_grid()` setzt vor den Hauptmessungen eine einheitliche zusätzliche Pilotregel um: Q in der Umgebung der aus Pilotkosten berechneten ersten strikt günstigeren Abfrageanzahl q, mit den Werten floor(q/2), q-1, q, q+1 und 2q, begrenzt bei Q=5000. Die feste Q-Liste bleibt zusätzlich erhalten. Ohne spätere Amortisation wird die feste Liste nicht ergänzt. Der Hauptlauf muss die tatsächlich angewandten Abfrageanzahlen speichern; die Regel darf nicht anhand gewünschter Resultate verändert werden. Profile vergleichen dieselbe vorher gewählte Einzelanfrage beziehungsweise festgelegte Abfragefolge mit den entsprechenden öffentlichen direkten und indexbasierten Operationen.

Die bereits geprüften Skalierungs-, Wortschatz-, booleschen und Positionsreihen aus Themen 01 bis 04 bleiben eigene Messungen. Die kleinere neue Reihe misst die vollständigen Kostenfolgen und führt deren Interpretation zusammen. Synthetische und reale Ergebnisse müssen getrennt ausgewiesen werden.

## Artefakte und Reproduzierbarkeit

Je Datensatz werden vollständige Parameter, Generatorfassung, Dateiordnung, SHA-256 je Rohdatei, N/D/V/Bytes und sämtliche unabhängig erwarteten Tokens gespeichert. Abfragen stehen als eigene JSON-Datei neben dem Manifest, dessen Hash sie absichert. Der Generator benutzt einen lokalen Zufallsgenerator. Tests vergleichen zwei vollständige Wiedererzeugungen, kontrollieren feste Unicode-Erwartungen, alle überlappenden Phrasepositionen und beschädigte reale Archive/Auszüge beziehungsweise zusätzliche Dokumente.

Die verwendeten Python-/Unicode-Versionen und vollständigen Quellfassungen gehören zusätzlich in die Messmetadaten der Pipeline. Eine Version und ein Seed ersetzen keinen Dateivergleich. Die reale Beschaffung ist ohne Netzwerk aus dem bereits archivierten Quellenstand nachvollziehbar; genaue Quelle, Abrufzeit, Nutzungsbedingungen und Auswahl bleiben in `daten/real/kafka_verwandlung/manifest.json` und dessen README dokumentiert.

Die zusätzlichen Daten-/Query-Regeln von Thema 05 stehen in [daten/05_gesamtvergleich.md](../../../daten/05_gesamtvergleich.md). Das historische `daten/README.md` bleibt für seinen ursprünglichen Integrationsnachweis byteidentisch erhalten.

## Ausgeführte Hauptserie

Pilot:612 Phasen-/Queryrohwerte, 72 Profilblöcke, 1002 vollständige Abläufe, 12 Speicherwerte; Hauptlauf:4080/480/1670/12. Alle Rohwertgruppen, Integerzeiten, Einheiten, Abfragen, wiederholten Ergebnisse, Q-Kalibrierung und Quellenstände wurden nach dem Lauf überprüft. Der separate `render.py` erzeugt die Publikationsbilder mit Q≥0 aus denselben geprüften Modellen; beide Skripte liegen außerhalb der eingefrorenen gemessenen Paketcodefassung. Das Bildmanifest benennt den tatsächlich verwendeten Renderer.

Für erneute Ausführung vorhandene Messziele erhalten und neue Namen verwenden, beispielsweise `05_pilot_neu` und `05_haupt_neu`; in einer Kopie von main.json `pilot_directory` auf das neue Pilotziel setzen. Daten-/Query-/Messgrenzenparameter müssen semantisch gleich bleiben; Wiederholungen/Warmups und mode unterscheiden Pilot/Hauptlauf. Experimente benötigen die Repositorystruktur und die dokumentierte Editable-Installation. Wheel-CLI/API wird zusätzlich unabhängig geprüft, ohne damit einen externen Wheel-Benchmark zu behaupten.

## Archivprüfung der gelieferten Läufe (Stand 14.10.2026)

Seit der Messung von `05_pilot` und `05_experimentelle_analyse` haben sich aktive Quellen geändert (Thema 03: Galloping Search und AND NOT, `provenance.py` ohne Pflicht auf `/proc/cpuinfo`, CLI-Erweiterung und BGB-Erweiterung in Thema 05). Der strenge Verifier scheitert deshalb erwartungsgemäß mit „Aktiver Quellcode weicht von Messfassung ab“. Der Archivmodus ersetzt nur diesen Vergleich durch die Prüfung von `code_source/` gegen die gespeicherten Hashes, wie `--archive-only` in den Reihen 03 und 04. Rohwerte, Reihenfolgen, Statistik, Daten- und Anfragereproduktion, Speicherprozesse und die Suchwiederholung mit dem aktiven Code bleiben unverändert geprüft. Das Ergebnis heißt ausdrücklich `verified_archive_only` und listet die abweichenden Dateien.

```sh
.venv/bin/python themen/05_experimentelle_analyse/experimente/verify_results.py --input ergebnisse/messungen/05_pilot --archive-only
.venv/bin/python themen/05_experimentelle_analyse/experimente/verify_results.py --input ergebnisse/messungen/05_experimentelle_analyse --archive-only
```

Die Python-API heißt `verify_run(pfad, archive_only=True)`, ebenso `analyse(..., archive_only=True)`, `render.py --archive-only`. Die Gesamt-CLI kennt den Schalter ebenfalls: `experimentelle_analyse verify --input … --archive-only` und `analyse … --archive-only`. `analyse` verweigert inzwischen das Schreiben in einen Ordner, der bereits Auswertungsdateien enthält; gelieferte Auswertungen werden nicht überschrieben.

## BGB-Realteil (Reihe 05, ab 14.10.2026)

Realkorpus der Arbeit ist das BGB, ein Paragraph je Dokument (`daten/real/bgb`, D=2.486, N=213.718, V=11.398). Die neuen Läufe enthalten nur diesen Datensatz, die synthetischen Ergebnisse der Reihe 05 werden nicht neu gemessen. Kafka und die alten Läufe bleiben unverändert prüfbar.

Konfigurationen: `bgb_pilot.json` (1 Aufwärmlauf, 3 Wiederholungen, 3 Gesamtablauf- Wiederholungen) und `bgb_main.json` (5/20/5, gebunden an `05_bgb_pilot`). Blockgrößen, Seed, Speicherwiederholungen und das Grundraster q=0, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000 sind dieselben wie in der bisherigen Reihe. Die Kalibrierregel ergänzt wie bisher floor(q/2), q−1, q, q+1 und 2q um die erste strikt günstigere Abfragezahl des Pilots. Eine Erweiterung des Rasters war nicht nötig: Der Pilot `05_bgb_pilot` ergibt q* weit innerhalb des Rasters bis 1.000 (Werte des Hauptlaufs in `ergebnisse/abbildungen/05_bgb/amortisation.json`); die Kalibrierregel ergänzt dort die Stufen.

Feste Profilanfragen (in der Konfiguration, Abfragegenerator `05-queries-fixed-v1`):

| Profil | Anfrage | Treffer (Dokumente) | Erwartung geprüft gegen |
|---|---|---:|---|
| `word_missing` | Server | 0 | Manifest, Vorschläge Reihe 01 und 05 |
| `word_frequent` | der | 2.280 (cf 11.486) | Manifest, Vorschläge Reihe 01 und 05 |
| `word_rare` | Verbindung | 16 (cf 21) | Manifest, Vorschläge Reihe 05 |
| `and_present3` | Gläubiger AND Schuldner AND Frist | 5 | Vorschläge Reihe 03 und 05 |
| `or_present3` | Mieter OR Vermieter OR Miete | 105 | Vorschläge Reihe 03 und 05 |
| `phrase_present3` | „im Sinne des“ | 62 (85 Starts) | Manifest, Vorschläge Reihe 04 und 05 |

Die erwarteten Ergebnisse stammen aus dem unabhängigen Tokenorakel dieses Pakets. Jede Anfrage muss zusätzlich mit mindestens einer unabhängig berechneten Erwartung aus `manifest.json` oder `anfragevorschlaege.json` übereinstimmen, sonst bricht der Lauf vor jeder Zeitmessung ab. Das AND-Profil verwendet wie bisher `shortest_first`.

Datenprüfung für Mehrdokumentkorpora (Manifest mit `corpus_root`), ersetzt die bisherige Prüfung auf genau ein Dokument: Quellarchiv und Abrufprotokoll, Größe und SHA-256 jedes Dokuments, kanonischer Korpushash, exakte Dateiliste, Offline- Neuerzeugung mit dem gepinnten `erzeuge_korpus.py pruefen` sowie unabhängige Tokenisierung gegen D/N/V/P, Dokumentlängen, Rangliste, Präfix, Wort- und Phrasenerwartungen des Manifests. Eine geprüfte Kopie (Daten, Archiv, Skripte, Dokumente) liegt pro Lauf unter `datasets/bgb/corpus/`. Gepinnt sind Manifest, Anfragevorschläge, Quellarchiv, Abrufprotokoll und Umwandlungsskript. Nach dem Finallauf darf `daten/real/bgb` nicht mehr geändert werden, sonst scheitert die Reproduktionsprüfung.

Laufkonventionen: neues leeres Zielverzeichnis (sonst Abbruch), Hauptlauf nur mit `PYTHONHASHSEED=0` (sonst Abbruch vor jeder Ausgabe, der Verifier prüft den Wert), Pilot vor Final mit identischem Code-Hash und identischen Versuchsparametern, Quellarchiv und Code-Hashes im Lauf. Die Metadaten enthalten unter `background_load` Lastmittel und die fünf CPU-stärksten Prozesse (nur Kurzname) vor der Messung, nach jedem Messabschnitt, nach jedem Profil und nach der Speichermessung. Die Angabe beschreibt die Umgebung, sie korrigiert keine Werte.

Mit `amortisation_table: abschnitt_3_6` schreibt `analyse` zusätzlich `amortisation.json` (Nanosekunden) und `amortisation.csv` (Millisekunden) mit den Bezeichnungen aus Abschnitt 3.6: t_Aufbau, t_direkt, t_index, q* = t_Aufbau/(t_direkt − t_index), ⌈q*⌉ und „nie“, wenn die Indexabfrage nicht schneller ist. Dazu die erste getestete Stufe, an der alle Paare positiv sind, mit dem Median der gepaarten Ersparnis dort. Alte Läufe besitzen das Feld nicht; ihre Auswertung bleibt bytegleich.

```sh
# Pilot (erledigt am 14.10.2026, siehe 05_bgb_pilot)
PYTHONHASHSEED=0 .venv/bin/python -m experimentelle_analyse run --config themen/05_experimentelle_analyse/experimente/bgb_pilot.json --output ergebnisse/messungen/05_bgb_pilot
.venv/bin/python -m experimentelle_analyse verify --input ergebnisse/messungen/05_bgb_pilot
# Final, erst wenn kein Quellcode mehr geändert wird und der Rechner sonst ruht
PYTHONHASHSEED=0 .venv/bin/python -m experimentelle_analyse run --config themen/05_experimentelle_analyse/experimente/bgb_main.json --output ergebnisse/messungen/05_bgb
.venv/bin/python -m experimentelle_analyse verify --input ergebnisse/messungen/05_bgb
.venv/bin/python -m experimentelle_analyse analyse --input ergebnisse/messungen/05_bgb --output ergebnisse/abbildungen/05_bgb
.venv/bin/python themen/05_experimentelle_analyse/experimente/render_bgb.py --input ergebnisse/messungen/05_bgb --analysis ergebnisse/abbildungen/05_bgb
```

Der Finallauf übernimmt die Stützstellen des Pilots und verlangt dessen Code-Hashes. Ändert sich nach dem Pilot irgendeine Datei unter `gemeinsam/src`, `themen/*/src`, `pyproject.toml` oder `requirements-lock.txt`, ist vorher ein neuer Pilot in ein neues Verzeichnis nötig (in einer Kopie von `bgb_main.json` dann `pilot_directory` anpassen). Jeder Gesamtablauf bereitet den Korpus neu auf (etwa 0,5 bis 2 s). Auf ruhiger Maschine dauerte der Pilot `05_bgb_pilot` am 14.10.2026 21 Minuten und der Hauptlauf `05_bgb` 34 Minuten. Bekannte Kleinigkeit der Lastangabe: `ps` erscheint unter den CPU-stärksten Prozessen manchmal selbst, weil sein pcpu über die kurze eigene Laufzeit gerechnet wird.
