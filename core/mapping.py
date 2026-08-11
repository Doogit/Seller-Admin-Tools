"""Header auto-suggestion and mapping-profile persistence."""

from __future__ import annotations

import re

from core import schema, store

# Synonyms are matched after _norm(); order within a list is irrelevant.
SYNONYMS: dict[str, list[str]] = {
    "account_name": ["account", "customer", "company", "account name", "customer name"],
    "opportunity_name": ["opportunity", "opp", "deal", "deal name", "opportunity title", "name"],
    "stage": ["sales stage", "opportunity stage", "phase", "stage name"],
    "amount": ["est revenue", "estimated revenue", "opportunity revenue", "acr", "value",
               "deal value", "revenue", "deal size", "total value"],
    "close_date": ["close dt", "close", "expected close", "close date", "closing date",
                   "est close date"],
    "owner": ["opportunity owner", "seller", "account executive", "ae", "sales rep", "rep",
              "owner name"],
    "opportunity_id": ["opp id", "id", "opportunity number", "opp number", "crm id"],
    "forecast_category": ["forecast", "forecast cat", "category", "commit status"],
    "probability": ["prob", "win probability", "probability pct", "win"],
    "last_activity_date": ["last activity", "last touch", "last contact", "activity date"],
    "product": ["product family", "workload", "solution", "offering", "sku"],
    "sub_vertical": ["subvertical", "sub industry", "segment", "industry segment", "vertical"],
    "exec_sponsor": ["executive sponsor", "sponsor", "exec"],
    "created_date": ["created", "created on", "create date", "open date", "created dt"],
    # account-facts schema
    "annual_spend": ["annual spend", "yearly spend", "spend", "acr"],
    "agreement_end_date": ["agreement end", "contract end", "renewal date", "ea end"],
    "install_base": ["install base", "installed products", "current products", "deployed"],
    "incumbent_tools": ["incumbents", "competitor tools", "current tools", "incumbent"],
    "known_gaps": ["gaps", "known gaps"],
    "exec_contacts": ["contacts", "executive contacts", "key contacts"],
    "regulatory_scope": ["regulatory", "regulations", "compliance scope", "frameworks"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^\w\s]", " ", s.lower()).strip().replace("_", " ")


def suggest_mapping(
    headers: list[str], target_schema: schema.Schema | None = None
) -> dict[str, str | None]:
    """Fuzzy-match source headers to canonical fields of the target schema
    (default: pipeline). Suggestions only — the user confirms everything in
    the mapping UI."""
    sch = target_schema or schema.PIPELINE_SCHEMA
    normed = {h: " ".join(_norm(h).split()) for h in headers}
    used: set[str] = set()
    suggestion: dict[str, str | None] = {}

    def take(canonical: str, header: str) -> None:
        suggestion[canonical] = header
        used.add(header)

    for canonical in sch.all_fields:
        suggestion[canonical] = None
        targets = [" ".join(canonical.split("_"))] + [
            " ".join(_norm(s).split()) for s in SYNONYMS.get(canonical, [])
        ]
        # Pass 1: exact normalized match
        for h, hn in normed.items():
            if h not in used and hn in targets:
                take(canonical, h)
                break
        if suggestion[canonical]:
            continue
        # Pass 2: containment either way (e.g. "probability (%)" ~ "probability")
        for h, hn in normed.items():
            if h in used:
                continue
            if any(t and (t in hn or hn in t) for t in targets):
                take(canonical, h)
                break
    return suggestion


def save_profile(
    name: str,
    mapping: dict[str, str | None],
    stage_assignments: dict[str, str],
    date_format: str,
    db_path=None,
) -> int:
    return store.save_profile(name, mapping, stage_assignments, date_format, db_path=db_path)


def load_profiles(db_path=None) -> dict[str, dict]:
    return store.load_profiles(db_path=db_path)
