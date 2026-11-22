# Beobachtete Ergebnisse der Reihe 03b (Galloping Search gegen Zwei-Zeiger)

Mediane und Interquartilsabstände (IQR) in Mikrosekunden pro vollständiger Anfrage aus 20 Blöcken mit je 5 Anfragen. Beide Verfahren laufen über `search_index_boolean` mit AND, kurzes Wort zuerst, und sortieren die Listen stabil nach Länge. Ein Verhältnis Zwei-Zeiger/Galloping über 1 beschreibt einen beobachteten Medianvorteil der Galloping Search, unter 1 einen Nachteil. Es ist kein Signifikanztest. Die Vergleichszahlen stammen aus getrennten Diagnoseläufen außerhalb der Timer.

## Fall „verteilt“: kurze Liste verteilt

| df lange Liste | Zwei-Zeiger µs (IQR) | Galloping µs (IQR) | Zwei-Zeiger/Galloping | Vergleiche Zwei-Zeiger | Vergleiche Galloping |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 14,12 (0,59) | 15,14 (0,84) | 0,933 | 10 | 20 |
| 20 | 15,87 (0,86) | 16,16 (0,70) | 0,982 | 30 | 30 |
| 50 | 20,55 (0,74) | 19,32 (0,54) | 1,064 | 90 | 60 |
| 100 | 27,93 (0,98) | 23,72 (0,68) | 1,177 | 190 | 97 |
| 200 | 42,56 (1,08) | 25,77 (0,45) | 1,651 | 390 | 117 |
| 500 | 96,74 (0,94) | 30,06 (0,43) | 3,219 | 990 | 138 |
| 1.000 | 181,23 (1,15) | 33,79 (1,72) | 5,363 | 1.990 | 158 |
| 2.000 | 352,09 (13,51) | 36,61 (0,67) | 9,618 | 3.990 | 178 |
| 5.000 | 853,18 (31,80) | 39,31 (0,73) | 21,705 | 9.990 | 199 |
| 10.000 | 1.694,05 (39,80) | 42,30 (0,74) | 40,051 | 19.990 | 219 |

## Fall „anfang“: kurze Liste am Anfang

| df lange Liste | Zwei-Zeiger µs (IQR) | Galloping µs (IQR) | Zwei-Zeiger/Galloping | Vergleiche Zwei-Zeiger | Vergleiche Galloping |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 14,26 (0,55) | 14,94 (0,73) | 0,954 | 10 | 20 |
| 20 | 14,15 (0,74) | 15,00 (0,77) | 0,943 | 10 | 20 |
| 50 | 14,51 (0,86) | 14,78 (0,55) | 0,982 | 10 | 20 |
| 100 | 14,28 (0,99) | 14,95 (0,72) | 0,955 | 10 | 20 |
| 200 | 14,34 (0,55) | 15,18 (1,02) | 0,945 | 10 | 20 |
| 500 | 14,48 (0,80) | 14,80 (0,58) | 0,978 | 10 | 20 |
| 1.000 | 14,40 (0,76) | 15,00 (0,56) | 0,961 | 10 | 20 |
| 2.000 | 14,50 (0,46) | 14,98 (0,67) | 0,968 | 10 | 20 |
| 5.000 | 14,68 (0,68) | 14,89 (0,59) | 0,986 | 10 | 20 |
| 10.000 | 14,42 (0,88) | 14,81 (0,62) | 0,974 | 10 | 20 |

Vergleiche sind relationale Kennungsvergleiche: beim Zwei-Zeiger-Verfahren `==` und bei Ungleichheit zusätzlich `<`, bei der Galloping Search Proben der Sprungphase, Binärsuchschritte und die abschließende Gleichheitsprüfung. Einzelzähler stehen in `comparisons.json` und `metadata.json`.

Korpus: 10.000 erzeugte Dokumente mit je 100 Tokens (N = 1.000.000), kurze Liste immer 10 Dokumente und Teilmenge der langen Liste. Die direkte Suche diente nur der Trefferprüfung vor dem ersten Timer und wurde nicht gemessen. Betriebssystem-Caches, Python-Allokation und gewöhnliche Hintergrundlast sind Grenzen. Laufzeiten enthalten Normalisierung, Postingzugriff, Sortierung und die vollständige Ergebnisliste.

Quelle: `ergebnisse/messungen/03b_galloping/raw.csv`. Gemessener Git-Ausgangspunkt: `7bc4f9a3a110afa9f259131add5849719eba8b50`, uncommittierte Änderungen vorhanden: `True`, PYTHONHASHSEED: `0`. Exakte Quellenstände mit SHA-256 sind unter `code_source/` archiviert.
