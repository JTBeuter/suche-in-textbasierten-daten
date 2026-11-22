# Beobachtete Ergebnisse der Reihe 03 auf dem BGB (Realteil)

Mediane und Interquartilsabstände (IQR) in Mikrosekunden pro vollständiger Anfrage aus 20 Blöcken mit je 5 Anfragen. Gemessen werden die öffentlichen Funktionen inklusive Normalisierung, Postingzugriff, Sortierung und vollständiger Ergebnisliste. Verhältnisse über 1 beschreiben einen beobachteten Medianvorteil des jeweils zweiten Verfahrens. Es ist kein Signifikanztest. Vergleiche sind relationale Kennungsvergleiche aus getrennten Diagnoseläufen außerhalb der Timer, bei AND NOT einschließlich der Differenz.

## AND und AND NOT

| Anfrage | Listenlängen | Treffer | direkt µs (IQR) | input_order µs (IQR) | shortest_first µs (IQR) | galloping µs (IQR) | input/shortest | shortest/galloping | Vergleiche input/shortest/galloping |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Verbindung AND der | 16/2.280 | 15 | 11.491,62 (945,68) | 376,84 (15,09) | 379,83 (6,40) | 44,79 (4,61) | 0,992 | 8,480 | 4.227/4.227/198 |
| der AND Verbindung | 2.280/16 | 15 | 11.415,40 (429,63) | 399,01 (11,04) | 377,06 (6,03) | 44,77 (4,62) | 1,058 | 8,422 | 4.227/4.227/198 |
| Erbschaftskauf AND der | 1/2.280 | 1 | 11.708,49 (176,22) | 406,50 (10,75) | 406,45 (11,42) | 23,50 (4,40) | 1,000 | 17,293 | 4.559/4.559/22 |
| Mieter AND Vermieter | 79/82 | 66 | 9.475,59 (341,54) | 33,41 (3,88) | 33,99 (4,43) | 36,47 (4,39) | 0,983 | 0,932 | 122/122/173 |
| Vertrag AND Schadensersatz | 188/77 | 14 | 8.881,94 (452,41) | 61,59 (6,67) | 61,61 (5,63) | 53,91 (6,47) | 1,000 | 1,143 | 464/464/293 |
| Gläubiger AND Schuldner AND Frist | 215/145/165 | 5 | 10.527,71 (150,32) | 105,39 (5,57) | 89,98 (6,92) | 72,27 (6,60) | 1,171 | 1,245 | 865/785/441 |
| Vertrag AND Schadensersatz AND Frist AND Gläubiger AND Schuldner | 188/77/165/215/145 | 0 | 8.961,49 (323,63) | 116,01 (6,58) | 113,08 (6,28) | 82,39 (7,00) | 1,026 | 1,373 | 877/880/347 |
| Verbindung AND der AND die AND des AND und | 16/2.280/2.177/1.844/1.243 | 12 | 14.211,67 (522,57) | 1.216,38 (18,96) | 1.232,25 (32,21) | 126,38 (7,37) | 0,987 | 9,751 | 13.995/14.000/725 |
| und AND des AND die AND der AND Verbindung | 1.243/1.844/2.177/2.280/16 | 12 | 14.284,30 (444,21) | 1.489,58 (42,43) | 1.223,07 (23,03) | 125,76 (6,39) | 1,218 | 9,726 | 12.001/14.000/725 |
| der AND die AND des AND und AND oder | 2.280/2.177/1.844/1.243/1.391 | 674 | 11.500,28 (652,10) | 1.714,44 (52,27) | 1.654,20 (38,56) | 1.279,52 (25,48) | 1,036 | 1,293 | 11.274/13.615/11.366 |
| Mieter AND Erblasser | 79/139 | 0 | 9.435,54 (298,85) | 31,33 (2,72) | 32,05 (4,81) | 33,68 (3,13) | 0,977 | 0,952 | 166/166/163 |
| Vertrag AND Schadensersatz AND NOT Verbraucher | 188/77, NOT 106 | 9 | 12.466,77 (1.103,43) | 90,23 (7,44) | 86,11 (5,12) | 79,82 (5,63) | 1,048 | 1,079 | 673/673/502 |

## OR

| Anfrage | Listenlängen | Treffer | direkt µs (IQR) | input_order µs (IQR) | direkt/Index | Vergleiche |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Vertrag OR Schadensersatz | 188/77 | 251 | 7.677,67 (210,03) | 70,46 (3,35) | 108,960 | 464 |
| Gläubiger OR Schuldner OR Frist | 215/145/165 | 420 | 9.145,69 (1.154,11) | 165,61 (7,85) | 55,224 | 1.267 |
| der OR die OR des OR und OR oder | 2.280/2.177/1.844/1.243/1.391 | 2.463 | 1.936,68 (102,76) | 2.075,31 (41,46) | 0,933 | 13.118 |

Korpus: BGB, 2.486 Paragraphen als Dokumente, N = 213.718 Tokens, Wortschatz 11.398. Erwartungen stammen aus `daten/real/bgb/anfragevorschlaege.json` und einer eigenen Regex-Tokenisierung und wurden vor dem ersten Timer mit der direkten Referenz geprüft. Zweck jeder Anfrage, Einzelzähler und Trefferlisten stehen in `comparisons.json` und `metadata.json`. Betriebssystem-Caches, Python-Allokation und gewöhnliche Hintergrundlast sind Grenzen.

Quelle: `ergebnisse/messungen/03_bgb/raw.csv`. Gemessener Git-Ausgangspunkt: `7bc4f9a3a110afa9f259131add5849719eba8b50`, uncommittierte Änderungen vorhanden: `True`, PYTHONHASHSEED: `0`, Hintergrundlast: Keine parallelen Messungen, Agenten oder Builds; Videopipeline pausiert; Lastmittel vor Start 1.20 2.25 4.22. Exakte Quellenstände mit SHA-256 sind unter `code_source/` archiviert.
