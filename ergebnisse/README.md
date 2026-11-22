# Ergebnisse

| Ordner | Inhalt |
|---|---|
| `messungen/` | Rohmesswerte (`raw.csv`), Zusammenfassungen (`summary.json`), Metadaten (`metadata.json`) und Quellarchiv (`code_source/`) je Messreihe. |
| `abbildungen/` | Aus den Messwerten erzeugte Diagramme der Reihen 01 bis 05. |
| `abbildungen_arbeit/` | Die vier Diagramme der schriftlichen Arbeit mit den Skripten, die sie erzeugen. |

Die gelieferten Messwerte werden nicht überschrieben. Einzige nachträgliche Änderung: Im Feld `python_executable` der `metadata.json` ist der lokale Verzeichnispfad des Messrechners durch `<Projektordner>` ersetzt, die Hashes in den Diagramm-Manifesten sind entsprechend angepasst. Messwerte sind davon nicht betroffen. Neue Messungen gehören in neue Zielverzeichnisse. Welche Reihe zu welchem Thema gehört und wie man sie prüft und auswertet, steht im [Haupt-README](../README.md), die Versuchsparameter in `themen/0X_*/experimente/README.md`.

Aufbauzeit und Suchzeit werden getrennt ausgewiesen, ebenso Laden und Aufbereitung. Zeiten sind Mediane mit Quartilen aus 20 Wiederholungen nach 5 Aufwärmläufen (Gesamtabläufe: 5 Wiederholungen nach einem Aufwärmlauf, siehe [Messkonzept](../doku/messkonzept.md)).

| Reihe | Inhalt |
|---|---|
| `01_direkte_suche`, `01b_direkte_suche` | Direkte Suche: Skalierung, Aufbereitungsregeln, BGB-Teil. |
| `02_invertierter_index`, `02b_tokenpruefung`, `02_bgb` | Index: Aufbau, Abfrage, Speicher, Anteil der Tokenprüfung, BGB-Teil. |
| `03_boolesche_mehrwortsuche`, `03_bgb`, `03b_galloping` | Boolesche Suche: AND-Reihenfolge, BGB-Anfragen, Galloping Search. |
| `04_positionsindex_phrasensuche`, `04_bgb` | Phrasensuche und Speicher des Positionsindex. |
| `05_experimentelle_analyse`, `05_bgb` | Gesamtkosten und Amortisation. Auswertung in `abbildungen/05/` und `abbildungen/05_bgb/`. |
| `*_pilot` | Probeläufe, an die der jeweilige Hauptlauf gebunden ist. |
