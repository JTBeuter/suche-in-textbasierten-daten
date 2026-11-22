"""Strikte Gesamtkostenungleichung auf einem ganzzahligen Q-Bereich."""
from fractions import Fraction


def cheaper_range(delta_c, delta_t, q_min=0, q_max=None):
    """Löse Q*delta_t > delta_c; Gleichheit zählt nicht als Vorteil.

    Fraction erhält rationale Blockkosten ohne vorzeitige Rundung. Q=0 ist
    zulässig und macht anfängliche Vorteile bei negativer Vorbereitung sichtbar.
    """
    for name, value in (("q_min", q_min), ("q_max", q_max)):
        if (value is None and name == "q_min") or (value is not None and (type(value) is not int or value < 0)):
            raise ValueError(f"{name} muss eine nichtnegative ganze Zahl sein")
    if q_max is not None and q_max < q_min:
        raise ValueError("q_max muss mindestens q_min sein")
    dc, dt = Fraction(delta_c), Fraction(delta_t)
    first, last = q_min, q_max
    threshold = None if not dt else dc / dt
    if dt > 0:
        first = max(first, threshold.numerator // threshold.denominator + 1)
    elif dt < 0:
        ceiling = -(-threshold.numerator // threshold.denominator)
        last = ceiling - 1 if last is None else min(last, ceiling - 1)
    elif dc >= 0:
        first, last = 1, 0
    exists = last is None or first <= last
    return {"delta_c_ns": float(dc), "delta_t_ns": float(dt),
            "equality_q": None if threshold is None else float(threshold),
            "first_cheaper_q": first if exists else None,
            "last_cheaper_q": last if exists else None,
            "has_advantage": exists,
            "later_amortisation": bool(dt > 0 and exists)}


def amortisation_3_6(t_aufbau, t_direkt, t_index):
    """Vereinfachte Amortisationsrechnung aus Abschnitt 3.6 der Arbeit.

    T_direkt(q)=Vorbereitung+q*t_direkt und T_index(q)=Vorbereitung+t_Aufbau+q*t_index.
    Bei t_direkt>t_index gilt q*=t_Aufbau/(t_direkt-t_index); ab ⌈q*⌉ ist der Index
    nach dem Modell nicht langsamer (bei ganzzahligem q* herrscht dort Gleichstand,
    strikt schneller ist er dann erst ab q*+1, siehe ``cheaper_range``). Ist die
    Indexabfrage nicht schneller, amortisiert sich der Aufbau nie. Fraction
    vermeidet Rundung vor dem Aufrunden.
    """
    aufbau, direkt, index = Fraction(t_aufbau), Fraction(t_direkt), Fraction(t_index)
    if aufbau < 0 or direkt < 0 or index < 0:
        raise ValueError("Zeiten müssen nichtnegativ sein")
    differenz = direkt - index
    result = {"t_aufbau_ns": float(aufbau), "t_direkt_ns": float(direkt), "t_index_ns": float(index),
              "differenz_ns": float(differenz)}
    if differenz <= 0:
        return {**result, "q_stern": None, "q_stern_aufgerundet": None,
                "gleichstand_bei_q_stern": False, "amortisation": "nie"}
    q_stern = aufbau / differenz
    aufgerundet = -(-q_stern.numerator // q_stern.denominator)
    return {**result, "q_stern": float(q_stern), "q_stern_aufgerundet": aufgerundet,
            "gleichstand_bei_q_stern": q_stern.denominator == 1, "amortisation": aufgerundet}
