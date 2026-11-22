"""Reproducible datasets and independent query expectations for experiment 05.

The synthetic token plan is made before writing or loading any document. The
real dataset keeps the pinned project snapshot, with an independent tokenizer
and the manually recorded prefix/word positions as additional checks.
"""

from __future__ import annotations

from collections import Counter
import hashlib
from itertools import groupby
import json
from pathlib import Path
import random
import unicodedata

from gemeinsam import load_corpus, prepare_corpus


GENERATOR_VERSION = "05-planted-v1"
QUERY_GENERATOR_VERSION = "05-queries-v1"
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


def verify_real_snapshot(root: Path) -> tuple[dict, dict[str, tuple[str, ...]]]:
    """Check source archive, extraction and fixed independent expectations."""
    source_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
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
            validated.append((spec, _synthetic_parameters(spec, default_seed)))
        elif kind == "real":
            if not isinstance(spec.get("path"), str) or not spec["path"]:
                raise ValueError("real dataset path must be a nonempty string")
            root = Path(spec["path"])
            if not root.is_absolute():
                root = REPOSITORY / root
            source_manifest, token_plan = verify_real_snapshot(root)
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
            root = directory / "corpus"
            root.mkdir()
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
