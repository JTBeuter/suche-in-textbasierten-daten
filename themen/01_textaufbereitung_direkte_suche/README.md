# 01 – Textaufbereitung und direkte Suche

Thema 01 stellt die gemeinsame Aufbereitung und eine sequenzielle Einzelwortreferenz für die nächsten Themen bereit.

## Installation und Nutzung

Vom Repository-Verzeichnis aus, mit Python ab 3.11:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -e .
.venv/bin/python -m direkte_suche --corpus daten/beispiele/d0_d5 --query Fehler
.venv/bin/python -m direkte_suche --corpus daten/beispiele/d0_d5 --query Fehler --mode substring
.venv/bin/python -m pytest -q
```

Die erste Suche liefert `{"mode": "word", "query": "Fehler", "matches": ["D0.txt", "D2.txt"]}`. Die Teilzeichendemonstration findet zusätzlich `D1.txt`, dessen Text `Serverfehler` enthält. Die CLI schreibt eine JSON-Zeile auf stdout; Eingabefehler werden erklärt und beenden sie mit Exitcode 2. Dokumentkennungen sind zugleich relative Quelldateipfade. Ein separater Mappingblock ist deshalb nicht erforderlich.

## Suchvertrag

```python
from gemeinsam import load_corpus, prepare_corpus
from direkte_suche import search_direct_word, search_direct_substring

raw = load_corpus("daten/beispiele/d0_d5")
prepared = prepare_corpus(raw)
assert search_direct_word(prepared, "FEHLER") == ["D0.txt", "D2.txt"]
assert search_direct_substring(raw, "Fehler") == ["D0.txt", "D1.txt", "D2.txt"]
```

`search_direct_word(corpus: Iterable[PreparedDocument], query: str) -> list[str]` validiert und normalisiert die Anfrage gemeinsam, vergleicht Tokens eines Dokuments der Reihe nach und beendet dieses Dokument beim ersten Treffer. Es gibt keine vorbereiteten Wortmengen oder Token-zu-Dokument-Listen. Jede Anfrage durchsucht die bereits aufbereiteten Dokumente erneut. Die Suche sortiert die gefundenen IDs und entfernt doppelte Ergebniseinträge. Eine gültige Anfrage ohne Vorkommen liefert `[]`; null oder mehrere Tokens führen zu `QueryError(ValueError)`. Beispielsweise ist `Fehler!` ein gültiges Wort, `E-Mail` ergibt zwei Tokens und ist für die Wortsuche ungültig.

`search_direct_substring(corpus: Iterable[RawDocument], query: str) -> list[str]` sucht eine nichtleere, normalisierte Zeichenfolge im normalisierten Rohtext. Sie tokenisiert nicht: Leerzeichen und Satzzeichen gehören zur Anfrage. Diese Demonstration hat andere Semantik und Vorbereitungskosten als die Wortsuche und ist keine Laufzeitbaseline für einen Wortindex.

Die vollständigen gemeinsamen Typen, UTF-8-Fehlerregeln, Kennungen und Unicode-Regeln sind im [gemeinsamen README](../../gemeinsam/README.md) dokumentiert. Quellen, Rohtexte und Tokenfolgen werden erhalten. Die Sortierung der Dateien hat keinen Einfluss auf Kennungen oder Treffer.

## Beispiele und Prüfungen

`daten/beispiele/d0_d5/` enthält genau die sechs Dokumente des Implementation Plans. Die erklärende Kennung D0 entspricht `D0.txt`; D4 ist eine tatsächlich leere Datei. Unabhängig festgelegte Tokens, Worttreffer und spätere Phrasenstarts stehen in `daten/beispiele/d0_d5_expected.json`. Die Phrase `a a` hätte in D5 die Startpositionen 0 und 1; `Server Fehler` hätte in D2 Position 2 und überschreitet dort eine Satzgrenze.

Die Tests prüfen feste Sollwerte, Unicode und kombinierende Zeichen, Ergebnisordnung und Eindeutigkeit, leere und ungültige Eingaben, erhaltenen Rohtext, stabile Kennungen bei Dateiänderungen, Codierungs- und Dateisystemfehler, symbolische Links sowie das unveränderliche Datenmodell. Ein erzeugter kleiner Korpus erhält seinen unabhängigen Erwartungswert aus vorher festgelegten Pflanzentscheidungen mit Seed 20261006. CLI-Tests laufen ohne `PYTHONPATH` aus dem Repository und aus einem fremden Verzeichnis.

## Untersuchung und Übergabe

Die ausführbare Untersuchung und ihre Befehle sind unter [experimente/](experimente/README.md) dokumentiert. Sie trennt Einlesen, Aufbereitung und Wortabfragen, prüft bekannte Treffer und speichert Rohmesswerte, Metadaten und beschriftete Diagramme in `ergebnisse/`. Der kontrollierte Regelvergleich ändert genau die Behandlung der Groß-/Kleinschreibung. Der reale feste deutschsprachige Auszug mit Herkunft, Nutzungsbedingungen und Prüfsummen liegt unter `daten/real/kafka_verwandlung/`.

- Thema 02 übernimmt dieselben vorbereiteten Dokumente und vergleicht seine
  Einzelworttreffer gegen `search_direct_word`.
- Thema 04 erhält die unveränderten nullbasierten Tokenpositionen einschließlich
  Satzgrenzenregel und Handfixtures für überlappende Phrasen.
- Thema 05 übernimmt Datenidentität, Generatorseed und getrennte Messgrenzen;
  Wortabfragezeit enthält Anfrageaufbereitung und Ergebnisbildung.

Thema 01 schließt seinen Bereich ab; die späteren Indizes und der vollständige Gesamtvergleich bleiben Aufgaben der Themen 02 bis 05.
