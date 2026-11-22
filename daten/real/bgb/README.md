# Fester realer Korpus: Bürgerliches Gesetzbuch nach Paragraphen

Datensatz `bgb-gesetze-im-internet-v1`, abgerufen am **14. Oktober 2026, 15:56:45 +02:00**. Ein Paragraph des BGB ist ein Dokument. Entscheidung: Der Korpus ersetzt Kafka für alle **neuen** Realtext-Messungen. Er ist **kein Ersatz für alte Ergebnisse**: `daten/real/kafka_verwandlung/` bleibt unverändert, damit die gelieferten Messungen unter `ergebnisse/` weiter mit Kafka prüfbar sind. Neue Messungen gehören in neue Zielverzeichnisse.

## Inhalt des Ordners

| Pfad | Inhalt |
|---|---|
| `dokumente/` | Korpuspfad für `load_corpus`; nur die 2.486 Dateien `bgb_NNNN[suffix].txt` |
| `quelle/bgb_xml.zip` | unverändert archivierte Quell-ZIP (Endung nicht `.txt`) |
| `quelle/abruf.json` | Abrufprotokoll: URL, Zeit mit Zeitzone, HTTP-Status, alle Antwortheader, Bytes, SHA-256 |
| `manifest.json` | Herkunft, Stand, Regeln, Ausschlüsse, Dateiliste mit Prüfsummen, unabhängige Erwartungen, Abgleich |
| `anfragevorschlaege.json` | Anfragevorschläge für die Reihen 01 bis 05 mit unabhängig berechneten Erwartungen |
| `erzeuge_korpus.py` | Herunterladen, Umwandeln, Offline-Prüfung (nur Standardbibliothek) |
| `berechne_erwartungen.py` | unabhängige Erwartungen, Vorschläge und Abgleich mit dem Produktivcode |

Dokumentkennungen sind die reinen Dateinamen, weil `dokumente/` die Korpuswurzel ist. `load_corpus("daten/real/bgb")` wäre falsch: Die Kennungen bekämen das Präfix `dokumente/`.

## Herkunft und Stand

- Quelle: [Gesetze im Internet, BGB](https://www.gesetze-im-internet.de/bgb/), XML-Download
  `https://www.gesetze-im-internet.de/bgb/xml.zip`. Laut Startseite stellen „das Bundesministerium
  der Justiz und für Verbraucherschutz und das Bundesamt für Justiz“ das Bundesrecht bereit, laut
  Impressum erfolgt die technische Bereitstellung durch die juris GmbH.
- HTTP-Antwort beim Abruf: `Last-Modified: Sat, 26 Sep 2026 19:55:12 GMT`,
  `ETag: "72156-65c6835fce6bb"`, 467.286 Bytes, SHA-256
  `a4f41098aad1932df88ba2743de4a650b931a23cf71958bf5fad1c0e3785284a`.
- ZIP-Inhalt: genau eine Datei `BJNR001950896.xml` (2.519.002 Bytes, Zeitstempel 26.09.2026 21:55:10,
  DTD `gii-norm.dtd` 1.01, `builddate` 20260926215507).
- Stand laut XML (`standangabe`): Neufassung durch Bek. v. 2.1.2002 I 42, 2909; 2003, 738;
  **zuletzt geändert durch Art. 6 G v. 23.7.2026 I Nr. 226**. Ausfertigung 18.08.1896 (RGBl 1896, 195).
- Das XML ist bereits vollständig Unicode-NFC (`unicodedata.is_normalized`, Unicode 14.0.0).
- Der Text ist ein fester Abrufstand für Suchexperimente, keine Rechtsquelle. Rechtlich verbindlich ist
  die Verkündung im Bundesgesetzblatt.

## Rechtsgrundlage

[§ 5 Abs. 1 UrhG](https://www.gesetze-im-internet.de/urhg/__5.html) (Amtliche Werke): „Gesetze, Verordnungen, amtliche Erlasse und Bekanntmachungen sowie Entscheidungen und amtlich verfaßte Leitsätze zu Entscheidungen genießen keinen urheberrechtlichen Schutz.“ Das BGB ist ein Gesetz, der Normtext ist daher gemeinfrei. Die Pflicht zur Quellenangabe aus Abs. 2 gilt nur für andere amtliche Werke, nicht für Gesetze. Zusätzlich erklärt die Startseite von Gesetze im Internet (abgerufen am 14.10.2026): „Die Rechtsnormen in deutscher Sprache stehen in allen angebotenen Formaten zur freien Nutzung und Weiterverwendung zur Verfügung.“ Es gibt keine Lizenzauflagen. Die Quelle wird trotzdem genannt. Es wurde genau eine Datei heruntergeladen, kein Crawler eingerichtet.

## Umwandlungsregeln (`bgb-umwandlung-v1`)

1. Quelle ist die einzige XML-Datei der unveränderten ZIP. Sie wird strikt als UTF-8 gelesen und mit
   `xml.etree.ElementTree` geparst.
2. Ein Dokument entsteht aus jeder Norm, deren `metadaten/enbez` mit „§“ beginnt (2.526 von 2.841
   Normen). Nicht dazu gehören 290 Normen ohne `enbez` (289 Gliederungseinheiten wie Buch, Abschnitt,
   Titel und die Rahmennorm mit den Gesetzesmetadaten), die Inhaltsübersicht und 24
   Sammeleinträge wie `(XXXX) §§ 3 bis 6` mit Überschrift „(weggefallen)“. Die Sammeleinträge stehen
   im Manifest (`collective_entries`). Anlagen enthält das BGB-XML nicht.
3. Die Paragraphenbezeichnung steht nur im Dateinamen. Erste Zeile ist die Überschrift
   `metadaten/titel`, falls vorhanden.
4. Danach folgt der Normtext aus `textdaten/text/Content`. Die Textknoten werden in
   Dokumentreihenfolge wie bei `itertext()` verbunden. Vor `P`, `DL`, `DT` und `BR` sowie nach `P` und
   `DL` steht ein Zeilenumbruch, vor `DD` und `LA` ein Leerzeichen, `I`, `NB` und `FnR` erzeugen keinen
   Trenner. Jeder Absatz und jeder Listenpunkt (Nummer und Text) steht so auf einer eigenen Zeile.
   Andere Elemente im Normtext führen zum Abbruch.
   *Begründung:* Ein reines `"".join(itertext())` verklebt in 200 Paragraphen Wörter mit der
   folgenden Listennummer, z. B. in § 55a „und“ + „3.“ zu `und3`.
5. Fußnoten gehören nicht dazu: weder `textdaten/fussnoten` noch das Element
   `textdaten/text/Footnotes` (amtliche Hinweise, z. B. in § 14).
6. Leerraum je Zeile wird normalisiert (`" ".join(zeile.split())`). Das ersetzt auch die 149
   geschützten Leerzeichen U+00A0, davon 136 direkt nach „§“ wie in „§ 30“. Leere Zeilen entfallen.
7. Nicht aufgenommen werden 39 weggefallene Paragraphen: Überschrift „(weggefallen)“ mit leerem
   Normtext, Normtext „-“ oder „(weggefallen)“, oder ohne Überschrift mit Normtext genau
   „(weggefallen)“. Ebenfalls nicht aufgenommen wird § 651 ohne Normtext mit der Überschrift
   „(jetzt § 650)“. Alle 40 stehen mit Grund im Manifest (`excluded_paragraphs`).
8. Dateiname `bgb_NNNN<suffix>.txt`: Nummer vierstellig mit führenden Nullen, Buchstabensuffix klein,
   z. B. `§ 1` → `bgb_0001.txt`, `§ 312a` → `bgb_0312a.txt`. Ein Leerzeichen vor dem Suffix wäre zulässig
   (`§ 312 a` → `bgb_0312a.txt`), kommt im Abrufstand aber nicht vor. Bezeichnungen mit „§§“, mehr als
   vier Ziffern oder anderen Zeichen führen zum Abbruch, außer sie sind weggefallen. Kollisionen führen
   zum Abbruch.
9. Das Skript prüft, dass die Dateinamen in XML-Reihenfolge streng aufsteigen (Bytevergleich wie
   Pythons `sorted`). Die sortierten Dokumentkennungen folgen damit der Gesetzesreihenfolge.
   Achtung: `ls` mit deutscher oder englischer Locale sortiert anders (`bgb_0031a.txt` vor
   `bgb_0031.txt`). Maßgeblich ist die Bytereihenfolge.
10. UTF-8 ohne BOM, LF, genau ein abschließender Zeilenumbruch. NFC und Case Folding werden nicht vorab
    angewandt. Das macht die gemeinsame Aufbereitung.

Beispiel `bgb_0001.txt`:

```text
Beginn der Rechtsfähigkeit
Die Rechtsfähigkeit des Menschen beginnt mit der Vollendung der Geburt.
```

Der kanonische Korpushash (`corpus_sha256`) ist SHA-256 über die Zeilen `<sha256>  <dateiname>\n` in Bytereihenfolge: `dc1641fd49dfa45270a1865f454abd64cf7cf94d79b37af9657ff97d7602eadf`. Nachrechnen: `cd daten/real/bgb/dokumente && (export LC_ALL=C; sha256sum *.txt | sha256sum)`.

## Kennzahlen

| Kennzahl | Wert |
|---|---|
| Dokumente $D$ | 2.486 |
| Tokens $N$ | 213.718 |
| Wortschatz $V$ | 11.398 |
| Postings $P=\sum_t df(t)$ | 133.909 |
| Positionseinträge | 213.718 (= $N$) |
| Rohbytes | 1.587.032 |
| Tokens je Dokument | min. 8, Median 61, Mittel 85,97, max. 1.168 (§ 309) |
| Terme mit Umlaut ä/ö/ü | 2.267 |
| Oberflächenformen mit ß vor dem Case Folding | 236 (werden zu „ss“, z. B. Maßgabe → `massgabe`) |
| Terme nur aus Ziffern | 1.048 („1“ und „2“ gehören zu den zehn häufigsten Tokens) |

**df-Verteilung (Grundlage für Zipf-Aussagen):** df > 1.000: 21 Terme, 100–1.000: 159, 10–99: 1.579, 2–9: 4.678, df = 1: 4.961 (43,5 % des Wortschatzes). 4.453 Terme kommen genau einmal vor (cf = 1).

**Rang und Häufigkeit (cf):** 1 `der` 11.486, 2 `die` 8.803, 3 `des` 5.699, 10 `2` 2.766, 50 `satz` 637, 100 `dies` 242, 500 `entrichten` 49, 1.000 `teilhaber` 25, 2.000 `aufstellung` 10, 5.000 `stillschweigende` 3, 10.000 `rechtsverwirkung` 1 (Gleichstand nach Term sortiert).

Diese Werte lassen sich exakt nachbilden mit „alle §-Normen, `" ".join(itertext())` über das ganze `textdaten/text` einschließlich amtlicher Hinweise, ohne Überschrift, Dokumente mit mindestens einem Token“. Damals zählten die 16 Paragraphen mit Normtext „(weggefallen)“ als Dokumente. Der Korpus hier nimmt Überschriften auf und lässt weggefallene Paragraphen und Fußnoten weg.

## Unabhängige Erwartungswerte

`berechne_erwartungen.py berechnen` liest die Dateien selbst und tokenisiert ohne Import aus `gemeinsam`: NFC → `casefold` → NFC, dann `re.finditer` mit einer Zeichenklasse, die aus `unicodedata.category` aller Codepunkte für L* und Nd gebaut wird (die Produktivfassung prüft Zeichen für Zeichen in einer Schleife). Das Ergebnis steht in `manifest.json` unter `independent_expectations`: $D, N, V, P$, Dokumentlängen, df-Verteilung, Rangliste, Zeichenbestand, die ersten Tokens von § 1, df/cf mit Dokumentlisten für 17 Wortanfragen und Startpositionen für 8 Phrasen. Listen bis 200 Einträge stehen vollständig darin, längere als Anzahl, SHA-256 sowie erste und letzte fünf Kennungen.

| Anfrage | Term | df | cf | Bemerkung |
|---|---|---:|---:|---|
| der / die / und | | 2.280 / 2.177 / 1.243 | 11.486 / 8.803 / 2.996 | sehr häufig |
| Vertrag | `vertrag` | 188 | 351 | mittel |
| Schadensersatz | `schadensersatz` | 77 | 99 | mittel |
| Gläubiger | `gläubiger` | 215 | 380 | Umlaut |
| Maßgabe, MASSGABE | `massgabe` | 80 | 96 | ß → ss, beide Schreibweisen gleich |
| Verbindung | `verbindung` | 16 | 21 | selten |
| Fehler | `fehler` | 5 | 10 | selten |
| Erbschaftskauf | `erbschaftskauf` | 1 | 1 | nur `bgb_2385.txt`, Position 9 |
| Server, Unauffindbar | | 0 | 0 | fehlen |

Anfangstokens § 1: `beginn der rechtsfähigkeit die rechtsfähigkeit des menschen beginnt mit der vollendung der geburt` (13 Tokens). Phrasen: „nach Maßgabe“ 57 Dokumente/64 Treffer, „im Sinne des“ 62/85, „es sei denn, dass“ 82/85, „nach den Vorschriften über die“ 35/35, „Treu und Glauben“ 7/9, „Beginn der Rechtsfähigkeit“ 1/1 (`bgb_0001.txt`, Start 0), „die die“ 24/29, „Maßgabe nach“ 0.

**Abgleich mit der produktiven Aufbereitung** (`berechne_erwartungen.py abgleichen`, Ergebnis unter `production_comparison`): alle 2.486 Dokumente Token für Token gleich, $D, N, V, P$ gleich, alle Wort-, Phrasen-, AND/OR- und Teilmengenerwartungen gleich mit `search_direct_word`, `search_index_word`, `search_direct_boolean`, `search_index_boolean` (beide Varianten), `search_direct_phrase`, `search_index_phrase` und `search_direct_substring`. **Es gibt keine Abweichung.** Der Grund steht im Zeichenbestand: Außer ASCII kommen nur § Ä Ö Ü ß ä ö ü „ “ vor. Zeichen der Kategorien No, Nl, Mn, Mc, Cf oder Pc (hochgestellte Ziffern, römische Zahlzeichen, kombinierende Akzente, weiche Trennstriche, Unterstrich) fehlen. Die bewusst abweichende Gegenprobe `[^\W_]+`, die No/Nl mitzählen würde, ergibt deshalb ebenfalls in keinem Dokument einen Unterschied. Das ist eine Eigenschaft dieses Abrufstands, keine allgemeine Gleichheit der beiden Regeln.

## Vorschläge für Realanfragen

Vollständige Daten (Dokumentlisten, Positionen, Hashes) in `anfragevorschlaege.json`. Nur Vorschläge, die Auswahl treffen die Reihen.

- **Reihe 01 (direkte Suche):** früher Treffer „Beginn“ (`bgb_0001.txt`, Position 0, df 52),
  „Rechtsfähigkeit“ (Position 2 im ersten Dokument, df 11), häufig „der“ (df 2.280), spät und selten
  „Erbschaftskauf“ (nur letztes Dokument), fehlend „Server“. Die direkte Suche öffnet immer alle
  Dokumente und bricht nur innerhalb eines Dokuments ab: Tokenvergleiche „der“ 37.889, „Vertrag“
  191.941, „Erbschaftskauf“ 213.615, „Server“ 213.718 (= $N$). Wort- gegen Teilzeichensuche:
  „Vertrag“ 188 gegen 453 Dokumente, „Fehler“ 5 gegen 20 (fehlerhaft, Behandlungsfehler), „Server“
  0 gegen 2 (Wasserverbrauch, Wasserversorgungsunternehmen).
- **Reihe 02 (Aufbau/Speicher, erste $k$ Dokumente in Kennungsordnung):**

  | Teilmenge | letzte Kennung | $N$ | $V$ | $P$ |
  |---|---|---:|---:|---:|
  | erste 250 | `bgb_0241a.txt` | 16.899 | 2.577 | 11.077 |
  | erste 500 | `bgb_0439.txt` | 44.221 | 4.699 | 26.529 |
  | erste 1.000 | `bgb_0721.txt` | 103.733 | 7.750 | 61.468 |
  | erste 1.500 | `bgb_1210.txt` | 135.600 | 8.975 | 83.782 |
  | erste 2.000 | `bgb_1838.txt` | 183.132 | 10.595 | 112.759 |
  | alle 2.486 | `bgb_2385.txt` | 213.718 | 11.398 | 133.909 |

Die Teilmengen folgen der Gesetzesreihenfolge und sind thematisch nicht zufällig gemischt. Die ersten 1.000 Paragraphen (bis § 721) sind im Mittel länger als die übrigen 1.486 (103,7 gegen 74,0 Tokens) und enthalten deshalb schon 49 % von $N$. - **Reihe 03 (boolesche Suche):** AND „Mieter Vermieter“ (79/82, 66 Treffer), „Vertrag Schadensersatz“ (188/77, 14), großes Längenverhältnis „Verbindung der“ (16/2.280, Faktor 142,5, 15 Treffer) und „Erbschaftskauf der“ (1/2.280, 1 Treffer) für Galloping Search, dieselbe Anfrage mit häufigem Wort zuerst für die Reihenfolge, drei Begriffe „Gläubiger Schuldner Frist“ (5), fünf Begriffe „Verbindung der die des und“ (12) und „der die des und oder“ (674), fünf mittlere Begriffe mit leerem Schnitt, leer trotz vorhandener Wörter „Mieter Erblasser“ (79/139, 0), leer durch fehlendes Wort „Vertrag Server“. OR mit 2, 3 und 5 Begriffen (bis 2.463 Treffer). AND NOT: „Vertrag Schadensersatz NOT Verbraucher“ 14 → 9 Treffer, „Gläubiger Schuldner NOT Frist“ 88 → 83. - **Reihe 04 (Phrasen):** Länge 2 „nach Maßgabe“ (57/64), „grobe Fahrlässigkeit“ (11/11), „Bürgerlichen Gesetzbuchs“ (1/1), „der die“ (beide Wörter sehr häufig, Phrase nur 32/34); Länge 3 „im Sinne des“ (62/85), „es sei denn“ (131/143), „Beginn der Rechtsfähigkeit“ (1/1); Länge 4 „es sei denn, dass“ (82/85), „Vorsatz und grobe Fahrlässigkeit“ (6/6), „nach Treu und Glauben“ (1/1); Länge 5 „nach den Vorschriften über die“ (35/35), „mit Rücksicht auf die Verkehrssitte“ (2/2); falsche Reihenfolge „Maßgabe nach“, „des Sinne im“, „Glauben und Treu“ (je 0); wiederholtes Wort „die die“ (24/29); Beispielphrase der Arbeit „Verbindung zum Server“ (0). - **Reihe 05 (Profile):** Wort fehlt „Server“, häufig „der“, selten „Verbindung“ (df 16), sehr selten „Erbschaftskauf“ (df 1), AND drei „Gläubiger Schuldner Frist“ (5), OR drei „Mieter Vermieter Miete“ (105), Phrase drei „im Sinne des“ (62 Dokumente, 85 Starts).

## Befehle

Aus der Repositorywurzel:

```sh
# Offline: aus der archivierten ZIP neu erzeugen bzw. byteweise prüfen
.venv/bin/python daten/real/bgb/erzeuge_korpus.py umwandeln
.venv/bin/python daten/real/bgb/erzeuge_korpus.py pruefen
# Unabhängige Erwartungen und Vorschläge berechnen, danach mit dem Produktivcode abgleichen
.venv/bin/python daten/real/bgb/berechne_erwartungen.py berechnen
.venv/bin/python daten/real/bgb/berechne_erwartungen.py abgleichen
# Test (ohne Netzwerk, darin auch die Offline-Neuerzeugung in einem temporären Ordner)
.venv/bin/python -m pytest themen/01_textaufbereitung_direkte_suche/tests/test_real_bgb.py -q
# Beispielsuchen
.venv/bin/python -m direkte_suche --corpus daten/real/bgb/dokumente --query Erbschaftskauf
.venv/bin/python -m experimentelle_analyse search --corpus daten/real/bgb/dokumente --kind phrase --method index --query "Treu und Glauben"
```

`erzeuge_korpus.py herunterladen` lädt die ZIP erneut. Es verweigert das Überschreiben der archivierten ZIP ohne `--ersetzen`. Ein neuer Abruf ist ein neuer Datenstand (Gesetze ändern sich) und braucht eine neue Datensatz-ID statt `-v1`.

## Grenzen

- Fester Abrufstand. Spätere Gesetzesänderungen werden nicht übernommen.
- Juristischer Wortschatz: kaum Informatikbegriffe (df(fehler) = 5, df(server) = 0). Die laufenden
  Beispiele der Arbeit bleiben beim Beispielkorpus D0–D5.
- Sehr ungleiche Dokumentlängen (8 bis 1.168 Tokens) und viele Zahlen-Tokens aus Verweisen
  („§ 312a Absatz 1“). Komposita und Flexionsformen bleiben eigene Tokens („Schadensersatzpflicht“
  und „Schadensersatzes“ treffen nicht „Schadensersatz“).
- Die Messskripte der Themen 01 bis 05 prüfen bisher fest auf genau ein Realdokument (Kafka) und
  müssen für diesen Korpus umgestellt werden. Das ist nicht Teil dieses Datensatzes.
