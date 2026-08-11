"""Shared import orchestration.

Home.py, sample_data/seed_snapshots.py, and any future seeding script all
import snapshots through import_snapshot() so UI-imported and seeded snapshots
are structurally identical.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from core import ingest, schema, store


@dataclass
class ImportResult:
    snapshot_id: int | None = None
    skipped: bool = False
    duplicate_of: dict | None = None  # existing snapshot row when hash matches
    n_rows: int = 0
    n_accounts: int = 0
    total_amount: float = 0.0
    date_format_used: str = ""
    unmapped_stages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)


@dataclass
class AccountImportResult:
    n_accounts: int = 0
    warnings: list[str] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    date_format_used: str = ""


def import_account_facts(
    file,
    mapping: dict[str, str | None],
    date_format: str = "auto",
    alias_index: dict[str, str] | None = None,
    db_path=None,
) -> AccountImportResult:
    """Import an account-facts CSV (replace-latest-by-account, no snapshots).

    Same load/map/validate pipeline as pipeline imports, against ACCOUNT_SCHEMA.
    """
    result = AccountImportResult()
    df = ingest.load_csv(_read_bytes(file))
    canonical, problems, resolved = ingest.apply_mapping(
        df, mapping, date_format, alias_index=alias_index,
        target_schema=schema.ACCOUNT_SCHEMA,
    )
    result.date_format_used = resolved
    result.warnings.extend(problems)
    issues = schema.validate_frame(canonical, schema.ACCOUNT_SCHEMA)
    result.blocking = [i["message"] for i in issues if i["severity"] == schema.BLOCKING]
    result.warnings.extend(i["message"] for i in issues if i["severity"] == schema.WARNING)
    if result.blocking:
        return result
    result.n_accounts = store.upsert_account_facts(canonical, db_path=db_path)
    return result


def _read_bytes(file) -> bytes:
    if isinstance(file, bytes):
        return file
    if hasattr(file, "read"):
        data = file.read()
        return data.encode("utf-8") if isinstance(data, str) else data
    return Path(file).read_bytes()


def import_snapshot(
    file,
    mapping: dict[str, str | None],
    date_format: str,
    stage_assignments: dict[str, str],
    label: str,
    as_of_date: dt.date | str | None = None,
    on_duplicate: str = "ask",  # ask | skip | override
    profile_id: int | None = None,
    alias_index: dict[str, str] | None = None,
    db_path=None,
) -> ImportResult:
    """Import one CSV as a new snapshot. May raise AmbiguousDateFormat /
    ConflictingDateFormat when date_format='auto' cannot be resolved.

    Unparseable dates are stored as empty with a warning; blocking issues
    (unmapped required fields) abort with nothing written.
    """
    result = ImportResult()
    raw = _read_bytes(file)
    sha = hashlib.sha256(raw).hexdigest()

    existing = store.find_snapshot_by_hash(sha, db_path=db_path)
    if existing and on_duplicate != "override":
        result.skipped = True
        result.duplicate_of = existing
        result.warnings.append(
            f"This file was already imported as '{existing['label']}' on "
            f"{existing['imported_at']} — override required to import again."
        )
        return result

    df = ingest.load_csv(raw)
    canonical, problems, resolved_format = ingest.apply_mapping(
        df, mapping, date_format, alias_index=alias_index
    )
    result.date_format_used = resolved_format
    result.warnings.extend(problems)

    issues = schema.validate_frame(canonical)
    result.blocking = [i["message"] for i in issues if i["severity"] == schema.BLOCKING]
    result.warnings.extend(i["message"] for i in issues if i["severity"] == schema.WARNING)
    if result.blocking:
        return result

    lowered = {str(k).lower(): v for k, v in stage_assignments.items()}
    canonical["stage_bucket"] = canonical["stage"].map(
        lambda s: lowered.get(str(s).lower(), "")
    )
    result.unmapped_stages = sorted(
        canonical.loc[canonical["stage_bucket"] == "", "stage"].unique().tolist()
    )
    if result.unmapped_stages:
        result.warnings.append(
            "Unmapped stage value(s) stored without a bucket: "
            + ", ".join(result.unmapped_stages)
        )

    if as_of_date is None:
        as_of_date = dt.date.today()
    snapshot_id = store.write_snapshot(
        label, as_of_date, profile_id, sha, canonical, db_path=db_path
    )

    result.snapshot_id = snapshot_id
    result.n_rows = len(canonical)
    result.n_accounts = canonical["account_name"].nunique()
    result.total_amount = float(canonical["amount"].fillna(0).sum())
    return result
