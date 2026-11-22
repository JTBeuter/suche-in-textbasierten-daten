# Datensätze und Anfragen für Thema 05

`experimentelle_analyse.datasets` erzeugt mit `05-planted-v1` den zusätzlichen
kleinen Amortisationskorpus aus den gespeicherten Versuchsdefinitionen unter
`themen/05_experimentelle_analyse/experimente/`. Die Definition legt D=20,
500 Tokens je Dokument, N=10000 und einen tatsächlich erreichten Wortschatz
V=64 fest. Der Pflanzplan aus Thema 04 wird auf 48 gleichverteilte Füllwörter
und 16 reservierte Marker angepasst. Alle Füllwörter werden auf freien Positionen
garantiert; ein lokaler `random.Random(20261006)` erzeugt die restliche Füllung.

Vor dem Schreiben steht jede erwartete Tokenfolge aus dem Pflanzplan fest.
Danach werden sämtliche vorbereiteten Dokumente mit diesen Erwartungen
verglichen. Großschreibung und Satzpunkte in den Rohdateien prüfen zusätzlich
die gemeinsame Normalisierung und Tokenabgrenzung. Je Ausgabeverzeichnis stehen
die `.txt`-Dateien unter `<id>/corpus/`; `<id>/manifest.json` und
`<id>/queries.json` liegen außerhalb dieses Ladefilters. Das Manifest enthält
Generatorfassung und alle Parameter, tatsächliche Dokument-/Token-/Wortschatz-
und Bytegrößen, sortierte Dateiliste, SHA-256 je Datei, unabhängige erwartete
Tokens und den Hash des gesamten Abfragesatzes. Zwei getrennte Erzeugungen
werden in Tests anhand sämtlicher Dateibytes, Prüfsummen und Query-Manifeste
verglichen; ein gleicher Seed allein dient nicht als Nachweis.

Die gespeicherten Anfragen (`05-queries-v1`) haben deterministische IDs,
Typ, normalisierte Begriffe, Länge, CF/DF, vollständige erwartete Ergebnisse
und Dokumentzahl; Phrasen enthalten zusätzlich die Zahl aller Startpositionen.
Wortanfragen sind häufig, selten oder fehlend. AND/OR verwenden 2, 3 und 5
Begriffe in häufigen, seltenen, gemischten und teilweise fehlenden Gruppen.
Eine OR-Anfrage mit einem fehlenden Begriff kann durch ihre übrigen Begriffe
weiterhin Treffer liefern. Phrasenlängen 1, 2, 3 und 5 decken vorhandene,
fehlende und überlappende Wiederholungen ab. Umgekehrte häufige Markerfolgen
fehlen im synthetischen Korpus. Erwartungen stammen ausschließlich aus
Tupelmitgliedschaft beziehungsweise direkten Tupelschnitten, ohne Hilfsindex
oder produktive Suchfunktion. Query-Auswahl verwendet keinen Zufallsgenerator
und keine Messwerte.

Der bestehende reale Kafka-Korpus wird unverändert verwendet. Quelle,
Abrufdatum, Rechtebelege und Bereinigung bleiben im ursprünglichen Manifest;
Thema 05 prüft erneut Archivhash, Auszugshash, eindeutige Auswahlmarker,
Absatzanzahl, feste Anfangstokens und sämtliche vorhandenen Wortpositionsbelege.
Eine unabhängige Unicode-Tokenisierung sichert die vollständige Tokenfolge.
Der reale Querysatz enthält unter anderem das häufige `er`, das seltene
`Fenster` und `Gregor Gregor` mit Starts 1060 und 1078. Das Quellenarchiv
`quelle.pg` wird nicht zu einem Suchdokument und wird weder neu heruntergeladen
noch bei der Datenerzeugung überschrieben. Für portable Laufartefakte wird der
geprüfte Snapshot byteidentisch in das Datenausgabeverzeichnis kopiert und
erneut geprüft. Der kleine Auszug ist kein
repräsentativer deutscher Textkorpus.

Bedienung, feste Parameter und Wiederholung:
[Experimente 05](../themen/05_experimentelle_analyse/experimente/README.md).
