"""Eigene Zwei-Zeiger-Verfahren; Eingaben sind sortiert und eindeutig."""

from collections.abc import Sequence


def intersect_sorted(left: Sequence[str], right: Sequence[str]) -> list[str]:
    """Schnittmenge in O(len(left)+len(right)); keine Eingabemutation.

    Vorbedingung: beide Folgen enthalten eindeutige, lexikografisch sortierte
    Dokumentkennungen. Der Indexaufbau sichert diese Invariante einmalig;
    die Abfrage wiederholt keine vollständige Listenvalidierung.
    """
    result: list[str] = []
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = left[i], right[j]
        if a == b:
            result.append(a)
            i += 1
            j += 1
        elif a < b:
            i += 1
        else:
            j += 1
    return result


def union_sorted(left: Sequence[str], right: Sequence[str]) -> list[str]:
    """Vereinigung inklusive beider Reste; sortierte, eindeutige neue Liste."""
    result: list[str] = []
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = left[i], right[j]
        if a == b:
            result.append(a)
            i += 1
            j += 1
        elif a < b:
            result.append(a)
            i += 1
        else:
            result.append(b)
            j += 1
    while i < len(left):
        result.append(left[i])
        i += 1
    while j < len(right):
        result.append(right[j])
        j += 1
    return result
