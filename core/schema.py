"""Canonical field definitions and frame-level validation."""

from __future__ import annotations

import pandas as pd

REQUIRED_FIELDS: dict[str, dict] = {
    "account_name": {"type": "str", "description": "Customer account name"},
    "opportunity_name": {"type": "str", "description": "Opportunity / deal name"},
    "stage": {"type": "str", "description": "Raw sales stage (normalized via stage map)"},
    "amount": {"type": "float", "description": "Deal value in USD"},
    "close_date": {"type": "date", "description": "Expected close date"},
    "owner": {"type": "str", "description": "Seller alias or name"},
}

OPTIONAL_FIELDS: dict[str, dict] = {
    "opportunity_id": {
        "type": "str",
        "description": "CRM opportunity ID — join key for week-over-week deltas (strongly recommended)",
    },
    "forecast_category": {"type": "str", "description": "commit / upside / pipeline"},
    "probability": {"type": "float", "description": "Win probability, 0-100"},
    "last_activity_date": {"type": "date", "description": "Most recent activity date"},
    "product": {"type": "str", "description": "Product or workload on the deal"},
    "sub_vertical": {"type": "str", "description": "power & utilities / oil & gas / pipelines"},
    "exec_sponsor": {"type": "str", "description": "Executive sponsor on the account"},
    "created_date": {"type": "date", "description": "Opportunity created date"},
}

ALL_FIELDS = {**REQUIRED_FIELDS, **OPTIONAL_FIELDS}

DATE_FIELDS = [name for name, spec in ALL_FIELDS.items() if spec["type"] == "date"]

BLOCKING = "blocking"
WARNING = "warning"


def validate_frame(df: pd.DataFrame) -> list[dict]:
    """Validate a canonical-column frame. Returns [{severity, message}, ...].

    Severity is BLOCKING only for problems that make the import meaningless
    (missing required columns); data-quality issues are warnings — rows are
    stored as-is with the problem surfaced.
    """
    issues: list[dict] = []

    for field in REQUIRED_FIELDS:
        if field not in df.columns:
            issues.append(
                {"severity": BLOCKING, "message": f"Required field '{field}' is not mapped."}
            )
    if any(i["severity"] == BLOCKING for i in issues):
        return issues

    for field in DATE_FIELDS:
        raw_col = f"{field}_unparsed"
        if raw_col in df.columns:
            bad = df[df[raw_col] != ""]
            for _, row in bad.iterrows():
                issues.append(
                    {
                        "severity": WARNING,
                        "message": (
                            f"Unparseable {field} '{row[raw_col]}' on opportunity "
                            f"'{row.get('opportunity_name', '?')}' — stored as empty."
                        ),
                    }
                )

    negatives = df[df["amount"].notna() & (df["amount"] < 0)]
    for _, row in negatives.iterrows():
        issues.append(
            {
                "severity": WARNING,
                "message": (
                    f"Negative amount {row['amount']:,.2f} on opportunity "
                    f"'{row.get('opportunity_name', '?')}'."
                ),
            }
        )

    if "opportunity_id" in df.columns:
        ids = df["opportunity_id"].fillna("").astype(str).str.strip()
        n_blank = int((ids == "").sum())
        if n_blank:
            issues.append(
                {
                    "severity": WARNING,
                    "message": (
                        f"{n_blank} row(s) lack opportunity_id — week-over-week matching "
                        "falls back to normalized names for those rows."
                    ),
                }
            )
        dupes = ids[(ids != "") & ids.duplicated(keep=False)].unique().tolist()
        if dupes:
            issues.append(
                {
                    "severity": WARNING,
                    "message": f"Duplicate opportunity_id value(s): {', '.join(sorted(dupes))}.",
                }
            )

    return issues
