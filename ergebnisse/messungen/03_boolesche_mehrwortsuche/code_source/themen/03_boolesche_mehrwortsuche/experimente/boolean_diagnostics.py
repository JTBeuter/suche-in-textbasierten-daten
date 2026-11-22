"""Gesonderte Kostendiagnose: niemals aus dem gemessenen Suchpfad aufgerufen."""

from __future__ import annotations


def merge_diagnostic(left, right, operator):
    """Eigener Diagnose-Durchlauf zählt ID-Vergleiche und Fortschritte.

    Zähler gehören nur zu dieser nachgebildeten Listenoperation. Gleiche
    Ausgabewerte beweisen keine identischen Laufzeitkonstanten im Suchcode.
    """
    i = j = comparisons = advances = 0
    result = []
    while i < len(left) and j < len(right):
        comparisons += 1
        if left[i] == right[j]:
            result.append(left[i])
            i += 1
            j += 1
            advances += 2
        else:
            # Neben == wird bei Ungleichheit auch < ausgewertet, wie im
            # Produktionsverfahren; Schleifen-/Längenprüfungen sind kein ID-Vergleich.
            comparisons += 1
            if left[i] < right[j]:
                if operator == "OR":
                    result.append(left[i])
                i += 1
                advances += 1
            else:
                if operator == "OR":
                    result.append(right[j])
                j += 1
                advances += 1
    if operator == "OR":
        result.extend(left[i:])
        result.extend(right[j:])
        advances += len(left) - i + len(right) - j
    return result, comparisons, advances


def diagnose_postings(postings, terms, operator, variant):
    order = list(terms)
    if variant == "shortest_first":
        order.sort(key=lambda word: len(postings.get(word, ())))
    intermediate = []
    merge_inputs = []
    comparisons = advances = 0
    result = list(postings.get(order[0], ()))
    intermediate.append(len(result))
    for word in order[1:]:
        if operator == "AND" and not result:
            break
        following = postings.get(word, ())
        merge_inputs.append([len(result), len(following)])
        result, count, progress = merge_diagnostic(result, following, operator)
        comparisons += count
        advances += progress
        intermediate.append(len(result))
    return {"ordered_terms": order, "posting_lengths": [len(postings.get(word, ())) for word in order],
            "merge_input_lengths": merge_inputs, "intermediate_lengths": intermediate,
            "id_comparisons": comparisons, "pointer_advances": advances,
            "result_ids": result}


def diagnose_direct(tokens_by_id, terms, operator):
    required = set(terms)
    visited = 0
    result = []
    for identifier, tokens in sorted(tokens_by_id.items()):
        seen = set()
        for token in tokens:
            visited += 1
            if token in required:
                seen.add(token)
                if operator == "OR" or seen == required:
                    result.append(identifier)
                    break
    return {"visited_tokens": visited, "result_ids": result}
