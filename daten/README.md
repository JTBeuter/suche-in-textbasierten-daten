# Daten

| Ordner | Inhalt |
|---|---|
| `beispiele/` | Kleine Textbeispiele und Suchanfragen mit vorab bekannten Treffern für Tests und Demonstrationen. |
| `real/kafka_verwandlung/` | Acht feste Absätze aus Kafkas deutschem Originaltext, archivierte Quelle, Manifest, Nutzungsbedingungen und SHA-256. |
| `roh/` | Ursprüngliche oder erzeugte Textdateien vor der gemeinsamen Aufbereitung. |
| `aufbereitet/` | Aus den Rohdaten abgeleitete Dokumente und Tokenfolgen für die Suchverfahren. |

Für jeden späteren Datensatz werden Herkunft beziehungsweise Erzeugungsverfahren, Umfang und relevante Eigenschaften festgehalten. Bei erzeugten Daten gehören die Parameter und der Zufallsstartwert dazu. Bei aufbereiteten Daten werden der zugehörige Rohdatensatz und die verwendeten Aufbereitungsregeln dokumentiert.

Die Testdaten und Abfragesätze werden durch [Bereich 05](../themen/05_experimentelle_analyse/) koordiniert. Die Aufbereitung wird mit [Bereich 01](../themen/01_textaufbereitung_direkte_suche/) abgestimmt. Alle zu vergleichenden Verfahren verwenden dieselbe Datengrundlage.

`beispiele/d0_d5/` enthält die sechs Texte des Implementation Plans;
`beispiele/d0_d5_expected.json` enthält unabhängig festgelegte Tokens,
Worttreffer und Phrasenstarts. Im festen realen Korpus wird nur `01_anfang.txt`
gesucht; das Quellenarchiv mit Endung `.pg` und JSON/README sind außerhalb des
`.txt`-Ladefilters. Generierte Skalierungskorpora werden in temporären Verzeichnissen
erzeugt; Generatorfassung, Seed und jede Dateiprüfsumme stehen in den Messmetadaten.
Die Wiedererzeugung wurde geprüft. Große Zwischenstände werden nicht versioniert.
