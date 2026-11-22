# 04 – Positionsindex und Phrasensuche

Der eigene Positionsindex speichert die nullbasierten Vorkommenspositionen jedes Tokens innerhalb eines Dokuments. Die Indexsuche findet zusammenhängende Tokenfolgen; eine unabhängig implementierte direkte Referenz prüft alle zulässigen Startpositionen.

## Installation und Nutzung

Aus der Repositorywurzel in der vorhandenen Entwicklungsumgebung:

```sh
.venv/bin/python -m pip install -e .
.venv/bin/python -m positionsindex --corpus daten/beispiele/d0_d5 --phrase 'Verbindung zum Server' --method index
.venv/bin/python -m positionsindex --corpus daten/beispiele/d0_d5 --phrase 'a a' --method direct
.venv/bin/python -m pytest -q themen/04_positionsindex_phrasensuche/tests
.venv/bin/python -m pytest -q
```

Eine neue Umgebung entsteht mit `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements-dev.txt` und der Editable-Installation. Python ≥3.11; keine zusätzlichen Laufzeitabhängigkeiten. Die installierte CLI funktioniert auch außerhalb der Repositorywurzel. Kein manuell gesetzter Importpfad ist erforderlich. `--method index` ist Standard, `--method direct` wählt den Tokenvergleich.

Die Ausgabe ist eine JSON-Zeile. Das erste Beispiel liefert `"matches": {"D0.txt": [3], "D2.txt": [0]}`, das zweite `"matches": {"D5.txt": [0, 1]}`. Weitere Felder sind `mode`, `method`, `phrase` und `normalized_tokens`. Eingabefehler erzeugen eine erklärte stderr-Meldung und Exitcode 2; unbekannte gültige Phrasen ergeben `{}` bei Exitcode 0. Jeder CLI-Aufruf lädt, bereitet auf und baut gegebenenfalls einen Index. Seine gesamte Laufzeit entspricht deshalb nicht der isolierten Suchzeit der Versuche.

## Öffentliche Schnittstellen

```python
from gemeinsam import load_corpus, normalize_query, prepare_corpus
from positionsindex import build_positional_index, search_direct_phrase, search_index_phrase

corpus = prepare_corpus(load_corpus("daten/beispiele/d0_d5"))
tokens = normalize_query("Verbindung zum SERVER!", query_type="phrase")
index = build_positional_index(corpus)
assert tokens == ("verbindung", "zum", "server")
assert dict(index["verbindung"]) == {
    "D0.txt": (3,), "D1.txt": (2,), "D2.txt": (0,), "D3.txt": (2,),
}
assert search_direct_phrase(corpus, tokens) == {"D0.txt": [3], "D2.txt": [0]}
assert search_index_phrase(index, tokens) == {"D0.txt": [3], "D2.txt": [0]}
```

| Funktion oder Typ | Vertrag |
| --- | --- |
| `build_positional_index(corpus: Iterable[PreparedDocument]) -> PositionalIndex` | Eigener Aufbau; Token → Dokumentkennung → Tupel aller Vorkommenspositionen |
| `PositionalIndex` | Unveränderliche `Mapping[str, Mapping[str, tuple[int, ...]]]`, Erzeugung ausschließlich über die Aufbau-Funktion |
| `validate_phrase_tokens(phrase_tokens: Iterable[str]) -> tuple[str, ...]` | Nichtleere, bereits normalisierte Einzel-Tokens prüfen; Reihenfolge und Wiederholungen erhalten |
| `search_direct_phrase(corpus: Iterable[PreparedDocument], phrase_tokens: Iterable[str]) -> PhraseMatches` | Alle zulässigen Starts durch unmittelbar folgende Tokenvergleiche prüfen |
| `search_index_phrase(index: PositionalIndex, phrase_tokens: Iterable[str]) -> PhraseMatches` | Kandidatendokumente bestimmen, dann verschobene Positionslisten zusammenführen |
| `PhraseMatches` | Typalias `dict[str, list[int]]`; vollständige, frisch erzeugte Treffercontainer |

Die Kernanfragen erwarten Tokens aus der zentralen Aufbereitung, keinen Rohtext. `normalize_query(text, query_type="phrase")` bereitet die Anfrage vor. Ein Rohstring anstelle des Iterables, leere Anfragen, Nichtstrings und unnormalisierte Elemente wie `Fehler`, `Straße`, `a!` oder `a b` ergeben `QueryError(ValueError)`. Auch bei einem unbekannten ersten Token wird die gesamte Anfrage validiert. Einmalige Iterables sind zulässig. Listen oder Tupel sichern eine ausdrücklich festgelegte Phrasenreihenfolge.

Der Aufbau übernimmt die vorbereiteten Tokenfolgen und validiert wie Thema 02 Dokumenttypen, eindeutige Kennungen und jeden unterschiedlichen Tokenvertrag einmal mit der gemeinsamen `tokenize`-Funktion. Falsche Korpustypen, doppelte Kennungen und unnormalisierte vorbereitete Tokens ergeben `CorpusError(ValueError)`. Er unterstützt beliebige Eingabereihenfolge und einmalige Iteratoren. Direkte Abfragen prüfen Korpustypen und eindeutige Kennungen; die vorbereitete Tokenkonsistenz ist Vorbedingung von `prepare_corpus`. Kein Verfahren bereitet die aufbewahrten Rohtexte erneut auf.

## Semantik und unveränderliche Ergebnisse

Eine Phrase bezeichnet unmittelbar aufeinanderfolgende normalisierte Tokens im selben Dokument. Alle Startpositionen einschließlich überlappender Treffer werden geliefert. `a a a` enthält `a a` an `[0, 1]`, `a a a` an `[0]` und `a a a a` überhaupt nicht. Eine Einwortphrase liefert alle Wortvorkommen. Leere Korpora und Dokumente sind zulässig; gültige unbekannte Wörter oder fehlende zusammenhängende Folgen ergeben `{}`.

Dokumente und Anfragen verwenden unverändert **NFC → casefold → NFC** und Tokens aus Unicode-Buchstaben (`L*`) und Dezimalziffern (`Nd`). Umlaute und Stopwörter bleiben erhalten; `Straße` und `STRASSE` werden `strasse`, kanonisch zerlegte und zusammengesetzte `Äpfel` werden `äpfel`. Andere Zeichen trennen Tokens. `a. b`, `a—b` und `a_b` enthalten deshalb die Phrase `a b`. Satzzeichen und Satzgrenzen verhindern einen Treffer bei benachbarten Tokens nicht. Dokument A mit `a` und Dokument B mit `b` enthält zusammen niemals `a b`. Positionen sind Tokenindizes, keine Zeichenoffsets oder Satznummern.

AND nach `Verbindung` und `Server` trifft D0, D2 und D3. Die Phrase `Verbindung zum Server` trifft ausschließlich D0 an Position 3 und D2 an Position 0. In D3 stehen die Wörter in anderer Reihenfolge. Wiederholungen verändern Phrasen: `a a` ist eine andere Anfrage als `a`.

Die beiden Suchfunktionen liefern Dokumentkennungen lexikografisch sortiert und je Dokument aufsteigend sortierte, eindeutige Startlisten. Jeder Aufruf erzeugt einen neuen Dictionarycontainer und neue Ergebnislisten, auch bei Einwortphrasen. Die Positionslisten im Index sind Tupel; beide Mappingebenen sind unveränderliche Lesesichten privater finaler Dictionaries. Änderungen an Ausgaben, Kopien oder ursprünglichen Eingabecontainern ändern weder Index noch spätere Treffer. Der Indexzugriff `index[token]` ist ein exakter Schlüsselzugriff: ein unbekannter Token ergibt `KeyError`. Äußere Tokens haben keine zugesagte Iterationsreihenfolge; innere Dokumentkennungen sind sortiert.

## Algorithmus und kleine Herleitung

Der Aufbau traversiert jedes Dokument und fügt per `enumerate(doc.tokens)` jede tatsächliche Position genau einmal ein. Positionen entstehen aufsteigend und beginnen pro Dokument neu. Abschließende ID-Sortierung und Tupelbildung sichern die Invarianten auch bei unsortierten Korpora.

Die direkte Referenz läuft je Dokument über `0 … n−m` und vergleicht die `m` Phrasenelemente unmittelbar in dessen Tokenfolge. Ein Tokenunterschied beendet die Prüfung des aktuellen Starts. Sie benutzt weder Index noch Positionslisten.

Die Indexsuche nimmt für jedes unterschiedliche Phrasenwort dessen bereits sortierte Dokumentkeys. Die Kandidatenschnittmenge verwendet das eigene Zwei-Zeiger-Verfahren `boolesche_suche.intersect_sorted` aus Thema 03; Dokumentlisten werden stabil nach ihrer Länge geordnet. Danach werden **alle** Phrasenelemente einschließlich ihrer Wiederholungen mit ihrem ursprünglichen Offset geprüft. Pro Dokument werden ihre Positionslisten stabil nach Länge geordnet. Eine Ankerposition `p` am Offset `j` ergibt den Start `p−j`; negative Starts entfallen. Zwei Zeiger bilden nacheinander die Schnittmenge der Starts mit jeder entsprechend verschobenen Positionsliste. Fehlende Wörter und leere Zwischenergebnisse führen zum frühen Abbruch.

Beispiel D2 für `Verbindung zum Server`: Die Listen sind `verbindung:[0]`, `zum:[1]`, `server:[2]`. Nach Verschiebung um die Offsets 0, 1 und 2 bleibt jeweils `[0]`; damit ist 0 ein Phrasenstart. Für `a a` in D5 stehen dieselben Vorkommenslisten `[0,1,2]` an zwei verschiedenen Offsets. Die Schnittmenge von `[0,1,2]` und `[-1,0,1]` ergibt `[0,1]`. Ein einzelnes wiederholtes Wort darf deshalb nur für die Dokumentkandidaten dedupliziert werden.

## Prüfungen, Untersuchung und Übergabe

Feste, vorab angegebene Tokenfolgen und Startpositionen verankern D0–D5, Überlappungen, Reihenfolge, fehlende Wörter, Dokumentgrenzen, Satzzeichen, Unicode und leere Daten. Indexinvarianten rekonstruieren alle Tokens aus ihren Positionen; Unveränderlichkeit wird auf beiden Mappingebenen, den Positions-Tupeln und sämtlichen Ergebnislisten geprüft. Diagnosetests prüfen die Kandidatenreihenfolge und einen seltenen Anker innerhalb einer Phrase einschließlich der negativen Startgrenze.

Die Differentialtests erzeugen **300 kleine Korpora**, jeweils 100 für die Seeds **31, 20261006 und 9001**. Solltokens entstehen vor der Darstellung mit Groß-/Kleinschreibung und Satzzeichen. Danach werden erwartete Tokenfolgen, eine separate Fensteroracle, direkte Referenz und Indexsuche verglichen. Alle Vergleiche berücksichtigen sämtliche Positionen und enthalten wiederholte Tokens, unterschiedliche Dokumentlängen, vorhandene und fehlende Phrasen. Ein bekannter Realtextanfang und dessen vollständige Fenster der Längen 1, 2, 3 und 5 ergänzen die Nachweise. Die CLI wird ohne `PYTHONPATH` aus der Repositorywurzel und einem fremden Verzeichnis ausgeführt.

Die [Experimente](experimente/README.md) vergleichen invertierten Index und Positionsindex auf identischen vorbereiteten Korpora sowie direkte und indexbasierte Phrasenabfragen nach Länge, Häufigkeit, Vorkommen und Wiederholung. Aufbau, Suche und Speicherprofiling sind getrennte Läufe. Die gemessene Suche beinhaltet für beide Methoden die zentrale Rohtextnormalisierung der Query, Kernanfragevalidierung und vollständige Ergebnisbildung; Laden und Korpusaufbereitung liegen außerhalb der Suchintervalle. Die gelieferten historischen Archive werden nach der Integration von Thema 05 so erneut geprüft:

```sh
.venv/bin/python -m themen.04_positionsindex_phrasensuche.experimente.verify_results --pilot --archive-only
.venv/bin/python -m themen.04_positionsindex_phrasensuche.experimente.verify_results --archive-only
.venv/bin/python -m pytest -q themen/04_positionsindex_phrasensuche/tests themen/04_positionsindex_phrasensuche/experimente/tests
```

Der Standardverifier verlangt zusätzlich identische aktive Quelltext-Hashes, einschließlich `pyproject.toml`. Dessen Erweiterung um Thema 05 unterscheidet sich vom gemessenen Stand. `--archive-only` lässt diese Abweichung zu, prüft weiterhin sämtliche archivierten Quellen gegen ihre gespeicherten SHA-256-Werte und überprüft Tokenpläne und Phrasenergebnisse mit dem aktuellen Code. Die historischen Zeiten bleiben an ihren archivierten Quellstand gebunden; die Tests prüfen die aktuelle Funktionalität. Neue Messungen nach der [Versuchsanleitung](experimente/README.md) erfolgen wegen der festen Ausgabeziele in einer getrennten Arbeitskopie.

Thema 05 erhält dieselben vorbereiteten Dokumente, stabile importierbare APIs, vollständige Positionsresultate und reproduzierbare Rohwerte mit Daten-/Code- Prüfsummen. Unterschiedliche Funktionalität der beiden Indexarten bleibt bei Speicher- und Aufbauvergleichen ausdrücklich sichtbar. Eine universelle Laufzeitüberlegenheit wird nicht vorausgesetzt. Theorie und geprüfte Quellen: Der Gesamtprojektabschluss bleibt Gegenstand von Thema 05.
