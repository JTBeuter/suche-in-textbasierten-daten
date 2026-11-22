"""Eigene Listenverfahren (Zwei-Zeiger, Galloping Search); Eingaben sind sortiert und eindeutig."""

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


def intersect_galloping(left: Sequence[str], right: Sequence[str]) -> list[str]:
    """Schnittmenge per Galloping Search in O(a·log(b/a)); keine Eingabemutation.

    a ist die Länge der kürzeren, b die der längeren Folge. Die Funktion wählt
    selbst: Die Kennungen kommen immer aus der kürzeren Folge (bei gleicher
    Länge aus left). Für jede Kennung prüft sie in der längeren Folge zuerst
    die aktuelle Position und springt dann mit exponentiell wachsenden
    Abständen 1, 2, 4, 8, … ab dieser Position vorwärts, bis ein Eintrag
    nicht mehr kleiner ist oder das Ende erreicht ist. Danach sucht eine
    Binärsuche nur im letzten Sprungintervall die erste Stelle, deren Eintrag
    nicht kleiner ist. Die Position wandert nur vorwärts; Einträge vor ihr
    sind kleiner als jede noch folgende Kennung.

    Liegt die gesuchte Stelle d Einträge hinter der aktuellen Position,
    kosten Sprünge und Binärsuche je O(1 + log d) Vergleiche. Weil die
    Abstände zusammen höchstens b ergeben, folgt insgesamt O(a·log(b/a)),
    genauer O(a·(1 + log(b/a))). Bei ähnlich langen Folgen ist das wie bei
    intersect_sorted linear, bei sehr ungleichen Längen deutlich weniger.
    Vorbedingung wie bei intersect_sorted: beide Folgen eindeutig und
    lexikografisch sortiert; geprüft wird das hier nicht erneut.
    """
    shorter, longer = (right, left) if len(right) < len(left) else (left, right)
    result: list[str] = []
    size = len(longer)
    position = 0
    for key in shorter:
        if position >= size:
            break
        # Sprungphase: low ist die erste noch mögliche Stelle, high die Probe.
        low = high = position
        step = 1
        while high < size and longer[high] < key:
            low = high + 1
            high = position + step
            step *= 2
        if high > size:
            high = size
        # Binärsuche im letzten Sprungintervall [low, high): erste Stelle >= key.
        while low < high:
            middle = (low + high) // 2
            if longer[middle] < key:
                low = middle + 1
            else:
                high = middle
        if low < size and longer[low] == key:
            result.append(key)
            low += 1
        position = low
    return result


def difference_sorted(left: Sequence[str], right: Sequence[str]) -> list[str]:
    """Differenz left ohne right in O(len(left)+len(right)); keine Eingabemutation.

    Zwei-Zeiger-Verfahren wie intersect_sorted: Übernommen werden nur
    Kennungen aus left, die in right fehlen. Der Rest von left nach dem Ende
    von right wird vollständig übernommen. Dieselbe Vorbedingung.
    """
    result: list[str] = []
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = left[i], right[j]
        if a == b:
            i += 1
            j += 1
        elif a < b:
            result.append(a)
            i += 1
        else:
            j += 1
    while i < len(left):
        result.append(left[i])
        i += 1
    return result
