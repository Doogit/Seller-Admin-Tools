"""CSV loading, type coercion, date-format inference, name normalization."""

from __future__ import annotations

import datetime as dt
import io
import re
from pathlib import Path

import pandas as pd
import yaml

from core import schema

CURRENCY_RE = re.compile(r"[$€£¥]")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLASH_DATE_RE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$")

CORPORATE_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited",
    "co", "company", "plc", "gmbh",
}

DATE_FORMATS = ("auto", "mdy", "dmy", "iso")


class AmbiguousDateFormat(Exception):
    """All sampled date values are ambiguous (both parts <= 12) — the user
    must choose a format explicitly."""


class ConflictingDateFormat(Exception):
    """The data contains both mdy-only and dmy-only values; no single format
    can parse the file correctly."""

    def __init__(self, mdy_values: list[str], dmy_values: list[str]):
        self.mdy_values = mdy_values
        self.dmy_values = dmy_values
        super().__init__(
            "Conflicting date evidence: values only valid as month-first "
            f"({', '.join(mdy_values[:3])}) AND values only valid as day-first "
            f"({', '.join(dmy_values[:3])}) in the same file."
        )


def load_csv(file) -> pd.DataFrame:
    """Load a CSV (path, bytes, or file-like) into an all-string frame.

    Tolerates UTF-8 BOM and semicolon delimiters. Blank cells become "".
    """
    if isinstance(file, bytes):
        raw = file
    elif hasattr(file, "read"):
        raw = file.read()
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
    else:
        raw = Path(file).read_bytes()
    text = raw.decode("utf-8-sig")

    header = text.splitlines()[0] if text else ""
    sep = ";" if header.count(";") > header.count(",") else ","

    df = pd.read_csv(
        io.StringIO(text), sep=sep, dtype=str, keep_default_na=False, skipinitialspace=True
    )
    df.columns = [str(c).strip() for c in df.columns]
    return df


def parse_amount_series(s: pd.Series) -> tuple[pd.Series, list[str]]:
    """Coerce currency strings to floats. Handles $, thousands separators,
    and ($1,234.00)-style negatives. Warns if multiple currency symbols appear."""
    problems: list[str] = []
    symbols: set[str] = set()
    values: list[float | None] = []
    for v in s:
        v0 = (v or "").strip()
        if not v0:
            values.append(None)
            continue
        symbols.update(CURRENCY_RE.findall(v0))
        negative = v0.startswith("(") and v0.endswith(")")
        cleaned = re.sub(r"[^\d.\-]", "", v0)
        try:
            num = float(cleaned)
        except ValueError:
            problems.append(f"Unparseable amount '{v0}' — stored as empty.")
            values.append(None)
            continue
        values.append(-abs(num) if negative else num)
    if len(symbols) > 1:
        problems.append(
            f"Multiple currency symbols detected ({', '.join(sorted(symbols))}) — "
            "mixed currencies are out of scope; all amounts treated as USD."
        )
    return pd.Series(values, index=s.index, dtype="float64"), problems


def _classify_date_value(v: str) -> str:
    """'iso' | 'mdy_only' | 'dmy_only' | 'ambiguous' | 'blank' | 'other'."""
    v = (v or "").strip()
    if not v:
        return "blank"
    if ISO_DATE_RE.match(v):
        return "iso"
    m = SLASH_DATE_RE.match(v)
    if not m:
        return "other"
    a, b = int(m.group(1)), int(m.group(2))
    a_ok_month, b_ok_month = a <= 12, b <= 12
    if a_ok_month and b_ok_month:
        return "ambiguous"
    if a_ok_month:
        return "mdy_only"  # second part > 12, so it must be the day
    if b_ok_month:
        return "dmy_only"
    return "other"  # neither part can be a month — malformed


def infer_date_format(columns: list[pd.Series]) -> str:
    """Resolve 'auto' by sampling ALL mapped date columns jointly (one format
    per file). Three branches: infer / conflict error / ambiguous error."""
    mdy_evidence: list[str] = []
    dmy_evidence: list[str] = []
    saw_ambiguous = False
    saw_iso = False
    for col in columns:
        for v in col:
            kind = _classify_date_value(v)
            if kind == "mdy_only":
                mdy_evidence.append(v.strip())
            elif kind == "dmy_only":
                dmy_evidence.append(v.strip())
            elif kind == "ambiguous":
                saw_ambiguous = True
            elif kind == "iso":
                saw_iso = True
    if mdy_evidence and dmy_evidence:
        raise ConflictingDateFormat(mdy_evidence, dmy_evidence)
    if mdy_evidence:
        return "mdy"
    if dmy_evidence:
        return "dmy"
    if saw_ambiguous:
        raise AmbiguousDateFormat(
            "Every slash-form date is ambiguous (both parts <= 12) — choose a date format."
        )
    return "iso" if saw_iso else "iso"


def parse_date_series(s: pd.Series, date_format: str) -> tuple[pd.Series, pd.Series]:
    """Parse to ISO date strings. Returns (parsed, unparsed) where parsed is
    'YYYY-MM-DD' or '' and unparsed holds the raw value for failures (else '').

    ISO-form values are accepted under any format (they are unambiguous).
    """
    parsed: list[str] = []
    unparsed: list[str] = []
    for v in s:
        v0 = (v or "").strip()
        if not v0:
            parsed.append("")
            unparsed.append("")
            continue
        result = None
        if ISO_DATE_RE.match(v0):
            try:
                result = dt.date.fromisoformat(v0)
            except ValueError:
                result = None
        else:
            m = SLASH_DATE_RE.match(v0)
            if m and date_format in ("mdy", "dmy"):
                a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
                month, day = (a, b) if date_format == "mdy" else (b, a)
                try:
                    result = dt.date(year, month, day)
                except ValueError:
                    result = None
        parsed.append(result.isoformat() if result else "")
        unparsed.append("" if result else v0)
    return (
        pd.Series(parsed, index=s.index, dtype="str"),
        pd.Series(unparsed, index=s.index, dtype="str"),
    )


def base_normalize(name: str) -> str:
    """Lowercase, strip punctuation, drop trailing corporate suffixes."""
    tokens = re.sub(r"[^\w\s]", " ", (name or "").lower()).split()
    while tokens and tokens[-1] in CORPORATE_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def load_alias_index(path) -> dict[str, str]:
    """Build {normalized alias -> canonical} from config/aliases.yaml."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    index: dict[str, str] = {}
    for section in ("accounts", "owners"):
        for canonical, aliases in (data.get(section) or {}).items():
            canon_norm = base_normalize(canonical)
            for alias in aliases or []:
                index[base_normalize(alias)] = canon_norm
    return index


def normalize_name(name: str, alias_index: dict[str, str] | None = None) -> str:
    base = base_normalize(name)
    if alias_index:
        return alias_index.get(base, base)
    return base


def apply_mapping(
    df: pd.DataFrame,
    mapping: dict[str, str | None],
    date_format: str,
    alias_index: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, list[str], str]:
    """Rename mapped source columns to canonical names and coerce types.

    Returns (canonical frame, problem strings, resolved date format).
    Raises AmbiguousDateFormat / ConflictingDateFormat when date_format='auto'
    cannot be resolved — callers (UI) catch these to force a user choice.
    """
    problems: list[str] = []
    out = pd.DataFrame(index=df.index)

    for canonical, source in mapping.items():
        if source and source in df.columns:
            out[canonical] = df[source].astype(str).str.strip()

    mapped_date_cols = [f for f in schema.DATE_FIELDS if f in out.columns]
    resolved = date_format
    if date_format == "auto":
        resolved = infer_date_format([out[f] for f in mapped_date_cols])
    if resolved not in ("mdy", "dmy", "iso"):
        raise ValueError(f"Unknown date format '{resolved}'")

    for field in mapped_date_cols:
        parsed, unparsed = parse_date_series(out[field], resolved)
        out[field] = parsed
        out[f"{field}_unparsed"] = unparsed

    if "amount" in out.columns:
        out["amount"], amount_problems = parse_amount_series(out["amount"])
        problems.extend(amount_problems)

    if "probability" in out.columns:
        out["probability"] = pd.to_numeric(
            out["probability"].str.replace("%", "", regex=False), errors="coerce"
        )

    for field in ("account_name", "owner"):
        if field in out.columns:
            out[f"{field}_raw"] = out[field]
            out[field] = out[field].map(lambda v: normalize_name(v, alias_index))

    return out, problems, resolved
