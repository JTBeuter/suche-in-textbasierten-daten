# Messkonzept

**Stand: 6. Oktober 2026, nachgeführt am 14. Oktober 2026.** Die erste Pipeline und Untersuchung für Thema 01 sind implementiert. Thema 02 ergänzt Indexaufbau, Einzelwortvergleich und separate Speichermessung. Mehrwortreihen aus 03 sind umgesetzt; Thema 04 ergänzt Phrasen- und Positionsspeicherreihen. Die Amortisationsanalyse bleibt Thema 05.

Die Abschnitte zu den Reihen 01 bis 05 beschreiben die **gelieferten Läufe vom 6. Oktober 2026** mit dem Kafka-Auszug als Realtext. Die Überarbeitung vom 14. Oktober 2026 hat Reihe 01 neu gemessen und die Läufe 02b, 03b sowie BGB-Realteile der Reihen 02 bis 05 ergänzt. Diese neuen Läufe, ihre gemeinsamen Regeln und der Archivmodus für die gelieferten Läufe stehen im Abschnitt [Überarbeitung vom 14. Oktober 2026](#überarbeitung-vom-14-oktober-2026). Prüfergebnisse:

## Vergleichbarkeit und Messgrenzen

Alle Verfahren erhalten denselben vorbereiteten Korpus, dieselben Kennungen, Aufbereitungsregeln und semantisch gleichwertige Anfragen. Die Ganzwortreferenz scannt Tokenfolgen; die Teilzeichendemonstration gehört nicht in diesen Vergleich. Vor der Messung werden bei generierten Korpora ganze Tokenfolgen und Treffer gegen unabhängig festgelegte Erwartungen geprüft. Beim realen Auszug werden der feste Tokenanfang, die Tokenzahl, die Abfragevorkommen und sämtliche Positionen der drei Versuchswörter geprüft; nicht jedes reale Token besitzt eine handgeschriebene Erwartung. Beim BGB der neuen Läufe prüft jeder Lauf alle 2.486 Dateien gegen das Manifest (Bytes, SHA-256, kanonischer Korpushash) und vergleicht die produktive Aufbereitung Dokument für Dokument mit einer unabhängigen Regex-Tokenisierung. Die Anfrageerwartungen stammen aus `manifest.json` und `anfragevorschlaege.json`. Fehlgeschlagene Ergebnisprüfungen brechen die Reihe ab.

| Phase | Gemessener Abschnitt | Einheit/Rückgabe |
| --- | --- | --- |
| `load` | Ganze `load_corpus`: Traversieren, Pfadsortieren, Bytezugriff, striktes UTF-8 und Dokumentobjekte | `load_ms`; vollständige Rohdokumente |
| `preparation` | Ganze `prepare_corpus`: Validierung, ID-Sortierung, NFC/Casefold/NFC, Tokenisierung, vorbereitete Objekte | `preparation_ms`; vollständiges vorbereitetes Tupel |
| `build` | Ganze `build_inverted_index`: vorbereitete Dokumenttypen/ID-Eindeutigkeit/Tokenverträge prüfen, dokumentweise deduplizieren, Postings erzeugen, sortieren und einfrieren | `build_ms`; Thema 01 leer |
| `query` | Öffentliche Suchfunktion: gemeinsame Anfragevalidierung, Tokenvergleich, komplette sortierte eindeutige Trefferliste | `query_ms`; Zeit pro Anfrage eines Blocks |

Keine Dateiausgabe, Terminalausgabe, Ergebnisprüfung, Zählung oder Speicheranalyse im Zeitintervall. Der Blocktreiber hält sämtliche Ergebnisse bis zur anschließenden Prüfung: Listen-/Schleifenaufwand ist enthalten und explizit dokumentiert. Anfrageaufbereitung ist enthalten; Korpusaufbereitung erfolgt vor der Abfragefolge. Laden wird nach bereits erfolgter Validierung mehrfach wiederholt; der Betriebssystem- Dateicache wird nicht geleert. Das ist ein warmer Ladeversuch, keine Messung kalter Festplattenzugriffe. Speicher wird für Thema 01 nicht gemessen.

## Gemeinsame ausführbare Pipeline

`gemeinsam.datengenerator.generate_corpus` erzeugt deterministische Textdateien und Erwartungen aus einem Pflanzplan. `gemeinsam.messung` enthält `MeasurementPlan`, `QuerySpec`, `measure_phase`, `measure_queries`, `write_measurements` und `summarize_measurements`. Neue Themen verwenden diese Messgrenzen und ergänzen eigene Suchoperationen und Erwartungsprüfungen.

Zeitmessung verwendet `time.perf_counter_ns()`; die rohe Blockdifferenz bleibt als ganzzahliges `elapsed_ns` erhalten. Laut [Python-Dokumentation](https://docs.python.org/3.11/library/time.html#time.perf_counter_ns) eignet sich dieser Zähler für kurze Intervalle und liefert Nanosekundenwerte; die Einheit allein sagt nichts über tatsächliche Auflösung oder Messgenauigkeit. Die Versuchsreihe verwendet fünf Aufwärmläufe und 20 gemessene Wiederholungen. Kurze Anfragen werden in Blöcken von zehn identischen Aufrufen gemessen; `query_ms = elapsed_ns / (1_000_000 * block_size)`. Die Anfrageblockreihenfolge wird je Wiederholung mit festem Seed gemischt. Korpusgrößen werden aufsteigend untersucht, nicht randomisiert.

Die Zusammenfassung verwendet Median und inklusive Quartile `statistics.quantiles(..., n=4, method="inclusive")`; IQR ist Q3−Q1. Ein Queryblock ist eine Stichprobe; zehn darin enthaltene Aufrufe sind keine zehn unabhängigen Wiederholungen. Quartilsbereiche sind keine Konfidenzintervalle. Die Methodik dokumentiert Hintergrundlast, Hardware, Laufzeitumgebung und Cache.

## Messformat (Version 01)

CSV-Felder in `gemeinsam.messung.CSV_FIELDS`:

| Felder | Bedeutung |
| --- | --- |
| `run_id`, `git_commit`, `seed` | Versuch und reproduzierbare Code-/Generatorzuordnung; Codehashes zusätzlich im JSON |
| `dataset_id`, `document_count`, `text_bytes`, `token_count` | Identität und Umfang; Dateien/Hashes/Mapping im JSON |
| `algorithm`, `phase`, `query_id`, `query_type`, `query_text` | Verfahren, Kostenphase, Anfrage; Typ `word`, Häufigkeitsklasse separat |
| `repeat`, `order_index`, `block_size`, `elapsed_ns` | Messwiederholung, deterministische Reihenfolge, Block und Rohzeit |
| `load_ms`, `preparation_ms`, `build_ms`, `query_ms` | Getrennte Kosten, jeweils nur zutreffende Phase gefüllt |
| `index_bytes`, `peak_memory_bytes` | Für spätere separate Speicherläufe; Thema 01 leer |
| `hit_count`, `correct` | Zahl der Dokumenttreffer, außerhalb des Zeitabschnitts geprüft |

Nicht zutreffende Werte bleiben leer; sie werden nicht durch fiktive Nullen ersetzt. JSON enthält Parameter, Queryvorkommen, Dateien, relative IDs und SHA-256, Gesamt-Datensatzhash, Softwarestände, Git-Commit, Dirty-Status und Hashes des tatsächlich gemessenen Codes. Die Zusammenfassung und Abbildungen leiten sich aus `raw.csv` ab. Rein beschreibende Aufzeichnungskorrekturen nach Messung sind mit ursprünglichem und korrigiertem Codehash zu kennzeichnen; ursprüngliche `elapsed_ns` werden nicht verändert.

## Erste Reihe Thema 01 (gelieferter Lauf, 6. Oktober 2026)

20 gleich lange Dokumente, Seed 20261006, Grundwortschatz `wort0000` bis `wort0999`, 10.000/100.000/1.000.000 Tokens. Fehler steht an Position null und jeder hundertsten Position pro Dokument; Verbindung nur am Ende von doc00.txt; Unauffindbar fehlt. Ihre Häufigkeiten sind 100/1/0, 1.000/1/0 und 10.000/1/0. Damit werden frühe Treffer und nahezu/vollständig durchlaufene Korpora getrennt untersucht. Dokumentzahl, Zufallsverfahren und Grundwortschatz bleiben konstant. Die Gesamtzahl der Tokens ist der variierte Faktor; die Zahl der Fehler-Vorkommen wächst proportional. Ein erfolgreicher Pilot sperrt die vorab gewählten Parameter.

Der reale Datensatz des gelieferten Laufs ist ein fester Kafka-Auszug mit 1.271 Tokens in einer Datei. Gregor/Fenster/Unauffindbar haben 15/1/0 Vorkommen. Quelle und Prüfsummen stehen in `daten/real/kafka_verwandlung/manifest.json`. Seine Zeiten sind eine eigene Beobachtung ohne Gleichsetzung mit den generierten 20-Dokument-Korpora. Der separate Regelvergleich ändert ausschließlich Casefold zu Lower und prüft Tokens/Treffer, keine Geschwindigkeit.

Der gelieferte Lauf liegt in `01_pilot` und `01_direkte_suche`. Seit dem 14. Oktober 2026 schreibt `run.py` ohne `--ausgabe` nicht mehr in diese Ordner, sondern in neue Ordner der Neumessung 01b. Die gelieferten Ergebnisse werden nur noch geprüft:

```sh
.venv/bin/python themen/01_textaufbereitung_direkte_suche/experimente/verify_results.py --eingabe 01_pilot --archive-only
.venv/bin/python themen/01_textaufbereitung_direkte_suche/experimente/verify_results.py --archive-only
```

Die Neumessung 01b mit dem BGB als Realteil steht im Abschnitt zur Überarbeitung.

## Fortsetzung in Themen 02–05

Thema 02 übernimmt Plan, QuerySpec, Aufbau-Messung, CSV und Statistik aus `gemeinsam.messung`. Ein kleiner fachlicher Treiber mischt je Wiederholung alle sechs (Verfahren, Wortanfrage)-Blöcke zusammen, um eine feste Reihenfolge zwischen direkter und indexbasierter Suche zu vermeiden. Auswahl, Mischen und Prüfung liegen außerhalb des Timers. Beide öffentlichen Suchfunktionen erzeugen vollständig materialisierte neue Listen; Anfrageaufbereitung ist enthalten. Die dokumentierten Versuche setzen `PYTHONHASHSEED=0`; der tatsächliche Hashseed und Software-/Code-/Datensatzstände werden aufgezeichnet.

N-Reihe: 10.000/100.000/1.000.000 Tokens bei 1.000 Tokens pro Dokument, D=10/100/1.000, Grundwortschatz 1.000 plus zwei Pflanzwörter. V-Reihe: 100/1.000/10.000 Grundwörter, N=100.000, D=100 und L=1.000; garantierte Einpflanzung jedes Grundwortes sichert tatsächlich V=102/1.002/10.002. Der mittlere Datenpunkt gehört zu beiden Reihen. Die N-Reihe verändert zugleich D/P; die V-Reihe verändert zugleich V/P. Erreichte N/D/V/P, Dokumentlängen und Wort-/Dokumenthäufigkeiten werden ausgewiesen; diese Beziehungen werden nicht als isolierte Kausaleffekte eines einzelnen Faktors interpretiert. Der Realtext des gelieferten Laufs ist der unveränderte gemeinsame Kafka-Auszug, der BGB-Realteil ist der neue Lauf `02_bgb`. Die direkte Suche nach frühem Fehler prüft D Tokens, Verbindung am Ende der ersten Datei und Unauffindbar verlangen N Vergleiche.

Ein gesonderter Python-Prozess misst drei neue Builds pro Datensatz mit Tracerstart nach Korpusvorbereitung: aktuelle Allokationen nach minus vor Build sowie seit zurückgesetztem Peak maximal zusätzliche Bytes. Weiterhin zählt `sys.getsizeof` den erreichbaren Index-/Proxy-/Dictionary-/Tupelgraphen mit jeder Objektidentität einmal; geliehene Korpus-Token-/ID-Strings werden ausgenommen. Diese Größen heißen `retained_traced_bytes`, `peak_traced_bytes` und `exclusive_index_bytes` in separatem `memory.csv`/`memory.json`. Die Speicherfelder des Zeit-CSV bleiben leer. Profilingzeiten sind keine Laufzeitnachweise. Tracemalloc und Objektgraphmaß erfassen keinen vollständigen Prozess-RSS und keinen persistenten Index. Rohwerte und Auswertung:

Weitere Reihen variieren Dokumentzahl und Wortschatz beim Index, Listenlängen und Begriffsanzahl bei AND/OR sowie Phrasenlänge und Positionshäufigkeit. Zusätzliche behaltene und temporäre Indexallokationen werden in separaten `tracemalloc`-Läufen gemessen, nicht zusammen mit Zeitintervallen. Diese Werte sind weder gesamter Prozessspeicher noch Dateigröße eines Index.

Für dieselbe gemeinsame Vorbereitung P gelten als Modell `T_direkt(Q) = P + Q*t_direkt` und `T_index(Q) = P+B+Q*t_index`. Bei positiver Ersparnis ist `Q* = B/(t_direkt-t_index)` die Gleichstandsschwelle; sonst gibt es keine endliche Amortisation in diesem Modell. Die Arbeit verwendet seit der Überarbeitung die vereinfachte Rechnung aus Abschnitt 3.6: `q* = t_Aufbau/(t_direkt − t_index)`, ab `⌈q*⌉` ist der Index nach dem Modell nicht langsamer, bei `t_direkt ≤ t_index` amortisiert sich der Aufbau nie. Die BGB-Auswertung der Reihe 05 schreibt genau diese Größen (`amortisation_table: abschnitt_3_6`). Thema 05 prüft das Modell mit tatsächlich gemessenen Abfragefolgen. Die Summe einzelner Mediane wird nicht als exakt gemessene Gesamtzeit ausgegeben. Thema 01 behauptet weder einen Indexvorteil noch eine abgeschlossene Gesamtuntersuchung.

## Boolesche Reihe Thema 03 (gelieferter Lauf, 6. Oktober 2026)

Der gemeinsame CSV-/Statistikvertrag bleibt unverändert. Der kontrollierte Korpus hat D=1000 und N=100000, 100 Tokens pro Dokument, Seed 20261006. Anfrage- und Fülltokens sind jeweils vier ASCII-Zeichen lang. Sieben explizite Vorkommensrezepte untersuchen seltene, häufige, gemischte, fehlende und disjunkte Treffer sowie starke/schwache Überschneidung. k=2/3/5 und Vorwärts-/Rückwärtsfolge verwenden denselben Korpus; ein Duplikatfall zeichnet Original-/Effektivzahl auf. Reihenfolgepaare verwenden exakt dieselben Wörter, Längen und Treffer. Ein allgemeiner k-Effekt unabhängig von Frequenz/Überschneidung wird nicht behauptet.

Fünf Warmups, zwanzig Wiederholungen, fünf vollständige Aufrufe je Abfrageblock; Verfahren und Anfragen werden pro Wiederholung deterministisch gemischt. Alle öffentlichen Suchkosten einschließlich zentraler Normalisierung, Postingzugriff, Sammeln, stabiler Längensortierung und vollständiger Materialisierung sind enthalten. Dateiladen, Aufbereitung und Indexaufbau erhalten getrennte Messphasen. Ergebnisse werden außerhalb des Timers geprüft und vor dem nächsten Timer freigegeben. Zähler, Listengrößen und Zwischenresultate stammen ausschließlich aus separaten Diagnoseläufen. Speicherfelder bleiben leer; diese Reihe misst keinen Speicher.

Der unveränderte Kafka-Auszug ergänzt dieselbe Semantik bei k=2/3/5, fehlenden und doppelten Begriffen. Ein Dokument ist keine repräsentative Frequenz-/ Skalierungsuntersuchung. Manifest, Quellarchiv und unabhängige Tokenfolge werden geprüft. Vor Zeitmessungen müssen alle Ergebnisse mit dem Pflanzplan bzw. Realtextoracle übereinstimmen. Pilot und Quellenhashes binden den finalen Lauf. Rohwerte, Gruppenstatistik, Abfragemanifeste und Quellenstände: `ergebnisse/messungen/03_boolesche_mehrwortsuche/`; ausführbare Befehle: [Experimente 03](../themen/03_boolesche_mehrwortsuche/experimente/README.md). Befunde und Grenzen: Seit der Erweiterung um Galloping Search und AND NOT bestehen `03_pilot` und `03_boolesche_mehrwortsuche` nur noch mit `verify_results.py --archive-only`. Der BGB-Realteil (`03_bgb`) und die Galloping-Reihe (`03b_galloping`) sind eigene neue Läufe.

## Phrasenreihe Thema 04 (gelieferter Lauf, 6. Oktober 2026)

Die APIs aus `positionsindex` übernehmen die gemeinsamen vorbereiteten Dokumente. Im gemessenen Wrapper verwenden beide Verfahren `normalize_query(raw_query, "phrase")`, anschließend ihre Kernsuche und vollständig materialisierte neue Dicts/Startlisten. Ergebnisprüfung und Freigabe vor dem nächsten Timer liegen außerhalb des Intervalls. Zeitrohwerte behalten exakt `CSV_FIELDS`: `query_type=phrase`, `hit_count` zählt Dokumente. Das Querymanifest ergänzt `phrase_tokens`, `phrase_length`, `position_count`, vollständige `expected_positions`, CF/DF, Kandidaten und Positionslistenlängen. So werden Dokumenttreffer und tatsächlicher Ausgabenumfang auseinandergehalten.

Laden und Aufbereitung erfolgen für Thema 04 vor der Zeitmessung. Dafür werden keine fiktiven neuen Lade-/Aufbereitungskosten eingetragen. Beide Indizes werden auf demselben vorbereiteten Korpus getrennt mit der gemeinsamen `measure_phase` aufgebaut und gegen unabhängige Sollstrukturen geprüft. Keine Abfrage benötigt einen versteckten Indexaufbau. Die direkte Referenz verwendet keine Postings. Fünf Warmups, zwanzig Wiederholungen und fünf vollständige Anfragen je Block; Verfahren/Queryblöcke werden deterministisch gemischt. Aufbauarten folgen einer festen Reihenfolge (Dokumentindex, dann Positionsindex); diese Reihenfolge ist kein isolierter kausaler Vergleich. Code-/Datenhashes und Quellarchive sichern den ausgeführten Stand. `PYTHONHASHSEED=0` wird für die dokumentierten Läufe gesetzt.

Der Generator verwendet D=200, L=500, N=100000 und V=66, Seed 20261006. Gepflanzte häufige und seltene Fünfwortfolgen sowie sechs gleiche Tokens erlauben m=1/2/3/5. Häufige/seltene Präfixe haben bei jeder Länge 2000/2 Starts; Wiederholung verändert die Ausgabegröße von 1200 auf 400 Starts. Fehlende Wörter und vorhandene Wörter in falscher Reihenfolge sind eigene Querygruppen. Drei Korpora mit H=0/20/200 Trefferdokumenten permutieren ausschließlich eine Fünfwortfolge: N/D/V, Wortlängen und sämtliche CF/DF bleiben gleich. Die Reihenfolge verändert dennoch neben der Ausgabe auch den Verlauf der Positionsschnittbildung; ein reiner Allokationseffekt wird nicht behauptet.

Der unveränderte Kafka-Auszug (ein Dokument, 1271 Tokens) ergänzt 19 Anfragen: Satzpräfixe, häufiges `er`, wiederholtes `gregor`, fehlendes Wort und falsche Reihenfolge. Seine Tokens werden über eine unabhängige Regex-Aufbereitung mit Kategorieprüfungen und die bekannten Manifestwerte überprüft. Beim Generator werden sämtliche Tokenfolgen vor der Suche mit dem Pflanzplan verglichen. Insgesamt 41 Anfragen und 90 Statistikgruppen; Pilot und Hauptlauf verwenden dieselben Korpora. Die Pilotstichprobe hat einen Warmup und drei Wiederholungen.

Speicherprofiling läuft anschließend in acht sequenziellen separaten Prozessen: ein Prozess je Datensatz/Indexart, jeweils drei neue Builds. Tracerstart folgt auf vorhandenen vorbereiteten Korpus und unabhängige Sollstrukturen; deren Allokationen werden nicht zugerechnet. Keine alternative Produktionsindexart ist gleichzeitig aufgebaut. Der Zustand wird vor validierenden Ergebniskopien erfasst. `retained_traced_bytes` und `peak_traced_bytes` sind Differenzen zum Buildbeginn; `transient_peak_bytes=peak−retained` bezeichnet den Peaküberhang, keine separat addierbare Speichermenge. CSV-Speicherfelder im Zeitlauf bleiben leer. Diese Werte sind keine Prozess-RSS- oder Indexdateigrößen.

Rohwerte: `ergebnisse/messungen/04_positionsindex_phrasensuche/`. Verifier prüft vollständige Starts, Tokenpläne, Hasharchive, Integer-Blockzeiten, Statistiken, Reihenfolge, Stichprobenplan und getrennte Speicherprozesse. Befehle: [Experimente 04](../themen/04_positionsindex_phrasensuche/experimente/README.md). Beobachtungen: Thema 05 verwendet dieselben APIs und CSV-Felder; neu zu messende Vorbereitungs-/Abfragefolgen werden dort konsistent zugerechnet.

## Gesamtvergleich Thema 05: ausgeführter Vertrag (gelieferter Lauf, 6. Oktober 2026)

Die neue Reihe ergänzt die korrektheitsgesicherten Teilreihen aus 01–04. Synthetisch: N10000/D20/V64/L500, `05-planted-v1`, Seed20261006; real: unveränderter Kafka-Auszug N1271/D1/V608. Vollständige Pflanzpläne, Unicode-Orakel, File-/Query-SHA und alle Parameter stehen in den Laufmanifesten. Separate Resultate verhindern eine Gleichsetzung beider Datenverteilungen.

Fünf Warmups und zwanzig Phasen-/Querywiederholungen; kurze Queryblöcke mit fünf Aufrufen. Jeder materialisierte Block wird nach dem Timer vollständig validiert und freigegeben. GC ist ausschließlich während der Zeitintervalle deaktiviert; der ursprüngliche Zustand wird bei Erfolg und Fehler wiederhergestellt. `perf_counter_ns()` wird als monotone Uhr verwendet; Metadaten nennen Implementierung und tatsächliche angegebene Auflösung. Zeit-/Speicherläufe werden nicht parallel ausgeführt. Während der Zeitläufe laufen keine Projekttests, PDF-Builds oder andere Benchmarkreihen. Dateiladen ist eine eigene Warmcache-Beobachtung, keine Kaltstartmessung.

Sechs feste Profile je Datensatz: fehlendes/häufiges/seltenes Wort, vorhandene AND3/OR3/Phrase3. Jedes Profil wiederholt dieselbe Anfrage; AND verwendet shortest_first inklusive Sortierkosten. Repräsentative t-Werte kommen aus Medianen tatsächlich gemessener vollständiger 50er-Blöcke geteilt durch 50, nicht aus summierten Einzelmedians. Eine deterministische Pilotregel ergänzt feste Q=0,1,2,5,10,20,50,100,200,500,1000 um Nähe zur errechneten ersten strikten Integergrenze. Der Hauptlauf übernimmt die Pilotwerte unverändert.

Gesamtabläufe: bereits geladene Rohtexte im Speicher → gemeinsame Aufbereitung → optionaler Indexaufbau → Q vollständige Anfragen. Ein Warmup und fünf vollständige Wiederholungen je Q/Verfahren, deterministisch gemischt. Index und sämtliche Resultate bleiben bis nach Timer/Prüfung erhalten, sodass ihre Destruktion nicht als versteckter Aufbauaufwand eingeht. Der Korpus ist statisch. Dateiladen liegt außerhalb dieser Hauptgrenze; ein gleicher Ladeanteil kann beiden Seiten zugerechnet werden und verändert die theoretische Differenz nicht. Die gehaltene Ergebnisfolge ist Teil des gemessenen konkreten Verbrauchsmodells.

Allgemein: T_d(Q)=P_d+B_d+Q*t_d und T_i(Q)=P_i+B_i+Q*t_i. ΔC=(P_i+B_i)−(P_d+B_d), Δt=t_d−t_i. Der Index ist genau für Q*Δt>ΔC strikt billiger. Bei Δt>0 ist die erste Integerzahl strikt oberhalb ΔC/Δt relevant; Gleichheit genügt nicht. Bei Δt=0 entscheidet allein ΔC<0; bei Δt<0 kann bei negativer Vorbereitung ein anfänglicher Vorteil später verschwinden. Die Implementierung löst alle Fälle als rationale Ungleichung auf einem zulässigen Q-Bereich. In der neuen Hauptserie ist P_d=P_i dieselbe Aufbereitung und B_d=0. Modellkurven sind Vorhersagen; beobachtete Gesamtkosten sind ausschließlich direkt gestoppte ganze Abläufe.

Median und inklusive Quartile werden aus allen Rohwerten berechnet, IQR=Q3−Q1. Gepaarte Einsparung innerhalb derselben Wiederholung wird zusätzlich ausgewiesen; ihre Quartile sind keine Konfidenzintervalle. Keine Ausreißer werden entfernt. Übergänge sind beobachtete Rasterbereiche, keine garantiert universellen Einzelzahlen. Speicherprozesse beginnen nach Ende des Zeitlaufs: vier getrennte Worker (je Datensatz und Indexart), je drei Builds. Tracerstart nach vorbereitetem Korpus; gehaltener Mehrbedarf und Peaküberhang werden getrennt erfasst. Kein Prozess-RSS, keine Indexdateigröße.

Seit dem 14. Oktober 2026 bestehen auch `05_pilot`, `05_experimentelle_analyse` und `05_clean_smoke` nur noch im Archivmodus (`experimentelle_analyse verify --input … --archive-only`, Ergebnis `verified_archive_only`). Der strenge Verifier meldet erwartungsgemäß „Aktiver Quellcode weicht von Messfassung ab“. Eine erneute Auswertung geht nur mit `analyse --archive-only` in einen neuen Ordner. Der BGB-Realteil ist der neue Lauf `05_bgb`.

## Überarbeitung vom 14. Oktober 2026

Realkorpus aller neuen Läufe ist das BGB nach Paragraphen (`daten/real/bgb/dokumente/`, D = 2.486, N = 213.718, V = 11.398, P = 133.909, Korpushash `dc1641fd49dfa45270a1865f454abd64cf7cf94d79b37af9657ff97d7602eadf`). Synthetische Ergebnisse der Reihen 02 bis 05 werden nicht neu gemessen. Reihe 05 bei größerem N wird nicht gemessen und ist in der Arbeit als offene Messung genannt.

### Gemeinsame Regeln der neuen Läufe

- **Neue Zielordner.** Jeder Lauf schreibt in einen eigenen Ordner unter
  `ergebnisse/messungen/`, gewählt mit `--ausgabe NAME` (Reihe 05: `--output PFAD`).
  Ist der Ordner vorhanden und nicht leer, bricht der Lauf vor jeder Messung ab.
  Gelieferte Ordner werden nie überschrieben.
- **Pilotbindung.** Zuerst läuft ein Pilot mit einem Warmup und drei Wiederholungen.
  Er schreibt `pilot_decision.json` mit den gesperrten Parametern, den SHA-256 des
  gemessenen Codes und dem tatsächlichen `PYTHONHASHSEED`. Der Hauptlauf liest den Pilot
  über `--pilot-ordner NAME` und bricht ab, wenn Parameter, Messcode oder Hashseed
  abweichen. Reihe 05 bindet stattdessen über `pilot_directory` in `bgb_main.json`: Der
  Hauptlauf verlangt dieselben Code-Hashes und Versuchsparameter wie der Pilotlauf,
  übernimmt dessen Stützstellen und speichert dessen Kennung als `pilot_run_id`. Nach einer Codeänderung braucht
  es einen neuen Pilot in einem neuen Ordner. Die Läufe 03_bgb und 03b ersetzen einen
  Pilot nur ausdrücklich mit `--pilot --replace-pilot`.
- **Hauptlauf** mit fünf Warmups und 20 Wiederholungen. Abfrageblöcke wie in der
  jeweiligen gelieferten Reihe mit 10 Aufrufen (01b, 02_bgb) bzw. 5 Aufrufen (03_bgb,
  03b, 04_bgb, 05_bgb). 02b misst nur den Aufbau. Zeitmessung mit `perf_counter_ns`, Laden, Aufbereitung, Aufbau und
  Abfrage getrennt, Rohschema `gemeinsam.messung.CSV_FIELDS`, Median und inklusive Quartile.
- **`PYTHONHASHSEED=0`.** Alle Läufe wurden mit `PYTHONHASHSEED=0` gestartet. 03_bgb, 03b
  und der Hauptlauf 05_bgb verweigern den Start ohne diesen Wert. 01b, 02b, 02_bgb und
  04_bgb zeichnen den tatsächlichen Wert auf und verlangen im Hauptlauf denselben Wert
  wie im Pilot.
- **Hintergrundlast.** 01b bis 04_bgb schreiben den Text aus `--hintergrundlast TEXT` in
  `metadata.json`. Bei den Finalläufen lautete er
  `Keine parallelen Messungen, Agenten oder Builds; Videopipeline pausiert; Lastmittel vor Start …`
  mit den drei Lastmitteln aus `/proc/loadavg` unmittelbar vor dem Schritt. Ohne Angabe steht dort das geplante
  Protokoll mit dem Hinweis, dass das Skript es nicht prüft. Reihe 05 zeichnet selbst unter
  `background_load` Lastmittel und die fünf CPU-stärksten Prozesse vor der Messung, nach
  jedem Messabschnitt, nach jedem Profil und nach der Speichermessung auf. Der
  CPU-Anteil von `ps` ist ein Mittel seit Prozessstart, kein Momentanwert. Die
  Lastangaben beschreiben die Umgebung, sie korrigieren keine Werte.
- **Quellarchiv.** Jeder Lauf archiviert die gebundenen Quellen unter `code_source/`.
  Die strenge Prüfung vergleicht Archiv und aktiven Code, `--archive-only` nur das Archiv.
- Während der Zeitläufe laufen keine Tests, PDF-Builds oder anderen Messungen.

### Neue Läufe

| Lauf (Pilot, Final) | Zweck | Daten und Messplan | Umfang Final |
| --- | --- | --- | --- |
| 01b (`01b_pilot`, `01b_direkte_suche`) | Neumessung der Reihe 01 unter denselben Bedingungen wie 02 bis 05 | generierte Korpora wie bisher (10⁴, 10⁵, 10⁶ Tokens, 20 Dokumente) und BGB mit vier Anfragen: früh „Beginn“, häufig „der“, selten „Erbschaftskauf“, fehlend „Server“ | 420 Rohwerte, 21 Gruppen |
| 02b (`02b_pilot`, `02b_tokenpruefung`) | Anteil der Tokenprüfung an der Aufbauzeit in der V-Reihe | V-Datensätze `v100`, `n100000`, `v10000` der Reihe 02 (byteidentisch, N = 100.000, D = 100), öffentliche Funktion gegen messinterne Kopie ohne Tokenprüfung (AST-geprüft), Reihenfolge der Varianten je Datensatz wechselnd, nicht gepaart | 120 Rohwerte, 6 Gruppen |
| 02_bgb (`02_bgb_pilot`, `02_bgb`) | Indexaufbau, Speicher und Einzelwortsuche auf dem BGB | Aufbau für die ersten 250, 500, 1.000, 1.500, 2.000 und alle 2.486 Paragraphen (geschachtelte Präfixe in Gesetzesreihenfolge), sieben Wortanfragen direkt gegen Index auf dem ganzen BGB (14 gemischte Blöcke), Speicher in eigenem Prozess mit drei Aufbauten je Teilmenge, Heaps-Anpassung und Rang-Häufigkeit nur beschreibend | 400 Rohwerte, 20 Gruppen, 18 Speicherwerte |
| 03_bgb (`03_bgb_pilot`, `03_bgb`) | boolesche Suche auf dem BGB | 15 Anfragen (AND mit k = 2, 3, 5, Reihenfolgepaare, extremes Längenverhältnis, leere Schnitte, OR mit k = 2, 3, 5, AND NOT), direkte Referenz, `input_order`, `shortest_first`, `galloping` bei AND und AND NOT, `input_order` bei OR | 1.140 Rohwerte, 57 Gruppen |
| 03b (`03b_pilot`, `03b_galloping`) | Galloping Search gegen Zwei-Zeiger | 10.000 erzeugte Dokumente zu je 100 Tokens, AND mit k = 2, kurze Liste df = 10, lange Liste in 10 Stufen von df = 10 bis 10.000, Fall „verteilt“ und Gegenprobe „anfang“, nur `shortest_first` gegen `galloping`, direkte Suche nur zur Trefferprüfung | 860 Rohwerte, 43 Gruppen |
| 04_bgb (`04_bgb_pilot`, `04_bgb`) | Phrasensuche und Positionsspeicher auf dem BGB | 12 Phrasen der Längen 2 bis 5 (häufig, selten, häufige Einzelwörter, falsche Reihenfolge, fehlendes Wort), Aufbau von Dokument- und Positionsindex, direkte Phrasensuche gegen Positionsindex, Speicher in zwei getrennten Prozessen mit je drei Aufbauten | 520 Rohwerte, 26 Gruppen, 6 Speicherwerte |
| 05_bgb (`05_bgb_pilot`, `05_bgb`) | Gesamtkosten und Amortisation auf dem BGB | sechs feste Profile (Wort fehlend „Server“, häufig „der“, selten „Verbindung“, AND3, OR3, Phrase „im Sinne des“), Raster q = 0 bis 1.000 plus Kalibrierstufen aus dem Pilot, fünf Gesamtablauf-Wiederholungen, Ausgabe nach Abschnitt 3.6 | 340 Rohwerte, 240 Profilblöcke, 890 Gesamtabläufe, 6 Speicherwerte |

Die Pilotläufe haben dieselben Daten und Anfragen mit einem Warmup und drei Wiederholungen. Einzelheiten zu Anfragen und Erwartungen stehen in den Experiment-READMEs der Themen und in `daten/real/bgb/README.md`.

### Befehle der Finalläufe

So wurden die Läufe am 14. Oktober 2026 nacheinander ausgeführt, aus der Repositorywurzel, mit `export PYTHONHASHSEED=0`. `"TEXT"` steht für die tatsächliche Lastangabe.

```sh
T1=themen/01_textaufbereitung_direkte_suche/experimente
T2=themen/02_invertierter_index_einzelwortsuche/experimente
T3=themen/03_boolesche_mehrwortsuche/experimente
T4=themen/04_positionsindex_phrasensuche/experimente
T5=themen/05_experimentelle_analyse/experimente

.venv/bin/python $T1/run.py --pilot --ausgabe 01b_pilot --hintergrundlast "TEXT"
.venv/bin/python $T1/run.py --ausgabe 01b_direkte_suche --pilot-ordner 01b_pilot --hintergrundlast "TEXT"

.venv/bin/python $T2/tokenpruefung.py --pilot --ausgabe 02b_pilot --hintergrundlast "TEXT"
.venv/bin/python $T2/tokenpruefung.py --ausgabe 02b_tokenpruefung --pilot-ordner 02b_pilot --hintergrundlast "TEXT"

.venv/bin/python $T2/bgb_lauf.py --pilot --ausgabe 02_bgb_pilot --hintergrundlast "TEXT"
.venv/bin/python $T2/bgb_lauf.py --ausgabe 02_bgb --pilot-ordner 02_bgb_pilot --hintergrundlast "TEXT"

.venv/bin/python $T3/bgb/run.py --pilot --ausgabe 03_bgb_pilot --hintergrundlast "TEXT"
.venv/bin/python $T3/bgb/run.py --ausgabe 03_bgb --pilot-ordner 03_bgb_pilot --hintergrundlast "TEXT"
.venv/bin/python $T3/bgb/analyse.py --eingabe 03_bgb

.venv/bin/python $T3/galloping/run.py --pilot --ausgabe 03b_pilot --hintergrundlast "TEXT"
.venv/bin/python $T3/galloping/run.py --ausgabe 03b_galloping --pilot-ordner 03b_pilot --hintergrundlast "TEXT"
.venv/bin/python $T3/galloping/analyse.py --eingabe 03b_galloping
.venv/bin/python $T3/galloping/plots/render.py --eingabe 03b_galloping

.venv/bin/python $T4/run_bgb.py --pilot --ausgabe 04_bgb_pilot --hintergrundlast "TEXT"
.venv/bin/python $T4/run_bgb.py --ausgabe 04_bgb --pilot-ordner 04_bgb_pilot --hintergrundlast "TEXT"

.venv/bin/python -m experimentelle_analyse run --config $T5/bgb_pilot.json --output ergebnisse/messungen/05_bgb_pilot
.venv/bin/python -m experimentelle_analyse run --config $T5/bgb_main.json --output ergebnisse/messungen/05_bgb
.venv/bin/python -m experimentelle_analyse analyse --input ergebnisse/messungen/05_bgb --output ergebnisse/abbildungen/05_bgb
.venv/bin/python $T5/render_bgb.py --input ergebnisse/messungen/05_bgb --analysis ergebnisse/abbildungen/05_bgb
```

Der Pilot der Reihe 01 heißt hier `01b_pilot`. `run.py` verwendet ohne Angabe die Standardnamen `01b_pilot2` und `01b_direkte_suche`, deshalb sind `--ausgabe` und `--pilot-ordner` oben ausdrücklich gesetzt. `run_bgb.py` (Reihe 04) prüft den Lauf am Ende selbst. Abbildungen: 01b und 02_bgb im eigenen Laufordner unter `abbildungen/`, 03b unter `ergebnisse/abbildungen/03b_galloping.{png,svg,pdf}`, 05_bgb unter `ergebnisse/abbildungen/05_bgb/` (dort auch `amortisation.json` und `amortisation.csv`). Auswertungen der Reihe 03 liegen als `comparisons.json` und `auswertung.md` im Laufordner, die der Reihe 02 als `auswertung.json`.

### Prüfbefehle

Neue Läufe werden streng geprüft (aktiver Code gleich Archiv):

```sh
.venv/bin/python $T1/verify_results.py --eingabe 01b_pilot
.venv/bin/python $T1/verify_results.py --eingabe 01b_direkte_suche
.venv/bin/python $T2/tokenpruefung.py --pruefen 02b_pilot
.venv/bin/python $T2/tokenpruefung.py --pruefen 02b_tokenpruefung
.venv/bin/python $T2/bgb_lauf.py --pruefen 02_bgb_pilot
.venv/bin/python $T2/bgb_lauf.py --pruefen 02_bgb
.venv/bin/python $T3/bgb/verify_results.py --eingabe 03_bgb_pilot
.venv/bin/python $T3/bgb/verify_results.py --eingabe 03_bgb
.venv/bin/python $T3/galloping/verify_results.py --eingabe 03b_pilot
.venv/bin/python $T3/galloping/verify_results.py --eingabe 03b_galloping
.venv/bin/python $T4/verify_bgb.py --eingabe 04_bgb_pilot
.venv/bin/python $T4/verify_bgb.py --eingabe 04_bgb
.venv/bin/python -m experimentelle_analyse verify --input ergebnisse/messungen/05_bgb_pilot
.venv/bin/python -m experimentelle_analyse verify --input ergebnisse/messungen/05_bgb
```

Die gelieferten Läufe vom 6. Oktober 2026 werden seit den Quelländerungen vom 14. Oktober 2026 so geprüft:

| Lauf | Befehl | Modus | Grund |
| --- | --- | --- | --- |
| `01_pilot`, `01_direkte_suche` | `$T1/verify_results.py --eingabe 01_pilot --archive-only` bzw. `$T1/verify_results.py --archive-only` | Archiv | `run.py` um neue Zielordner erweitert, gemessenes `run_source_measured.py` bleibt hashgeprüft |
| `02_pilot`, `02_invertierter_index` | `$T2/verify_results.py --pilot` bzw. `$T2/verify_results.py` | streng | gemessener Code der Reihe 02 unverändert |
| `03_pilot`, `03_boolesche_mehrwortsuche` | `$T3/verify_results.py --pilot --archive-only` bzw. `$T3/verify_results.py --archive-only` | Archiv | `boolesche_suche` und `boolean_diagnostics.py` erweitert |
| `04_pilot`, `04_positionsindex_phrasensuche` | `$T4/verify_results.py --pilot --archive-only` bzw. `$T4/verify_results.py --archive-only` | Archiv | aktive Quellen weichen vom gemessenen Stand ab (schon seit Thema 05) |
| `05_pilot`, `05_experimentelle_analyse`, `05_clean_smoke` | `python -m experimentelle_analyse verify --input ergebnisse/messungen/<lauf> --archive-only` | Archiv | Thema 03, `provenance.py`, CLI und BGB-Erweiterung in Thema 05 geändert |

Der Archivmodus ersetzt nur den Vergleich „aktive Quelle gleich Messfassung“ durch die Prüfung des Quellarchivs gegen die gespeicherten Hashes. Rohwerte, Statistik, Daten, Reihenfolgen und die semantische Wiederholung mit dem aktiven Code bleiben geprüft. Die historischen Ordner `02_vor_cli_integration` und `02_pilot_vor_cli_integration` haben keinen eigenen Prüfbefehl.
