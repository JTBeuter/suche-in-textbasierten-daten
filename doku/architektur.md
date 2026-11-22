# Gemeinsame Architektur und Schnittstellen

**Stand: 6. Oktober 2026, Themen 01 bis 04 implementiert. Nachgeführt am 14. Galloping Search und AND NOT in Thema 03, Gesamt-CLI-Optionen, Archivmodus der Prüfungen und der neue Realkorpus BGB. Die Suchsemantik ist dabei unverändert geblieben. Die folgenden Regeln sind Arbeitsannahmen der autorisierten Umsetzung, keine zusätzliche Teamabstimmung. Die vereinheitlichte Groß-/Kleinschreibung ist eine Nutzervorgabe. Themen 02–05 übernehmen diese Verträge und ändern sie nicht stillschweigend.

## Datenfluss und Module

```text
UTF-8-Dateien -> load_corpus -> RawDocument-Tupel
             -> prepare_corpus -> PreparedDocument-Tupel
                               -> direkte Wortsuche (erneuter Scan je Anfrage)
                               -> invertierter Index -> Einzelwort-/boolesche Mehrwortsuche
                                  (AND, OR und AND NOT mit eigenen Listenverfahren)
                               -> Positionsindex -> Phrasen mit Startpositionen
Korpus + Queries -> Validierung -> getrennte Messung -> CSV/Metadaten -> Diagramme
```

Python-Pakete werden über `pyproject.toml` installiert: `gemeinsam` liegt in `gemeinsam/src/gemeinsam/`, `direkte_suche` in `themen/01_textaufbereitung_direkte_suche/src/direkte_suche/`. `invertierter_index` liegt in `themen/02_invertierter_index_einzelwortsuche/src/invertierter_index/`. Die Fachordner mit führenden Ziffern sind keine Python-Paketnamen. Es gibt keine Laufzeitabhängigkeiten außerhalb der Standardbibliothek. `gemeinsam/__init__.py` ist ein offengelegter Importadapter für den normalen Editable-Install aus der Repositorywurzel; er ergänzt nur den Paketpfad zum Source-Verzeichnis. Ein installiertes Wheel verwendet das Source-Paket direkt. Ein manuell gesetzter `PYTHONPATH` ist nicht nötig.

## Dokument- und Ergebnisvertrag

| Begriff | Implementierter Vertrag |
| --- | --- |
| Dokumentkennung | `str`: relativer POSIX-Dateipfad einschließlich `.txt`, bezogen auf Korpuswurzel |
| Rohdokument | Unveränderlicher `RawDocument(document_id, source_path, raw_text)` |
| Vorbereitetes Dokument | Unveränderlicher `PreparedDocument(document_id, source_path, raw_text, tokens)` |
| Tokenfolge | `tuple[str, ...]`, neue Folge ohne Veränderung des Rohtexts |
| Tokenposition | `int`, Index von `enumerate(doc.tokens)`, ab null pro Dokument |
| Korpus | Tupel mit eindeutigen Kennungen; Loader/Aufbereitung sortieren nach Kennung |
| Worttreffer | Neue `list[str]`, lexikografisch sortierte, eindeutige Dokumentkennungen |
| Phrasentreffer | Neue `dict[str, list[int]]`, Kennungen lexikografisch eingefügt, Starts aufsteigend/eindeutig, keine veränderbaren Aliase |

Bei geladenen Dokumenten ist `source_path == document_id`. `[(d.document_id, d.source_path) for d in corpus]` ist die explizite Zuordnung. Experimente speichern sie mit Datei-SHA-256 im Datensatzmanifest. Bei manueller Dokumentkonstruktion kann die Herkunft abweichen; Kennungen bleiben eindeutig.

Hinzufügen/Entfernen anderer Dateien und Verschieben der Korpuswurzel ändern bestehende Kennungen nicht. Eine Umbenennung im Korpus erzeugt eine neue Kennung. Verschiedene Korpora dürfen gleiche relative Kennungen besitzen; `dataset_id` und Hashes unterscheiden ihre Daten. Inhaltsänderungen ändern die Kennung nicht, wohl aber den Hash. Ein Versuch verwendet einen festen Snapshot; laufende Indexaktualisierung gehört nicht zu Thema 01.

Der etablierte CLI-Einstieg `python -m direkte_suche` bietet neben `word` und `substring` den additiven Modus `index`. Nur dieser Zweig importiert das Indexpaket und führt getrennt Laden, Aufbereitung, Aufbau und Abfrage aus. `python -m invertierter_index` dient zusätzlich als fachliche Demonstration.

## Dateiladen und Fehler

`load_corpus(root)` akzeptiert ein Verzeichnis als `str` oder `Path`, lädt rekursiv Dateien mit Endung `.txt` und sortiert relative Pfade deterministisch. Andere normale Dateien sind ausdrücklich außerhalb des Filters; Quellenarchive und Manifeste gelangen nicht versehentlich in den Korpus. UTF-8 wird strikt decodiert. Leere Dateien und Verzeichnisse sind gültig. Dokumente werden nie verkettet. Symlinks im Baum werden abgewiesen: keine Aliasdateien oder fremden Dokumente werden stillschweigend aufgenommen.

Fehlende/nicht passende Pfade, Lesefehler, ungültige UTF-8-Bytes, unzulässige Typen und doppelte Kennungen ergeben erklärte Fehler. Es gibt kein scheinbar erfolgreiches Teilergebnis. Die CLI meldet Eingabefehler nach stderr mit Fehlerstatus. Ein unbekanntes gültiges Wort bleibt ein erfolgreicher Aufruf mit leerer Trefferliste. Die Loader-/Dokumentfehler sind `CorpusError(ValueError)`; Anfragefehler `QueryError(ValueError)`. Allgemeine Textfunktionen weisen falsche Texttypen mit `TypeError` zurück.

## Datensätze

| Datensatz | Pfad (Korpuswurzel für `load_corpus`) | Dokumentmodell | Rolle |
| --- | --- | --- | --- |
| Beispielkorpus D0–D5 | `daten/beispiele/d0_d5/` | sechs kurze Dateien `D0.txt` bis `D5.txt`, Erwartungen in `daten/beispiele/d0_d5_expected.json` | laufende Beispiele, Tests |
| BGB (`bgb-gesetze-im-internet-v1`) | `daten/real/bgb/dokumente/` | ein Paragraph je Datei `bgb_NNNN<suffix>.txt`, erste Zeile ist die Paragraphenüberschrift, danach der Normtext | Realkorpus aller neuen Messungen ab 14. Oktober 2026 |
| Kafka-Auszug | `daten/real/kafka_verwandlung/` | eine Datei mit acht Absätzen, 1.271 Tokens | nur Datengrundlage der gelieferten Läufe vom 6. Oktober 2026 |
| Generierte Korpora | temporär bzw. `<lauf>/datasets/` | Pflanzpläne der jeweiligen Reihe | kontrollierte Messreihen |

Beim BGB ist `dokumente/` die Korpuswurzel. Die Dokumentkennung ist daher der reine Dateiname, etwa `bgb_0001.txt` für § 1 oder `bgb_0312a.txt` für § 312a. Vierstellige Nummern mit führenden Nullen sorgen dafür, dass die Bytereihenfolge der Kennungen der Gesetzesreihenfolge folgt. `load_corpus("daten/real/bgb")` ist falsch, denn dann bekämen die Kennungen das Präfix `dokumente/` und Quellarchiv und Skripte lägen neben dem Korpus. Die Paragraphenbezeichnung steht nur im Dateinamen, Fußnoten und weggefallene Paragraphen sind nicht enthalten. Kennzahlen des Abrufstands: D = 2.486, N = 213.718, V = 11.398, P = 133.909. Herkunft, Umwandlungsregeln, Prüfsummen, kanonischer Korpushash und unabhängig berechnete Erwartungen stehen in `daten/real/bgb/manifest.json` und im [BGB-README](../daten/real/bgb/README.md). Weil ein Paragraph ein Dokument ist, findet die Phrasensuche keine Phrase über eine Paragraphengrenze hinweg. Das folgt aus der bestehenden Regel, dass Dokumentgrenzen nie überschritten werden. Die Aufbereitung (NFC → casefold → NFC, Runs aus L* und Nd) gilt für das BGB unverändert. Im Abrufstand kommen außer ASCII nur § Ä Ö Ü ß ä ö ü „ “ vor. Die Gesamtmessung erkennt Mehrdokumentkorpora am Manifestfeld `corpus_root`.

## Zentrale Aufbereitung

`normalize_text(text)` führt **NFC → casefold() → NFC** aus. Der erste Schritt vereinheitlicht kanonische Darstellungen, der zweite die Groß-/Kleinschreibung, der dritte komponiert durch Casefold entstandene Folgen erneut. Die wiederholte Anwendung ist in den geprüften Fällen stabil.

`tokenize(text)` bildet zusammenhängende Folgen von Unicode-Buchstaben (Kategorie `L*`) und Dezimalziffern (`Nd`). Alle übrigen Zeichen trennen: Satzzeichen, Leerraum, Zeilenumbrüche, Bindestriche, Unterstriche und nach NFC verbleibende kombinierende Zeichen. Beispielsweise trennt ein nicht komponierbarer Akzent zwischen `x` und `y` diese in zwei Tokens; `İ` ergibt `i` plus ein trennendes Punktzeichen. Andere Unicode-Zahlen (`Nl`/`No`, etwa `Ⅳ` oder `²`) zählen nicht als Dezimalziffern. Der konkrete Unicode-Datenstand der Python-Version gehört in die Messmetadaten. Dies ist eine vereinfachte Tokenregel und keine allgemeine sprachwissenschaftliche Wortsegmentierung.

Umlaute bleiben erhalten; `Äpfel` und seine kanonisch zerlegte Darstellung werden `äpfel`, nicht `aepfel`. `Straße` und `STRASSE` werden `strasse`. Stopwörter bleiben, Stemming fehlt. `Fehler-Code_42` ergibt `fehler`, `code`, `42`; `Serverfehler` bleibt ein Token und ist kein Worttreffer für `Fehler`. Dokumente und Anfragen nutzen dieselben Funktionen.

Eine Position ist ein Tokenindex, kein Zeichenoffset und keine Satznummer. `Server. Fehler` enthält benachbarte Tokens: Eine spätere Phrase `Server Fehler` darf die Satzgrenze überschreiten. End-/Anfangstokens zweier Dokumente bilden niemals zusammen eine Phrase.

## Importierbare API

```python
from gemeinsam import (
    RawDocument, PreparedDocument, CorpusError, QueryError,
    load_corpus, prepare_corpus, normalize_text, tokenize, normalize_query,
)
from direkte_suche import search_direct_word, search_direct_substring

raw = load_corpus("daten/beispiele/d0_d5")
corpus = prepare_corpus(raw)
query_tokens = normalize_query("FEHLER", query_type="word")  # ("fehler",)
hits = search_direct_word(corpus, "FEHLER")  # ["D0.txt", "D2.txt"]
```

`normalize_query(query, query_type="word")` verlangt genau ein Token; `query_type="phrase"` mindestens eines. Ungültige Anfragen erzeugen `QueryError`. Die direkte Wortsuche scannt die vorbereiteten Tokenfolgen sequenziell und bricht pro Dokument nach dem ersten Vorkommen ab. Keine vorbereiteten Wortmengen oder Token-zu-Dokument-Listen. Die Ergebnisbildung inklusive Sortierung gehört zur Abfragezeit. Laden und Aufbereitung erfolgen einmal vor der Abfragefolge.

Teilzeichensuche normalisiert Rohtext und Anfrage und sucht eine Zeichenfolge. Für `Fehler` trifft sie auch `D1.txt` mit `Serverfehler`. Sie ist eine getrennte Demonstration, keine Wortbaseline. Die gemeinsame Messpipeline und der Generator liegen unter `gemeinsam`; Schema und Messgrenzen stehen im [messkonzept.md](messkonzept.md).

## Übergabe

Thema 02 erhält das vorbereitete Tupel und `search_direct_word` als Referenz. Thema 04 erhält unveränderte Tokens und feste Beispiel-Phrasenstarts in `daten/beispiele/d0_d5_expected.json`. Thema 05 erhält Datensatzkennungen, Hashes, Querymanifeste und getrennte Kosten.

## Invertierter Index und Übergabe aus Thema 02

```python
from invertierter_index import build_inverted_index, search_index_word, get_postings

index = build_inverted_index(corpus)
hits = search_index_word(index, "FEHLER!")  # neue Liste: D0.txt und D2.txt
(token,) = normalize_query("Fehler")
postings = get_postings(index, token)  # immutable Tupel ohne Kopie
```

`InvertedIndex` ist eine unveränderliche `Mapping[str, tuple[str, ...]]`. Erzeugung ausschließlich über `build_inverted_index`. Der Aufbau erhält `Iterable[PreparedDocument]`, akzeptiert unsortierte/einmalige Iteratoren und weist falsche Elemente, doppelte IDs und unnormalisierte Tokens mit `CorpusError` zurück. Er übernimmt die vorbereitete Tokenfolge und prüft jedes verschiedene Token einmal mit der gemeinsamen Tokenisierung. Er bereitet Rohtexte nicht erneut auf; deren Tokenkonsistenz ist Vorbedingung der Vorstufe.

Dokumentweise Duplikatvermeidung, Wörterbuchaufbau und abschließende Sortierung erzeugen genau eine lexikografisch sortierte ID je Token/Dokumentvorkommen. Die privaten finalen Dictionarywerte sind Tupel, der Dictionaryzugriff eine `MappingProxyType`-Lesesicht. Leere Dokumente/Korpora erzeugen keine Einträge. Dictionaryschlüssel haben keine zugesagte Iterationsreihenfolge; Trefferlisten haben die festgelegte ID-Reihenfolge. Positionen werden nicht gespeichert.

Die Wortsuche akzeptiert Rohtext mit gemeinsamer Anfrageaufbereitung und gibt eine vollständig materialisierte unabhängige `list[str]` zurück. `get_postings` nimmt nur bereits normalisierte Tokens; eine Vertragsverletzung ist `QueryError`, ein unbekannter gültiger Schlüssel ergibt `()`. Mappingzugriff mit `index[token]` ist ein exakter Schlüsselzugriff und ergibt für unbekannte Tokens `KeyError`. Abfragen haben weder Korpuszugriff noch versteckten Neuaufbau oder globalen Cache. Thema 03 kann Tupel ohne Veränderung/kopierende Wortabfrage kombinieren.

Thema 05 erhält das bestehende Zeit-CSV-Schema sowie separate Speicherdaten, N/D/V/P, Queryvorkommen/df, Dokumentlängen und Daten-/Codeprüfsummen.

## Boolesche Suche aus Thema 03

`boolesche_suche` übernimmt gemeinsame Dokumente, zentrale Anfrageaufbereitung und `InvertedIndex` aus den geprüften Vorstufen. Die API hat `search_direct_boolean(corpus, terms, operator, exclude=None)` und `search_index_boolean(index, terms, operator, variant="input_order", exclude=None)`. Begriffe sind ein Iterable von Rohwörtern; Operatoren exakte Strings AND/OR. `normalize_boolean_query(terms, operator, exclude=None)` erzeugt eine immutable `BooleanQuery` mit `terms`, `operator`, `original_term_count`, `effective_term_count` und `exclude` (normalisiertes NOT-Wort oder `None`). Die Normalisierung jedes Wortes verwendet `normalize_query`; Duplikate entfallen stabil nach Normalisierung. Leere/ungültige Anfragen ergeben `QueryError`.

AND bietet drei Varianten, zusammengefasst in `VARIANTS`:

| Variante | Reihenfolge der Postinglisten | Schnitt |
| --- | --- | --- |
| `input_order` | effektive Eingabereihenfolge | `intersect_sorted` (Zwei-Zeiger) |
| `shortest_first` | stabil aufsteigend nach Länge (Gleichstand: erste Eingabeposition) | `intersect_sorted` |
| `galloping` | wie `shortest_first` | `intersect_galloping` (Galloping Search) |

OR bietet ausschließlich `input_order` und vereinigt mit `union_sorted`. OR wird bewusst nicht optimiert. Unbekanntes Wort: AND leer, OR kein Beitrag. Ein effektives Wort entspricht der Wortsuche. Jede Variante liefert neue sortierte `list[str]` ohne Duplikate. Alle Listenverfahren arbeiten auf sortierten eindeutigen Sequenzen mit Zeigern, ohne Mengenoperationen und ohne die Eingaben zu verändern. Die Sortiervorbedingung sichert der Indexaufbau, interne Postingtupel bleiben erhalten.

`intersect_galloping(left, right)` nimmt die Kennungen der kürzeren Folge (bei gleicher Länge aus `left`) und sucht jede in der längeren Folge ab der aktuellen Position mit Sprüngen der Weite 1, 2, 4, 8 und so weiter, danach mit Binärsuche im letzten Sprungintervall. Die Position wandert nur vorwärts. Die Schranke ist O(a·log(b/a)) für Listenlängen a ≤ b. `difference_sorted(left, right)` liefert in O(len(left) + len(right)) die Kennungen aus `left`, die in `right` fehlen.

AND NOT hat beliebig viele Pflichtwörter und genau ein ausgeschlossenes Wort (`exclude`, nur mit `AND`). Das NOT-Wort wird wie die Pflichtwörter normalisiert und muss genau ein Token ergeben. Die Indexsuche schneidet zuerst die Pflichtwörter in der gewählten Variante und zieht danach die Postingliste des NOT-Worts mit `difference_sorted` ab. Bei leerem Schnitt entfällt dieser Schritt. Ist das NOT-Wort zugleich Pflichtwort, ist das Ergebnis leer. NOT ohne Pflichtwort ist nicht vorgesehen, weil es eine Liste aller Dokumente bräuchte. Es gibt keinen Abfrageparser. Ein im Suchtext geschriebenes `AND` oder `NOT` bleibt ein gewöhnliches Suchwort.

Die direkte Referenz durchläuft Tokens, mit kleiner Anfragemenge und bei AND einer dokumentweisen Fundmenge. Sie stoppt beim vollständigen AND-/ersten OR-Treffer. Mit `exclude` bricht sie ein Dokument nur beim NOT-Wort ab, denn nach dem Fund aller Pflichtwörter muss der Rest des Dokuments noch auf das NOT-Wort geprüft werden. Keine Dokumentwortsets, kein Postingzugriff. Die Fach-CLI `python -m boolesche_suche` hat `--variant input_order|shortest_first|galloping` und `--exclude WORT` (nur mit `--operator AND`, beide Methoden). Nur mit `--exclude` enthält die JSON-Ausgabe zusätzlich `exclude` und `normalized_exclude`, ohne den Schalter bleibt sie unverändert. `--boolean` integriert den Paketparser additiv in `direkte_suche`, frühere Zweige werden zusätzlich gegen hashgesicherte Archive per AST geprüft. Einzelheiten und Fehlerfälle: [README 03](../themen/03_boolesche_mehrwortsuche/README.md).

## Positionsindex und Phrasensuche aus Thema 04

Das additive Paket `positionsindex` liegt unter `themen/04_positionsindex_phrasensuche/src/positionsindex/`. Vorhandene APIs, die CLI aus 01–03 und die gemeinsame Messpipeline bleiben erhalten.

```python
from gemeinsam import load_corpus, prepare_corpus, normalize_query
from positionsindex import build_positional_index, search_direct_phrase, search_index_phrase

corpus = prepare_corpus(load_corpus("daten/beispiele/d0_d5"))
phrase_tokens = normalize_query("Verbindung zum Server", "phrase")
index = build_positional_index(corpus)
assert search_index_phrase(index, phrase_tokens) == {"D0.txt": [3], "D2.txt": [0]}
assert search_direct_phrase(corpus, phrase_tokens) == {"D0.txt": [3], "D2.txt": [0]}
```

`PositionalIndex` ist eine unveränderliche `Mapping[str, Mapping[str, tuple[int, ...]]]`. Aufbau ausschließlich durch `build_positional_index(Iterable[PreparedDocument])`: Typen und ID-Eindeutigkeit prüfen, jedes unterschiedliche Token einmal mit zentraler Tokenisierung prüfen, Dokumenttokens enumerieren, innere Dokumentkennungen sortieren und beide Mappingebenen mit privaten Dictionaries/MappingProxyType einfrieren. Die Positionslisten entstehen pro Dokument aufsteigend und eindeutig; der Rohtext wird nicht erneut aufbereitet. Beliebige Dokumentreihenfolge und einmalig konsumierbare Iteratoren sind zulässig.

Die beiden Suchfunktionen erhalten `phrase_tokens: Iterable[str]`. Diese Kerneingabe muss bereits aus normalisierten ganzen Tokens bestehen. Reihenfolge und Wiederholungen bleiben erhalten. Rohstrings als Iterable, leere Folgen, Nichtstrings, Leer-/Mehrworttokens und unnormalisierte Tokens ergeben `QueryError`, auch wenn vorher ein unbekanntes Wort steht. Rohtextanfragen werden mit `normalize_query(text, "phrase")` vorbereitet. Die CLI übernimmt diesen Schritt; beide Messwrapper zählen ihn zur Abfragezeit.

Die direkte Referenz prüft zulässige Startpositionen mit unmittelbar folgenden Tokenvergleichen. Die Indexsuche schneidet Dokumentlisten unterschiedlicher Phrasenwörter mit `intersect_sorted` aus 03. Je Kandidat dienen die kürzesten Positionslisten als Anker (stabiler Gleichstand: erster Phraseoffset). Ankerposition p bei Offset j ergibt Start p−j; negative Starts entfallen. Zwei Zeiger vergleichen die übrigen Listen nach Verschiebung um ihren Phraseoffset, auch bei wiederholten Wörtern. Fehlende Wörter, leere Kandidaten und leere Zwischenresultate erlauben einen frühen Abbruch. Ein vorhandenes letztes Phrasenelement sichert das Ende innerhalb derselben Dokumenttokenfolge.

Das Ergebnis `dict[str, list[int]]` enthält lexikografisch eingefügte eindeutige Kennungen mit aufsteigenden eindeutigen Startpositionen, inklusive überlappender Treffer. Einwortphrasen liefern sämtliche Vorkommen. Alle veränderlichen Ergebnislisten sind neu; Index und Korpus verändern sich auch bei wiederholten Abfragen und Ausgabemutationen nicht. Leere gültige Korpora und unbekannte gültige Phrasen ergeben `{}`. Mappingzugriff selbst bleibt exakter Schlüsselzugriff mit `KeyError` bei fehlendem Token.

Bedienung: `python -m positionsindex --corpus daten/beispiele/d0_d5 --phrase "Verbindung zum Server" --method index` (nach Installation). `--method direct` wählt die unabhängige Referenz. Fehlerstatus ist 2; erfolgreiche leere Treffer haben Status 0. Der CLI-Gesamtaufruf enthält Laden/Aufbereitung und gegebenenfalls Aufbau; er bezeichnet keine isolierte Suchzeit. Nachweise und Übergabe:

## Gesamtintegration Thema 05

Das zusätzliche installierbare Paket `experimentelle_analyse` liegt in `themen/05_experimentelle_analyse/src/experimentelle_analyse/`. Es delegiert Suchalgorithmen an die APIs aus 01–04. `search --corpus --kind --method --query` liefert JSON. `run --config --output`, `generate --config --output`, `verify --input` und `analyse --input --output` sind getrennte Befehle. Fach-CLIs bleiben kompatibel. Die Optionen seit dem 14. Oktober 2026 stehen im Unterabschnitt „Gesamt-CLI und Archivmodus“.

Der Datentyp bleibt `PreparedDocument` mit stringbasierten relativen Dateikennungen; es gibt keine neue int-ID-Semantik. Boolean-CLI-Queries sind Tokenfolgen, der Operator kommt ausschließlich aus `--kind`. Rohtextanfragen werden innerhalb der Abfrage normalisiert; Wort/Phrase erhalten denselben Rohtext, boolesche Begriffe die einzelnen großgeschriebenen Rohwörter. Der CLI-Adapter ist außerhalb der Messung.

`datasets.build_datasets(config,output)` persistiert Manifeste, Abfragen und portable Korpuskopien. `pipeline.run_experiment(config_path,output)` prüft volle Solltokenfolgen, Indexstrukturen und sämtliche Ergebnisse. `verify.verify_run(directory)` prüft Quellarchive, Byte-Reproduktion, API-Ergebnisse, Schemas, Einheiten, vollständige Wiederholungen, deterministische Reihenfolge, kalibrierte Q-Werte und getrennte Profilingprozesse. `analysis.analyse(input_dir,output_dir)` verweigert fehlerhafte Läufe und erzeugt Zusammenfassungen/Modelle/Diagramme mit SHA-Zuordnung.

Dateizugriff, gemeinsame Aufbereitung, Kernalgorithmen, Messung und Ausgabe bleiben getrennt. Neue Phasen-/Queryrohwerte verwenden exakt `gemeinsam.messung.CSV_FIELDS`. `batches.csv` enthält ganze Profilfolgen; `totals.csv` tatsächlich gemessene Gesamtabläufe. Beide enthalten `elapsed_ns` und explizit `unit=ns`. Speicherwerte heißen `retained_traced_bytes`, `peak_traced_bytes`, `transient_peak_bytes` und `unit=bytes`. `correctness.json` ordnet die Basisprüfungen jeder Query/Variante zu; sämtliche zusätzlichen Profil-/Gesamtresultate werden ebenfalls außerhalb des Timers vollständig überprüft.

### Gesamt-CLI und Archivmodus (Stand 14. Oktober 2026)

| Befehl | Optionen | Bedeutung |
| --- | --- | --- |
| `search` | `--corpus PFAD --kind word\|and\|or\|phrase --method direct\|index --query TEXT` | wie bisher |
| `search` | `--variant basic\|shortest_first\|galloping` | `basic` ist die Eingabereihenfolge (`input_order`), die beiden anderen nur mit `--kind and --method index` |
| `search` | `--exclude WORT` | AND NOT mit genau einem ausgeschlossenen Wort, nur mit `--kind and`, beide Methoden, Ausgabe zusätzlich mit `exclude` und `normalized_exclude` |
| `run` | `--config DATEI --output ORDNER` | Ziel muss leer sein, Hauptläufe (`"mode": "main"`) brechen ohne `PYTHONHASHSEED=0` vor jeder Ausgabe ab |
| `generate` | `--config DATEI --output ORDNER` | unverändert |
| `verify` | `--input ORDNER [--archive-only]` | streng: aktiver Code muss der Messfassung gleichen. Mit `--archive-only`: Quellarchiv `code_source/` gegen die gespeicherten Hashes, Ergebnis `verified_archive_only` mit Liste der abweichenden aktiven Dateien |
| `analyse` | `--input ORDNER --output ORDNER [--archive-only]` | prüft wie `verify` und verweigert ein Ziel, das schon Auswertungsdateien enthält |

Unzulässige Kombinationen, etwa `galloping` mit `--method direct` oder `--exclude` mit `--kind or`, enden mit Exit 2 und einer Erklärung auf stderr. In beiden Prüfmodi bleiben Rohwerte, Reihenfolgen, Statistik, Daten- und Anfragereproduktion, Speicherprozesse und die Suchwiederholung mit dem aktiven Code geprüft. Die Python-API dazu heißt `verify_run(pfad, archive_only=True)` und `analyse(eingabe, ausgabe, archive_only=True)`.

Erweiterungen der Pipeline für den BGB-Realteil: `datasets.py` akzeptiert Mehrdokumentkorpora (Manifest mit `corpus_root`) und prüft dafür Quellarchiv, Abrufprotokoll, Größe und SHA-256 jedes Dokuments, den kanonischen Korpushash, die exakte Dateiliste, eine Offline-Neuerzeugung mit dem gepinnten Umwandlungsskript und eine unabhängige Tokenisierung gegen die Manifesterwartungen. Feste Profilanfragen stehen in der Konfiguration (Abfragegenerator `05-queries-fixed-v1`) und brauchen je mindestens eine unabhängige Erwartung aus Manifest oder Anfragevorschlägen. Die Metadaten erhalten unter `background_load` Momentaufnahmen von Lastmittel und den fünf CPU-stärksten Prozessen, nur zwischen den Zeitintervallen. Mit `"amortisation_table": "abschnitt_3_6"` schreibt `analyse` zusätzlich `amortisation.json` und `amortisation.csv` mit t_Aufbau, t_direkt, t_index, q* = t_Aufbau/(t_direkt − t_index), ⌈q*⌉ oder „nie“ (`costs.amortisation_3_6`). Alte Konfigurationen ohne dieses Feld bleiben gültig. `provenance.environment()` liest `/proc/cpuinfo` nur, wenn die Datei existiert, sonst gilt `platform.processor()`.
