"""Bağımlılıksız küçük istatistik yardımcıları (deterministik)."""
from __future__ import annotations


def siralar(degerler: list[float]) -> list[float]:
    """Ortalama sıra (eşitlikte ortalama), 1'den başlar."""
    sirali = sorted(range(len(degerler)), key=lambda i: degerler[i])
    r = [0.0] * len(degerler)
    i = 0
    while i < len(sirali):
        j = i
        while j + 1 < len(sirali) and degerler[sirali[j + 1]] == degerler[sirali[i]]:
            j += 1
        ort = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[sirali[k]] = ort
        i = j + 1
    return r


def yuzdelik(degerler: dict[str, float]) -> dict[str, float]:
    """Soru içi yüzdelik sıra (0 = en az, 1 = en çok). Tek değer -> 0.5."""
    anahtar = sorted(degerler)
    if not anahtar:
        return {}
    if len(anahtar) == 1:
        return {anahtar[0]: 0.5}
    r = siralar([degerler[a] for a in anahtar])
    n = len(anahtar)
    return {a: (r[i] - 1) / (n - 1) for i, a in enumerate(anahtar)}


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3 or len(x) != len(y):
        return None
    rx, ry = siralar(x), siralar(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    pay = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    px = sum((a - mx) ** 2 for a in rx) ** 0.5
    py = sum((b - my) ** 2 for b in ry) ** 0.5
    if not px or not py:
        return None
    return pay / (px * py)


def medyan(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
