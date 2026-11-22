# 03 – Boolesche Mehrwortsuche und Optimierung

Eigene Zeigerverfahren kombinieren die unveränderlichen Postinglisten aus Thema 02. Eine unabhängige direkte Referenz scannt die vorbereiteten Tokens aus Thema 01. Nachweise und Grenzen:

## Installation und Nutzung

Aus der Repositorywurzel in der vorhandenen Entwicklungsumgebung:

```sh
.venv/bin/python -m pip install -e .
.venv/bin/python -m direkte_suche --boolean --corpus daten/beispiele/d0_d5 --terms Verbindung Server --operator AND --variant shortest_first
.venv/bin/python -m boolesche_suche --corpus daten/beispiele/d0_d5 --terms Verbindung Server --operator AND --method direct
.venv/bin/python -m boolesche_suche --corpus daten/beispiele/d0_d5 --terms Fehler a --operator OR
.venv/bin/python -m boolesche_suche --corpus daten/beispiele/d0_d5 --terms Verbindung Server --operator AND --variant galloping
.venv/bin/python -m boolesche_suche --corpus daten/beispiele/d0_d5 --terms Verbindung --exclude Server --operator AND
.venv/bin/python -m pytest -q
```

Neue Umgebung: `python3 -m venv .venv`, danach `.venv/bin/python -m pip install -r requirements-dev.txt` und die Editable-Installation. Python ≥3.11; keine neuen Laufzeitabhängigkeiten. `direkte_suche --boolean` delegiert an denselben Parser wie `boolesche_suche`. Die bisherigen Wort-, Index- und Teilzeichenaufrufe bleiben erhalten. `--boolean --help` zeigt die neue Bedienung. `--method index` ist Standard; `--method direct` wählt die direkte Referenz. Ein CLI-Aufruf lädt und bereitet vor und baut gegebenenfalls einen Index auf; seine Gesamtzeit entspricht nicht der isolierten Suchzeit der Versuche.

Ausgabe ist eine JSON-Zeile mit Begriffen, normalisierten Begriffen, ursprünglicher und effektiver Begriffszahl, Operator, Methode, Variante und Treffern. Nur mit `--exclude` kommen vor `matches` die Felder `exclude` (Rohwort) und `normalized_exclude` hinzu, ohne den Schalter bleibt die Ausgabe byteidentisch. Das AND- Beispiel liefert `["D0.txt", "D2.txt", "D3.txt"]`, `Verbindung --exclude Server` liefert `["D1.txt"]`. Eingabefehler erzeugen eine erklärte stderr-Meldung und Exitcode 2; unbekannte gültige Wörter können eine leere Trefferliste bei Exitcode 0 liefern.

## Öffentliche Schnittstellen

```python
from gemeinsam import load_corpus, prepare_corpus
from invertierter_index import build_inverted_index
from boolesche_suche import normalize_boolean_query, search_direct_boolean, search_index_boolean

corpus = prepare_corpus(load_corpus("daten/beispiele/d0_d5"))
index = build_inverted_index(corpus)
terms = ["Verbindung", "SERVER!", "VERBINDUNG"]
query = normalize_boolean_query(terms, "AND")
assert query.terms == ("verbindung", "server")
assert (query.original_term_count, query.effective_term_count) == (3, 2)
assert search_direct_boolean(corpus, terms, "AND") == ["D0.txt", "D2.txt", "D3.txt"]
assert search_index_boolean(index, terms, "AND", "shortest_first") == ["D0.txt", "D2.txt", "D3.txt"]
```

| Funktion | Vertrag |
| --- | --- |
| `normalize_terms(terms: Iterable[str]) -> tuple[str, ...]` | Jedes Wort mit zentraler `normalize_query` prüfen; Duplikate stabil nach Normalisierung entfernen |
| `normalize_boolean_query(terms, operator) -> BooleanQuery` | Zusätzlich Operator prüfen und beide Begriffszahlen dokumentieren; immutable Dataclass |
| `normalize_boolean_query(terms, operator, exclude=None) -> BooleanQuery` | Optional genau ein NOT-Wort, gleich normalisiert, genau ein Token, nur bei `AND`; Feld `exclude` (sonst `None`) |
| `search_direct_boolean(corpus: Iterable[PreparedDocument], terms: Iterable[str], operator: str, exclude: str \| None = None) -> list[str]` | Tokenscan ohne Index/Dokumentwortmengen; früher Abbruch innerhalb eines getroffenen Dokuments, mit `exclude` nur beim NOT-Wort |
| `search_index_boolean(index: InvertedIndex, terms: Iterable[str], operator: str, variant: str = "input_order", exclude: str \| None = None) -> list[str]` | Vorhandene Tupel über `get_postings` lesen und eigene Listenverfahren verwenden |
| `intersect_sorted(left: Sequence[str], right: Sequence[str]) -> list[str]` | Zwei-Zeiger-Schnittmenge; Eingaben sortiert und eindeutig |
| `union_sorted(left: Sequence[str], right: Sequence[str]) -> list[str]` | Zwei-Zeiger-Vereinigung inklusive Reste; dieselbe Vorbedingung |
| `intersect_galloping(left: Sequence[str], right: Sequence[str]) -> list[str]` | Galloping Search: Kennungen der kürzeren Liste, Sprünge 1, 2, 4, 8, … und Binärsuche in der längeren, O(a·log(b/a)); dieselbe Vorbedingung |
| `difference_sorted(left: Sequence[str], right: Sequence[str]) -> list[str]` | Zwei-Zeiger-Differenz: Kennungen aus `left`, die in `right` fehlen; dieselbe Vorbedingung |

Iterables werden einmal konsumiert; ihre Reihenfolge bestimmt die Grundvariante. Für reproduzierbare Anfragen Listen oder Tupel verwenden. Begriffe und Operator sind getrennt; eine Zeichenkette anstelle des Iterables ist ungültig. Jeder Begriff muss genau ein Token ergeben: `Server!` ist gültig, `Fehler Server`, `E-Mail`, Leertext und Nichtstrings sind ungültig. NFC → casefold → NFC und Unicode- Kategorien L*/Nd bleiben unverändert. `Straße` und `STRASSE` sind derselbe Begriff; Umlaute und Stopwörter bleiben erhalten.

## Semantik, Varianten und sichere Listen

AND verlangt sämtliche unterschiedlichen Begriffe im selben Dokument, OR mindestens einen. Wortreihenfolge und Wiederholungen ändern Treffer nicht. Eine Einbegriffsabfrage entspricht der Wortsuche. Leere Anfragen, Operatoren außerhalb der exakten Werte `AND`/`OR` und ungültige Varianten ergeben `QueryError(ValueError)`. Unbekanntes Wort: AND leer, OR kein Beitrag. Leere Dokumente und Korpora sind zulässig.

AND hat `input_order` (effektive Eingabereihenfolge), `shortest_first` (aufsteigende Postinglängen; Gleichstand bleibt in Eingabereihenfolge) und `galloping` (gleiche Sortierung, danach schrittweise `intersect_galloping`). OR unterstützt nur `input_order`; die direkte CLI ebenfalls, da sie keine Listen plant. `AND NOT` hat beliebig viele Pflichtwörter und genau ein ausgeschlossenes Wort (`exclude`, CLI `--exclude WORT`, nur mit `AND`): Nach dem Schnitt wird dessen Postingliste mit `difference_sorted` abgezogen, bei leerem Schnitt entfällt der Schritt. Ist das NOT-Wort zugleich Pflichtwort, ist das Ergebnis leer. `NOT` allein ist nicht vorgesehen. Ein im Suchtext geschriebenes `AND` oder `NOT` bleibt ein gewöhnliches Suchwort; es gibt keinen Abfrageparser. Alle Varianten liefern neue, vollständig materialisierte, lexikografisch sortierte `list[str]` ohne Duplikate. Kennungen bleiben relative POSIX-Pfade; D10 kommt vor D2.

`get_postings` liefert immutable Tupel ohne Kopie. Sortiert werden nur lokale Listenreferenzen; die erste Liste wird zur Ergebnisliste kopiert. Weitere Operationen erzeugen neue Zwischenlisten, AND bricht bei leerem Ergebnis ab. Ausgabemutationen ändern weder Index noch spätere Treffer. Die Zeigeroperationen prüfen Sortierung/Eindeutigkeit nicht erneut; diese garantiert der Indexaufbau. Die direkte Referenz setzt den einmalig geprüften Korpus voraus; Rohtext-/Token- Konsistenz bleibt Vorbedingung von `prepare_corpus`.

## Prüfungen, Untersuchung und Übergabe

Feste Solltokens/D0–D5-Treffer, zufällige Listen gegen eine unabhängige Mengenoracle und gepflanzte Korpora prüfen Semantik, Fehler und Grenzen. Seeds und vollständige Fehlerkontexte sind im Testcode. Permutation, Idempotenz, AND-Teilmengen, OR-Obermengen, frühe Tokenabbrüche, tatsächliche Längengleichstände und wechselnde Ausgabemutationen ergänzen die Vergleiche. Reale Stichproben verwenden den unveränderten Kafka-Auszug mit bekannten Anfangstokens/Wortvorkommen.

[Experimente](experimente/README.md) untersuchen k=2/3/5, Häufigkeiten, Reihenfolge und Überschneidung bei gleicher synthetischer Datengrundlage sowie separat den Realtext. Die gemessene öffentliche Abfrage enthält Normalisierung, Postingzugriffe, Sammeln, Sortieren und vollständige Ergebnisbildung. Aufbereitung und Aufbau werden getrennt gemessen, Zähler in separaten Diagnoseläufen erhoben. Die eigene Reihe 03b vergleicht Galloping Search und Zwei-Zeiger ([galloping/README.md](experimente/galloping/README.md)). Der neue Realteil auf dem BGB steht in [bgb/README.md](experimente/bgb/README.md). Rohwerte: `ergebnisse/messungen/03_*` und `03b_*`; Methode und beobachtete Befunde: Die Längenheuristik kann Vorteil oder Nachteil zeigen; universelle Überlegenheit wird nicht behauptet.

Thema 04 erhält dieselben Dokument-/Postingverträge und die Listenoperationen. Thema 05 erhält stabile APIs, konkrete Abfragesätze, Listen-/Zwischengrößen, Rohkosten und Streuung sowie Daten-/Codeprüfsummen. Umfassende Auswertung und Amortisation bleiben dort. Der Gesamtprojektabschluss ist offen.
