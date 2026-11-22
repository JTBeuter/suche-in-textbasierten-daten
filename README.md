# Textsuche: von direkter Suche zur Indexsuche

Das Projekt untersucht die Suche in textbasierten Daten und vergleicht die Verfahren auf denselben Daten und mit derselben Messmethode. Fünf aufeinander aufbauende Themenbereiche sind in **Python** umgesetzt:

| Thema | Inhalt | Paket |
|---|---|---|
| 01 | Textaufbereitung und direkte Suche | `direkte_suche` |
| 02 | Invertierter Index und Einzelwortsuche | `invertierter_index` |
| 03 | Boolesche Suche (AND, OR, AND NOT), Galloping Search | `boolesche_suche` |
| 04 | Positionsindex und Phrasensuche | `positionsindex` |
| 05 | Gesamt-CLI, Messpipeline, Gesamtkostenvergleich | `experimentelle_analyse` |

Die Kernsuche nutzt nur die Standardbibliothek. pytest und Matplotlib sind reine Entwicklungswerkzeuge.

## Projektstruktur

```text
.
├── gemeinsam/                  Korpus laden, Textaufbereitung, Modelle, Messung
├── themen/0X_*/                je Thema: src/ (Paket), tests/, experimente/ (Messskripte)
├── daten/                      Beispielkorpus d0_d5, Realkorpus BGB, Kafka-Auszug
├── ergebnisse/
│   ├── messungen/              Rohmesswerte und Zusammenfassungen aller Läufe
│   ├── abbildungen/            Diagramme aus den Messwerten
│   └── abbildungen_arbeit/     die vier Diagramme der schriftlichen Arbeit mit ihren Skripten
├── doku/                       Architektur und Messkonzept
├── pyproject.toml              Paketzuordnung (Paketnamen und Ordnernamen unterscheiden sich)
└── requirements-*.txt          festgelegte Versionen
```

Die Paketnamen weichen von den Ordnernamen ab. Die Zuordnung steht in `pyproject.toml`. Verträge und Schnittstellen beschreibt [doku/architektur.md](doku/architektur.md), die Messmethode [doku/messkonzept.md](doku/messkonzept.md). Jeder Themenordner hat eine eigene `README.md`.

## Installation

Voraussetzung ist **Python 3.11** (geprüft mit CPython 3.11.2). Git wird nicht benötigt, das Projekt läuft direkt aus dem entpackten ZIP-Archiv. Nur beim Neu-Messen wird der Git-Stand in den Metadaten vermerkt, falls vorhanden (sonst `kein-git`).

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install -e .
```

`requirements-lock.txt` enthält die vollständige geprüfte Paketauflösung, `requirements-dev.txt` nur pytest und Matplotlib. Mit `uv` geht es ebenso:

```sh
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -r requirements-lock.txt
uv pip install --python .venv/bin/python -e .
```

## Tests

```sh
.venv/bin/python -m pytest -q
```

Die Testsammlung umfasst 1.131 Tests und braucht etwa 2 bis 4 Minuten. Jedes Indexverfahren wird gegen eine direkte Referenzsuche und gegen die vorab festgelegten Sollwerte in `daten/beispiele/d0_d5_expected.json` geprüft.

## Suche ausprobieren

Alle Aufrufe aus dem Repository-Verzeichnis. Die Ausgabe ist eine JSON-Zeile.

```sh
.venv/bin/python -m experimentelle_analyse search --corpus daten/beispiele/d0_d5 --kind word --method index --query Fehler
```

Erwartet: Treffer `D0.txt` und `D2.txt`. Die Gesamt-CLI `experimentelle_analyse search` bedient alle Sucharten:

| Option | Werte |
|---|---|
| `--kind` | `word`, `and`, `or`, `phrase` |
| `--method` | `direct` (Referenz ohne Index), `index` |
| `--variant` | `basic` (Eingabereihenfolge), `shortest_first`, `galloping` (nur mit `--kind and --method index`) |
| `--exclude WORT` | schließt genau ein Wort aus (AND NOT), nur mit `--kind and` |
| `--query` | Suchtext, bei `and`/`or`/`phrase` mehrere Wörter |

Beispiele:

```sh
.venv/bin/python -m experimentelle_analyse search --corpus daten/beispiele/d0_d5 --kind and --method index --variant galloping --query "Verbindung Server"
.venv/bin/python -m experimentelle_analyse search --corpus daten/beispiele/d0_d5 --kind and --method index --exclude Server --query Verbindung
.venv/bin/python -m experimentelle_analyse search --corpus daten/beispiele/d0_d5 --kind phrase --method index --query "Verbindung zum Server"
.venv/bin/python -m experimentelle_analyse search --corpus daten/real/bgb/dokumente --kind and --method index --variant galloping --exclude Verbraucher --query "Vertrag Schadensersatz"
```

Die Phrase liefert `{"D0.txt": [3], "D2.txt": [0]}`. Die Positionen sind nullbasierte Tokenpositionen. Der Realkorpus wird immer mit dem Unterordner `dokumente/` als Korpuswurzel geladen, die Dokumentkennungen sind dann die Dateinamen (`bgb_2385.txt` und so weiter).

Jedes Thema hat zusätzlich ein eigenes Kommandozeilenprogramm:

```sh
.venv/bin/python -m direkte_suche --corpus daten/beispiele/d0_d5 --query Fehler
.venv/bin/python -m direkte_suche --corpus daten/beispiele/d0_d5 --query Fehler --mode substring
.venv/bin/python -m invertierter_index --corpus daten/beispiele/d0_d5 --query Fehler
.venv/bin/python -m boolesche_suche --corpus daten/beispiele/d0_d5 --terms Verbindung Server --operator AND --variant galloping
.venv/bin/python -m positionsindex --corpus daten/beispiele/d0_d5 --phrase "Verbindung zum Server"
```

Jeder `search`-Aufruf lädt den Korpus neu und baut bei `--method index` einen neuen Index. Für mehrere Abfragen auf demselben Index die Python-Schnittstelle verwenden:

```python
from gemeinsam import load_corpus, prepare_corpus
from invertierter_index import build_inverted_index, search_index_word

corpus = prepare_corpus(load_corpus("daten/beispiele/d0_d5"))
index = build_inverted_index(corpus)
for query in ("Fehler", "Verbindung", "Server"):
    print(query, search_index_word(index, query))
```

Suchsemantik: Unicode-Normalisierung NFC, dann Case Folding. Ein Wort besteht aus Buchstaben und Ziffern, alles andere trennt. Es gibt keine Stoppwortentfernung und kein Stemming, Umlaute bleiben erhalten. `Straße` und `STRASSE` sind derselbe Begriff.

## Die Messergebnisse nachvollziehen

Alle Rohwerte liegen in `ergebnisse/messungen/<Reihe>/`. Jeder Ordner enthält typischerweise `raw.csv` (Einzelmessungen), `summary.json` (Median, Quartile je Gruppe), `metadata.json` (Umgebung, Parameter, Zufallsstartwert, Git-Stand) und `code_source/` (Kopie des gemessenen Quellcodes). Die Läufe `*_pilot` sind die Probeläufe, an die der jeweilige Hauptlauf gebunden ist. Die Prüfung der Hauptläufe braucht sie.

| Thema | Reihe | Inhalt |
|---|---|---|
| 01 | `01_direkte_suche`, `01b_direkte_suche` | Skalierung der direkten Suche, Aufbereitungsregeln, BGB-Teil |
| 02 | `02_invertierter_index`, `02b_tokenpruefung`, `02_bgb` | Aufbauzeit, Abfragezeit, Speicher, Anteil der Tokenprüfung, BGB-Teil |
| 03 | `03_boolesche_mehrwortsuche`, `03_bgb`, `03b_galloping` | AND-Reihenfolge, BGB-Anfragen, Galloping Search |
| 04 | `04_positionsindex_phrasensuche`, `04_bgb` | Phrasensuche, Speicher des Positionsindex |
| 05 | `05_experimentelle_analyse`, `05_bgb` | Gesamtkosten und Amortisation (ab wie vielen Anfragen lohnt sich der Index) |

### Messläufe prüfen

Jeder Verifier prüft Schema, Einheiten, Statistik, Korpus-Hashes, Treffer gegen die Referenzsuche und das Quellarchiv des Laufs. Mit `--archive-only` wird gegen das archivierte statt gegen das aktuelle Quellverzeichnis geprüft. Das ist für alle gelieferten Läufe nötig, weil der Code nach den Messungen bewusst erweitert wurde (Galloping, `--exclude`, BGB-Teile, optionaler Git-Aufruf).

```sh
# Thema 01
.venv/bin/python themen/01_textaufbereitung_direkte_suche/experimente/verify_results.py --archive-only
.venv/bin/python themen/01_textaufbereitung_direkte_suche/experimente/verify_results.py --eingabe 01b_direkte_suche --archive-only
# Thema 02
.venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/verify_results.py --archive-only
.venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/tokenpruefung.py --pruefen 02b_tokenpruefung --archive-only
.venv/bin/python themen/02_invertierter_index_einzelwortsuche/experimente/bgb_lauf.py --pruefen 02_bgb --archive-only
# Thema 03
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/verify_results.py --archive-only
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/bgb/verify_results.py --eingabe 03_bgb --archive-only
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/galloping/verify_results.py --eingabe 03b_galloping --archive-only
# Thema 04
.venv/bin/python themen/04_positionsindex_phrasensuche/experimente/verify_results.py --archive-only
.venv/bin/python themen/04_positionsindex_phrasensuche/experimente/verify_bgb.py --archive-only
# Thema 05
.venv/bin/python -m experimentelle_analyse verify --input ergebnisse/messungen/05_bgb --archive-only
.venv/bin/python -m experimentelle_analyse verify --input ergebnisse/messungen/05_experimentelle_analyse --archive-only
```

Jeder Befehl endet mit Exitcode 0 und einer Zeile, die die geprüften Werte nennt. Neue Läufe (zum Beispiel `mein_pilot` unten) bestehen die strenge Prüfung ohne `--archive-only`.

### Auswertung und Diagramme

- **Fertige Diagramme:** `ergebnisse/abbildungen/` (Reihen 01 bis 04, `05/` und `05_bgb/` für den Gesamtvergleich) und `ergebnisse/abbildungen_arbeit/` (die vier in der schriftlichen Arbeit verwendeten Diagramme). Dort liegen auch die Modelle zur Amortisation (`models.json`, `amortisation.csv`).
- **Auswertung und Diagramme neu berechnen** (Thema 05, schreibt in ein neues Verzeichnis, nichts wird überschrieben). `render.py` liest die Ausgabe von `analyse` und legt die Diagramme im selben Verzeichnis ab:

```sh
.venv/bin/python -m experimentelle_analyse analyse --input ergebnisse/messungen/05_experimentelle_analyse --output /tmp/auswertung05 --archive-only
.venv/bin/python themen/05_experimentelle_analyse/experimente/render.py --output /tmp/auswertung05 --archive-only
```

- **Diagramme der Arbeit neu zeichnen** (byteidentisch zu den vorhandenen Dateien, ersetzt sie durch gleiche):

```sh
.venv/bin/python ergebnisse/abbildungen_arbeit/42_woerterbuch_postings.py
.venv/bin/python ergebnisse/abbildungen_arbeit/03b_galloping_arbeit.py
.venv/bin/python ergebnisse/abbildungen_arbeit/render_eval_figures.py
.venv/bin/python ergebnisse/abbildungen_arbeit/render_eval_figures.py --kapitel5
```

- **Weitere Auswertungsskripte** der Themen 03 und 04 (`analyse.py`, `plots/render.py` in den Ordnern `experimente/`) schreiben direkt nach `ergebnisse/abbildungen/` und ersetzen dort vorhandene Dateien. Sie am besten in einer Kopie ausführen oder danach mit `git restore ergebnisse/` zurücksetzen.

Die Beschreibung der einzelnen Versuche, Parameter und Befehle steht in `themen/0X_*/experimente/README.md`.

### Neu messen

Messläufe immer in **neue Zielverzeichnisse** schreiben, die gelieferten Rohwerte werden nicht überschrieben. Zuerst läuft ein Pilot, danach der Hauptlauf mit festem Zufallsstartwert (`PYTHONHASHSEED=0`), zum Beispiel der Pilot des Gesamtvergleichs (etwa eine Minute):

```sh
PYTHONHASHSEED=0 .venv/bin/python -m experimentelle_analyse run --config themen/05_experimentelle_analyse/experimente/pilot.json --output ergebnisse/messungen/mein_pilot
.venv/bin/python -m experimentelle_analyse verify --input ergebnisse/messungen/mein_pilot
```

Während einer Zeitmessung dürfen keine Tests oder andere rechenintensive Programme laufen. Die genauen Befehle je Reihe stehen in den `experimente/README.md` der Themen, die Messmethode (Warmups, Wiederholungen, getrennte Phasen) in [doku/messkonzept.md](doku/messkonzept.md). Neue Messwerte hängen von der Hardware ab und weichen von den gelieferten Werten ab. Ein fehlender Geschwindigkeitsvorteil ist ein zulässiges Ergebnis.

## Lizenz und Daten

Das BGB stammt von [gesetze-im-internet.de](https://www.gesetze-im-internet.de) und ist nach § 5 UrhG gemeinfrei (Herkunft, Abrufstand und Prüfsummen in [daten/real/bgb/README.md](daten/real/bgb/README.md)). Der Kafka-Auszug unter `daten/real/kafka_verwandlung/` ist die Datengrundlage der frühen Messläufe.
