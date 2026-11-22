# Fester realer Korpus: Kafka, Die Verwandlung

Datensatz `kafka-verwandlung-anfang-v1`, abgerufen am **6. Oktober 2026**.
Quelle: [Project Gutenberg, eBook 22367](https://www.gutenberg.org/ebooks/22367),
Franz Kafka (1883–1924), deutscher Originaltext. Der Katalog nennt den
21. August 2007 als Veröffentlichung des eBooks und den 29. Dezember 2017
als letzte inhaltliche Aktualisierung. Der tatsächlich empfangene HTTP-Header
`Last-Modified` nennt zusätzlich den 9. September 2026; diese Angaben sind
verschiedene Metadaten und werden im Manifest getrennt festgehalten.

## Auswahl und Umwandlung

`quelle.pg` archiviert den vollständig abgerufenen UTF-8-Quellstand einschließlich
Herkunftsangaben und Project-Gutenberg-Lizenz. Seine Endung ist bewusst nicht
`.txt`, damit `load_corpus` ihn nicht versehentlich als zweites Dokument liest.
`01_anfang.txt` ist die einzige Korpusdatei: acht durch Leerzeilen getrennte
Absätze vom Beginn des Abschnitts I, ab „Als Gregor Samsa eines Morgens“ bis
unmittelbar vor „Die Decke abzuwerfen war ganz einfach;“.
Die Endmarker sind im Quellenarchiv eindeutig.

Die Umwandlung decodiert strikt UTF-8, vereinheitlicht CRLF/CR zu LF, entfernt
nur äußeren Leerraum des ausgewählten Bereichs und ergänzt einen abschließenden
Zeilenumbruch. Die umbrochenen Prosa-Zeilen bleiben erhalten. Titel,
Abschnittsnummer, Quellenkopf und Lizenzfooter gehören nicht zum Suchkorpus.
Es gibt keine Rechtschreibkorrektur, Übersetzung oder inhaltliche Kürzung innerhalb
der Auswahl. Der Loader liest diese gespeicherte Datei einmal als ein Dokument;
die Suchaufbereitung erfolgt erst danach über die gemeinsame API.

`manifest.json` enthält Abrufzeit mit Zeitzone, Quell-URL, Auswahlmarker,
Dateizuordnung, Bytegrößen und SHA-256-Prüfsummen sowie explizite erwartete
Anfangstokens und Wortpositionen für die erste Untersuchung. Die Erwartungen
wurden am sichtbaren Auszug und ergänzend mit einem unabhängigen Regexdurchlauf
geprüft; sie werden nicht aus der produktiven Tokenisierung abgeleitet.

## Nutzungsbedingungen

Der [Katalog](https://www.gutenberg.org/ebooks/22367) kennzeichnet den Text als
„Public domain in the USA“. Die [Permission-Hinweise](https://www.gutenberg.org/policy/permission.html)
erlauben nichtkommerzielle Weitergabe und Auszüge und unterscheiden Werkrechte
von der Marke Project Gutenberg. [Nutzungsbedingungen](https://www.gutenberg.org/policy/terms_of_use.html)
und [PG-Lizenz](https://www.gutenberg.org/policy/license.html) sind verlinkt;
die vollständige beim Download enthaltene Lizenz bleibt in `quelle.pg` erhalten.
Es wurde genau ein Werk heruntergeladen, kein Crawler eingerichtet.

Für den deutschen Originaltext folgt aus Kafkas Todesjahr 1924 sowie
[§ 64 UrhG](https://www.gesetze-im-internet.de/urhg/__64.html) und
[§ 69 UrhG](https://www.gesetze-im-internet.de/urhg/__69.html) als eigene Ableitung:
Die Frist endete mit Ablauf 1994. Der ausgewählte Originaltext ist seit 1995
gemeinfrei. Der Korpus enthält keine moderne Übersetzung. Die Herkunftsangabe
besagt keine Zusammenarbeit oder Empfehlung durch Project Gutenberg.

## Wiederholbare Verwendung

Aus dem Repository-Verzeichnis nach Installation:

```sh
.venv/bin/python -m direkte_suche --corpus daten/real/kafka_verwandlung --query Gregor
.venv/bin/python -m pytest themen/01_textaufbereitung_direkte_suche/tests/test_real_corpus.py -q
```

Der erneute Test benötigt kein Netzwerk. Änderungen an der Onlinequelle werden
nicht stillschweigend übernommen: Der archivierte Quellstand und der Auszug
sind Teil der Abgabe. Das kleine Einzeldokument dient einem überprüfbaren
Fließtextbeispiel und erlaubt keine Aussage über repräsentative Suchlasten
oder allgemeine Eigenschaften deutschsprachiger Korpora.
