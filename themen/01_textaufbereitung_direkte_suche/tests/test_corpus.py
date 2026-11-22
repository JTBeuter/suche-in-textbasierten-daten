import dataclasses
import errno
from pathlib import Path

import pytest

from gemeinsam import CorpusError, PreparedDocument, RawDocument, load_corpus, prepare_corpus


def test_loader_sorts_relative_paths_and_preserves_source_bytes(tmp_path):
    (tmp_path / "z.txt").write_bytes("Äpfel\r\nFehler\rnoch".encode("utf-8"))
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.txt").write_text("Straße", encoding="utf-8")
    (tmp_path / "empty.txt").write_bytes(b"")
    (tmp_path / "ignored.md").write_bytes(b"\xff")
    (tmp_path / "ignored.TXT").write_bytes(b"\xff")
    documents = load_corpus(str(tmp_path))
    assert isinstance(documents, tuple)
    assert [doc.document_id for doc in documents] == ["a/b.txt", "empty.txt", "z.txt"]
    assert [doc.source_path for doc in documents] == ["a/b.txt", "empty.txt", "z.txt"]
    assert [doc.raw_text for doc in documents] == ["Straße", "", "Äpfel\r\nFehler\rnoch"]
    assert load_corpus(tmp_path) == documents


def test_identifier_survives_adding_and_removing_other_files(tmp_path):
    (tmp_path / "b.txt").write_text("bestehend", encoding="utf-8")
    existing = load_corpus(tmp_path)[0]
    (tmp_path / "a.txt").write_text("neu", encoding="utf-8")
    assert load_corpus(tmp_path)[1] == existing
    (tmp_path / "a.txt").unlink()
    assert load_corpus(tmp_path) == (existing,)
    (tmp_path / "b.txt").rename(tmp_path / "c.txt")
    assert load_corpus(tmp_path)[0].document_id == "c.txt"


def test_empty_directory_and_document_are_valid(tmp_path):
    assert load_corpus(tmp_path) == ()
    assert prepare_corpus(()) == ()
    (tmp_path / "empty.txt").touch()
    (doc,) = prepare_corpus(load_corpus(tmp_path))
    assert doc.raw_text == ""
    assert doc.tokens == ()


def test_utf8_bom_is_preserved_in_raw_text_and_separates_tokens(tmp_path):
    (tmp_path / "bom.txt").write_bytes(b"\xef\xbb\xbfFehler")
    (raw,) = load_corpus(tmp_path)
    assert raw.raw_text == "\ufeffFehler"
    assert prepare_corpus((raw,))[0].tokens == ("fehler",)


def test_missing_root_and_file_root_are_explained(tmp_path):
    with pytest.raises(CorpusError, match="existiert nicht"):
        load_corpus(tmp_path / "missing")
    (tmp_path / "file.txt").touch()
    with pytest.raises(CorpusError, match="kein Verzeichnis"):
        load_corpus(tmp_path / "file.txt")


@pytest.mark.parametrize("invalid", [None, 123, True, b"path", [], "", "\x00"])
def test_loader_rejects_invalid_path_inputs(invalid):
    with pytest.raises(CorpusError):
        load_corpus(invalid)


def test_invalid_utf8_aborts_without_a_partial_result(tmp_path):
    (tmp_path / "a.txt").write_text("gültig", encoding="utf-8")
    (tmp_path / "b.txt").write_bytes(b"ung\xffltig")
    with pytest.raises(CorpusError, match=r"gültiges UTF-8: b\.txt") as caught:
        load_corpus(tmp_path)
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize("kind", ["file", "directory", "broken", "ignored_extension", "root"])
def test_all_encountered_symlinks_are_rejected(tmp_path, kind):
    outside = tmp_path.parent / f"outside-{tmp_path.name}"
    outside.mkdir()
    (outside / "text.txt").write_text("außerhalb", encoding="utf-8")
    if kind == "root":
        link = tmp_path / "root-link"
        link.symlink_to(outside, target_is_directory=True)
        root = link
    else:
        root = tmp_path
        target = outside if kind == "directory" else outside / "text.txt"
        if kind == "broken":
            target = outside / "missing"
        name = "link.md" if kind == "ignored_extension" else "link.txt"
        (tmp_path / name).symlink_to(target, target_is_directory=kind == "directory")
    with pytest.raises(CorpusError, match="Symbolischer Link"):
        load_corpus(root)


def test_read_failure_is_reported_with_cause(tmp_path, monkeypatch):
    (tmp_path / "a.txt").touch()

    def fail_read(path):
        raise PermissionError(errno.EACCES, "Permission denied", str(path))

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(CorpusError, match="vollständig gelesen") as caught:
        load_corpus(tmp_path)
    assert isinstance(caught.value.__cause__, PermissionError)


def test_directory_walk_failure_is_reported(tmp_path, monkeypatch):
    def fail_walk(root, *, onerror):
        onerror(PermissionError(errno.EACCES, "Permission denied", str(root)))
        yield  # os.walk is a generator; execution occurs on first iteration.

    monkeypatch.setattr("gemeinsam.corpus.os.walk", fail_walk)
    with pytest.raises(CorpusError, match="vollständig gelesen"):
        load_corpus(tmp_path)


def test_special_txt_file_is_not_opened(tmp_path):
    import os

    os.mkfifo(tmp_path / "pipe.txt")
    with pytest.raises(CorpusError, match="reguläre Textdatei"):
        load_corpus(tmp_path)


def test_preparation_is_sorted_reusable_and_does_not_mutate_input():
    raw = [RawDocument("b.txt", "b.txt", "a a a"), RawDocument("a.txt", "a.txt", "FEHLER.\nStraße")]
    saved = raw.copy()
    prepared = prepare_corpus(iter(raw))
    assert raw == saved
    assert prepared == (
        PreparedDocument("a.txt", "a.txt", "FEHLER.\nStraße", ("fehler", "strasse")),
        PreparedDocument("b.txt", "b.txt", "a a a", ("a", "a", "a")),
    )
    assert list(enumerate(prepared[1].tokens)) == [(0, "a"), (1, "a"), (2, "a")]


def test_duplicate_document_ids_are_rejected():
    corpus = [RawDocument("a.txt", "first", "a"), RawDocument("a.txt", "second", "b")]
    with pytest.raises(CorpusError, match="Doppelte Dokumentkennung: a.txt"):
        prepare_corpus(corpus)


@pytest.mark.parametrize("invalid", [None, 42, "text", b"text", ["text"], [object()], [PreparedDocument("a.txt", "a.txt", "a", ("a",))]])
def test_preparation_rejects_invalid_corpus(invalid):
    with pytest.raises(CorpusError):
        prepare_corpus(invalid)


@pytest.mark.parametrize("identifier", ["", "a", "/a.txt", "../a.txt", "./a.txt", "a//b.txt", "a/../b.txt", "a.TXT", "a\x00.txt", 123, None])
def test_models_validate_document_identifiers(identifier):
    with pytest.raises(CorpusError):
        RawDocument(identifier, "source", "text")


@pytest.mark.parametrize("source", [None, 123, "", "\x00"])
def test_models_validate_source_paths(source):
    with pytest.raises(CorpusError):
        RawDocument("a.txt", source, "text")


@pytest.mark.parametrize("raw_text", [None, 42, b"text", []])
def test_models_validate_raw_text(raw_text):
    with pytest.raises(CorpusError):
        RawDocument("a.txt", "source", raw_text)


@pytest.mark.parametrize("tokens", [["a"], ("",), (1,), "a", None])
def test_prepared_document_requires_immutable_string_tokens(tokens):
    with pytest.raises(CorpusError):
        PreparedDocument("a.txt", "source", "text", tokens)


def test_document_objects_and_token_tuple_are_immutable():
    raw = RawDocument("a.txt", "a.txt", "A")
    prepared = prepare_corpus((raw,))[0]
    for document in (raw, prepared):
        with pytest.raises(dataclasses.FrozenInstanceError):
            document.raw_text = "changed"
    with pytest.raises(TypeError):
        prepared.tokens[0] = "changed"
