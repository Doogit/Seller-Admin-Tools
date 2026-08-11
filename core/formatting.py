"""Money formatting shared by narrative, pages, and deck export.

fmt_money and parse_money are exact inverses at display precision — the deck
consistency-guard test relies on formatting both sides with fmt_money and
comparing parse_money outputs, so a wording tweak can't hide a wrong number.
"""

from __future__ import annotations


def fmt_money(x: float) -> str:
    neg = "-" if x < 0 else ""
    v = abs(x)
    if v >= 1_000_000:
        return f"{neg}${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{neg}${v / 1_000:.0f}K"
    return f"{neg}${v:,.0f}"


def parse_money(s: str) -> float:
    t = s.strip().replace("$", "").replace(",", "")
    sign = -1.0 if t.startswith("-") else 1.0
    t = t.lstrip("-")
    mult = 1.0
    if t.endswith("M"):
        mult, t = 1_000_000.0, t[:-1]
    elif t.endswith("K"):
        mult, t = 1_000.0, t[:-1]
    return sign * float(t) * mult
