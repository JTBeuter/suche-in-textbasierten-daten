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


def galloping_diagnostic(left, right):
    """Eigener Diagnose-Durchlauf für die Galloping Search (Variante galloping).

    Bildet intersect_galloping Schritt für Schritt nach und zählt relationale
    Kennungsvergleiche getrennt: Proben der Sprungphase (`<`, einschließlich
    der ersten Probe an der aktuellen Position), Binärsuchschritte (`<`) und
    abschließende Gleichheitsprüfungen (`==`). Schleifen- und Längenprüfungen
    sind kein Kennungsvergleich. Niemals aus dem gemessenen Suchpfad
    aufgerufen; gleiche Ausgaben beweisen keine gleichen Laufzeitkonstanten.
    """
    shorter, longer = (right, left) if len(right) < len(left) else (left, right)
    result = []
    size = len(longer)
    position = probes = binary_steps = equality_checks = keys = 0
    for key in shorter:
        if position >= size:
            break
        keys += 1
        low = high = position
        step = 1
        while high < size:
            probes += 1
            if not longer[high] < key:
                break
            low = high + 1
            high = position + step
            step *= 2
        if high > size:
            high = size
        while low < high:
            middle = (low + high) // 2
            binary_steps += 1
            if longer[middle] < key:
                low = middle + 1
            else:
                high = middle
        if low < size:
            equality_checks += 1
            if longer[low] == key:
                result.append(key)
                low += 1
        position = low
    counts = {"id_comparisons": probes + binary_steps + equality_checks, "gallop_probes": probes,
              "binary_search_steps": binary_steps, "equality_checks": equality_checks,
              "examined_short_ids": keys}
    return result, counts


def diagnose_postings_galloping(postings, terms):
    """Wie diagnose_postings für AND, aber stabil nach Länge sortiert und galoppierend geschnitten."""
    order = sorted(terms, key=lambda word: len(postings.get(word, ())))
    intermediate = []
    merge_inputs = []
    totals = {"id_comparisons": 0, "gallop_probes": 0, "binary_search_steps": 0,
              "equality_checks": 0, "examined_short_ids": 0}
    result = list(postings.get(order[0], ()))
    intermediate.append(len(result))
    for word in order[1:]:
        if not result:
            break
        following = postings.get(word, ())
        merge_inputs.append([len(result), len(following)])
        result, counts = galloping_diagnostic(result, following)
        for name, value in counts.items():
            totals[name] += value
        intermediate.append(len(result))
    return {"ordered_terms": order, "posting_lengths": [len(postings.get(word, ())) for word in order],
            "merge_input_lengths": merge_inputs, "intermediate_lengths": intermediate, **totals,
            "result_ids": result}


def difference_diagnostic(left, right):
    """Nachbildung von difference_sorted (AND NOT) mit Zählern wie merge_diagnostic.

    Gezählt werden `==` und bei Ungleichheit zusätzlich `<` sowie Zeigerschritte
    im gemeinsamen Teil; der Rest von left wird ohne Vergleich übernommen.
    """
    i = j = comparisons = advances = 0
    result = []
    while i < len(left) and j < len(right):
        comparisons += 1
        if left[i] == right[j]:
            i += 1
            j += 1
            advances += 2
        else:
            comparisons += 1
            if left[i] < right[j]:
                result.append(left[i])
                i += 1
            else:
                j += 1
            advances += 1
    result.extend(left[i:])
    advances += len(left) - i
    return result, comparisons, advances


def diagnose_direct_exclude(tokens_by_id, terms, exclude):
    """Besuchte Tokens der direkten Referenz bei AND NOT.

    Wie search_direct_boolean mit exclude: Abbruch nur beim NOT-Wort, sonst wird
    das ganze Dokument gelesen.
    """
    required = set(terms)
    visited = 0
    result = []
    for identifier, tokens in sorted(tokens_by_id.items()):
        seen = set()
        excluded = False
        for token in tokens:
            visited += 1
            if token == exclude:
                excluded = True
                break
            if token in required:
                seen.add(token)
        if not excluded and seen == required:
            result.append(identifier)
    return {"visited_tokens": visited, "result_ids": result}
