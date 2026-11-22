# Handprüfbarer Beispielkorpus D0–D5

`d0_d5/` enthält die sechs UTF-8-Dokumente des Implementation Plans; D4 ist
leer. Die erklärende Kennung D0 entspricht der stabilen Dateikennung D0.txt.
`d0_d5_expected.json` wurde unabhängig von der Implementierung mit erwarteten
Tokens, Worttreffern, Teilzeichentreffern und später nutzbaren Phrasenpositionen
angelegt. Es enthält auch überlappende Phrasen (`a a`), eine Phrase über eine
Satzgrenze (`Server Fehler`) sowie ausgeschlossene Treffer über die Grenze
zwischen D0 und D1 (`Server Serverfehler`). Thema 01 implementiert die
Einzelwortsuche und demonstriert Teilzeichensuche; die Phrase-Schnittstelle
folgt in Thema 04.

```sh
.venv/bin/python -m direkte_suche --corpus daten/beispiele/d0_d5 --query Fehler
.venv/bin/python -m pytest -q
```

Die kleinen Beispiele sind selbst erstellt, enthalten keine externen
Quellen und werden für unabhängige Korrektheitsprüfungen versioniert.
