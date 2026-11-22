# Reproduzierbare Untersuchung 03

Die Messung vergleicht die öffentliche direkte boolesche Suche, AND in Eingabereihenfolge, AND nach aufsteigender Postinglänge und OR in Eingabereihenfolge. Alle Verfahren erhalten identische vorbereitete Dokumente und Anfragen und liefern vollständig materialisierte, sortierte Trefferlisten. Normalisieren, Sammeln der Postings und gegebenenfalls stabiles Sortieren sind Teil der Abfragezeit. Korrektheit, Diagnosezähler und Ausgabe liegen außerhalb.

Aus dem Repository-Verzeichnis, nach Installation wie im Haupt-README:

```sh
.venv/bin/python -m pytest themen/03_boolesche_mehrwortsuche/experimente/tests -q
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/run.py --pilot
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/verify_results.py --pilot
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/run.py
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/verify_results.py
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/analyse.py
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/plots/render.py
```

Es werden keine lokalen Importpfade oder Umgebungsvariablen benötigt. Importe starten keine Versuche. Die Untersuchung verwendet ausschließlich die Standardbibliothek und die installierten Projektpakete; pytest ist ein Entwicklungswerkzeug. Gewöhnliche Betriebssystemlast wird dokumentiert.

Der Pilot verwendet ein Warmup und drei Wiederholungen und bindet Parameter und SHA-256 des gesamten Messcodes. Die Finalmessung benötigt diesen erfolgreichen, unveränderten Pilot. Sie verwendet fünf Warmups, 20 Wiederholungen und fünf vollständige Aufrufe pro Abfrageblock. Die Reihenfolge sämtlicher gültiger Kombinationen aus Verfahren, Operator und Anfrage wird pro Wiederholung mit festem Seed gemischt. Ergebnisse des vorherigen Blocks werden vor Beginn des nächsten Timers freigegeben. Einlesen, Aufbereitung und Aufbau werden mit dem gemeinsamen `measure_phase` getrennt jeweils einmal pro Wiederholung gemessen.

Der Generator erzeugt temporär genau 1000 Dokumente mit je 100 Tokens. Alle Anfrage- und Fülltokens sind vier ASCII-Zeichen lang, damit unterschiedliche Wortlängen die synthetischen Häufigkeitsvergleiche nicht zusätzlich beeinflussen. Das gesamte Korpus einschließlich Tokenpositionen bleibt für sämtliche k und Permutationen gleich. Familiennamen stehen nur in den Metadaten:

| Familie | Fünf Begriffe | Dokumenthäufigkeiten bei D=1000 | Konstruktion |
| --- | --- | --- | --- |
| rare | q000–q004 | 20,20,20,20,20 | Bereiche mit Start 0,2,4,6,8; Schnittgröße 18/16/12 für k=2/3/5 |
| frequent | q005–q009 | 900,900,900,900,900 | jeder Begriff fehlt in einer anderen Restklasse modulo 10 |
| mixed | q010–q014 | 950,750,500,100,10 | ineinander liegende Präfixbereiche |
| unknown | q005,q999,q006,q007,q008 | 900,0,900,900,900 | q999 wird nie gepflanzt |
| disjoint | q015–q019 | 100,100,100,100,100 | fünf getrennte Bereiche |
| high_overlap | q020–q024 | 600,600,600,600,600 | identische Bereiche |
| low_overlap | q025–q029 | 500,500,500,500,500 | erster Schnitt 10, nach drittem Begriff leer |

Jede Familie erhält k=2,3,5 als Präfix und dessen umgekehrte Reihenfolge, jeweils für AND und OR. Zusätzlich prüft `Q010,q010,q014` ursprüngliches k=3 und effektives k=2. Häufigkeits- und Überschneidungsgruppen werden separat interpretiert: mit steigendem k können auch Treffer und Zwischenlisten schrumpfen. Ein allgemeiner, von der Verteilung unabhängiger k-Effekt wird nicht behauptet.

Der vorhandene, unveränderte [Kafka-Korpus](../../../daten/real/kafka_verwandlung/README.md) ergänzt 18 Anfragen mit 2/3/5 vorkommenden Begriffen, Umkehrung, unbekanntem Wort und Duplikat. Sein einziges Dokument und 1271 Tokens erlauben Semantikprüfung an Prosa; sie liefern keine repräsentative Skalierungsreihe. Quellarchiv, Auswahlmarker, Manifest, Dateibytes und erwartete Wortpositionen werden erneut geprüft. Ein unabhängiger Regexdurchlauf bestätigt die ganze Tokenfolge.

Vor dem ersten Timer werden vollständige Tokenfolgen gegen den unabhängig erzeugten Pflanzplan, Postinglisten gegen eine Mengenoracle und jede Suchvariante gegen erwartete Dokumentkennungen geprüft. Jede Blockausgabe wird anschließend erneut geprüft. `boolean_diagnostics.py` durchläuft eigene Kopien der Zusammenführung und erfasst relationale ID-Vergleiche (`==`, bei Ungleichheit zusätzlich `<`), Zeigerfortschritte und Zwischenlängen. Schleifenprüfungen und Sortiervergleiche sind dort nicht gezählt. Die direkten besuchten Tokens werden separat gezählt. Diese Funktionen werden niemals vom Produktionscode oder aus einem Timer aufgerufen; ihre Zähler sind keine Zeitmessungen.

Artefakte liegen in `ergebnisse/messungen/03_pilot/` und `ergebnisse/messungen/03_boolesche_mehrwortsuche/`: `raw.csv` im unveränderten gemeinsamen Schema, `summary.json` mit Median/Q1/Q3/IQR/Minimum/Maximum, `metadata.json` mit Original-/Effektivzahl, Posting-/Zwischenlängen, IDs, Diagnosen, Umgebung und Dateihashes sowie `code_source/` mit SHA-256-gebundenen Quellenständen. Nicht gemessene Speicherfelder bleiben leer. Eine Finalmessung enthält 5320 Rohwerte, 266 Statistikgruppen und 1001 überprüfte Dokumentdateien. `analyse.py` erzeugt daraus `comparisons.json`, `auswertung.md` und eine einfache zusätzliche SVG-Tabelle; sie führt keinen neuen Zeitlauf aus. Die bevorzugte wissenschaftliche Abbildung erzeugt der getrennte Matplotlib-Befehl `plots/render.py`: `ergebnisse/abbildungen/03_and_reihenfolge.png` und `03_and_reihenfolge_matplotlib.svg` mit Medianen und Q1/Q3-Fehlerbalken. Ihr `plot_manifest.json` bindet Eingabedateien, Rendererquelle, Matplotlib-Version, gezeigte Werte und Ausgabedateien an SHA-256. Die Rendererquelle wird unter `plot_source/` archiviert. Sie gehört zum getrennten Nachverarbeitungsschritt; die bereits gebundenen Zeitmessquellen und Rohwerte bleiben unverändert.

`verify_results.py` prüft Schema, Blockzeiten, alle Wiederholungen, Statistik, randomisierte Reihenfolge, Dateien, regenerierten Pflanzplan, Abfrageerwartungen, Diagnosen und eingefrorene Quellen. Standardmäßig muss auch der aktuelle Code identisch sein. `--archive-only` erlaubt späteren aktiven Codeänderungen, prüft weiterhin archivierte Quellen und Daten; die erneute Datenprüfung verwendet die aktuellen Generator-/Suchfunktionen und scheitert bei abweichendem Verhalten. Historische Ergebnisse werden nicht auf einen neuen Quellstand umetikettiert.

Stand 14.10.2026: Thema 03 wurde um Galloping Search (`variant="galloping"`) und `AND NOT` (`exclude`) erweitert, `boolean_diagnostics.py` um `galloping_diagnostic` und `diagnose_postings_galloping`. Die bestehenden Funktionen und das Verhalten der Varianten `input_order` und `shortest_first` sind unverändert. Weil sich der aktive Code dennoch geändert hat, besteht für die gelieferten Ordner `03_pilot` und `03_boolesche_mehrwortsuche` nur noch `verify_results.py --archive-only`. Die Galloping-Messreihe liegt getrennt in [galloping/](galloping/README.md) (Reihe 03b). Der neue Realteil auf dem BGB (ein Paragraph je Dokument) liegt in [bgb/](bgb/README.md) und schreibt nach `ergebnisse/messungen/03_bgb_pilot/` und `03_bgb/`; der Kafka-Realteil oben bleibt als gelieferte Messung unverändert. Beide neuen Reihen nutzen die Laufkonvention der neuen Reihe 01 (`--ausgabe`, `--pilot-ordner`, `--hintergrundlast`, `PYTHONHASHSEED=0`) aus `messlauf03.py`.

Vollständige Prüfung:
