# 02 – Invertierter Index und Einzelwortsuche

Der eigene In-Memory-Index bildet ein normalisiertes Token auf die Dokumente seines Vorkommens ab. Er übernimmt sämtliche Typen, Kennungen, Unicode- und Fehlerregeln von [Thema 01](../01_textaufbereitung_direkte_suche/README.md). Positionsdaten bleiben Aufgabe von Thema 04. Vollständige Nachweise:

## Installieren und demonstrieren

Aus der Repositorywurzel, Python ≥3.11 und die vorhandene Entwicklungsumgebung:

```sh
.venv/bin/python -m pip install -e .
.venv/bin/python -m direkte_suche --mode index --corpus daten/beispiele/d0_d5 --query Fehler
.venv/bin/python -m invertierter_index --corpus daten/beispiele/d0_d5 --query Fehler
.venv/bin/python -m invertierter_index --corpus daten/real/kafka_verwandlung --query Gregor
.venv/bin/python -m pytest -q
```

Neue Umgebung: `python3 -m venv .venv`, anschließend `.venv/bin/python -m pip install -r requirements-dev.txt` und die obige Editable-Installation. Die Paketzuordnung steht explizit in `pyproject.toml`; kein manuelles `PYTHONPATH` nötig. Alle Suchmodule verwenden die Standardbibliothek. Die CLI gibt JSON mit `mode`, `query` und `matches` aus; `Fehler` ergibt `["D0.txt", "D2.txt"]`, ohne `D1.txt` mit `Serverfehler`. Eingabefehler erzeugen eine erklärte stderr-Meldung und Exitcode 2. Der etablierte Einstieg `direkte_suche` besitzt zusätzlich `--mode index`; seine bisherigen Modi bleiben unverändert. `invertierter_index` ist der ergänzende themenspezifische Einstieg mit demselben Treffervertrag.

## Öffentliche Schnittstellen

```python
from gemeinsam import load_corpus, prepare_corpus, normalize_query
from invertierter_index import build_inverted_index, search_index_word, get_postings

corpus = prepare_corpus(load_corpus("daten/beispiele/d0_d5"))
index = build_inverted_index(corpus)
assert search_index_word(index, "FEHLER!") == ["D0.txt", "D2.txt"]
(token,) = normalize_query("Fehler")
assert get_postings(index, token) == ("D0.txt", "D2.txt")
```

| Funktion/Typ | Vertrag |
| --- | --- |
| `build_inverted_index(corpus: Iterable[PreparedDocument]) -> InvertedIndex` | Einmaliger Aufbau; eindeutige IDs, vorbereitete Tokens, beliebige Dokumentreihenfolge |
| `InvertedIndex` | Unveränderliche `Mapping[str, tuple[str, ...]]`; Erzeugung nur über Aufbau; Mappingzugriff nimmt exakte Schlüssel und ergibt bei fehlendem Schlüssel `KeyError` |
| `search_index_word(index, query: str) -> list[str]` | Benutzerseitiger Rohtext; zentrale `normalize_query`; vollständig materialisierte neue Trefferliste |
| `get_postings(index, token: str) -> tuple[str, ...]` | Bereits normalisiertes einzelnes Token; dasselbe interne immutable Tupel ohne Kopie; unbekannter gültiger Schlüssel ergibt `()` |

ID und Herkunft sind relative POSIX-.txt-Pfade wie in Thema 01. Sortierung ist lexikografisch: `D10.txt` kommt vor `D2.txt`. Innerhalb eines Dokuments verhindert ein Set wiederholte ID-Einträge. Ein Wörterbuch sammelt pro Token Listen; abschließend werden diese sortiert und zu Tupeln. Das private finale Dictionary wird ausschließlich durch `MappingProxyType` gelesen und entweicht nicht. Die Eingaben und spätere Abfragen verändern den Index nicht.

Leere Korpora oder Dokumente sind gültig. Nicht iterierbare/zeichenkettenartige Korpora, Elemente außerhalb von `PreparedDocument`, doppelte IDs und nicht normalisierte Einzel-Tokens werden mit `CorpusError(ValueError)` abgewiesen. Die gemeinsame Dataclass prüft Typen und grundlegende Dokumentfelder; der Aufbau prüft mit der zentralen Tokenisierung einmal pro verschiedenem Token zusätzlich `tokenize(token) == (token,)`. Er tokenisiert keinen Dokumentrohtext neu. Die Konsistenz zwischen Rohtext und Tokens garantiert die vorgeschaltete `prepare_corpus`; manuell erzeugte Dokumente müssen dieselbe Vorbedingung erfüllen.

`search_index_word` erlaubt z. B. `Fehler!`, `Straße` oder `STRASSE`, sofern nach gemeinsamer Tokenisierung genau ein Token bleibt. `Straße` und `STRASSE` sind dasselbe Token `strasse`. Leere/mehrwortige/falsch typisierte Anfragen werden wie in Thema 01 mit `QueryError(ValueError)` abgewiesen. Ein gültiges unbekanntes Wort ergibt `[]`. `get_postings` weist Rohtext wie `Fehler!` oder `FEHLER` ausdrücklich zurück: Der Aufrufer normalisiert vorher zentral. Direkter Mappingzugriff validiert keine Rohtextanfragen.

Thema 03 kann Postinglisten über `get_postings` abrufen und zusammenführen, ohne den Korpus zu behalten. Die Kern-Vertragsprüfung kostet Zeichenarbeit; das Lesen/Kombinieren benötigt weder Neubau noch globale Caches. Die zurückgegebenen Tupel sind sicher wiederverwendbar. Die unabhängige Listenausgabe der öffentlichen Wortsuche lässt sich beliebig verändern, ohne spätere Ergebnisse zu beeinflussen.

## Aufwand und Nachweise

N = gesamte Tokenzahl, D = Dokumentzahl, V = realisierter Wortschatz und P = Summe der Dokumenthäufigkeiten df(t). Bei durchschnittlichen Dictionary- und Setkosten sowie beschränkten Token-/ID-Längen kostet der Aufbau `O(D + N + V + Σ df(t) log(df(t)+1))`; für V>0 ist V≤N. D bleibt relevant, weil auch leere Dokumente geprüft werden. Zeichenlängen beeinflussen Hashen, einmalige Tokenvalidierung und Kennungsvergleiche; die Aussage ist keine garantierte konstante Hashzugriffskomplexität. Die Abschluss-Sortierung ist erforderlich, weil Eingabereihenfolge frei bleibt.

Der gespeicherte Index enthält größenordnungsmäßig `O(V + P)` Einträge. Temporäre Aufbaustrukturen enthalten zusätzlich geprüfte IDs und Tokens sowie je eine Dokumentwortmenge. Eine Rohtextanfrage der Länge m kostet Aufbereitung plus erwarteten Lookup plus `Θ(df(t))` für die Listenkopie: unter üblichen Zeichenkosten `O(m + df(t))`. Vollständige Treffer benötigen mindestens `Ω(df(t))` Arbeit. Das Kopieren einer langen Postingliste ist kein konstanter Suchschritt. Der zusätzliche Python-Speicher wird separat gemessen.

Die Tests verwenden einen vollständigen handberechneten D0–D5-Index, feste Tokenfolgen statt nur gemeinsamen Ergebnisvergleichs, Unicode-/Trennerfälle, unsortierte Iteratoren und unabhängige Dokumentdurchläufe für alle Wörter mehrerer deterministischer Prüfkorpora. Seeds/Parameter stehen direkt in `tests/test_index.py`. Zusätzlich werden alle Wörter des realen Auszugs mit direkter Referenz und unabhängiger Dokumentreferenz verglichen. Mutationstests prüfen Listenkopien, Tupel, Mapping und wiederholte Abfragen in wechselnder Folge.

## Untersuchung und Übergabe

Reproduzierbare Versuche und deren Befehle stehen in [experimente/](experimente/README.md). Aufbau, Abfrage und zusätzlicher Speicher werden getrennt erhoben. Fehlende, seltene und frühe häufige Treffer werden gesondert behandelt; die direkte Suche beendet ein getroffenes Dokument beim ersten Tokenvorkommen.

Thema 03 erhält den unveränderlichen Postingzugriff. Thema 05 erhält N/D/V/P, Dokumentlängen, Dokument-/Tokenhäufigkeiten, Daten-/Codeprüfsummen, das gemeinsame Zeit-CSV-Schema und separate Speicherdaten. Die kombinierte Auswertung und Amortisation bleiben Aufgabe von Thema 05; hier wird keine Fertigstellung des Gesamtprojekts behauptet. Theorie:
