# Gemeinsame Bausteine

Die implementierten Python-Pakete heißen `gemeinsam`, `direkte_suche` und
`invertierter_index`.
`pyproject.toml` ordnet sie ihren fachlichen Quellverzeichnissen zu. Python
**ab 3.11** ist erforderlich; die Suchimplementierung braucht nur die
Standardbibliothek. Vom Repository-Verzeichnis aus:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -e .
.venv/bin/python -m pytest -q
```

`requirements-dev.txt` legt pytest 8.3.5 und Matplotlib 3.10.1 fest. Die
vollständigen verwendeten Paketversionen stehen bei den Experimentmetadaten.
Der dokumentierte Testaufruf umfasst Fachtests und Experimente. Er benötigt
kein `PYTHONPATH`. `gemeinsam/__init__.py` ist ein offener Importadapter für
den gleichnamigen fachlichen Repositoryordner: Er ergänzt den Paketpfad um
`src/gemeinsam`, damit der normale editable-Import auch aus dem Repository
funktioniert. Installierte Wheels importieren direkt das Quellpaket.

## Datenvertrag

| Typ oder Begriff | Festlegung |
| --- | --- |
| `RawDocument` | Unveränderliche Dataclass: `document_id: str`, `source_path: str`, `raw_text: str` |
| `PreparedDocument` | Dieselben Felder plus unveränderliches `tokens: tuple[str, ...]` |
| Dokumentkennung | Relativer POSIX-Dateipfad einschließlich `.txt`, z. B. `teil/D0.txt` |
| Herkunft | `load_corpus` setzt `source_path` auf denselben relativen Pfad; zusammen mit der Korpuswurzel ergibt sich die Quelldatei |
| Tokenposition | Index in `tokens`, ab null und für jedes Dokument neu |
| Worttreffer | `list[str]`, lexikografisch sortiert und ohne doppelte Kennungen |

Neue oder entfernte Dateien verändern die Kennungen bestehender Dateien
nicht. Eine Umbenennung erzeugt eine andere Kennung. Die ID garantiert keine
unveränderten Dateiinhalte; dafür dienen Manifest und Prüfsummen eines
dokumentierten Datensatzes. Der Loader erhält den Rohtext einschließlich
Zeilenenden. Aufbereitung erzeugt zusätzliche Tokens und ändert ihn nicht.

## Öffentliche Funktionen

```python
from gemeinsam import (
    CorpusError, QueryError, RawDocument, PreparedDocument,
    load_corpus, prepare_corpus, normalize_text, tokenize, normalize_query,
)

raw = load_corpus("daten/beispiele/d0_d5")
prepared = prepare_corpus(raw)
```

| Funktion | Vertrag |
| --- | --- |
| `load_corpus(root: str \| Path) -> tuple[RawDocument, ...]` | Rekursiv ausschließlich die exakte Endung `.txt`, striktes UTF-8, sortierte relative Pfade |
| `prepare_corpus(raw_documents: Iterable[RawDocument]) -> tuple[PreparedDocument, ...]` | Dokumenttypen und eindeutige IDs prüfen, IDs sortieren, Texte tokenisieren |
| `normalize_text(text: str) -> str` | NFC → `casefold()` → NFC |
| `tokenize(text: str) -> tuple[str, ...]` | Normalisieren; maximale Folgen aus Unicode-Buchstaben `L*` und Dezimalziffern `Nd` |
| `normalize_query(query: str, query_type: str = "word") -> tuple[str, ...]` | `word`: genau ein Token; `phrase`: mindestens ein Token; andere Sucharten ungültig |

Leere Verzeichnisse und Dateien sind gültig. Fehlende Wurzeln, Dateiwurzeln,
ungültiges UTF-8, nicht reguläre `.txt`-Dateien und Dateisystemfehler brechen
mit `CorpusError(ValueError)` und einer Erklärung ab. Die ursprüngliche
Codierungs- oder Betriebssystemausnahme bleibt als `__cause__` erhalten.
Symbolische Links als Wurzel oder irgendwo im durchlaufenen Baum werden
abgewiesen, einschließlich Links auf Unterverzeichnisse und ignorierte
Dateiendungen. Nichts wird still über solche Links ausgelassen oder verfolgt.

Manuell erzeugte Dokumente müssen eine gültige ID, einen nichtleeren
Herkunftsstring und einen Rohtext vom Typ `str` besitzen. `prepare_corpus`
weist doppelte Kennungen und andere Elementtypen ab. Die Suchfunktionen
setzen diesen einmalig geprüften Korpus voraus. Sie führen keine erneute
Tokenisierung oder vollständige Konsistenzprüfung pro Wortanfrage durch.

## Verbindliche Textregeln von Thema 01

NFC vor `casefold()` vereinheitlicht kanonisch unterschiedliche Schreibweisen;
das abschließende NFC stellt die normalisierte Form nach den durch
`casefold()` erzeugten Zeichen wieder her. Wiederholte Anwendung bleibt
stabil. `Straße` und `STRASSE` ergeben `strasse`; `Äpfel` und `A\u0308pfel`
ergeben `äpfel`. `ä` bleibt von `a` und `ae` verschieden. Stopwörter bleiben
erhalten, es gibt kein Stemming.

Satzzeichen, Leerraum, Bindestriche, Unterstriche und alle übrigen Kategorien
trennen Tokens. Verbleibende kombinierende Zeichen (`M*`) sind ebenfalls
Trenner: `İx` wird durch `casefold()` zu `i\u0307x` und ergibt `("i", "x")`.
Zahlen aus `Nd` bilden Tokens; hochgestellte `²` (`No`) und römische `Ⅲ`
(`Nl`) sind Trenner. Diese präzise Unicode-Regel hängt von der Unicode-Version
der eingesetzten Python-Laufzeit ab; die Experimente erfassen diese Version.

Satzgrenzen werden nicht gespeichert. Deshalb hat `Server. Fehler` die
benachbarten Tokens `("server", "fehler")`. Spätere Tokenphrasen dürfen
diese Satzgrenze überschreiten, niemals eine Dokumentgrenze. Doppelte
Tokens werden erhalten, damit alle überlappenden Phrasenpositionen prüfbar
bleiben. Die Handfixtures in `daten/beispiele/d0_d5_expected.json` enthalten
dafür bereits Sollpositionen; Thema 01 implementiert noch keine Phrasensuche.

Die fachlichen Entscheidungen und Messgrenzen stehen zusätzlich in
[Architektur](../doku/architektur.md) und [Messkonzept](../doku/messkonzept.md).
Weitere gemeinsame Mess- und Generatorbausteine werden direkt als
`gemeinsam.messung` und `gemeinsam.datengenerator` importiert.
