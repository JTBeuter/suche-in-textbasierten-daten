"""Reproducible datasets and independent query expectations for experiment 05.

The synthetic token plan is made before writing or loading any document. The
real dataset keeps the pinned project snapshot, with an independent tokenizer
and the manually recorded prefix/word positions as additional checks.
Realkorpora mit mehreren Dokumenten (Manifest mit ``corpus_root``, z. B. das
BGB je Paragraph) werden über Datei-Hashes, die Offline-Neuerzeugung und die
unabhängig berechneten Erwartungen des Manifests geprüft; ihre Profilanfragen
stehen fest in der Versuchsdefinition.
"""

from __future__ import annotations

from collections import Counter
import hashlib
from itertools import groupby
import json
from pathlib import Path, PurePosixPath
import random
import statistics
import subprocess
import sys
import unicodedata

from gemeinsam import load_corpus, prepare_corpus


GENERATOR_VERSION = "05-planted-v1"
QUERY_GENERATOR_VERSION = "05-queries-v1"
FIXED_QUERY_GENERATOR_VERSION = "05-queries-fixed-v1"
QUERY_KINDS = ("word", "and", "or", "phrase")
FREQUENT = tuple(f"f{i:03d}" for i in range(5))
RARE = tuple(f"s{i:03d}" for i in range(5))
RESULT_SIZE = tuple(f"z{i:03d}" for i in range(5))
REPEATED = ("r000",) * 5
PHRASE_LENGTHS = (1, 2, 3, 5)
REPOSITORY = Path(__file__).resolve().parents[4]


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def independent_tokens(text: str) -> tuple[str, ...]:
    """Independent groupby oracle for NFC/casefold/NFC and L*/Nd tokens.

    str.isalpha/isdecimal implement the declared Unicode categories; the
    productive character accumulator and its helper are never called here.
    Fixed hand-written examples additionally guard the shared semantics.
    """
    folded = unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).casefold())
    return tuple(
        "".join(characters)
        for is_token, characters in groupby(folded, lambda char: char.isalpha() or char.isdecimal())
        if is_token
    )


def expected_result(tokens_by_id: dict[str, tuple[str, ...]], kind: str,
                    terms: tuple[str, ...] | list[str]) -> list[str] | dict[str, list[int]]:
    """Direct oracle: tuple membership/slices, without production search/index."""
    terms = tuple(terms)
    if not terms or kind not in {"word", "and", "or", "phrase"}:
        raise ValueError("nonempty terms and a known query kind are required")
    if kind == "word" and len(terms) != 1:
        raise ValueError("a word query must have exactly one term")
    if kind == "phrase":
        results = {}
        for identifier, tokens in sorted(tokens_by_id.items()):
            starts = [start for start in range(len(tokens) - len(terms) + 1)
                      if tokens[start:start + len(terms)] == terms]
            if starts:
                results[identifier] = starts
        return results
    quantifier = any if kind == "or" else all
    return [identifier for identifier, tokens in sorted(tokens_by_id.items())
            if quantifier(term in tokens for term in terms)]


def _synthetic_parameters(spec: dict, default_seed: int) -> dict:
    required = {"documents", "length", "vocabulary"}
    missing = required - spec.keys()
    if missing:
        raise ValueError(f"missing synthetic parameters: {sorted(missing)}")
    params = {name: spec[name] for name in ("documents", "length", "vocabulary")}
    params["seed"] = spec.get("seed", default_seed)
    for name, value in params.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    if params["documents"] < 2 or params["length"] < 100 or params["length"] % 50:
        raise ValueError("documents >= 2 and length >= 100 divisible by 50 required")
    if params["vocabulary"] < 17:
        raise ValueError("vocabulary >= 17 required (16 marker terms plus filler)")
    free = (params["documents"] * (params["length"] - params["length"] // 50 * 5 - 11) - 10)
    if params["vocabulary"] - 16 > free:
        raise ValueError("requested vocabulary cannot fit in the free token positions")
    params.update({
        "distribution": "uniform", "frequent_interval": 50,
        "frequent_terms": list(FREQUENT), "rare_terms": list(RARE),
        "rare_document_count": 2, "rare_start": 30,
        "repeated_term": "r000", "repeated_start": 20, "repeated_run_length": 6,
        "result_size_terms": list(RESULT_SIZE), "result_size_start": 40,
        "result_document_count": params["documents"],
        "filler_vocabulary": params["vocabulary"] - 16,
        "serialization": "uppercase ASCII terms separated by '. '; one final '.\\n'",
        "random_api": "local random.Random(seed).randrange(filler_vocabulary)",
        "filler_guarantee": "first free positions in document and token order",
    })
    return params


def _generate_synthetic(root: Path, params: dict) -> dict[str, tuple[str, ...]]:
    """The checked 04 planting layout, generalized to an actual vocabulary V."""
    root.mkdir(parents=True)
    rng = random.Random(params["seed"])
    guaranteed = 0
    plan = {}
    for number in range(params["documents"]):
        identifier = f"d{number:05d}.txt"
        words = [f"b{rng.randrange(params['filler_vocabulary']):03d}"
                 for _ in range(params["length"])]
        occupied = set()
        for start in range(0, params["length"], 50):
            words[start:start + 5] = FREQUENT
            occupied.update(range(start, start + 5))
        words[20:26] = ("r000",) * 6
        occupied.update(range(20, 26))
        if number < 2:
            words[30:35] = RARE
            occupied.update(range(30, 35))
        words[40:45] = RESULT_SIZE
        occupied.update(range(40, 45))
        for position in range(params["length"]):
            if position not in occupied and guaranteed < params["filler_vocabulary"]:
                words[position] = f"b{guaranteed:03d}"
                guaranteed += 1
        plan[identifier] = tuple(words)
        (root / identifier).write_bytes((". ".join(word.upper() for word in words) + ".\n").encode("utf-8"))
    if guaranteed != params["filler_vocabulary"]:
        raise ValueError("filler guarantee failed")
    return plan


def _list_hash(values: list[str]) -> str:
    """SHA-256 über zeilenweise verbundene Werte, wie in ``berechne_erwartungen.py``."""
    return _digest("\n".join(values).encode("utf-8"))


def _positions_hash(result: dict[str, list[int]]) -> str:
    """SHA-256 über Zeilen '<dokument>\\t<start>,<start>' in Dokumentordnung."""
    return _list_hash([f"{document}\t{','.join(map(str, starts))}"
                       for document, starts in sorted(result.items())])


def canonical_corpus_hash(entries: list[tuple[str, str]]) -> str:
    """SHA-256 über '<sha256>  <dateiname>\\n' in Bytereihenfolge der Namen.

    Entspricht ``LC_ALL=C sha256sum *.txt | sha256sum`` im Dokumentordner.
    """
    ordered = sorted(entries, key=lambda entry: entry[0].encode("utf-8"))
    return _digest("".join(f"{digest}  {name}\n" for name, digest in ordered).encode("utf-8"))


def _relative_path(value: object, what: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{what} must be a nonempty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{what} must stay inside the snapshot")
    return path


def is_document_collection(source_manifest: dict) -> bool:
    """Neues Manifestformat mit eigenem Dokumentordner und Dokumentliste."""
    return "corpus_root" in source_manifest


def _compare_document_list(record: dict, documents: list[str], what: str) -> None:
    if "document_ids" in record:
        same = record["document_ids"] == documents
    else:
        same = (record.get("document_ids_count") == len(documents)
                and record.get("document_ids_sha256") == _list_hash(documents)
                and record.get("document_ids_first5") == documents[:5]
                and record.get("document_ids_last5") == documents[-5:])
    if not same:
        raise ValueError(f"{what}: document list disagrees with the independent expectation")


def _phrase_by_positions(tokens: dict[str, tuple[str, ...]], positions: dict, terms: tuple[str, ...]) -> dict:
    """Unabhängige Phrasenprüfung: Startkandidaten des ersten Terms, Vergleich per Slice."""
    result = {}
    for identifier, starts in sorted(positions.get(terms[0], {}).items()):
        hits = [start for start in starts if tokens[identifier][start:start + len(terms)] == terms]
        if hits:
            result[identifier] = hits
    return result


def _df_band(df: int) -> str:
    return ("df > 1000" if df > 1000 else "df 100-1000" if df >= 100
            else "df 10-99" if df >= 10 else "df 2-9" if df >= 2 else "df 1")


def _check_collection_expectations(tokens: dict[str, tuple[str, ...]], manifest: dict) -> None:
    """Vergleicht die eigene Tokenfolge mit den unabhängig berechneten Manifestwerten."""
    expected = manifest["independent_expectations"]
    if expected.get("corpus_sha256", manifest["corpus_sha256"]) != manifest["corpus_sha256"]:
        raise ValueError("independent expectations belong to another corpus hash")
    identifiers = sorted(tokens)
    positions: dict[str, dict[str, list[int]]] = {}
    for identifier in identifiers:
        for position, token in enumerate(tokens[identifier]):
            positions.setdefault(token, {}).setdefault(identifier, []).append(position)
    lengths = [len(tokens[identifier]) for identifier in identifiers]
    measured = {"document_count": len(identifiers), "token_count": sum(lengths),
                "vocabulary_size": len(positions),
                "posting_count": sum(len(documents) for documents in positions.values()),
                "positional_posting_count": sum(lengths),
                "first_document_id": identifiers[0], "last_document_id": identifiers[-1]}
    for key, value in measured.items():
        if expected[key] != value:
            raise ValueError(f"real corpus disagrees with the independent {key}")
    prefixes = {key: value for key, value in expected.items() if key.startswith("prefix_tokens_")}
    if not prefixes:
        raise ValueError("independent expectations need fixed prefix tokens")
    for key, prefix in prefixes.items():
        identifier = key.removeprefix("prefix_tokens_") + ".txt"
        if identifier not in tokens or list(tokens[identifier][:len(prefix)]) != prefix:
            raise ValueError("real corpus disagrees with the fixed prefix tokens")
    cf = {term: sum(map(len, documents.values())) for term, documents in positions.items()}
    if "document_length_tokens" in expected:
        stored = expected["document_length_tokens"]
        shortest, longest = min(lengths), max(lengths)
        observed = {"min": shortest, "max": longest, "median": statistics.median(lengths),
                    "mean": round(statistics.fmean(lengths), 3),
                    "min_documents": [i for i in identifiers if len(tokens[i]) == shortest][:10],
                    "max_documents": [i for i in identifiers if len(tokens[i]) == longest]}
        if observed != stored:
            raise ValueError("real corpus disagrees with the independent document lengths")
    if "df_distribution" in expected:
        bands = Counter(_df_band(len(documents)) for documents in positions.values())
        if any(bands.get(band, 0) != count for band, count in expected["df_distribution"].items()):
            raise ValueError("real corpus disagrees with the independent df distribution")
    if "terms_with_cf_1" in expected and expected["terms_with_cf_1"] != sum(1 for v in cf.values() if v == 1):
        raise ValueError("real corpus disagrees with the independent cf=1 count")
    if "rank_frequency" in expected:
        ranked = sorted(positions, key=lambda term: (-cf[term], term))
        for entry in expected["rank_frequency"]:
            term = ranked[entry["rank"] - 1]
            if (term, cf[term], len(positions[term])) != (entry["term"], entry["cf"], entry["df"]):
                raise ValueError("real corpus disagrees with the independent rank list")
    for entry in expected.get("words", []):
        terms = independent_tokens(entry["query"])
        if terms != (entry["term"],):
            raise ValueError(f"word expectation {entry['query']!r} has another normal form")
        documents = sorted(positions.get(entry["term"], {}))
        if entry["df"] != len(documents) or entry["cf"] != cf.get(entry["term"], 0):
            raise ValueError(f"word expectation {entry['query']!r}: df/cf changed")
        if documents and (entry["first_document"], entry["first_position"], entry["last_document"]) != (
                documents[0], positions[entry["term"]][documents[0]][0], documents[-1]):
            raise ValueError(f"word expectation {entry['query']!r}: first/last occurrence changed")
        _compare_document_list(entry, documents, f"word {entry['query']!r}")
    for entry in expected.get("phrases", []):
        terms = independent_tokens(entry["query"])
        if list(terms) != entry["terms"]:
            raise ValueError(f"phrase expectation {entry['query']!r} has another normal form")
        result = _phrase_by_positions(tokens, positions, terms)
        if (entry["document_count"], entry["match_count"], entry["positions_sha256"]) != (
                len(result), sum(map(len, result.values())), _positions_hash(result)):
            raise ValueError(f"phrase expectation {entry['query']!r}: starts changed")
        if entry.get("positions", result) != result:
            raise ValueError(f"phrase expectation {entry['query']!r}: start list changed")
        if entry.get("df_terms", [len(positions.get(t, {})) for t in terms]) != [len(positions.get(t, {})) for t in terms]:
            raise ValueError(f"phrase expectation {entry['query']!r}: term df changed")


def _run_conversion_check(root: Path, manifest: dict) -> str | None:
    """Offline-Neuerzeugung aus dem archivierten Quellarchiv mit dem gepinnten Skript.

    ``-I`` isoliert den Prozess von Benutzer-Site und PYTHONPATH; das Skript
    vergleicht die Neuerzeugung byteweise mit dem eigenen Dokumentordner.
    """
    script = manifest.get("conversion", {}).get("script")
    if not script:
        return None
    root = Path(root).resolve()
    path = root / _relative_path(script, "conversion script")
    completed = subprocess.run([sys.executable, "-I", str(path), "pruefen"], cwd=root,
                               capture_output=True, text=True, timeout=900, check=False)
    if completed.returncode != 0 or not completed.stdout.startswith("OK"):
        raise ValueError("offline regeneration from the pinned source archive is not byte-identical: "
                         + (completed.stdout + completed.stderr).strip()[-500:])
    return f"{script} pruefen: {completed.stdout.strip()}"


def _verify_document_collection(root: Path, manifest: dict) -> tuple[dict, dict[str, tuple[str, ...]]]:
    """Mehrdokumentkorpus: ersetzt für dieses Format die Prüfung auf genau ein Dokument."""
    archive = (root / _relative_path(manifest["source_file"], "source_file")).read_bytes()
    if len(archive) != manifest["source_bytes"] or _digest(archive) != manifest["source_sha256"]:
        raise ValueError("real source archive does not match its pinned manifest")
    if manifest.get("retrieval_record"):
        record = json.loads((root / _relative_path(manifest["retrieval_record"], "retrieval_record"))
                            .read_text(encoding="utf-8"))
        if record.get("bytes") != manifest["source_bytes"] or record.get("sha256") != manifest["source_sha256"]:
            raise ValueError("retrieval record disagrees with the pinned source archive")
    documents_root = root / _relative_path(manifest["corpus_root"], "corpus_root")
    entries = manifest["documents"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("a document collection needs a nonempty document list")
    identifiers = [entry["document_id"] for entry in entries]
    if identifiers != sorted(set(identifiers)):
        raise ValueError("document ids must be unique and sorted")
    texts = {}
    for entry in entries:
        identifier = entry["document_id"]
        _relative_path(identifier, "document_id")
        if not identifier.endswith(".txt") or entry.get("source_path", identifier) != identifier:
            raise ValueError("document id must be its .txt path below the corpus root")
        payload = (documents_root / identifier).read_bytes()
        if len(payload) != entry["bytes"] or _digest(payload) != entry["sha256"]:
            raise ValueError(f"real document does not match hash/size: {identifier}")
        texts[identifier] = payload.decode("utf-8", errors="strict")
    if canonical_corpus_hash([(entry["document_id"], entry["sha256"]) for entry in entries]) != manifest["corpus_sha256"]:
        raise ValueError("canonical corpus hash changed")
    if {document.document_id: document.raw_text for document in load_corpus(documents_root)} != texts:
        raise ValueError("real corpus file list changed")
    tokens = {identifier: independent_tokens(text) for identifier, text in texts.items()}
    _check_collection_expectations(tokens, manifest)
    _run_conversion_check(root, manifest)
    return manifest, tokens


def _collection_snapshot_files(root: Path, manifest: dict) -> tuple[list[str], list[str]]:
    """Gepinnte Daten-/Umwandlungsdateien und nur dokumentierende Begleitdateien."""
    pinned = ["manifest.json", manifest["source_file"]]
    if manifest.get("retrieval_record"):
        pinned.append(manifest["retrieval_record"])
    if manifest.get("conversion", {}).get("script"):
        pinned.append(manifest["conversion"]["script"])
    if (root / "anfragevorschlaege.json").is_file():
        pinned.append("anfragevorschlaege.json")
    documenting = [name for name in ("README.md", "berechne_erwartungen.py") if (root / name).is_file()]
    for name in pinned + documenting:
        _relative_path(name, "snapshot file")
    return pinned, documenting


def _independent_query_records(root: Path, manifest: dict) -> list[tuple[str, str, tuple[str, ...], dict]]:
    """Unabhängige Anfrageerwartungen aus Manifest und Anfragevorschlägen."""
    expected = manifest["independent_expectations"]
    records = [("manifest:independent_expectations.words", "word", (entry["term"],), entry)
               for entry in expected.get("words", [])]
    records += [("manifest:independent_expectations.phrases", "phrase", tuple(entry["terms"]), entry)
                for entry in expected.get("phrases", [])]
    path = root / "anfragevorschlaege.json"
    if path.is_file():
        suggestions = json.loads(path.read_text(encoding="utf-8"))
        if suggestions.get("corpus_sha256") != manifest["corpus_sha256"]:
            raise ValueError("query suggestions belong to another corpus hash")
        for key, entries in suggestions.items():
            if not key.startswith("reihe_") or not isinstance(entries, list):
                continue
            for entry in entries:
                source = f"anfragevorschlaege:{key}"
                if not isinstance(entry, dict):
                    continue
                if entry.get("kind") in ("and", "or"):
                    records.append((source, entry["kind"], tuple(entry["terms"]), entry))
                elif "positions_sha256" in entry and "terms" in entry:
                    records.append((source, "phrase", tuple(entry["terms"]), entry))
                elif "term" in entry and "df" in entry and "kind" not in entry:
                    records.append((source, "word", (entry["term"],), entry))
    return records


def crosscheck_fixed_queries(queries: list[dict], root: Path, manifest: dict) -> list[dict]:
    """Jede feste Anfrage braucht mindestens eine unabhängige Erwartung; alle müssen passen."""
    records = _independent_query_records(root, manifest)
    checks = []
    for query in queries:
        matching = [record for record in records
                    if record[1] == query["kind"] and record[2] == tuple(query["terms"])]
        if not matching:
            raise ValueError(f"{query['id']}: no independent expectation in manifest or suggestions")
        for source, kind, _terms, entry in matching:
            expected = query["expected"]
            if kind == "word":
                same = entry["df"] == query["hit_count"] and entry["cf"] == query["cf"][0]
                _compare_document_list(entry, expected, f"{query['id']} ({source})")
            elif kind in ("and", "or"):
                same = entry["hit_count"] == query["hit_count"] and entry.get("df", query["df"]) == query["df"]
                _compare_document_list(entry, expected, f"{query['id']} ({source})")
            else:
                same = ((entry["document_count"], entry["match_count"], entry["positions_sha256"])
                        == (query["hit_count"], query["position_count"], _positions_hash(expected))
                        and entry.get("positions", expected) == expected
                        and entry.get("df_terms", query["df"]) == query["df"])
            if not same:
                raise ValueError(f"{query['id']}: disagrees with independent expectation ({source})")
        checks.append({"query_id": query["id"], "sources": sorted({record[0] for record in matching})})
    return checks


def validate_fixed_query_specs(specs: object) -> list[dict]:
    """Feste Profilanfragen der Versuchsdefinition: Art, Kategorie, Rohtext."""
    if not isinstance(specs, list) or not specs:
        raise ValueError("fixed queries must be a nonempty list")
    for spec in specs:
        if not isinstance(spec, dict) or set(spec) != {"kind", "category", "text"}:
            raise ValueError("each fixed query needs exactly kind, category and text")
        if spec["kind"] not in QUERY_KINDS:
            raise ValueError("unknown fixed query kind")
        if (not isinstance(spec["category"], str) or not spec["category"]
                or any(character not in "abcdefghijklmnopqrstuvwxyz_" for character in spec["category"])):
            raise ValueError("fixed query category must be lowercase ASCII")
        if not isinstance(spec["text"], str) or not spec["text"].strip():
            raise ValueError("fixed query text must be nonempty")
    return specs


def build_fixed_queries(tokens_by_id: dict[str, tuple[str, ...]], dataset_id: str,
                        specs: list[dict]) -> list[dict]:
    """Vorab festgelegte Profilanfragen mit Erwartung aus dem unabhängigen Orakel."""
    cf = Counter(token for tokens in tokens_by_id.values() for token in tokens)
    df = Counter(token for tokens in tokens_by_id.values() for token in set(tokens))
    queries = []
    for spec in validate_fixed_query_specs(specs):
        kind, category, text = spec["kind"], spec["category"], spec["text"]
        terms = independent_tokens(text)
        if not terms or (kind == "word" and len(terms) != 1):
            raise ValueError(f"fixed {kind} query {text!r} has an invalid token count")
        if kind in ("and", "or") and (
                [independent_tokens(word) for word in text.split()] != [(term,) for term in terms]
                or len(set(terms)) != len(terms)):
            raise ValueError(f"boolean query {text!r} must consist of distinct single-token words")
        expected = expected_result(tokens_by_id, kind, terms)
        if (category == "missing") != (not expected):
            raise ValueError(f"fixed query {text!r}: category missing must mean exactly no hits")
        queries.append({
            "id": f"{dataset_id}:{kind}:{category}:k{len(terms)}", "kind": kind, "text": text,
            "terms": list(terms), "category": category, "length": len(terms),
            "cf": [cf[term] for term in terms], "df": [df[term] for term in terms],
            "expected": expected, "hit_count": len(expected),
            "position_count": sum(map(len, expected.values())) if kind == "phrase" else None,
        })
    if len({query["id"] for query in queries}) != len(queries):
        raise ValueError("query IDs must be unique")
    return queries


def verify_real_snapshot(root: Path) -> tuple[dict, dict[str, tuple[str, ...]]]:
    """Check source archive, extraction and fixed independent expectations.

    Manifeste mit ``corpus_root`` (mehrere Dokumente) gehen an
    ``_verify_document_collection``; der Kafka-Auszug behält seine Prüfung.
    """
    source_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if is_document_collection(source_manifest):
        return _verify_document_collection(root, source_manifest)
    archive = (root / source_manifest["source_file"]).read_bytes()
    if len(archive) != source_manifest["source_bytes"] or _digest(archive) != source_manifest["source_sha256"]:
        raise ValueError("real source archive does not match its pinned manifest")
    source = archive.decode("utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")
    selection = source_manifest["selection"]
    start_marker, end_marker = selection["start_inclusive"], selection["end_exclusive"]
    if source.count(start_marker) != 1 or source.count(end_marker) != 1:
        raise ValueError("source extraction markers must be unique")
    start = source.index(start_marker)
    end = source.index(end_marker)
    if end <= start:
        raise ValueError("source extraction markers have wrong order")
    extracted = (source[start:end].strip() + "\n").encode("utf-8")
    entries = source_manifest["documents"]
    if len(entries) != 1:
        raise ValueError("the existing real snapshot must contain exactly one selected document")
    entry = entries[0]
    actual = (root / entry["source_path"]).read_bytes()
    if (actual != extracted or len(actual) != entry["bytes"] or _digest(actual) != entry["sha256"]):
        raise ValueError("real excerpt does not match extraction/hash/size")
    if len(actual.decode("utf-8").strip().split("\n\n")) != selection["paragraph_count"]:
        raise ValueError("real excerpt paragraph count changed")
    tokens = independent_tokens(actual.decode("utf-8"))
    if list(tokens[:len(source_manifest["expected_prefix_tokens"])]) != source_manifest["expected_prefix_tokens"]:
        raise ValueError("real excerpt disagrees with the fixed prefix tokens")
    for query in source_manifest["verified_queries"]:
        term, = independent_tokens(query["query"])
        starts = [position for position, token in enumerate(tokens) if token == term]
        if starts != query["expected_token_positions"] or len(starts) != query["expected_occurrences"]:
            raise ValueError("real excerpt disagrees with fixed term positions")
    expected_ids = {entry["document_id"]}
    loaded_ids = {document.document_id for document in load_corpus(root)}
    if loaded_ids != expected_ids:
        raise ValueError("real corpus file list changed")
    return source_manifest, {entry["document_id"]: tokens}


def build_queries(tokens_by_id: dict[str, tuple[str, ...]], dataset_id: str,
                  *, synthetic: bool = False) -> list[dict]:
    """Fixed deterministic query families, selected before timing, no query RNG."""
    cf = Counter(token for tokens in tokens_by_id.values() for token in tokens)
    df = Counter(token for tokens in tokens_by_id.values() for token in set(tokens))
    if not cf:
        raise ValueError("query generation requires a nonempty token corpus")
    missing = "x999"
    while missing in cf:
        missing += "x"
    ranked = sorted(cf, key=lambda token: (-cf[token], token))
    rare_ranked = sorted(cf, key=lambda token: (cf[token], token))
    queries = []

    def add(kind: str, terms: tuple[str, ...], category: str, suffix: str = "") -> None:
        expected = expected_result(tokens_by_id, kind, terms)
        identifier = f"{dataset_id}:{kind}:{category}:k{len(terms)}{suffix}"
        queries.append({
            "id": identifier, "kind": kind, "text": " ".join(terms).upper(),
            "terms": list(terms), "category": category, "length": len(terms),
            "cf": [cf[term] for term in terms], "df": [df[term] for term in terms],
            "expected": expected, "hit_count": len(expected),
            "position_count": sum(map(len, expected.values())) if kind == "phrase" else None,
        })

    add("word", (FREQUENT[0] if synthetic else ranked[0],), "frequent")
    add("word", (RARE[0] if synthetic else ("fenster" if "fenster" in cf else rare_ranked[0]),), "rare")
    add("word", (missing,), "missing")
    for kind in ("and", "or"):
        for length in (2, 3, 5):
            frequent = FREQUENT[:length] if synthetic else tuple(ranked[:length])
            rare = RARE[:length] if synthetic else tuple(rare_ranked[:length])
            mixed = ({2: ("f000", "s000"), 3: ("f000", "b000", "s000"),
                      5: ("f000", "f001", "b000", "b001" if "b001" in cf else "f002", "s000")}[length]
                     if synthetic else tuple(ranked[:length - 1]) + (rare_ranked[0],))
            for category, terms in (("frequent", frequent), ("rare", rare), ("mixed", mixed),
                                    ("missing", frequent[:-1] + (missing,))):
                add(kind, terms, category)

    for length in PHRASE_LENGTHS:
        if synthetic:
            frequent, rare = FREQUENT[:length], RARE[:length]
        else:
            windows = Counter(tokens[start:start + length]
                              for tokens in tokens_by_id.values()
                              for start in range(len(tokens) - length + 1))
            frequent = min(windows, key=lambda window: (-windows[window], window))
            rare = min(windows, key=lambda window: (windows[window], window))
        add("phrase", frequent, "frequent")
        add("phrase", rare, "rare")
        add("phrase", (missing,) * length, "missing")
        if synthetic:
            add("phrase", REPEATED[:length], "repeated")
            if length > 1:
                add("phrase", FREQUENT[:length][::-1], "wrong_order")
    if not synthetic:
        repeated_terms = [token for token in ranked
                          if expected_result(tokens_by_id, "phrase", (token, token))]
        if repeated_terms:
            # The existing real manifest independently pins both Gregor runs.
            repeated_term = "gregor" if "gregor" in repeated_terms else repeated_terms[0]
            add("phrase", (repeated_term,) * 2, "repeated")
    if len({query["id"] for query in queries}) != len(queries):
        raise ValueError("query IDs must be unique")
    return queries


def build_datasets(config: dict, output: Path) -> list[dict]:
    """Persist each dataset's manifest and query set, return prepared contracts.

    Raw files live in output/<id>/corpus; the pinned real archive is copied
    byte-for-byte, leaving the repository source unchanged. Existing dataset output is rejected.
    Every independently expected token is compared before query generation.
    """
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int or config.get("schema_version") != 1:
        raise ValueError("dataset config schema_version must equal 1")
    specs = config.get("datasets")
    if not isinstance(specs, list) or not specs:
        raise ValueError("datasets must be a nonempty list")
    default_seed = config.get("seed", 20261006)
    validated = []
    ids = set()
    output = Path(output)
    for spec in specs:
        if not isinstance(spec, dict):
            raise ValueError("each dataset specification must be an object")
        identifier = spec.get("id")
        if (not isinstance(identifier, str) or not identifier or
                any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in identifier)):
            raise ValueError("dataset id must contain only ASCII letters, digits, underscores or hyphens")
        if identifier in ids:
            raise ValueError("duplicate dataset id")
        ids.add(identifier)
        if (output / identifier).exists():
            raise ValueError(f"dataset output already exists: {output / identifier}")
        kind = spec.get("kind")
        if kind == "synthetic":
            if "queries" in spec:
                raise ValueError("fixed queries are only defined for document collections")
            validated.append((spec, _synthetic_parameters(spec, default_seed)))
        elif kind == "real":
            if not isinstance(spec.get("path"), str) or not spec["path"]:
                raise ValueError("real dataset path must be a nonempty string")
            root = Path(spec["path"])
            if not root.is_absolute():
                root = REPOSITORY / root
            source_manifest, token_plan = verify_real_snapshot(root)
            # Automatische Realfamilien sind auf den Kafka-Auszug zugeschnitten;
            # Mehrdokumentkorpora verwenden vorab festgelegte Profilanfragen.
            if is_document_collection(source_manifest):
                validate_fixed_query_specs(spec.get("queries"))
            elif "queries" in spec:
                raise ValueError("fixed queries are only defined for document collections")
            validated.append((spec, (root, source_manifest, token_plan)))
        else:
            raise ValueError("dataset kind must be synthetic or real")
    results = []
    for spec, detail in validated:
        directory = output / spec["id"]
        directory.mkdir(parents=True)
        if spec["kind"] == "synthetic":
            root = directory / "corpus"
            token_plan = _generate_synthetic(root, detail)
            provenance = {"generator_version": GENERATOR_VERSION, "parameters": detail}
        else:
            original, source_manifest, token_plan = detail
            collection = is_document_collection(source_manifest)
            root = directory / "corpus"
            root.mkdir()
            if collection:
                pinned, documenting = _collection_snapshot_files(original, source_manifest)
                names = [*pinned, *documenting,
                         *(f"{source_manifest['corpus_root']}/{entry['document_id']}"
                           for entry in source_manifest["documents"])]
            else:
                names = ["manifest.json", source_manifest["source_file"],
                         *(entry["source_path"] for entry in source_manifest["documents"])]
                if (original / "README.md").is_file():
                    names.append("README.md")
            for name in names:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((original / name).read_bytes())
            copied_manifest, copied_tokens = verify_real_snapshot(root)
            if copied_manifest != source_manifest or copied_tokens != token_plan:
                raise ValueError("real snapshot changed while copying")
            if collection:
                provenance = {
                    "generator_version": None, "source_location": spec["path"],
                    "source_dataset_id": source_manifest.get("dataset_id"),
                    "source_manifest_sha256": _digest((root / "manifest.json").read_bytes()),
                    "source_summary": {key: source_manifest.get(key) for key in (
                        "title", "publisher", "download_url", "retrieved_at",
                        "source_sha256", "corpus_sha256", "law_status")},
                    "snapshot_copy": "byte-identical", "corpus_root": source_manifest["corpus_root"],
                    "snapshot_files": {name: _digest((root / name).read_bytes()) for name in pinned},
                    "documentation_files": documenting,
                    "conversion_check": ("offline regeneration with the pinned conversion script "
                                         "('pruefen') is byte-identical"
                                         if source_manifest.get("conversion", {}).get("script") else None),
                }
                snapshot_root = root
                root = root / source_manifest["corpus_root"]
            else:
                provenance = {"generator_version": None, "source_manifest": source_manifest,
                              "source_location": spec["path"], "snapshot_copy": "byte-identical",
                              "selection_and_cleanup": source_manifest["selection"]}
        prepared = prepare_corpus(load_corpus(root))
        actual_tokens = {document.document_id: document.tokens for document in prepared}
        if actual_tokens != token_plan:
            raise ValueError(f"{spec['id']}: preparation disagrees with independent expected token plan")
        files = [{"document_id": identifier, "sha256": _digest((root / identifier).read_bytes()),
                  "bytes": (root / identifier).stat().st_size, "token_count": len(tokens)}
                 for identifier, tokens in sorted(token_plan.items())]
        fixed = "queries" in spec
        if fixed:
            queries = build_fixed_queries(token_plan, spec["id"], spec["queries"])
            provenance["query_crosschecks"] = crosscheck_fixed_queries(queries, snapshot_root, source_manifest)
        else:
            queries = build_queries(token_plan, spec["id"], synthetic=spec["kind"] == "synthetic")
        query_payload = (json.dumps(queries, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        manifest = {
            "schema_version": 1, "dataset_id": spec["id"], "kind": spec["kind"],
            **provenance, "document_count": len(files),
            "total_tokens": sum(entry["token_count"] for entry in files),
            "actual_vocabulary": len({token for tokens in token_plan.values() for token in tokens}),
            "raw_bytes": sum(entry["bytes"] for entry in files),
            "file_order": [entry["document_id"] for entry in files], "files": files,
            "expected_tokens": {identifier: list(tokens) for identifier, tokens in sorted(token_plan.items())},
            "token_expectation_origin": "independent planting plan" if spec["kind"] == "synthetic"
                                        else "independent Unicode groupby plus pinned prefix and term positions",
            "query_generator_version": QUERY_GENERATOR_VERSION, "query_seed": None,
            "query_selection": "deterministic fixed families; CF ties broken lexicographically; no measurement input",
            "queries_sha256": _digest(query_payload),
        }
        if fixed:
            manifest.update(
                token_expectation_origin=("independent Unicode groupby; compared with the independently computed "
                                          "D/N/V/P, document lengths, ranks, prefix, word and phrase expectations "
                                          "of the source manifest"),
                query_generator_version=FIXED_QUERY_GENERATOR_VERSION,
                query_selection=("fixed profile queries from the experiment definition, chosen before timing; "
                                 "expectations from the independent token oracle, cross-checked against "
                                 "manifest expectations and query suggestions; no measurement input"))
        if spec["kind"] == "synthetic" and manifest["actual_vocabulary"] != detail["vocabulary"]:
            raise ValueError("actual vocabulary differs from the requested vocabulary")
        _write_json(directory / "manifest.json", manifest)
        (directory / "queries.json").write_bytes(query_payload)
        results.append({"id": spec["id"], "kind": spec["kind"], "root": root,
                        "manifest": manifest, "queries": queries, "expected_tokens": token_plan})
    return results


def generate_from_config(config_path: str | Path, output: str | Path) -> list[dict]:
    """Read a persisted experiment definition and write raw/manifest/query files."""
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    return build_datasets(config, Path(output))
