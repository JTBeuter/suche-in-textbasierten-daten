# Reihe 03, Realteil BGB

Neuer Realteil der Reihe 03 auf dem BGB (`daten/real/bgb/dokumente/`, 2.486 Paragraphen, ein Paragraph je Dokument, Kennung = Dateiname). Nur der Realteil wird neu gemessen. Die synthetische Reihe 03 (`ergebnisse/messungen/03_boolesche_mehrwortsuche/`) und der Kafka-Realteil bleiben unverändert und sind mit `../verify_results.py --archive-only` prüfbar.

## Verfahren und Anfragen

Gemessen werden die öffentlichen Funktionen `search_direct_boolean` (direkte Referenz, alle Anfragen) und `search_index_boolean` mit `input_order`, `shortest_first` und `galloping` (AND und AND NOT) sowie `input_order` (OR). Normalisieren, Postings sammeln, Sortieren, Differenz bei AND NOT und die vollständige Ergebnisliste gehören zur Abfragezeit.

| Kennung | Anfrage | Listenlängen | Treffer | Zweck |
| --- | --- | --- | ---: | --- |
| `and_k2_selten_vorn` | Verbindung AND der | 16/2.280 | 15 | Reihenfolge kurz vorn, großes Längenverhältnis |
| `and_k2_haeufig_vorn` | der AND Verbindung | 2.280/16 | 15 | Reihenfolge lang vorn |
| `and_k2_extrem` | Erbschaftskauf AND der | 1/2.280 | 1 | Galloping bei extremem Verhältnis |
| `and_k2_aehnlich` | Mieter AND Vermieter | 79/82 | 66 | Galloping bei ähnlichen Längen |
| `and_k2_mittel` | Vertrag AND Schadensersatz | 188/77 | 14 | k = 2, Grundlage für AND NOT |
| `and_k3_mittel` | Gläubiger AND Schuldner AND Frist | 215/145/165 | 5 | k = 3 |
| `and_k5_mittel` | Vertrag AND Schadensersatz AND Frist AND Gläubiger AND Schuldner | 188/77/165/215/145 | 0 | k = 5, leerer Schnitt |
| `and_k5_selten_vorn` | Verbindung AND der AND die AND des AND und | 16/2.280/2.177/1.844/1.243 | 12 | k = 5, seltenes Wort vorn |
| `and_k5_selten_hinten` | und AND des AND die AND der AND Verbindung | 1.243/1.844/2.177/2.280/16 | 12 | Reihenfolge bei k = 5 |
| `and_k5_haeufig` | der AND die AND des AND und AND oder | 2.280/2.177/1.844/1.243/1.391 | 674 | k = 5, ähnliche Längen, großes Ergebnis |
| `and_leer_vorhanden` | Mieter AND Erblasser | 79/139 | 0 | leer, obwohl beide Wörter vorkommen |
| `or_k2_mittel` | Vertrag OR Schadensersatz | 188/77 | 251 | OR, k = 2 |
| `or_k3_mittel` | Gläubiger OR Schuldner OR Frist | 215/145/165 | 420 | OR, k = 3 |
| `or_k5_haeufig` | der OR die OR des OR und OR oder | 2.280/2.177/1.844/1.243/1.391 | 2.463 | OR mit großer Ergebnismenge |
| `and_not_k2` | Vertrag AND Schadensersatz AND NOT Verbraucher | 188/77, NOT 106 | 9 (14 vor dem Ausschluss) | AND NOT |

Alle Anfragen stammen aus `daten/real/bgb/anfragevorschlaege.json` (Abschnitt `reihe_03_boolesche_suche`), `and_k5_selten_hinten` als Permutation von `and_k5_selten_vorn`. Vor dem ersten Timer werden geprüft: Dateien, Bytes und SHA-256 gegen `manifest.json`, der kanonische Korpushash, eine eigene Regex-Tokenisierung gegen `prepare_corpus`, der Index gegen unabhängig gebildete Postings, Dokumentfrequenzen gegen Vorschläge und Manifest, Trefferlisten (vollständig oder Anzahl, SHA-256 und Ränder) gegen die Vorschläge sowie direkte Suche und alle Indexvarianten gegen diese Erwartung. Vergleichszähler (`../boolean_diagnostics.py`, bei AND NOT inklusive Differenz) und die besuchten Tokens der direkten Suche entstehen getrennt außerhalb der Timer.

## Befehle

Aus dem Repository-Verzeichnis.

```sh
# Pilot (sperrt Parameter, Messcode und PYTHONHASHSEED)
PYTHONHASHSEED=0 .venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/bgb/run.py --pilot
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/bgb/verify_results.py --eingabe 03_bgb_pilot

# Finallauf (nur auf ruhiger Maschine)
PYTHONHASHSEED=0 .venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/bgb/run.py \
    --ausgabe 03_bgb --pilot-ordner 03_bgb_pilot --hintergrundlast "TEXT"
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/bgb/verify_results.py --eingabe 03_bgb
.venv/bin/python themen/03_boolesche_mehrwortsuche/experimente/bgb/analyse.py --eingabe 03_bgb
```

Laufkonvention wie die neue Reihe 01 (gemeinsamer Code in `../messlauf03.py`, auch für 03b): `--ausgabe NAME` wählt einen neuen Ordner unter `ergebnisse/messungen` (Standard `03_bgb_pilot` bzw. `03_bgb`), `--pilot-ordner NAME` den Pilot für den Finallauf, `--hintergrundlast TEXT` landet in `metadata.json`. Ein nicht leerer Ordner wird nie überschrieben, ein Pilot nur mit `--pilot --replace-pilot` bewusst ersetzt. Pilot und Finallauf verlangen `PYTHONHASHSEED=0`. Der Finallauf bricht ab, wenn Parameter, Messcode oder Hashseed vom Pilot abweichen. Gebunden sind `gemeinsam/src/gemeinsam/*.py`, `invertierter_index`, `boolesche_suche`, alle `*.py` dieses Ordners, `../boolean_diagnostics.py`, `../messlauf03.py`, `gemeinsam/__init__.py`, `pyproject.toml` und `requirements-dev.txt`.

Messplan wie Reihe 03: Pilot 1 Warmup und 3 Wiederholungen, Final 5 Warmups und 20 Wiederholungen, Blöcke mit 5 vollständigen Aufrufen, alle zulässigen (Verfahren, Anfrage)-Blöcke je Wiederholung mit festem Seed gemischt, Laden, Aufbereitung und Aufbau getrennt mit `measure_phase`. Ausgabe: `raw.csv` (gemeinsames Schema, `query_type` `and`, `or` oder `and_not`), `summary.json`, `metadata.json` (Parameter, Umgebung, Git-Stand, Hintergrundlast, Hashes von Manifest und Vorschlägen, Anfragen mit Zweck, Listenlängen, Trefferlisten und Diagnosen), `code_source/`, beim Pilot `pilot_decision.json`. `verify_results.py` prüft Schema, Blockzeiten, Statistik, Reihenfolge, Quellarchive, den aktiven Code (außer mit `--archive-only`) und wiederholt alle Daten- und Anfrageprüfungen. `analyse.py` schreibt `comparisons.json` und `auswertung.md` in den Messordner.

Tests: `themen/03_boolesche_mehrwortsuche/experimente/tests/test_bgb_03.py`.
