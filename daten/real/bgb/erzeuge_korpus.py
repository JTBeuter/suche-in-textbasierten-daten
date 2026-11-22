#!/usr/bin/env python3
"""Erzeugt den Realkorpus „BGB nach Paragraphen“ aus dem amtlichen XML.

Nur Standardbibliothek. Aufruf aus der Repositorywurzel:

    python daten/real/bgb/erzeuge_korpus.py herunterladen [--ersetzen]
    python daten/real/bgb/erzeuge_korpus.py umwandeln
    python daten/real/bgb/erzeuge_korpus.py pruefen

``herunterladen`` lädt https://www.gesetze-im-internet.de/bgb/xml.zip genau
einmal, archiviert die ZIP unverändert unter ``quelle/bgb_xml.zip`` und hält
Abrufzeit, HTTP-Status und Antwortheader in ``quelle/abruf.json`` fest.
Anschließend wird wie bei ``umwandeln`` verfahren.

``umwandeln`` arbeitet ohne Netzwerk nur aus der archivierten ZIP, erzeugt
die Dokumente in ``dokumente/`` und schreibt ``manifest.json`` neu. Bereits
vorhandene Abschnitte mit unabhängigen Erwartungen bleiben erhalten, solange
der kanonische Korpushash unverändert ist.

``pruefen`` erzeugt die Dokumente ohne Netzwerk in einem temporären Ordner und
vergleicht sie byteweise mit ``dokumente/`` und mit den Prüfsummen im Manifest.

Die Umwandlungsregeln stehen in ``UMWANDLUNGSREGELN`` und im README.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tempfile
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DATENSATZ_ID = "bgb-gesetze-im-internet-v1"
UMWANDLUNG_VERSION = "bgb-umwandlung-v1"
QUELL_URL = "https://www.gesetze-im-internet.de/bgb/xml.zip"
UEBERSICHT_URL = "https://www.gesetze-im-internet.de/bgb/"
USER_AGENT = "dhbw-textsuche-korpus/1 (Python-urllib; einmaliger Abruf)"

ORDNER = Path(__file__).resolve().parent
ZIP_PFAD = ORDNER / "quelle" / "bgb_xml.zip"
ABRUF_PFAD = ORDNER / "quelle" / "abruf.json"
DOKUMENT_ORDNER = ORDNER / "dokumente"
MANIFEST_PFAD = ORDNER / "manifest.json"

# Abschnitte, die andere Skripte ergänzen und die ``umwandeln`` erhält.
ERHALTENE_ABSCHNITTE = ("independent_expectations", "production_comparison")

# Elemente, die innerhalb von textdaten/text/Content eines Paragraphen
# vorkommen dürfen. Unbekannte Elemente führen zum Abbruch, damit eine
# geänderte Quelle nicht stillschweigend anders umgewandelt wird.
UMBRUCH_DAVOR = frozenset({"P", "DL", "DT", "BR"})  # Zeilenumbruch vor dem Element
UMBRUCH_DANACH = frozenset({"P", "DL"})  # Zeilenumbruch nach dem Element
LEERZEICHEN_DAVOR = frozenset({"DD", "LA"})  # Leerzeichen vor dem Element
INLINE = frozenset({"Content", "I", "NB", "FnR"})  # kein Trenner
ERLAUBTE_ELEMENTE = UMBRUCH_DAVOR | UMBRUCH_DANACH | LEERZEICHEN_DAVOR | INLINE
ERLAUBTE_TEXTKINDER = frozenset({"Content", "Footnotes"})

WEGGEFALLEN = "(weggefallen)"
DATEINAME = re.compile(r"bgb_\d{4}[a-z]*\.txt")
_PARAGRAPH = re.compile(r"§ ?(\d{1,4}) ?([A-Za-z]*)")

UMWANDLUNGSREGELN = (
    "Quelle ist die einzige XML-Datei der unveränderten ZIP von Gesetze im Internet "
    "(DTD gii-norm 1.01); die Datei wird strikt als UTF-8 gelesen und mit "
    "xml.etree.ElementTree geparst.",
    "Ein Dokument entsteht aus jeder Norm, deren metadaten/enbez nach Leerraum-"
    "Normalisierung mit '§' beginnt. Gliederungseinheiten (Buch, Abschnitt, Titel), "
    "die Inhaltsübersicht und Sammeleinträge wie '(XXXX) §§ 3 bis 6' sind keine "
    "Dokumente; die Sammeleinträge werden im Manifest gelistet.",
    "Die Paragraphenbezeichnung steht nur im Dateinamen, nicht im Text.",
    "Erste Zeile ist die Paragraphenüberschrift metadaten/titel, falls vorhanden.",
    "Danach folgt der Normtext aus textdaten/text/Content. Textknoten werden in "
    "Dokumentreihenfolge wie bei itertext() verbunden. Vor P, DL, DT und BR sowie nach "
    "P und DL steht ein Zeilenumbruch, vor DD und LA ein Leerzeichen; I, NB und FnR "
    "erzeugen keinen Trenner. Damit steht jeder Absatz und jeder Listenpunkt "
    "(Nummer und Text) auf einer eigenen Zeile. Andere Elemente im Normtext führen "
    "zum Abbruch.",
    "Fußnoten gehören nicht dazu: textdaten/fussnoten und das Element "
    "textdaten/text/Footnotes (amtliche Hinweise) werden nicht gelesen.",
    "Leerraum je Zeile wird normalisiert: Folgen von Leerraumzeichen nach str.split() "
    "(einschließlich U+00A0) werden zu einem Leerzeichen, Anfang und Ende ohne Leerraum. "
    "Leere Zeilen entfallen.",
    "Weggefallene Paragraphen werden nicht aufgenommen: Überschrift '(weggefallen)' mit "
    "leerem Normtext, Normtext '-' oder Normtext '(weggefallen)', oder keine Überschrift "
    "und Normtext genau '(weggefallen)'. Paragraphen ohne Normtext (leer oder nur '-') "
    "mit anderer Überschrift, etwa '(jetzt § 650)', werden ebenfalls nicht aufgenommen. "
    "Beide Gruppen stehen mit Bezeichnung und Grund im Manifest.",
    "Dateiname bgb_NNNN<suffix>.txt: Nummer vierstellig mit führenden Nullen, "
    "Buchstabensuffix in Kleinbuchstaben; ein Leerzeichen zwischen '§', Nummer und Suffix "
    "ist zulässig ('§ 312 a' -> bgb_0312a.txt). Bezeichnungen mit '§§', mehr als vier "
    "Ziffern oder anderen Zeichen haben keine Dateinamenregel und führen zum Abbruch, "
    "außer sie sind weggefallen. Gleiche Dateinamen führen zum Abbruch.",
    "Die Dateinamen müssen in der Reihenfolge der Normen im XML streng lexikografisch "
    "aufsteigen (Bytevergleich), sonst Abbruch. Damit entspricht die Sortierung der "
    "Dokumentkennungen der Gesetzesreihenfolge.",
    "Kodierung UTF-8 ohne BOM, Zeilenende LF, genau ein abschließender Zeilenumbruch. "
    "Unicode-Normalisierung und Case Folding werden nicht vorab angewandt; das übernimmt "
    "die gemeinsame Aufbereitung (NFC -> casefold -> NFC).",
)


class UmwandlungsFehler(ValueError):
    """Die Quelle passt nicht zu den festgelegten Umwandlungsregeln."""


@dataclass(frozen=True)
class Dokument:
    paragraph: str
    dateiname: str
    doknr: str
    titel: str | None
    zeilen: tuple[str, ...]

    @property
    def inhalt(self) -> bytes:
        return ("\n".join(self.zeilen) + "\n").encode("utf-8")


@dataclass(frozen=True)
class Ergebnis:
    dokumente: tuple[Dokument, ...]
    ausgeschlossen: tuple[dict, ...]
    sammeleintraege: tuple[dict, ...]
    zaehlung: dict
    stand: dict
    xml_info: dict


def sha256(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


def _leerraum(text: str) -> str:
    return " ".join(text.split())


def _sammle(element: ET.Element, teile: list[str], paragraph: str) -> None:
    tag = element.tag
    if tag not in ERLAUBTE_ELEMENTE:
        raise UmwandlungsFehler(f"{paragraph}: unbekanntes Element <{tag}> im Normtext")
    if tag in UMBRUCH_DAVOR:
        teile.append("\n")
    elif tag in LEERZEICHEN_DAVOR:
        teile.append(" ")
    if element.text:
        teile.append(element.text)
    for kind in element:
        _sammle(kind, teile, paragraph)
        if kind.tail:
            teile.append(kind.tail)
    if tag in UMBRUCH_DANACH:
        teile.append("\n")


def normtext_zeilen(norm: ET.Element, paragraph: str) -> tuple[str, ...]:
    """Zeilen des Normtexts ohne Fußnoten, Leerraum je Zeile normalisiert."""
    text = norm.find("textdaten/text")
    if text is None:
        return ()
    for kind in text:
        if kind.tag not in ERLAUBTE_TEXTKINDER:
            raise UmwandlungsFehler(f"{paragraph}: unerwartetes Element <{kind.tag}> in text")
    if (text.text or "").strip():
        raise UmwandlungsFehler(f"{paragraph}: Text außerhalb von Content")
    content = text.find("Content")
    if content is None:
        return ()
    teile: list[str] = []
    _sammle(content, teile, paragraph)
    zeilen = (_leerraum(zeile) for zeile in "".join(teile).split("\n"))
    return tuple(zeile for zeile in zeilen if zeile)


def titel_von(norm: ET.Element) -> str | None:
    element = norm.find("metadaten/titel")
    if element is None:
        return None
    titel = _leerraum("".join(element.itertext()))
    return titel or None


def ausschlussgrund(titel: str | None, zeilen: tuple[str, ...], paragraph: str) -> str | None:
    """'weggefallen', 'ohne_normtext' oder None für ein aufzunehmendes Dokument."""
    normtext_leer = zeilen in ((), ("-",))
    if titel == WEGGEFALLEN and (normtext_leer or zeilen == (WEGGEFALLEN,)):
        return "weggefallen"
    if titel is None and zeilen == (WEGGEFALLEN,):
        return "weggefallen"
    if titel == WEGGEFALLEN:
        raise UmwandlungsFehler(f"{paragraph}: Überschrift weggefallen, aber Normtext vorhanden")
    if normtext_leer:
        return "ohne_normtext"
    return None


def dateiname_fuer(paragraph: str) -> str:
    """'§ 1' -> 'bgb_0001.txt', '§ 312a' -> 'bgb_0312a.txt'."""
    treffer = _PARAGRAPH.fullmatch(paragraph)
    if treffer is None:
        raise UmwandlungsFehler(f"Keine Dateinamenregel für Bezeichnung {paragraph!r}")
    nummer, suffix = treffer.groups()
    return f"bgb_{int(nummer):04d}{suffix.lower()}.txt"


def _xml_aus_zip(zip_bytes: bytes) -> tuple[str, zipfile.ZipInfo, bytes]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archiv:
        eintraege = archiv.infolist()
        if len(eintraege) != 1 or not eintraege[0].filename.endswith(".xml"):
            namen = [eintrag.filename for eintrag in eintraege]
            raise UmwandlungsFehler(f"ZIP muss genau eine XML-Datei enthalten, gefunden: {namen}")
        eintrag = eintraege[0]
        return eintrag.filename, eintrag, archiv.read(eintrag)


def _stand(wurzel: ET.Element, rahmen: ET.Element) -> dict:
    metadaten = rahmen.find("metadaten")
    fundstellen = [
        f"{f.findtext('periodikum', '')} {f.findtext('zitstelle', '')}".strip()
        for f in metadaten.findall("fundstelle")
    ]
    return {
        "doknr": wurzel.get("doknr"),
        "builddate": wurzel.get("builddate"),
        "jurabk": metadaten.findtext("jurabk"),
        "amtabk": metadaten.findtext("amtabk"),
        "long_title": metadaten.findtext("langue"),
        "ausfertigung_datum": metadaten.findtext("ausfertigung-datum"),
        "fundstelle": fundstellen,
        "standangaben": [
            {"standtyp": s.findtext("standtyp"), "standkommentar": s.findtext("standkommentar")}
            for s in metadaten.findall("standangabe")
        ],
    }


def wandle_um(zip_bytes: bytes) -> Ergebnis:
    """Reine Umwandlung ohne Dateizugriff; deterministisch für dieselben Bytes."""
    xml_name, eintrag, xml_bytes = _xml_aus_zip(zip_bytes)
    try:
        xml_text = xml_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as fehler:
        raise UmwandlungsFehler("XML ist kein gültiges UTF-8") from fehler
    if xml_text.startswith("﻿"):
        raise UmwandlungsFehler("XML beginnt unerwartet mit BOM")
    dtd = re.search(r'<!DOCTYPE\s+\w+\s+SYSTEM\s+"([^"]+)"', xml_text[:500])
    wurzel = ET.fromstring(xml_bytes)
    normen = wurzel.findall("norm")
    if not normen:
        raise UmwandlungsFehler("XML enthält keine Normen")

    dokumente: list[Dokument] = []
    ausgeschlossen: list[dict] = []
    sammeleintraege: list[dict] = []
    zaehlung = {"norms_total": len(normen), "norms_without_enbez": 0,
                "norms_other_enbez": 0, "norms_with_paragraph": 0}
    for norm in normen:
        enbez = _leerraum(norm.findtext("metadaten/enbez") or "")
        doknr = norm.get("doknr", "")
        if not enbez:
            zaehlung["norms_without_enbez"] += 1
            continue
        if not enbez.startswith("§"):
            zaehlung["norms_other_enbez"] += 1
            if "§" in enbez:
                titel = titel_von(norm)
                zeilen = normtext_zeilen(norm, enbez)
                sammeleintraege.append({"enbez": enbez, "doknr": doknr, "title": titel,
                                        "normtext": list(zeilen)})
            continue
        zaehlung["norms_with_paragraph"] += 1
        titel = titel_von(norm)
        zeilen = normtext_zeilen(norm, enbez)
        grund = ausschlussgrund(titel, zeilen, enbez)
        if enbez.startswith("§§"):
            if grund != "weggefallen":
                raise UmwandlungsFehler(f"Keine Dateinamenregel für Sammelbezeichnung {enbez!r}")
            sammeleintraege.append({"enbez": enbez, "doknr": doknr, "title": titel,
                                    "normtext": list(zeilen)})
            continue
        if grund is not None:
            ausgeschlossen.append({"paragraph": enbez, "reason": grund, "doknr": doknr,
                                   "title": titel, "normtext": list(zeilen)})
            continue
        dokumente.append(Dokument(enbez, dateiname_fuer(enbez), doknr, titel,
                                  ((titel,) if titel else ()) + zeilen))

    namen = [dokument.dateiname for dokument in dokumente]
    if len(set(namen)) != len(namen):
        doppelt = sorted({name for name in namen if namen.count(name) > 1})
        raise UmwandlungsFehler(f"Dateinamenkollision: {doppelt}")
    for vorher, nachher in zip(namen, namen[1:]):
        if not vorher.encode("utf-8") < nachher.encode("utf-8"):
            raise UmwandlungsFehler(f"Reihenfolge verletzt: {vorher} vor {nachher}")
    for dokument in dokumente:
        if not DATEINAME.fullmatch(dokument.dateiname):
            raise UmwandlungsFehler(f"Ungültiger Dateiname {dokument.dateiname}")
        if any("\n" in zeile or zeile != zeile.strip() for zeile in dokument.zeilen):
            raise UmwandlungsFehler(f"{dokument.paragraph}: Zeile nicht normalisiert")

    zaehlung.update({
        "documents": len(dokumente),
        "excluded_repealed": sum(1 for a in ausgeschlossen if a["reason"] == "weggefallen"),
        "excluded_without_normtext": sum(1 for a in ausgeschlossen if a["reason"] == "ohne_normtext"),
        "collective_entries": len(sammeleintraege),
    })
    xml_info = {
        "zip_member": xml_name,
        "zip_member_bytes": eintrag.file_size,
        "zip_member_sha256": sha256(xml_bytes),
        "zip_member_timestamp": "%04d-%02d-%02dT%02d:%02d:%02d" % eintrag.date_time,
        "doctype_system": dtd.group(1) if dtd else None,
        "encoding": "UTF-8",
        "xml_is_nfc": unicodedata.is_normalized("NFC", xml_text),
        "nfc_check": "unicodedata.is_normalized('NFC', ...) über das gesamte decodierte XML",
    }
    return Ergebnis(tuple(dokumente), tuple(ausgeschlossen), tuple(sammeleintraege),
                    zaehlung, _stand(wurzel, normen[0]), xml_info)


def schreibe_dokumente(dokumente: tuple[Dokument, ...], ziel: Path) -> None:
    """Schreibt nur bgb_*.txt; ersetzt vorhandene bgb_*.txt, weist Fremddateien ab."""
    ziel.mkdir(parents=True, exist_ok=True)
    vorhandene = sorted(ziel.iterdir())
    fremd = [p.name for p in vorhandene
             if p.is_symlink() or not p.is_file() or not DATEINAME.fullmatch(p.name)]
    if fremd:
        raise UmwandlungsFehler(f"Fremde Einträge im Dokumentordner {ziel}: {fremd}")
    for pfad in vorhandene:
        pfad.unlink()
    for dokument in dokumente:
        (ziel / dokument.dateiname).write_bytes(dokument.inhalt)


def kanonischer_hash(eintraege: list[tuple[str, str]]) -> str:
    """SHA-256 über '<sha256>  <dateiname>\\n' je Datei in Bytereihenfolge der Namen.

    Entspricht ``export LC_ALL=C; sha256sum *.txt | sha256sum`` im Dokumentordner.
    LC_ALL muss vor der Globexpansion gelten, sonst sortiert die Shell nach
    Locale (z. B. bgb_0031a.txt vor bgb_0031.txt).
    """
    zeilen = "".join(f"{digest}  {name}\n" for name, digest in sorted(eintraege))
    return sha256(zeilen.encode("utf-8"))


# ---------------------------------------------------------------- JSON-Ausgabe

def _skalar(wert: object) -> bool:
    return not isinstance(wert, (dict, list))


def _flach(wert: object) -> bool:
    if isinstance(wert, list):
        # Listen langer Texte (z. B. Regeln) werden zeilenweise ausgegeben.
        return all(_skalar(element) and not (isinstance(element, str) and len(element) > 100)
                   for element in wert)
    if isinstance(wert, dict):
        return all(_skalar(v) or (isinstance(v, list) and _flach(v)) for v in wert.values())
    return True


def json_text(wert: object, ebene: int = 0, in_liste: bool = False) -> str:
    """Eingerücktes JSON; Skalarlisten und flache Listeneinträge stehen auf einer Zeile."""
    if (_skalar(wert) or (isinstance(wert, list) and _flach(wert))
            or (in_liste and isinstance(wert, dict) and _flach(wert))):
        return json.dumps(wert, ensure_ascii=False)
    einzug = "  " * (ebene + 1)
    ende = "  " * ebene
    if isinstance(wert, dict):
        if not wert:
            return "{}"
        teile = [f"{einzug}{json.dumps(k, ensure_ascii=False)}: {json_text(v, ebene + 1)}"
                 for k, v in wert.items()]
        return "{\n" + ",\n".join(teile) + "\n" + ende + "}"
    teile = [f"{einzug}{json_text(v, ebene + 1, True)}" for v in wert]
    return "[\n" + ",\n".join(teile) + "\n" + ende + "]"


def schreibe_json(pfad: Path, wert: object) -> None:
    pfad.write_bytes((json_text(wert) + "\n").encode("utf-8"))


def lies_json(pfad: Path) -> dict:
    return json.loads(pfad.read_bytes().decode("utf-8"))


# ---------------------------------------------------------------- Modi

def herunterladen(ersetzen: bool) -> None:
    if ZIP_PFAD.exists() and not ersetzen:
        raise SystemExit(f"{ZIP_PFAD} existiert bereits; zum Ersetzen --ersetzen angeben.")
    anfrage = urllib.request.Request(QUELL_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(anfrage, timeout=120) as antwort:
        abgerufen = datetime.now().astimezone().isoformat(timespec="seconds")
        status = antwort.status
        header = {name.lower(): wert for name, wert in antwort.headers.items()}
        daten = antwort.read()
    if status != 200:
        raise SystemExit(f"HTTP-Status {status}")
    if "content-length" in header and int(header["content-length"]) != len(daten):
        raise SystemExit("Content-Length passt nicht zur empfangenen Bytezahl")
    wandle_um(daten)  # prüft die ZIP vor dem Archivieren
    ZIP_PFAD.parent.mkdir(parents=True, exist_ok=True)
    temporaer = ZIP_PFAD.with_suffix(".zip.tmp")
    temporaer.write_bytes(daten)
    temporaer.replace(ZIP_PFAD)
    schreibe_json(ABRUF_PFAD, {
        "url": QUELL_URL,
        "retrieved_at": abgerufen,
        "user_agent": USER_AGENT,
        "http_status": status,
        "http_headers": header,
        "bytes": len(daten),
        "sha256": sha256(daten),
    })
    print(f"ZIP archiviert: {ZIP_PFAD} ({len(daten)} Bytes, SHA-256 {sha256(daten)})")


def _lies_archiv() -> tuple[bytes, dict]:
    if not ZIP_PFAD.is_file() or not ABRUF_PFAD.is_file():
        raise SystemExit("Archivierte ZIP oder abruf.json fehlt; zuerst 'herunterladen'.")
    daten = ZIP_PFAD.read_bytes()
    abruf = lies_json(ABRUF_PFAD)
    if len(daten) != abruf["bytes"] or sha256(daten) != abruf["sha256"]:
        raise SystemExit("Archivierte ZIP passt nicht zu quelle/abruf.json.")
    return daten, abruf


def baue_manifest(ergebnis: Ergebnis, zip_bytes: bytes, abruf: dict, alt: dict | None) -> dict:
    eintraege = [{"paragraph": d.paragraph, "document_id": d.dateiname,
                  "source_path": d.dateiname, "title": d.titel, "doknr": d.doknr,
                  "lines": len(d.zeilen), "bytes": len(d.inhalt), "sha256": sha256(d.inhalt)}
                 for d in ergebnis.dokumente]
    korpus_hash = kanonischer_hash([(e["document_id"], e["sha256"]) for e in eintraege])
    header = abruf["http_headers"]
    manifest = {
        "dataset_id": DATENSATZ_ID,
        "title": "Bürgerliches Gesetzbuch (BGB), ein Paragraph je Dokument",
        "language": "de",
        "corpus_root": "dokumente",
        "publisher": ("Bundesministerium der Justiz und für Verbraucherschutz und Bundesamt "
                      "für Justiz, Angebot „Gesetze im Internet“; technische Bereitstellung "
                      "juris GmbH"),
        "catalogue_url": UEBERSICHT_URL,
        "download_url": abruf["url"],
        "retrieved_at": abruf["retrieved_at"],
        "http_status": abruf["http_status"],
        "http_last_modified": header.get("last-modified"),
        "http_etag": header.get("etag"),
        "http_content_length": header.get("content-length"),
        "http_date": header.get("date"),
        "source_file": "quelle/bgb_xml.zip",
        "source_bytes": len(zip_bytes),
        "source_sha256": sha256(zip_bytes),
        "retrieval_record": "quelle/abruf.json",
        "source_xml": ergebnis.xml_info,
        "law_status": ergebnis.stand,
        "conversion": {
            "script": "erzeuge_korpus.py",
            "version": UMWANDLUNG_VERSION,
            "python": sys.version.split()[0],
            "unicodedata_version": unicodedata.unidata_version,
            "rules": list(UMWANDLUNGSREGELN),
        },
        "rights": {
            "basis": "§ 5 Abs. 1 UrhG: Gesetze genießen keinen urheberrechtlichen Schutz.",
            "norm_url": "https://www.gesetze-im-internet.de/urhg/__5.html",
            "provider_statement": ("Startseite gesetze-im-internet.de: „Die Rechtsnormen in "
                                   "deutscher Sprache stehen in allen angebotenen Formaten zur "
                                   "freien Nutzung und Weiterverwendung zur Verfügung.“"),
            "attribution": "Quelle wird trotz fehlender Lizenzauflage genannt.",
        },
        "counts": {**ergebnis.zaehlung,
                   "raw_bytes": sum(e["bytes"] for e in eintraege)},
        "corpus_sha256": korpus_hash,
        "corpus_sha256_method": ("SHA-256 über die UTF-8-Bytes der Zeilen '<sha256>  <dateiname>\\n' "
                                 "aller Dokumente in Bytereihenfolge der Dateinamen; entspricht "
                                 "'cd dokumente && (export LC_ALL=C; sha256sum *.txt | sha256sum)'. "
                                 "LC_ALL muss vor der Globexpansion gelten."),
        "excluded_paragraphs": list(ergebnis.ausgeschlossen),
        "collective_entries": list(ergebnis.sammeleintraege),
        "documents": eintraege,
    }
    if alt:
        for abschnitt in ERHALTENE_ABSCHNITTE:
            if abschnitt not in alt:
                continue
            if alt[abschnitt].get("corpus_sha256") == korpus_hash:
                manifest[abschnitt] = alt[abschnitt]
            else:
                print(f"Hinweis: Abschnitt {abschnitt} verworfen (Korpushash geändert).",
                      file=sys.stderr)
    return manifest


def umwandeln() -> None:
    zip_bytes, abruf = _lies_archiv()
    ergebnis = wandle_um(zip_bytes)
    schreibe_dokumente(ergebnis.dokumente, DOKUMENT_ORDNER)
    alt = lies_json(MANIFEST_PFAD) if MANIFEST_PFAD.is_file() else None
    manifest = baue_manifest(ergebnis, zip_bytes, abruf, alt)
    schreibe_json(MANIFEST_PFAD, manifest)
    z = ergebnis.zaehlung
    print(f"{z['documents']} Dokumente geschrieben, {z['excluded_repealed']} weggefallen, "
          f"{z['excluded_without_normtext']} ohne Normtext, Korpushash {manifest['corpus_sha256']}")


def pruefen() -> int:
    zip_bytes, _ = _lies_archiv()
    manifest = lies_json(MANIFEST_PFAD)
    if sha256(zip_bytes) != manifest["source_sha256"]:
        print("Quell-ZIP passt nicht zum Manifest.")
        return 1
    ergebnis = wandle_um(zip_bytes)
    fehler = 0
    with tempfile.TemporaryDirectory() as tmp:
        ziel = Path(tmp) / "dokumente"
        schreibe_dokumente(ergebnis.dokumente, ziel)
        neu = sorted(p.name for p in ziel.iterdir())
        alt = sorted(p.name for p in DOKUMENT_ORDNER.iterdir())
        if neu != alt:
            print("Dateimengen unterscheiden sich.")
            fehler += 1
        erwartet = {e["document_id"]: e for e in manifest["documents"]}
        for name in neu:
            daten = (ziel / name).read_bytes()
            if not (DOKUMENT_ORDNER / name).is_file() or (DOKUMENT_ORDNER / name).read_bytes() != daten:
                print(f"Abweichung: {name}")
                fehler += 1
            elif name not in erwartet or erwartet[name]["sha256"] != sha256(daten):
                print(f"Manifest passt nicht: {name}")
                fehler += 1
    print("OK: Neuerzeugung byteidentisch." if not fehler else f"{fehler} Abweichungen.")
    return 1 if fehler else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    unter = parser.add_subparsers(dest="modus", required=True)
    laden = unter.add_parser("herunterladen", help="ZIP einmal laden, archivieren, umwandeln")
    laden.add_argument("--ersetzen", action="store_true", help="vorhandene ZIP ersetzen")
    unter.add_parser("umwandeln", help="nur aus der archivierten ZIP umwandeln (offline)")
    unter.add_parser("pruefen", help="offline neu erzeugen und byteweise vergleichen")
    argumente = parser.parse_args(argv)
    if argumente.modus == "herunterladen":
        herunterladen(argumente.ersetzen)
        umwandeln()
        return 0
    if argumente.modus == "umwandeln":
        umwandeln()
        return 0
    return pruefen()


if __name__ == "__main__":
    sys.exit(main())
