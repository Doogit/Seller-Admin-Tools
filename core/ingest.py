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


class IngestError(Exception):
    """File-level problem the user must fix (empty file, colliding headers,
    undecodable bytes) — shown as a friendly error, never a traceback."""


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
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")  # default Windows/Excel ANSI export
    if not text.strip():
        raise IngestError("The file is empty — nothing to import.")

    header = text.splitlines()[0]
    sep = ";" if header.count(";") > header.count(",") else ","

    df = pd.read_csv(
        io.StringIO(text), sep=sep, dtype=str, keep_default_na=False, skipinitialspace=True
    )
    df.columns = [str(c).strip() for c in df.columns]
    seen: dict[str, int] = {}
    for c in df.columns:
        seen[c] = seen.get(c, 0) + 1
    dupes = sorted(c for c, n in seen.items() if n > 1)
    if dupes:
        raise IngestError(
            "Duplicate column header(s) after trimming: " + ", ".join(dupes)
        )
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
        body = re.sub(r"[^\d.,\-]", "", v0)
        # Comma-as-decimal ("1.234,56" / "1234,56") is the unambiguous
        # European signal — normalize instead of silently corrupting ~1000x.
        if re.fullmatch(r"-?(\d{1,3}(\.\d{3})+|\d+),\d{1,2}", body):
            cleaned = body.replace(".", "").replace(",", ".")
        else:
            cleaned = body.replace(",", "")
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
    if a_ok_month and b <= 31:
        return "mdy_only"  # second part in 13..31, so it must be the day
    if b_ok_month and a <= 31:
        return "dmy_only"
    return "other"  # malformed (a day part > 31 is junk, not format evidence)


def infer_date_format(columns: list[pd.Series]) -> str:
    """Resolve 'auto' by sampling ALL mapped date columns jointly (one format
    per file). Three branches: infer / conflict error / ambiguous error."""
    mdy_evidence: list[str] = []
    dmy_evidence: list[str] = []
    saw_ambiguous = False
    saw_iso = False
    saw_other = False
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
            elif kind == "other":
                saw_other = True
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
    if saw_iso or not saw_other:
        return "iso"  # ISO evidence, or nothing but blanks (format is moot)
    raise AmbiguousDateFormat(
        "No recognizable date values found — choose a date format explicitly."
    )


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


def append_alias(canonical: str, alias: str, path, section: str = "accounts") -> None:
    """Persist a confirmed alias to config/aliases.yaml (both sides stored in
    base-normalized form, matching how the index is built)."""
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    sec = data.setdefault(section, {}) or {}
    data[section] = sec
    canon = base_normalize(canonical)
    entry = sec.setdefault(canon, []) or []
    alias_norm = base_normalize(alias)
    if alias_norm not in entry:
        entry.append(alias_norm)
    sec[canon] = entry
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


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
    target_schema: "schema.Schema | None" = None,
) -> tuple[pd.DataFrame, list[str], str]:
    """Rename mapped source columns to canonical names and coerce types per
    the target schema (default: pipeline).

    Returns (canonical frame, problem strings, resolved date format).
    Raises AmbiguousDateFormat / ConflictingDateFormat when date_format='auto'
    cannot be resolved — callers (UI) catch these to force a user choice.
    """
    sch = target_schema or schema.PIPELINE_SCHEMA
    problems: list[str] = []
    out = pd.DataFrame(index=df.index)

    for canonical, source in mapping.items():
        if source and source in df.columns:
            out[canonical] = df[source].astype(str).str.strip()

    mapped_date_cols = [f for f in sch.date_fields if f in out.columns]
    resolved = date_format
    if date_format == "auto":
        resolved = infer_date_format([out[f] for f in mapped_date_cols])
    if resolved not in ("mdy", "dmy", "iso"):
        raise ValueError(f"Unknown date format '{resolved}'")

    for field in mapped_date_cols:
        parsed, unparsed = parse_date_series(out[field], resolved)
        out[field] = parsed
        out[f"{field}_unparsed"] = unparsed

    for field in sch.fields_of_type("money"):
        if field in out.columns:
            out[field], money_problems = parse_amount_series(out[field])
            problems.extend(money_problems)

    for field in sch.fields_of_type("number"):
        if field in out.columns:
            out[field] = pd.to_numeric(
                out[field].str.replace("%", "", regex=False), errors="coerce"
            )

    for field in sch.normalized_fields:
        if field in out.columns:
            out[f"{field}_raw"] = out[field]
            out[field] = out[field].map(lambda v: normalize_name(v, alias_index))

    return out, problems, resolved
