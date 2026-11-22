"""Feste Sollwerte prüfen die Semantik unabhängig vom Suchalgorithmus."""

import pytest

from gemeinsam import QueryError, normalize_query, normalize_text, tokenize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ()),
        ("...!_ -\n\t", ()),
        ("Fehler FEHLER fehler", ("fehler", "fehler", "fehler")),
        ("Äpfel A\u0308pfel Österreich O\u0308sterreich", ("äpfel", "äpfel", "österreich", "österreich")),
        ("Straße STRASSE großes", ("strasse", "strasse", "grosses")),
        ("Fehler, bei\tder\nVerbindung. Zum Server!", ("fehler", "bei", "der", "verbindung", "zum", "server")),
        ("E-Mail Fehler_Code foo—bar", ("e", "mail", "fehler", "code", "foo", "bar")),
        ("abc42 007 ١٢३", ("abc42", "007", "١٢३")),
        # Nd digits form runs; numeric categories No and Nl do not.
        ("x²y Ⅲ vier", ("x", "y", "vier")),
        # NFC can compose the diaeresis of ä, but these marks remain separators.
        ("q\u0307r İx a\u034fb", ("q", "r", "i", "x", "a", "b")),
        ("東京 中文 ЖУК Σ σ ς", ("東京", "中文", "жук", "σ", "σ", "σ")),
        ("der und zum läuft laufen", ("der", "und", "zum", "läuft", "laufen")),
        ("ﬃ", ("ffi",)),
    ],
)
def test_tokens_have_independent_expected_values(raw, expected):
    assert tokenize(raw) == expected


@pytest.mark.parametrize("raw", ["A\u0308", "Straße", "İ", "ǰ", "ΐ", "ẞ", "\u0345", "\u1f88", "ﬃ", ""])
def test_normalization_is_idempotent(raw):
    normalized = normalize_text(raw)
    assert normalize_text(normalized) == normalized


def test_normalization_preserves_spacing_and_punctuation():
    assert normalize_text("Straße.\r\nA\u0308_! 42") == "strasse.\r\nä_! 42"


@pytest.mark.parametrize("invalid", [None, 42, True, b"Fehler", ["Fehler"]])
def test_text_functions_reject_non_strings(invalid):
    with pytest.raises(TypeError, match="Zeichenkette"):
        normalize_text(invalid)
    with pytest.raises(TypeError, match="Zeichenkette"):
        tokenize(invalid)
    with pytest.raises(QueryError, match="Zeichenkette"):
        normalize_query(invalid)


@pytest.mark.parametrize("query", ["", " ", "...", "_—!\n", "Verbindung zum Server", "E-Mail"])
def test_word_queries_reject_zero_or_multiple_tokens(query):
    with pytest.raises(QueryError):
        normalize_query(query)


def test_query_rules_are_shared_with_tokenization():
    assert normalize_query("FEHLER!") == ("fehler",)
    assert normalize_query("A\u0308pfel") == ("äpfel",)
    assert normalize_query("Verbindung, zum. Server", "phrase") == ("verbindung", "zum", "server")
    assert normalize_query("Fehler", "phrase") == ("fehler",)


@pytest.mark.parametrize("query_type", ["and", "", None, 4, []])
def test_unknown_query_type_is_rejected(query_type):
    with pytest.raises(QueryError, match="query_type"):
        normalize_query("fehler", query_type)


@pytest.mark.parametrize("query", ["", "...", " \n"])
def test_empty_phrase_is_rejected(query):
    with pytest.raises(QueryError):
        normalize_query(query, "phrase")
