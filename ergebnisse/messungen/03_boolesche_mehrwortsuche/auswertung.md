# Beobachtete Ergebnisse der Untersuchung 03

Die Tabelle zeigt Mediane und Interquartilsabstände (IQR) in Mikrosekunden pro vollständiger Anfrage. Das Verhältnis input/shortest > 1 beschreibt einen beobachteten Medianvorteil der Sortierung. Es ist kein Signifikanztest. Verglichen werden derselbe Korpus und dieselben Begriffe.

| Anfragegruppe, k=5 vorwärts | Postinglängen | Treffer | direkte Suche µs (IQR) | input_order µs (IQR) | shortest_first µs (IQR) | input/shortest | Diagnose Vergleiche input/shortest |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| rare | [20, 20, 20, 20, 20] | 12 | 3850.99 (1156.11) | 38.74 (19.42) | 40.11 (8.70) | 0.966 | 76/76 |
| frequent | [900, 900, 900, 900, 900] | 500 | 4356.75 (176.84) | 834.90 (385.40) | 834.73 (23.56) | 1.000 | 5400/5400 |
| mixed | [950, 750, 500, 100, 10] | 10 | 4224.66 (322.74) | 299.37 (12.30) | 36.09 (5.06) | 8.296 | 1360/40 |
| unknown | [900, 0, 900, 900, 900] | 0 | 4281.96 (1660.00) | 33.89 (5.37) | 28.91 (3.01) | 1.173 | 0/0 |
| disjoint | [100, 100, 100, 100, 100] | 0 | 3645.40 (57.96) | 42.07 (4.50) | 43.38 (19.73) | 0.970 | 200/200 |
| high_overlap | [600, 600, 600, 600, 600] | 600 | 3983.07 (445.07) | 493.02 (41.19) | 505.63 (29.48) | 0.975 | 2400/2400 |
| low_overlap | [500, 500, 500, 500, 500] | 0 | 4512.08 (81.80) | 169.58 (7.80) | 168.71 (9.26) | 1.005 | 1510/1510 |

Alle k=2/3/5, umgekehrten Anfragen, OR-Vergleiche, Duplikatfälle und realen Anfragen stehen in `comparisons.json`; Streuungen und Einzelwerte in `summary.json` und `raw.csv`. Die vollständigen IDs, Längen, Zwischenresultate und Diagnosezähler stehen in `metadata.json`.

Die Häufigkeitsgruppen ändern bei gleichem N=100000 die Postingverteilung. Die Reihenfolge wird durch Vorwärts-/Rückwärtspermutation exakt derselben Begriffe isoliert. k wird durch vorab definierte Präfixe auf demselben Korpus variiert; dabei kann auch die Schnittmenge schrumpfen. Daher folgt daraus kein von Häufigkeiten und Überschneidung unabhängiger universeller k-Effekt.

Der unveränderte Kafka-Auszug umfasst ein Dokument und 1271 Tokens. Er bestätigt Aufbereitung und Semantik an echter Prosa, trägt aber keine belastbare Skalierungs- oder Verteilungsanalyse. Die synthetische Textlänge ist konstant; Positionen und Füllwörter bleiben bei sämtlichen Anfragen gleich. Betriebssystem-Caches, Python-Allokation und gewöhnliche Hintergrundlast sind Grenzen. Laufzeiten enthalten die vollständige Materialisierung. Speicher und Amortisation des Gesamtprojekts werden hier nicht untersucht.

Gemessener Git-Ausgangspunkt: `9e40cec2880c4bde9501c90e4511256df96443e2`; uncommittierte Änderungen vorhanden: `True`. Exakte Quellenstände mit SHA-256 sind unter `code_source/` archiviert.
