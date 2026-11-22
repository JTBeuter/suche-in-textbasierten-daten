#!/usr/bin/env python3
"""Unabhängige Erwartungswerte und Anfragevorschläge für den BGB-Korpus.

Nur Standardbibliothek, kein Import aus ``gemeinsam`` oder den Themenpaketen.
Die Tokenregel aus ``doku/architektur.md`` (NFC -> casefold -> NFC, Tokens sind
maximale Folgen aus Unicode-Buchstaben L* und Dezimalziffern Nd) wird hier
eigenständig umgesetzt: Aus ``unicodedata.category`` aller Codepunkte wird eine
Regex-Zeichenklasse gebaut und mit ``re.finditer`` angewandt. Die produktive
Aufbereitung prüft dagegen Zeichen für Zeichen in einer Schleife.

Als zweite, bewusst abweichende Gegenprobe dient ``[^\\W_]+`` (Python-``str``-
Alphanumerik ohne Unterstrich). Sie zählt zusätzlich Zahlzeichen der Kategorien
No/Nl als Tokenzeichen; jede Abweichung zur Hauptregel wird mit Zeichen und
Kategorie ausgewiesen.

Aufruf aus der Repositorywurzel:

    python daten/real/bgb/berechne_erwartungen.py berechnen
    python daten/real/bgb/berechne_erwartungen.py abgleichen

``berechnen`` schreibt den Abschnitt ``independent_expectations`` in
``manifest.json`` und die Datei ``anfragevorschlaege.json``. ``abgleichen``
importiert danach die produktive Aufbereitung und die Suchpakete, vergleicht
alle Dokumente Token für Token sowie alle Erwartungen und schreibt das
Ergebnis in den Abschnitt ``production_comparison``.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import statistics
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from erzeuge_korpus import (DATENSATZ_ID, DOKUMENT_ORDNER, MANIFEST_PFAD, ORDNER,
                            kanonischer_hash, lies_json, schreibe_json, sha256)

VORSCHLAG_PFAD = ORDNER / "anfragevorschlaege.json"
VERFAHREN = "bgb-erwartungen-v1"
LISTE_VOLL_BIS = 200  # Dokument- und Positionslisten bis zu dieser Länge vollständig


# ---------------------------------------------------------------- Tokenisierung

def _baue_tokenmuster() -> re.Pattern[str]:
    """Zeichenklasse aller Codepunkte der Kategorien L* und Nd als Bereiche."""
    bereiche: list[tuple[int, int]] = []
    anfang = None
    for codepunkt in range(sys.maxunicode + 2):
        passt = False
        if codepunkt <= sys.maxunicode:
            kategorie = unicodedata.category(chr(codepunkt))
            passt = kategorie[0] == "L" or kategorie == "Nd"
        if passt and anfang is None:
            anfang = codepunkt
        elif not passt and anfang is not None:
            bereiche.append((anfang, codepunkt - 1))
            anfang = None
    klasse = "".join(f"\\U{a:08x}-\\U{b:08x}" if a != b else f"\\U{a:08x}" for a, b in bereiche)
    return re.compile(f"[{klasse}]+")


TOKENMUSTER = _baue_tokenmuster()
GEGENPROBE = re.compile(r"[^\W_]+")


def normalisiere(text: str) -> str:
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).casefold())


def tokens(text: str) -> list[str]:
    return [treffer.group() for treffer in TOKENMUSTER.finditer(normalisiere(text))]


def tokens_gegenprobe(text: str) -> list[str]:
    return GEGENPROBE.findall(normalisiere(text))


# ---------------------------------------------------------------- Korpus

def lies_dokumente(ordner: Path = DOKUMENT_ORDNER) -> dict[str, str]:
    """Liest alle .txt-Dateien eigenständig (striktes UTF-8, Codepunktordnung)."""
    texte: dict[str, str] = {}
    for pfad in sorted(ordner.iterdir(), key=lambda p: p.name):
        if pfad.suffix != ".txt":
            raise SystemExit(f"Unerwartete Datei im Dokumentordner: {pfad.name}")
        daten = pfad.read_bytes()
        text = daten.decode("utf-8", errors="strict")
        if text.startswith("﻿") or "\r" in text or not text.endswith("\n") or text.endswith("\n\n"):
            raise SystemExit(f"Dateiformat verletzt: {pfad.name}")
        texte[pfad.name] = text
    return texte


class Korpus:
    """Unabhängig berechnete Token-, Dokument- und Positionsdaten."""

    def __init__(self, texte: dict[str, str]):
        self.texte = texte
        self.ids = sorted(texte)
        self.tokens = {d: tokens(texte[d]) for d in self.ids}
        self.positionen: dict[str, dict[str, list[int]]] = {}
        for d in self.ids:
            for i, t in enumerate(self.tokens[d]):
                self.positionen.setdefault(t, {}).setdefault(d, []).append(i)

    def kennzahlen(self, ids: list[str] | None = None) -> dict:
        ids = self.ids if ids is None else ids
        wortschatz: set[str] = set()
        postings = 0
        n = 0
        for d in ids:
            folge = self.tokens[d]
            n += len(folge)
            menge = set(folge)
            postings += len(menge)
            wortschatz |= menge
        return {"D": len(ids), "N": n, "V": len(wortschatz), "P": postings}

    def df(self, term: str) -> int:
        return len(self.positionen.get(term, {}))

    def cf(self, term: str) -> int:
        return sum(len(p) for p in self.positionen.get(term, {}).values())

    def dokumentliste(self, term: str) -> list[str]:
        return sorted(self.positionen.get(term, {}))

    def und(self, terme: list[str]) -> list[str]:
        mengen = [set(self.positionen.get(t, {})) for t in terme]
        return sorted(set.intersection(*mengen))

    def oder(self, terme: list[str]) -> list[str]:
        return sorted(set().union(*(set(self.positionen.get(t, {})) for t in terme)))

    def phrase(self, terme: list[str]) -> dict[str, list[int]]:
        """Direkter Scan über alle Startpositionen, unabhängig vom Index."""
        k = len(terme)
        treffer: dict[str, list[int]] = {}
        for d in self.ids:
            folge = self.tokens[d]
            starts = [i for i in range(len(folge) - k + 1) if folge[i:i + k] == terme]
            if starts:
                treffer[d] = starts
        return treffer

    def gescannte_tokens(self, term: str) -> int:
        """Tokenvergleiche einer direkten Wortsuche mit Abbruch je Dokument."""
        summe = 0
        for d in self.ids:
            orte = self.positionen.get(term, {}).get(d)
            summe += orte[0] + 1 if orte else len(self.tokens[d])
        return summe


def listen_hash(werte: list[str]) -> str:
    return sha256("\n".join(werte).encode("utf-8"))


def _liste_oder_hash(schluessel: str, werte: list) -> dict:
    if len(werte) <= LISTE_VOLL_BIS:
        return {schluessel: werte}
    return {f"{schluessel}_count": len(werte),
            f"{schluessel}_sha256": listen_hash([str(w) for w in werte]),
            f"{schluessel}_first5": werte[:5], f"{schluessel}_last5": werte[-5:]}


def positions_hash(treffer: dict[str, list[int]]) -> str:
    """SHA-256 über Zeilen '<dokument>\\t<start>,<start>,...' in Dokumentordnung."""
    return listen_hash([f"{d}\t{','.join(map(str, s))}" for d, s in sorted(treffer.items())])


# ---------------------------------------------------------------- Auswahl

# Rohanfragen wie bei einer Eingabe; die Normalisierung erfolgt hier unabhängig.
WOERTER = (
    ("der", "sehr häufig"), ("die", "sehr häufig"), ("und", "sehr häufig"),
    ("Vertrag", "mittel"), ("Schadensersatz", "mittel"), ("Frist", "mittel"),
    ("Gläubiger", "mittel, Umlaut"), ("Maßgabe", "mittel, ß wird durch casefold zu ss"),
    ("MASSGABE", "Großschreibung ohne ß, gleiche Normalform wie Maßgabe"),
    ("Verbindung", "selten"), ("Rechtsfähigkeit", "selten, Umlaut, erster Paragraph"),
    ("Fehler", "selten"), ("Internet", "sehr selten"),
    ("Erbschaftskauf", "df 1, nur im letzten Dokument"),
    ("Beginn", "erstes Token des Korpus"),
    ("Server", "fehlt"), ("Unauffindbar", "fehlt"),
)

PHRASEN = (
    ("nach Maßgabe", "2 Wörter, häufig"),
    ("im Sinne des", "3 Wörter, häufig"),
    ("es sei denn, dass", "4 Wörter, häufig, Komma trennt"),
    ("nach den Vorschriften über die", "5 Wörter, häufig"),
    ("Beginn der Rechtsfähigkeit", "3 Wörter, selten, Überschrift von § 1"),
    ("Treu und Glauben", "3 Wörter, selten"),
    ("die die", "wiederholtes Wort"),
    ("Maßgabe nach", "falsche Reihenfolge"),
)


def normalisierte_terme(anfrage: str) -> list[str]:
    return tokens(anfrage)


def wort_eintrag(k: Korpus, anfrage: str, notiz: str) -> dict:
    terme = normalisierte_terme(anfrage)
    if len(terme) != 1:
        raise SystemExit(f"Wortanfrage {anfrage!r} ergibt nicht genau ein Token")
    term = terme[0]
    liste = k.dokumentliste(term)
    eintrag = {"query": anfrage, "note": notiz, "term": term, "df": k.df(term), "cf": k.cf(term)}
    if liste:
        eintrag.update({"first_document": liste[0],
                        "first_position": k.positionen[term][liste[0]][0],
                        "last_document": liste[-1]})
    eintrag.update(_liste_oder_hash("document_ids", liste))
    return eintrag


def phrasen_eintrag(k: Korpus, anfrage: str, notiz: str) -> dict:
    terme = normalisierte_terme(anfrage)
    treffer = k.phrase(terme)
    eintrag = {"query": anfrage, "note": notiz, "terms": terme,
               "df_terms": [k.df(t) for t in terme],
               "document_count": len(treffer), "match_count": sum(map(len, treffer.values())),
               "positions_sha256": positions_hash(treffer)}
    if len(treffer) <= LISTE_VOLL_BIS:
        eintrag["positions"] = treffer
    return eintrag


def zeichenbestand(k: Korpus) -> dict:
    zaehler: Counter[str] = Counter()
    for text in k.texte.values():
        zaehler.update(text)
    kategorien: Counter[str] = Counter()
    nicht_ascii = {}
    for zeichen, anzahl in sorted(zaehler.items()):
        kategorie = unicodedata.category(zeichen)
        kategorien[kategorie] += anzahl
        if not zeichen.isascii():
            nicht_ascii[f"U+{ord(zeichen):04X}"] = {
                "char": zeichen, "name": unicodedata.name(zeichen, "?"),
                "category": kategorie, "count": anzahl}
    return {"categories": dict(sorted(kategorien.items())), "non_ascii": nicht_ascii,
            "categories_No_Nl_Mn_Mc_Cf_Pc": {
                kat: kategorien.get(kat, 0) for kat in ("No", "Nl", "Mn", "Mc", "Cf", "Pc")}}


def gegenprobe(k: Korpus) -> dict:
    abweichungen = []
    for d in k.ids:
        a, b = k.tokens[d], tokens_gegenprobe(k.texte[d])
        if a != b:
            zeichen = sorted({z for z in normalisiere(k.texte[d])
                              if bool(TOKENMUSTER.fullmatch(z)) != bool(GEGENPROBE.fullmatch(z))})
            abweichungen.append({"document_id": d, "chars": [
                {"char": z, "codepoint": f"U+{ord(z):04X}", "category": unicodedata.category(z)}
                for z in zeichen]})
    return {"pattern": GEGENPROBE.pattern,
            "difference_to_main_rule": "zählt zusätzlich No/Nl (z. B. ², Ⅳ) und weitere "
                                       "str.isalnum-Zeichen als Tokenzeichen",
            "documents_with_difference": len(abweichungen), "differences": abweichungen}


def rangliste(k: Korpus) -> list[dict]:
    rang = sorted(k.positionen, key=lambda t: (-k.cf(t), t))
    plaetze = list(range(1, 21)) + [50, 100, 200, 500, 1000, 2000, 5000, 10000]
    return [{"rank": r, "term": rang[r - 1], "cf": k.cf(rang[r - 1]), "df": k.df(rang[r - 1])}
            for r in plaetze if r <= len(rang)]


def df_verteilung(k: Korpus) -> dict:
    baender = {"df > 1000": 0, "df 100-1000": 0, "df 10-99": 0, "df 2-9": 0, "df 1": 0}
    for orte in k.positionen.values():
        df = len(orte)
        schluessel = ("df > 1000" if df > 1000 else "df 100-1000" if df >= 100
                      else "df 10-99" if df >= 10 else "df 2-9" if df >= 2 else "df 1")
        baender[schluessel] += 1
    return baender


def erwartungen(k: Korpus, korpus_hash: str) -> dict:
    laengen = {d: len(k.tokens[d]) for d in k.ids}
    werte = sorted(laengen.values())
    kurz = min(werte)
    lang = max(werte)
    oberflaeche_ss = {t.group() for text in k.texte.values()
                      for t in TOKENMUSTER.finditer(unicodedata.normalize("NFC", text))
                      if "ß" in t.group()}
    gesamt = k.kennzahlen()
    return {
        "method": VERFAHREN,
        "dataset_id": DATENSATZ_ID,
        "corpus_sha256": korpus_hash,
        "python": sys.version.split()[0],
        "unicodedata_version": unicodedata.unidata_version,
        "tokenizer": ("eigenständig: NFC -> str.casefold -> NFC, danach re.finditer mit einer aus "
                      "unicodedata.category gebauten Zeichenklasse aller Codepunkte L* und Nd; "
                      "kein Import aus gemeinsam"),
        "file_checks": {"utf8_strict": True, "bom": False, "cr": False,
                        "single_final_newline": True,
                        "all_documents_nfc": all(unicodedata.is_normalized("NFC", t)
                                                 for t in k.texte.values())},
        "document_count": gesamt["D"],
        "token_count": gesamt["N"],
        "vocabulary_size": gesamt["V"],
        "posting_count": gesamt["P"],
        "positional_posting_count": gesamt["N"],
        "document_length_tokens": {
            "min": kurz, "min_documents": [d for d in k.ids if laengen[d] == kurz][:10],
            "max": lang, "max_documents": [d for d in k.ids if laengen[d] == lang],
            "median": statistics.median(werte), "mean": round(statistics.fmean(werte), 3)},
        "df_distribution": df_verteilung(k),
        "terms_with_cf_1": sum(1 for t in k.positionen if k.cf(t) == 1),
        "rank_frequency": rangliste(k),
        "vocabulary_terms_with_umlaut": sum(1 for t in k.positionen if any(z in t for z in "äöü")),
        "surface_forms_with_sharp_s_before_casefold": len(oberflaeche_ss),
        "vocabulary_terms_with_digits_only": sum(1 for t in k.positionen if t.isdigit()),
        "character_inventory": zeichenbestand(k),
        "prefix_tokens_bgb_0001": k.tokens[k.ids[0]][:20],
        "first_document_id": k.ids[0],
        "last_document_id": k.ids[-1],
        "words": [wort_eintrag(k, a, n) for a, n in WOERTER],
        "phrases": [phrasen_eintrag(k, a, n) for a, n in PHRASEN],
        "secondary_check": gegenprobe(k),
    }


# ---------------------------------------------------------------- Anfragevorschläge

def _bool_eintrag(k: Korpus, art: str, anfrage: list[str], notiz: str,
                  ausschluss: str | None = None) -> dict:
    terme = [normalisierte_terme(w)[0] for w in anfrage]
    if art == "and":
        ergebnis = k.und(terme)
    elif art == "or":
        ergebnis = k.oder(terme)
    else:
        raise ValueError(art)
    eintrag = {"kind": art, "query": anfrage, "note": notiz, "terms": terme,
               "df": [k.df(t) for t in terme]}
    if ausschluss is not None:
        nicht = normalisierte_terme(ausschluss)[0]
        vorher = len(ergebnis)
        ergebnis = sorted(set(ergebnis) - set(k.dokumentliste(nicht)))
        eintrag.update({"kind": "and_not", "exclude": ausschluss, "exclude_term": nicht,
                        "exclude_df": k.df(nicht), "and_hit_count_before_exclude": vorher})
    vorhandene = [k.df(t) for t in terme if k.df(t)]
    if art == "and" and len(vorhandene) == len(terme):
        eintrag["max_min_df_ratio"] = round(max(vorhandene) / min(vorhandene), 1)
    eintrag["hit_count"] = len(ergebnis)
    eintrag.update(_liste_oder_hash("document_ids", ergebnis))
    return eintrag


def _reihe01(k: Korpus) -> list[dict]:
    auswahl = (
        ("Beginn", "früher Treffer: erstes Token des ersten Dokuments"),
        ("Rechtsfähigkeit", "früher Treffer im ersten Dokument, sonst selten"),
        ("der", "häufigstes Wort"),
        ("Vertrag", "mittel; als Teilzeichenkette deutlich mehr Treffer"),
        ("Fehler", "selten; Teilzeichenkette trifft auch fehlerhaft usw."),
        ("Erbschaftskauf", "spät und selten: nur im letzten Dokument"),
        ("Server", "fehlt: voller Scan aller Tokens"),
    )
    vorschlaege = []
    for anfrage, notiz in auswahl:
        eintrag = wort_eintrag(k, anfrage, notiz)
        teil = normalisiere(anfrage)
        eintrag["scanned_tokens_direct"] = k.gescannte_tokens(eintrag["term"])
        eintrag["substring_hit_count"] = sum(1 for d in k.ids if teil in normalisiere(k.texte[d]))
        vorschlaege.append(eintrag)
    return vorschlaege


def _reihe02(k: Korpus) -> list[dict]:
    vorschlaege = []
    for anzahl in (250, 500, 1000, 1500, 2000, len(k.ids)):
        ids = k.ids[:anzahl]
        werte = k.kennzahlen(ids)
        vorschlaege.append({"subset": f"erste {anzahl}" if anzahl < len(k.ids) else "alle",
                            "selection": "erste Dokumente in Ordnung der Dokumentkennung",
                            "first_document_id": ids[0], "last_document_id": ids[-1],
                            **werte, "positional_postings": werte["N"],
                            "raw_bytes": sum(len(k.texte[d].encode("utf-8")) for d in ids)})
    return vorschlaege


def _reihe03(k: Korpus) -> list[dict]:
    return [
        _bool_eintrag(k, "and", ["Mieter", "Vermieter"], "2 Begriffe, ähnliche Listenlängen"),
        _bool_eintrag(k, "and", ["Vertrag", "Schadensersatz"], "2 Begriffe, mittel"),
        _bool_eintrag(k, "and", ["Verbindung", "der"], "großes Längenverhältnis (Galloping Search)"),
        _bool_eintrag(k, "and", ["Erbschaftskauf", "der"], "extremes Längenverhältnis 1 zu 2280"),
        _bool_eintrag(k, "and", ["der", "Verbindung"], "wie oben, häufiges Wort zuerst (Reihenfolge)"),
        _bool_eintrag(k, "and", ["Gläubiger", "Schuldner", "Frist"], "3 Begriffe, mittel"),
        _bool_eintrag(k, "and", ["Verbindung", "der", "die", "des", "und"],
                      "5 Begriffe, ein seltener und vier häufige"),
        _bool_eintrag(k, "and", ["der", "die", "des", "und", "oder"], "5 häufige Begriffe"),
        _bool_eintrag(k, "and", ["Vertrag", "Schadensersatz", "Frist", "Gläubiger", "Schuldner"],
                      "5 mittlere Begriffe, leerer Schnitt"),
        _bool_eintrag(k, "and", ["Mieter", "Erblasser"], "leeres Ergebnis, beide Wörter vorhanden"),
        _bool_eintrag(k, "and", ["Vertrag", "Server"], "leeres Ergebnis, ein Wort fehlt"),
        _bool_eintrag(k, "or", ["Mieter", "Vermieter"], "2 Begriffe, ähnliche Listenlängen"),
        _bool_eintrag(k, "or", ["Vertrag", "Schadensersatz"], "2 Begriffe, mittel"),
        _bool_eintrag(k, "or", ["Verbindung", "der"], "großes Längenverhältnis"),
        _bool_eintrag(k, "or", ["Mieter", "Vermieter", "Miete"], "3 Begriffe, überlappend"),
        _bool_eintrag(k, "or", ["Gläubiger", "Schuldner", "Frist"], "3 Begriffe, mittel"),
        _bool_eintrag(k, "or", ["der", "die", "des", "und", "oder"], "5 häufige Begriffe"),
        _bool_eintrag(k, "or", ["Vertrag", "Server"], "ein Wort fehlt, liefert keinen Beitrag"),
        _bool_eintrag(k, "and", ["Vertrag", "Schadensersatz"], "AND NOT", ausschluss="Verbraucher"),
        _bool_eintrag(k, "and", ["Gläubiger", "Schuldner"], "AND NOT, Ausschluss entfernt wenige",
                      ausschluss="Frist"),
    ]


def _reihe04(k: Korpus) -> list[dict]:
    auswahl = (
        ("nach Maßgabe", "Länge 2, häufig"),
        ("grobe Fahrlässigkeit", "Länge 2, mittel"),
        ("Bürgerlichen Gesetzbuchs", "Länge 2, selten"),
        ("der die", "Länge 2, beide Wörter sehr häufig, Phrase selten"),
        ("im Sinne des", "Länge 3, häufig"),
        ("es sei denn", "Länge 3, häufig"),
        ("Beginn der Rechtsfähigkeit", "Länge 3, selten"),
        ("es sei denn, dass", "Länge 4, häufig"),
        ("Vorsatz und grobe Fahrlässigkeit", "Länge 4, mittel"),
        ("nach Treu und Glauben", "Länge 4, selten"),
        ("nach den Vorschriften über die", "Länge 5, häufig"),
        ("mit Rücksicht auf die Verkehrssitte", "Länge 5, selten"),
        ("Maßgabe nach", "falsche Reihenfolge, leer"),
        ("des Sinne im", "falsche Reihenfolge, leer"),
        ("Glauben und Treu", "falsche Reihenfolge, leer"),
        ("die die", "wiederholtes Wort"),
        ("Verbindung zum Server", "Beispielphrase der Arbeit, fehlt"),
    )
    return [phrasen_eintrag(k, a, n) for a, n in auswahl]


def _reihe05(k: Korpus) -> list[dict]:
    return [
        {"profile": "wort_fehlt", **wort_eintrag(k, "Server", "fehlt")},
        {"profile": "wort_haeufig", **wort_eintrag(k, "der", "häufigstes Wort")},
        {"profile": "wort_selten", **wort_eintrag(k, "Verbindung", "selten")},
        {"profile": "wort_sehr_selten", **wort_eintrag(k, "Erbschaftskauf", "df 1")},
        {"profile": "and_drei", **_bool_eintrag(k, "and", ["Gläubiger", "Schuldner", "Frist"], "3 Begriffe")},
        {"profile": "or_drei", **_bool_eintrag(k, "or", ["Mieter", "Vermieter", "Miete"], "3 Begriffe")},
        {"profile": "phrase_drei", **phrasen_eintrag(k, "im Sinne des", "3 Wörter, häufig")},
    ]


def anfragevorschlaege(k: Korpus, korpus_hash: str) -> dict:
    return {
        "dataset_id": DATENSATZ_ID,
        "corpus_sha256": korpus_hash,
        "method": VERFAHREN,
        "note": ("Nur Vorschläge mit unabhängig berechneten Erwartungen (eigene Tokenisierung, "
                 "kein Import aus gemeinsam). Die Auswahl treffen die Reihen. Dokumentlisten bis "
                 f"{LISTE_VOLL_BIS} Einträge vollständig, sonst Anzahl, SHA-256 über die "
                 "zeilenweise verbundenen Kennungen sowie erste und letzte fünf."),
        "reihe_01_direkte_suche": _reihe01(k),
        "reihe_02_index_teilmengen": _reihe02(k),
        "reihe_03_boolesche_suche": _reihe03(k),
        "reihe_04_phrasensuche": _reihe04(k),
        "reihe_05_profile": _reihe05(k),
    }


# ---------------------------------------------------------------- Abgleich mit Produktivcode

def abgleichen(manifest: dict) -> dict:
    """Vergleicht Token für Token und alle Erwartungen mit der produktiven Aufbereitung."""
    from boolesche_suche import search_direct_boolean, search_index_boolean
    from direkte_suche import search_direct_substring, search_direct_word
    from gemeinsam import load_corpus, normalize_query, prepare_corpus
    from invertierter_index import build_inverted_index, search_index_word
    from positionsindex import build_positional_index, search_direct_phrase, search_index_phrase

    erwartet = manifest["independent_expectations"]
    vorschlaege = lies_json(VORSCHLAG_PFAD)
    k = Korpus(lies_dokumente())
    roh = load_corpus(DOKUMENT_ORDNER)
    korpus = prepare_corpus(roh)
    index = build_inverted_index(korpus)
    positionen = build_positional_index(korpus)
    abweichungen = []
    for dokument in korpus:
        if list(dokument.tokens) != k.tokens.get(dokument.document_id):
            abweichungen.append(dokument.document_id)
    if [d.document_id for d in korpus] != k.ids:
        abweichungen.append("<Dokumentmenge>")
    n = sum(len(d.tokens) for d in korpus)
    v = len(index)
    p = sum(len(index[t]) for t in index)
    kennzahlen_gleich = {"D": len(korpus) == erwartet["document_count"],
                         "N": n == erwartet["token_count"],
                         "V": v == erwartet["vocabulary_size"],
                         "P": p == erwartet["posting_count"]}
    fehler: list[str] = []

    def pruefe_liste(name: str, eintrag: dict, ergebnis: list[str]) -> None:
        if "document_ids" in eintrag:
            if ergebnis != eintrag["document_ids"]:
                fehler.append(name)
        elif (len(ergebnis) != eintrag["document_ids_count"]
              or listen_hash(ergebnis) != eintrag["document_ids_sha256"]):
            fehler.append(name)

    def pruefe_wort(eintrag: dict) -> None:
        (term,) = normalize_query(eintrag["query"])
        if term != eintrag["term"]:
            fehler.append(f"Normalisierung {eintrag['query']}")
        for name, ergebnis in (("direkt", search_direct_word(korpus, eintrag["query"])),
                               ("index", search_index_word(index, eintrag["query"]))):
            pruefe_liste(f"Wort {eintrag['query']} {name}", eintrag, ergebnis)

    def pruefe_phrase(eintrag: dict) -> None:
        terme = normalize_query(eintrag["query"], "phrase")
        for name, ergebnis in (("direkt", search_direct_phrase(korpus, terme)),
                               ("index", search_index_phrase(positionen, terme))):
            if positions_hash(ergebnis) != eintrag["positions_sha256"]:
                fehler.append(f"Phrase {eintrag['query']} {name}")
            if "positions" in eintrag and ergebnis != eintrag["positions"]:
                fehler.append(f"Phrase {eintrag['query']} {name} Positionen")

    def pruefe_bool(eintrag: dict) -> None:
        operator = "AND" if eintrag["kind"] in ("and", "and_not") else "OR"
        ergebnisse = [("direkt", search_direct_boolean(korpus, eintrag["query"], operator)),
                      ("index", search_index_boolean(index, eintrag["query"], operator))]
        if operator == "AND":
            ergebnisse.append(("index kürzeste zuerst", search_index_boolean(
                index, eintrag["query"], operator, "shortest_first")))
        for name, ergebnis in ergebnisse:
            if eintrag["kind"] == "and_not":
                # Ausschluss über die stabile Einzelwortsuche, unabhängig von einer AND-NOT-API.
                nicht = set(search_index_word(index, eintrag["exclude"]))
                ergebnis = [d for d in ergebnis if d not in nicht]
            pruefe_liste(f"{eintrag['kind']} {eintrag['query']} {name}", eintrag, ergebnis)

    for eintrag in erwartet["words"]:
        pruefe_wort(eintrag)
    for eintrag in erwartet["phrases"]:
        pruefe_phrase(eintrag)
    for eintrag in vorschlaege["reihe_01_direkte_suche"]:
        pruefe_wort(eintrag)
        teil = search_direct_substring(roh, eintrag["query"])
        if len(teil) != eintrag["substring_hit_count"]:
            fehler.append(f"Teilzeichen {eintrag['query']}")
    for eintrag in vorschlaege["reihe_02_index_teilmengen"]:
        teil = korpus[:eintrag["D"]]
        teilindex = build_inverted_index(teil)
        werte = {"D": len(teil), "N": sum(len(d.tokens) for d in teil), "V": len(teilindex),
                 "P": sum(len(teilindex[t]) for t in teilindex)}
        if any(werte[s] != eintrag[s] for s in werte) or teil[-1].document_id != eintrag["last_document_id"]:
            fehler.append(f"Teilmenge {eintrag['subset']}")
    for eintrag in vorschlaege["reihe_03_boolesche_suche"]:
        pruefe_bool(eintrag)
    for eintrag in vorschlaege["reihe_04_phrasensuche"]:
        pruefe_phrase(eintrag)
    for eintrag in vorschlaege["reihe_05_profile"]:
        if "term" in eintrag:
            pruefe_wort(eintrag)
        elif "positions_sha256" in eintrag:
            pruefe_phrase(eintrag)
        else:
            pruefe_bool(eintrag)
    if list(korpus[0].tokens[:20]) != erwartet["prefix_tokens_bgb_0001"]:
        fehler.append("Anfangstokens bgb_0001.txt")
    from datetime import date
    return {
        "corpus_sha256": manifest["corpus_sha256"],
        "compared_on": date.today().isoformat(),
        "python": sys.version.split()[0],
        "unicodedata_version": unicodedata.unidata_version,
        "apis": ["gemeinsam.load_corpus", "gemeinsam.prepare_corpus", "gemeinsam.normalize_query",
                 "direkte_suche.search_direct_word", "direkte_suche.search_direct_substring",
                 "invertierter_index.build_inverted_index", "invertierter_index.search_index_word",
                 "boolesche_suche.search_direct_boolean", "boolesche_suche.search_index_boolean",
                 "positionsindex.build_positional_index", "positionsindex.search_direct_phrase",
                 "positionsindex.search_index_phrase"],
        "documents_compared": len(korpus),
        "documents_with_token_difference": len(abweichungen),
        "token_differences": abweichungen,
        "statistics_equal": kennzahlen_gleich,
        "failed_checks": fehler,
        "all_equal": not abweichungen and all(kennzahlen_gleich.values()) and not fehler,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("modus", choices=("berechnen", "abgleichen"))
    modus = parser.parse_args(argv).modus
    manifest = lies_json(MANIFEST_PFAD)
    texte = lies_dokumente()
    eintraege = [(name, sha256(text.encode("utf-8"))) for name, text in texte.items()]
    korpus_hash = kanonischer_hash(eintraege)
    if korpus_hash != manifest["corpus_sha256"]:
        raise SystemExit("Dokumente passen nicht zum Manifest; zuerst erzeuge_korpus.py umwandeln.")
    if modus == "berechnen":
        k = Korpus(texte)
        manifest["independent_expectations"] = erwartungen(k, korpus_hash)
        manifest.pop("production_comparison", None)
        schreibe_json(MANIFEST_PFAD, manifest)
        schreibe_json(VORSCHLAG_PFAD, anfragevorschlaege(k, korpus_hash))
        e = manifest["independent_expectations"]
        print(f"D={e['document_count']} N={e['token_count']} V={e['vocabulary_size']} "
              f"P={e['posting_count']}; Gegenprobe: {e['secondary_check']['documents_with_difference']} "
              "Dokumente mit Abweichung")
        return 0
    ergebnis = abgleichen(manifest)
    manifest["production_comparison"] = ergebnis
    schreibe_json(MANIFEST_PFAD, manifest)
    print(f"Abgleich: {ergebnis['documents_with_token_difference']} Dokumente mit Tokenabweichung, "
          f"Kennzahlen gleich {ergebnis['statistics_equal']}, fehlgeschlagen {ergebnis['failed_checks']}")
    return 0 if ergebnis["all_equal"] else 1


if __name__ == "__main__":
    sys.exit(main())
