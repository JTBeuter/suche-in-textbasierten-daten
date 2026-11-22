# Reproduzierbare Phrasenversuche

## BGB-Realteil (Neumessung, Stand 14. Oktober 2026)

`run_bgb.py` misst **nur** diesen Realteil. Die synthetischen Korpora der Reihe 04 werden nicht neu gemessen; die gelieferten Ordner `04_pilot` und `04_positionsindex_phrasensuche` (mit dem früheren Kafka-Realteil) bleiben unverändert und werden weiter mit `verify_results.py --archive-only` geprüft.

```sh
PYTHONHASHSEED=0 .venv/bin/python themen/04_positionsindex_phrasensuche/experimente/run_bgb.py --pilot
PYTHONHASHSEED=0 .venv/bin/python themen/04_positionsindex_phrasensuche/experimente/verify_bgb.py --eingabe 04_bgb_pilot
PYTHONHASHSEED=0 .venv/bin/python themen/04_positionsindex_phrasensuche/experimente/run_bgb.py --hintergrundlast "TEXT"
PYTHONHASHSEED=0 .venv/bin/python themen/04_positionsindex_phrasensuche/experimente/verify_bgb.py
```

Optionen wie in Reihe 01: `--ausgabe NAME` (neuer Ordner unter `ergebnisse/messungen`, Standard `04_bgb_pilot` bzw. `04_bgb`), `--pilot-ordner NAME` (Pilot für den Hauptlauf, Standard `04_bgb_pilot`), `--hintergrundlast TEXT` (tatsächliche Last für die Metadaten). Vorhandene nicht-leere Ordner werden nie überschrieben. Ein Befehl führt Zeitlauf, anschließend den Speicherlauf in zwei getrennten Prozessen (`memory.py`, je Indexart drei Aufbauten) und zuletzt die vollständige Prüfung aus. Der Pilot (1 Aufwärmlauf, 3 Wiederholungen) schreibt danach `pilot_decision.json` und sperrt Parameter, Hashes aller gemessenen Quellen (einschließlich `boolesche_suche`, das die Positionssuche importiert), den Datenstand und `PYTHONHASHSEED`. Der Hauptlauf (5 Aufwärmläufe, 20 Wiederholungen, Suchblock fünf Anfragen) startet nur, wenn all das gleich ist und der Pilot erneut vollständig geprüft besteht. Jede Codeänderung an diesen Quellen verlangt einen neuen Pilot in einem neuen Ordner (`--ausgabe`), mit passendem `--pilot-ordner` für den Hauptlauf.

Vor jeder Messung prüft `run_bgb.py` den Korpus gegen `daten/real/bgb/manifest.json`: alle Dateien mit Bytes und SHA-256, keine zusätzlichen Dateien, kanonischer Korpushash, D/N/V/P und Tokenanfang von § 1. Die zweite, unabhängige Regex-Tokenisierung (`run.independent_tokens`) muss für jedes Dokument mit der produktiven Aufbereitung übereinstimmen. Für jede Phrase müssen gesperrter Erwartungswert, `anfragevorschlaege.json` (Reihe 04), das Manifest (für die sechs dort enthaltenen Phrasen) und ein Tupelschnitt-Orakel auf den Regex-Tokens in Dokumentliste, allen Startpositionen, Dokument- und Startzahl, Positionshash und df der Wörter übereinstimmen. Danach müssen beide Suchverfahren genau diese Ergebnisse liefern; jede gemessene Antwort wird außerhalb des Timers erneut geprüft. Gesperrt ist nur der verwendete Teil der Daten (Dokumentliste, Korpushash, unabhängige Erwartungen, Vorschläge der Reihe 04); ein erneuter Produktivabgleich, der nur `production_comparison` im Manifest neu schreibt, bricht die Sperre nicht.

| Anfrage-ID | Phrase | Länge | Dokumente | Starts |
| --- | --- | ---: | ---: | ---: |
| `bgb_frequent_k2` | nach Maßgabe | 2 | 57 | 64 |
| `bgb_frequent_k3` | im Sinne des | 3 | 62 | 85 |
| `bgb_frequent_k4` | es sei denn, dass | 4 | 82 | 85 |
| `bgb_frequent_k5` | nach den Vorschriften über die | 5 | 35 | 35 |
| `bgb_rare_k2` | Bürgerlichen Gesetzbuchs | 2 | 1 | 1 |
| `bgb_rare_k3` | Beginn der Rechtsfähigkeit | 3 | 1 | 1 |
| `bgb_rare_k4` | nach Treu und Glauben | 4 | 1 | 1 |
| `bgb_rare_k5` | mit Rücksicht auf die Verkehrssitte | 5 | 2 | 2 |
| `bgb_common_words_k2` | der die (df 2.280 und 2.177) | 2 | 32 | 34 |
| `bgb_wrong_order_k2` | Maßgabe nach | 2 | 0 | 0 |
| `bgb_wrong_order_k3` | des Sinne im | 3 | 0 | 0 |
| `bgb_missing_k3` | Verbindung zum Server (df(server) = 0) | 3 | 0 | 0 |

Gemessen werden wie bisher Aufbau von Dokumentindex und Positionsindex (Zeit; gehaltener Speicher und Peak im separaten Speicherlauf) sowie direkte Phrasensuche gegen Positionsindex; Zeitgrenzen, CSV-Felder und Statistik sind dieselben wie unten beschrieben. `hit_count` zählt Dokumente, `position_count` im JSON die Starts. Grenzen: Die realen Phrasen unterscheiden sich nicht nur in der Länge, sondern auch in Wörtern, CF/DF, Kandidaten und Ergebnisgröße; die Länge ist kein isolierter Faktor. Ein fester Abrufstand mit juristischem Wortschatz und sehr ungleichen Dokumentlängen.

`verify_bgb.py` (Standard `--eingabe 04_bgb`) rechnet Korpus, Erwartungen und beide Indizes mit dem aktiven Code neu, prüft Rohwerte, Statistik, Randomisierung, Quellarchiv, Speicherprozesse und die Pilotsperre; `--archive-only` lässt geänderte aktive Quellen zu, `--timing-only` prüft ohne Speicherwerte. Tests: `tests/test_bgb_experiments.py` (Kleinkorpus mit handgezählten Erwartungen für Pilot, Hauptlauf, Sperren und Manipulationen; ein Test liest den echten BGB-Korpus).

Ausgeführt am 14. Oktober 2026 auf ruhiger Maschine mit `PYTHONHASHSEED=0`: Pilot `ergebnisse/messungen/04_bgb_pilot` und Hauptlauf `ergebnisse/messungen/04_bgb` (17:57 bis 18:00 Uhr), beide mit `verify_bgb.py` streng geprüft. Die Hintergrundlast steht in `background_load` der Metadaten.

## Gelieferte Reihe (synthetisch und Kafka, 6. Oktober 2026)

Die gelieferten historischen Messarchive erneut prüfen, aus dem Repository-Verzeichnis nach der Installation gemäß Haupt-README:

```sh
.venv/bin/python themen/04_positionsindex_phrasensuche/experimente/verify_results.py --pilot --archive-only
.venv/bin/python themen/04_positionsindex_phrasensuche/experimente/verify_results.py --archive-only
.venv/bin/python -m pytest -q themen/04_positionsindex_phrasensuche/tests themen/04_positionsindex_phrasensuche/experimente/tests
```

`--archive-only` ist hier erforderlich, weil die aktive `pyproject.toml` nach Thema 04 um Thema 05 erweitert wurde und damit einen anderen SHA-256-Wert besitzt. Das gemessene `code_source/`-Archiv bleibt unverändert. Der Verifier prüft dessen gespeicherte Quelltext-Hashes, Daten, Rohwerte und Statistiken weiterhin vollständig und wiederholt die semantische Prüfung mit dem aktuellen Code. Historische Laufzeiten belegen die archivierte Fassung; `pytest` prüft zusätzlich die aktuelle Implementierung und ihre Integration.

Für neue Zeit- und Speicherläufe dieser Reihe gelten die folgenden Befehle. Der Runner verwendet feste Ausgabeziele und verweigert seit dem 14. Oktober 2026 Zeitläufe in nicht-leere Ordner; deshalb nur in einer getrennten Arbeitskopie mit leeren Versuchsverzeichnissen ausführen, damit die gelieferten Archive erhalten bleiben. Pilot und Hauptlauf müssen denselben aktuellen Quellstand verwenden; ihre Verifier laufen ohne `--archive-only`:

```sh
.venv/bin/python themen/04_positionsindex_phrasensuche/experimente/run.py --pilot
.venv/bin/python themen/04_positionsindex_phrasensuche/experimente/run.py --pilot --memory
.venv/bin/python themen/04_positionsindex_phrasensuche/experimente/verify_results.py --pilot
.venv/bin/python themen/04_positionsindex_phrasensuche/experimente/run.py
.venv/bin/python themen/04_positionsindex_phrasensuche/experimente/run.py --memory
.venv/bin/python themen/04_positionsindex_phrasensuche/experimente/verify_results.py
.venv/bin/python -m pytest -q themen/04_positionsindex_phrasensuche/experimente/tests
```

Auch `python -m themen.04_positionsindex_phrasensuche.experimente.run --help` funktioniert. Zeitläufe und Speicherläufe sind separate Befehle. Während der Zeitläufe laufen keine weiteren Projektmessungen, Tests oder PDF-Builds. Der Pilot hat einen Aufwärmlauf und drei Wiederholungen; der finale Lauf fünf Aufwärmläufe und zwanzig Wiederholungen. Ein Suchblock umfasst fünf vollständige gleiche Anfragen. Der finale Lauf verlangt einen erfolgreichen Pilot, dessen Parameter und relevante Quelltext-Hashes unverändert sind, einschließlich geprüftem separatem Speicherlauf.

`generator.py` erzeugt drei Korpora mit je 200 Dokumenten zu 500 Tokens, insgesamt 100000 Tokens und 66 verschiedenen vierstelligen ASCII-Tokens. Seed ist20261006. Fünf häufige Tokens stehen alle50 Positionen als Phrase zusammen; ein wiederholtes Token bildet ab20 einen Lauf der Länge6; fünf seltene Tokens stehen nur in den ersten beiden Dokumenten ab30. Phrasenlängen1,2,3 und5 werden auf dem Korpus mit200 Ergebnissen gemessen, einschließlich unbekannter Tokens, falscher Reihenfolge und Wiederholungen. Die handfesten Pflanzpläne geben vollständige erwartete Tokenfolgen und Startpositionen vor. Diese werden zusätzlich durch unabhängige Tupelschnitte überprüft.

Die Ergebnisgrößenreihe pflanzt `z000 z001 z002 z003 z004` ab40 in0,20 oder200 Dokumente. In den anderen Dokumenten stehen dieselben Tokens dort in umgekehrter Reihenfolge. Dokumentzahl, Tokenzahl, Wortlänge, Wortschatz, Häufigkeit jedes einzelnen Tokens je Dokument, globale Häufigkeit und Kandidatenmenge bleiben identisch. Die veränderte Reihenfolge beeinflusst zusätzlich den Fortschritt des Positionszusammenführens; die Reihe isoliert deshalb die Ausgabekosten nicht vollständig. In der Längenreihe ändern Wiederholungsphrasen außerdem die Zahl der Startpositionen. Beide Grenzen stehen auch in den Metadaten.

Der reale Versuch benutzt unverändert den vorhandenen Kafka-Anfang unter `daten/real/kafka_verwandlung/`: ein Dokument, acht Absätze,1271 Tokens. Quelle, Auswahl und Prüfsummen werden anhand des bestehenden Manifests geprüft. Eine unabhängige Regex-Tokenisierung mit Unicode-Kategorieprüfungen, der bekannte Anfang und die bereits handgeprüften Vorkommenspositionen sichern den Aufbereitungsvergleich. Abfragen sind Anfangspräfixe, das häufige `er`, Wiederholungen von `Gregor`, das unbekannte `x999` und umgekehrte Anfangspräfixe. Ein einzelnes kurzes Dokument erlaubt keine allgemeine Aussage über große reale Korpora.

Der Zeitvergleich schließt für beide Phrasenverfahren `normalize_query(raw, "phrase")`, die Kernsuche und sämtliche zurückgegebenen Startpositionen in frischen Ergebniscontainern ein. Ergebnisprüfungen, Laden, Aufbereitung, Ausgabe und Speicherprofiling liegen außerhalb der Suchintervalle. Alle Verfahren/Anfragen werden je Wiederholung deterministisch gemischt; die Ergebnisse eines Blocks werden vor dem nächsten Timer freigegeben. Invertierter Index und Positionsindex werden aus identischen vorbereiteten Dokumenten separat aufgebaut. Einwortphrasen liefern alle Vorkommenspositionen; die Einzelwortsuche des invertierten Index liefert nur Dokumente und wird deshalb nicht als semantisch gleiche Positionsabfrage verglichen.

Der separate Speicherlauf startet für jede Kombination aus Datensatz und Indexart einen eigenen Prozess und führt darin drei frische Builds aus. Vorbereiteter Korpus und unabhängige Erwartungscontainer existieren vor dem Tracerstart; ihre Allokationen sind ausgeschlossen. Der jeweils andere Produktionsindex wird nicht erzeugt. `retained_traced_bytes` ist die Differenz der gehaltenen Allokationen nach und vor dem Aufbau; `peak_traced_bytes` die Spitze seit `reset_peak()` relativ zu derselben Basis; `transient_peak_bytes` ihre Differenz. Der Tracer wird vor Ergebnisprüfung und Ausgabe gestoppt. Gemessen werden zusätzliche von Python verfolgte Allokationen, weder RSS noch serialisierte Indexgröße.

Artefakte stehen unter `ergebnisse/messungen/04_pilot/` beziehungsweise `04_positionsindex_phrasensuche/`: gemeinsames `raw.csv`, `summary.json`, `metadata.json`, `memory.csv`, `memory.json` sowie vollständiges `code_source/`-Archiv. CSV-`hit_count` zählt Dokumente. Phrase, Länge, Gruppen, globale Häufigkeiten, Dokumenthäufigkeiten, Kandidaten, Positionslistenlängen, volle erwartete Ergebnisse und Gesamtzahl der Startpositionen stehen je Query im JSON. Die Speicherwerte haben ein separates Schema und gehen nicht als Suchzeiten in die gemeinsame CSV ein.

`verify_results.py` rekonstruiert den Pflanzplan und reale Quelle, prüft volle Tokenfolgen und Phrasenergebnisse, kontrolliert unveränderte Einzelworthäufigkeiten in der Ergebnisgrößenreihe und berechnet alle Statistiken aus Integer-Blockzeiten neu. Es prüft außerdem Stichprobenzahlen, Randomisierung, CSV-Einheiten, Quellarchive und die getrennten Prozessintervalle des Profilings. `--timing-only` erlaubt die Prüfung vor dem Speicherlauf. `--archive-only` erlaubt veränderte aktive Quellen, prüft weiterhin die Hashes ihrer archivierten Fassungen und berechnet die Semantik mit dem aktiven Code neu; der Standard prüft zusätzlich alle aktiven Quelltext-Hashes einschließlich `pyproject.toml`.

Die Parameter sind im Code gesperrt; nach Änderungen muss der Pilot neu laufen. Die Rohwerte bilden die Übergabe an Thema 05. Dieses Skript bewertet keine Amortisation des Gesamtprojekts und ersetzt keine dortige Abfragefolge.

## Tatsächlich ausgeführter Stand

Am 6. Oktober 2026 wurden die sechs Befehle für Pilot-/Hauptzeitmessung, separate Speicherläufe und Standardverifier mit dem damaligen Quellstand erfolgreich ausgeführt, mit vorangestelltem `PYTHONHASHSEED=0`. Der Pilotverifier prüft 270 Rohwerte, 90 Gruppen, 601 Dateien und 24 Speicherwerte; der Hauptverifier 1800 Rohwerte bei demselben übrigen Umfang. Der CPU-/Softwarestand und die vollständigen Code-/Datenhashes stehen in den Metadaten.

Abbildungen erneut aus den geprüften Zusammenfassungen erzeugen:

```sh
.venv/bin/python themen/04_positionsindex_phrasensuche/experimente/plots/render.py
```

Der Renderer ist eine separate Auswertung und gehört nicht zum gemessenen Zeitcode; `plot_manifest.json` sichert Renderer- und Eingabe-/Bildhashes. Beobachtete Werte und Grenzen: Tatsächliche Nachweise:
