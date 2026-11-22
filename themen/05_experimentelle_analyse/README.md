# 05 – Experimentelle Analyse und Gesamtvergleich

## Implementierte Gesamtintegration

- Reproduzierbare Textdaten und Suchanfragen mit dokumentierten Parametern und festem Zufallsstartwert erzeugen.
- Ein gemeinsames Messverfahren für Aufbereitung, Indexaufbau, Suchzeit und Speicherbedarf entwickeln.
- Treffer vor der Laufzeitmessung gegen die direkten Referenzverfahren prüfen.
- Messungen mehrfach ausführen, Randbedingungen dokumentieren und Streuung berücksichtigen.
- Messergebnisse in [ergebnisse/messungen/](../../ergebnisse/messungen/) sammeln und Diagramme in [ergebnisse/abbildungen/](../../ergebnisse/abbildungen/) ablegen.
- Gesamtkosten der direkten und der indexbasierten Suche bei unterschiedlicher Anzahl von Abfragen vergleichen.

## Eigene Untersuchung

Ab wie vielen Suchanfragen gleichen die schnelleren Indexabfragen die Kosten des Indexaufbaus aus? Wie verändern Dokumentmenge, Wortschatz, Begriffshäufigkeit und Abfragetyp diesen Vergleich?

## Vorgesehene Prüfungen

Die Wiederholbarkeit der Datenerzeugung, vollständige Messprotokolle und korrekte Ergebnisvergleiche prüfen. Aufbaukosten und Abfragekosten getrennt erfassen; bei Gesamtkosten nur die zum jeweiligen Vergleich gehörenden Schritte berücksichtigen.

## Ordner und Theorie

- `src/`: Datenerzeugung, Messabläufe und Auswertung.
- `tests/`: Prüfungen der Reproduzierbarkeit und Messdatenverarbeitung.
- `experimente/`: Versuchsdefinitionen, Parameter und Abfragesätze.

Abhängigkeiten: Verfahren und Referenzsuchen aus Bereichen 01 bis 04. Gleiche Daten, Aufbereitungsregeln und Messbedingungen für vergleichbare Verfahren verwenden.

## Übergabe aus Thema 02

`ergebnisse/messungen/02_invertierter_index/` enthält Zeitrohwerte im gemeinsamen `gemeinsam.messung.CSV_FIELDS`-Schema: Aufbau auf vorbereiteten Dokumenten und öffentliche materialisierte Wortabfrage inklusive zentraler Anfrageaufbereitung. `metadata.json` enthält N/D/V/P, Dokumentlängen, Token-/Dokumenthäufigkeiten, besuchte Tokens der direkten Referenz, Daten-/Code-SHA und gemessene Quelltext-Snapshots. Die N-Reihe variiert N mit D/P bei fester Dokumentlänge, die V-Reihe V mit P bei gleicher N/D. Der gemeinsame reale Korpus ist `daten/real/kafka_verwandlung` mit dem vorhandenen Manifest.

Zusätzlicher Speicher liegt separat in `memory.csv`/`memory.json`: `retained_traced_bytes`, `peak_traced_bytes` und `exclusive_index_bytes`. Keine Profilingzeiten sind als Such-/Aufbauzeiten verwendet; keine dieser Größen bezeichnet Prozess-RSS. Pilotdaten stehen unter `02_pilot`, Diagramme unter `ergebnisse/abbildungen/02_*`. Befehle und Schemaerklärung: [Experimente 02](../02_invertierter_index_einzelwortsuche/experimente/README.md). Amortisationsmodell und Vergleich mit booleschen/ Positionsverfahren werden erst in Thema 05 zusammengeführt.

## Übergabe aus Thema 03

`boolesche_suche.search_direct_boolean` und `search_index_boolean` bieten reine AND-/OR-Abfragen mit vollständig materialisierten, sortierten Ergebnissen. AND hat `input_order` und `shortest_first` (stabile Längengleichstände), OR nur `input_order`. Begriffe werden normalisiert und stabil dedupliziert; original-/ effektive Anzahl stehen in `BooleanQuery` und den Abfragemanifesten.

`ergebnisse/messungen/03_boolesche_mehrwortsuche` enthält Rohwerte im unveränderten Zeit-CSV-Schema, inklusive öffentlicher Planung und Materialisierung. Getrennte Phasen erfassen Laden, Aufbereitung und Aufbau. Metadaten enthalten k, Listen-/ Zwischengrößen, Treffer, separate Vergleichs-/Zeiger-/Token-Diagnosen und Quellenstände mit SHA. Paare: gleiche Korpora/Begriffe bei beiden AND-Varianten; zusätzlich k=2/3/5, Frequenzfamilien, Umkehrungen, OR und vorhandener Realtext.

Der synthetische Korpus hat D=1000/N=100000. Der reale Kafka-Auszug bleibt ein Dokument; seine Resultate erlauben keine allgemeine Verteilungsanalyse. Keine Speicher-/Amortisationswerte sind für Thema 03 behauptet. Reproduktionsbefehle: [Experimente 03](../03_boolesche_mehrwortsuche/experimente/README.md), Befunde: Thema 05 führt die umfassende Auswertung und den Gesamtvergleich erst mit geprüfter Phrasensuche zusammen.

## Übergabe aus Thema 04

`positionsindex.build_positional_index` übernimmt `Iterable[PreparedDocument]`; beide Phrasensuchen verwenden die gemeinsam normalisierte Tokenfolge aus `normalize_query(raw, "phrase")`. Ergebnis ist `dict[str, list[int]]` mit geordneten Kennungen und allen Startpositionen. Der Index ist auf beiden Mappingebenen unveränderlich; Ergebnisse können unabhängig verändert werden. Direkte und indexbasierte Suche erhalten identische Phrasen, auch mit Wiederholungen, Satzzeichen und Stopwörtern. Beispiel/Nutzung: [README 04](../04_positionsindex_phrasensuche/README.md).

Rohzeit-CSV unter `ergebnisse/messungen/04_positionsindex_phrasensuche/` nutzt das unveränderte gemeinsame Schema. Buildzeiten gehören jeweils zur gesamten öffentlichen Aufbauoperation, Abfragen enthalten Rohtextnormalisierung, Kernprüfung und neue vollständige Ergebnisse. `hit_count` bleibt Dokumentzahl; Metadaten ergänzen `position_count`, vollständige erwartete Starts, m, CF/DF, Kandidaten-/Listenlängen und Code-/Datensatzprüfsummen. Separate Speicherdateien enthalten gehaltene und maximale zusätzliche Python-Allokationen sowie deren Differenz, jeweils drei Builds in getrennten Prozessen je Korpus/Indexart.

Kontrollierte Reihen verwenden D200/N100000/V66, m1/2/3/5 und häufige/seltene, wiederholte, fehlende und falsch geordnete Phrasen. Eine eigene H0/20/200-Reihe erhält sämtliche Einzelworthäufigkeiten durch Permutation. Die geänderte Tokenreihenfolge beeinflusst zusätzlich zur Ergebnisbildung die Mergearbeit. Der bestehende Kafka-Auszug bleibt byteidentisch (D1/N1271). Laden und Aufbereitung sind für 04 außerhalb der gemessenen Phasen; diese Kosten müssen im Gesamtvergleich von 05 tatsächlich erfasst bzw. konsistent ausgewiesen werden. Ein Dokumentindex liefert keine Phrasenstarts und ist deshalb nur Aufbau-/Speichervergleich, keine semantisch gleiche Phrasenbaseline.

Nachweise: [Experimente 04](../04_positionsindex_phrasensuche/experimente/README.md). Gemeinsame Auswertung, Abfragefolgen und Amortisationsprüfung bleiben Thema 05.

## Nutzung und erneute Prüfung

```sh
.venv/bin/python -m experimentelle_analyse search --corpus daten/beispiele/d0_d5 --kind phrase --method index --query "a a"
.venv/bin/python -m experimentelle_analyse verify --input ergebnisse/messungen/05_experimentelle_analyse --archive-only
.venv/bin/python -m experimentelle_analyse analyse --input ergebnisse/messungen/05_experimentelle_analyse --output ergebnisse/abbildungen/05
.venv/bin/python themen/05_experimentelle_analyse/experimente/render.py
.venv/bin/python -m pytest -q
```

Die erste Abfrage zeigt sämtliche Starts 0 und 1 in D5.txt. `search` unterstützt word/and/or/phrase und direct/index; shortest_first nur AND/index. Rohworte und alle vollständig materialisierten Treffer gehören zur Suchzeit, Bedienung und Ausgabe nicht. Neue Messläufe benötigen leere Zielverzeichnisse und neue zusammenpassende Pilot-/Hauptkonfigurationen; vorhandene Rohwerte werden nicht überschrieben.

Die gelieferten Läufe `05_pilot` und `05_experimentelle_analyse` bestehen den strengen Verifier seit den Quelländerungen vom 14.10.2026 (Thema 03, `provenance.py`, CLI, BGB-Erweiterung) erwartungsgemäß nicht mehr. Sie werden mit `experimente/verify_results.py --archive-only` geprüft: Nur der Vergleich mit dem aktiven Code entfällt, das Quellarchiv und alle übrigen Prüfungen bleiben. Der neue Realteil der Reihe 05 misst das BGB (ein Paragraph je Dokument) mit sechs festen Profilanfragen und gibt die Größen aus Abschnitt 3.6 aus (`bgb_pilot.json`, `bgb_main.json`, `render_bgb.py`, Einzelheiten im [Versuchs-README](experimente/README.md)).

