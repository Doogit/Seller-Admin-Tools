"""Canonical schema definitions and frame-level validation.

Two schemas share one mapping/ingest pipeline: PIPELINE_SCHEMA (opportunity
snapshots) and ACCOUNT_SCHEMA (account facts). Field spec: type is one of
str | money | number | date; normalize=True runs the name through
ingest.normalize_name at import time (raw preserved in a _raw column).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Schema:
    name: str
    required: dict
    optional: dict

    @property
    def all_fields(self) -> dict:
        return {**self.required, **self.optional}

    def fields_of_type(self, kind: str) -> list[str]:
        return [n for n, spec in self.all_fields.items() if spec["type"] == kind]

    @property
    def date_fields(self) -> list[str]:
        return self.fields_of_type("date")

    @property
    def normalized_fields(self) -> list[str]:
        return [n for n, spec in self.all_fields.items() if spec.get("normalize")]


PIPELINE_SCHEMA = Schema(
    name="pipeline",
    required={
        "account_name": {"type": "str", "normalize": True,
                         "description": "Customer account name"},
        "opportunity_name": {"type": "str", "description": "Opportunity / deal name"},
        "stage": {"type": "str",
                  "description": "Raw sales stage (normalized via stage map)"},
        "amount": {"type": "money", "description": "Deal value in USD"},
        "close_date": {"type": "date", "description": "Expected close date"},
        "owner": {"type": "str", "normalize": True,
                  "description": "Seller alias or name"},
    },
    optional={
        "opportunity_id": {
            "type": "str",
            "description": "CRM opportunity ID — join key for week-over-week deltas "
                           "(strongly recommended)",
        },
        "forecast_category": {"type": "str", "description": "commit / upside / pipeline"},
        "probability": {"type": "number", "description": "Win probability, 0-100"},
        "last_activity_date": {"type": "date", "description": "Most recent activity date"},
        "product": {"type": "str", "description": "Product or workload on the deal"},
        "sub_vertical": {"type": "str",
                         "description": "power & utilities / oil & gas / pipelines"},
        "exec_sponsor": {"type": "str", "description": "Executive sponsor on the account"},
        "created_date": {"type": "date", "description": "Opportunity created date"},
    },
)

ACCOUNT_SCHEMA = Schema(
    name="account_facts",
    required={
        "account_name": {"type": "str", "normalize": True,
                         "description": "Account name (joined to pipeline on the "
                                        "normalized form)"},
        "sub_vertical": {"type": "str",
                         "description": "power & utilities / oil & gas / pipelines"},
    },
    optional={
        "annual_spend": {"type": "money", "description": "Annual spend in USD"},
        "agreement_end_date": {"type": "date", "description": "Agreement end date"},
        "install_base": {"type": "str",
                         "description": "Semicolon-delimited installed product list"},
        "incumbent_tools": {"type": "str",
                            "description": "Semicolon-delimited competitor tools"},
        "known_gaps": {"type": "str",
                       "description": "Semicolon list of obligation IDs or free text"},
        "exec_contacts": {"type": "str", "description": "Executive contacts"},
        "regulatory_scope": {"type": "str",
                             "description": "Semicolon list: NERC_CIP, TSA_SD, "
                                            "IEC_62443, state_puc"},
    },
)

# Backward-compatible module-level views (pipeline is the default schema).
REQUIRED_FIELDS = PIPELINE_SCHEMA.required
OPTIONAL_FIELDS = PIPELINE_SCHEMA.optional
ALL_FIELDS = PIPELINE_SCHEMA.all_fields
DATE_FIELDS = PIPELINE_SCHEMA.date_fields

BLOCKING = "blocking"
WARNING = "warning"


def validate_frame(df: pd.DataFrame, schema: Schema = PIPELINE_SCHEMA) -> list[dict]:
    """Validate a canonical-column frame. Returns [{severity, message}, ...].

    Severity is BLOCKING only for problems that make the import meaningless
    (missing required columns); data-quality issues are warnings — rows are
    stored as-is with the problem surfaced.
    """
    issues: list[dict] = []
    label_field = "opportunity_name" if "opportunity_name" in df.columns else "account_name"

    for field in schema.required:
        if field not in df.columns:
            issues.append(
                {"severity": BLOCKING, "message": f"Required field '{field}' is not mapped."}
            )
    if any(i["severity"] == BLOCKING for i in issues):
        return issues

    for field in schema.date_fields:
        raw_col = f"{field}_unparsed"
        if raw_col in df.columns:
            bad = df[df[raw_col] != ""]
            for _, row in bad.iterrows():
                issues.append(
                    {
                        "severity": WARNING,
                        "message": (
                            f"Unparseable {field} '{row[raw_col]}' on "
                            f"'{row.get(label_field, '?')}' — stored as empty."
                        ),
                    }
                )

    for field in schema.fields_of_type("money"):
        if field not in df.columns:
            continue
        negatives = df[df[field].notna() & (df[field] < 0)]
        for _, row in negatives.iterrows():
            issues.append(
                {
                    "severity": WARNING,
                    "message": (
                        f"Negative {field} {row[field]:,.2f} on "
                        f"'{row.get(label_field, '?')}'."
                    ),
                }
            )

    if "opportunity_id" in schema.all_fields and "opportunity_id" in df.columns:
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
