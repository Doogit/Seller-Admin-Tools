"""Obligation -> capability -> gap crosswalk and whitespace estimation.

Reference data lives in config/obligation_map.yaml and config/product_map.yaml
— data, not code. Unresolvable products are excluded and reported, never
guessed.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OBLIGATIONS = REPO_ROOT / "config" / "obligation_map.yaml"
DEFAULT_PRODUCTS = REPO_ROOT / "config" / "product_map.yaml"

GAP_COLUMNS = [
    "obligation_id", "framework", "paraphrase", "capability_category",
    "product_label", "status", "matched_item",
]


def load_obligation_map(path=None) -> dict:
    return yaml.safe_load(Path(path or DEFAULT_OBLIGATIONS).read_text(encoding="utf-8"))


def load_product_map(path=None) -> dict:
    return yaml.safe_load(Path(path or DEFAULT_PRODUCTS).read_text(encoding="utf-8"))


def _split(value) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [t.strip() for t in str(value).split(";") if t.strip()]


def resolve_category(value: str, section: dict[str, list[str]]) -> str | None:
    """Case-insensitive substring match of a free-text value against alias
    lists. Returns the capability category or None."""
    v = value.lower().strip()
    if not v:
        return None
    for category, aliases in (section or {}).items():
        for alias in aliases or []:
            a = alias.lower()
            if a in v or v in a:
                return category
    return None


def append_product_alias(value: str, category: str, path=None) -> None:
    """One-click 'assign category': append a free-text value to the products
    section of product_map.yaml."""
    p = Path(path or DEFAULT_PRODUCTS)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data.setdefault("products", {}).setdefault(category, []).append(value.lower().strip())
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def gap_table(
    account_row, obligation_map: dict | None = None, product_map: dict | None = None
) -> pd.DataFrame:
    """One row per obligation in the account's regulatory_scope.

    Status: landed = an install_base entry resolves to the obligation's
    capability; partial = no install match but an incumbent_tools entry does
    (displacement play); else gap. IDs listed in known_gaps force gap.
    Warnings (unknown known_gaps IDs, scopes with no reference entries) go to
    df.attrs['warnings'].
    """
    obligations = (obligation_map or load_obligation_map())["obligations"]
    pmap = product_map or load_product_map()
    scopes = _split(account_row.get("regulatory_scope"))
    install = _split(account_row.get("install_base"))
    incumbents = _split(account_row.get("incumbent_tools"))
    known_gaps = _split(account_row.get("known_gaps"))

    warnings: list[str] = []
    known_ids = {o["obligation_id"] for o in obligations}
    for kg in known_gaps:
        if kg not in known_ids:
            warnings.append(
                f"known_gaps entry '{kg}' is not a recognized obligation ID — ignored."
            )

    covered_frameworks = {o["framework"] for o in obligations}
    for s in scopes:
        if s not in covered_frameworks:
            warnings.append(
                f"regulatory_scope '{s}' has no reference obligations shipped — "
                "add entries to config/obligation_map.yaml."
            )

    rows = []
    for ob in obligations:
        if ob["framework"] not in scopes:
            continue
        category = ob["capability_category"]
        status, matched = "gap", ""
        for item in install:
            if resolve_category(item, pmap.get("products")) == category:
                status, matched = "landed", item
                break
        if status == "gap":
            for item in incumbents:
                if resolve_category(item, pmap.get("incumbents")) == category:
                    status, matched = "partial", item
                    break
        if ob["obligation_id"] in known_gaps:
            status, matched = "gap", "flagged in known_gaps"
        rows.append({
            "obligation_id": ob["obligation_id"],
            "framework": ob["framework"],
            "paraphrase": ob["paraphrase"],
            "capability_category": category,
            "product_label": ob["default_product_label"],
            "status": status,
            "matched_item": matched,
        })
    out = pd.DataFrame(rows, columns=GAP_COLUMNS)
    out.attrs["warnings"] = warnings
    return out


def whitespace_estimate(
    gap_df: pd.DataFrame, pipeline_df: pd.DataFrame, product_map: dict | None = None
) -> dict:
    """Whitespace = open pipeline whose product resolves to a gap capability,
    plus the list of gap capabilities with zero pipeline ('no play exists
    yet'). Unresolvable products are excluded from the estimate and reported."""
    pmap = product_map or load_product_map()
    gap_categories = set(gap_df.loc[gap_df["status"] == "gap", "capability_category"])

    matched_amount = 0.0
    matched_categories: set[str] = set()
    unresolved: list[str] = []
    matched_rows: list[dict] = []
    if pipeline_df is not None and not pipeline_df.empty:
        open_df = pipeline_df[
            ~pipeline_df["stage_bucket"].fillna("").isin(["closed_won", "closed_lost"])
        ]
        for _, r in open_df.iterrows():
            product = (r.get("product") or "").strip()
            if not product:
                continue
            category = resolve_category(product, pmap.get("products"))
            if category is None:
                unresolved.append(product)
                continue
            if category in gap_categories:
                amount = float(r["amount"]) if pd.notna(r["amount"]) else 0.0
                matched_amount += amount
                matched_categories.add(category)
                matched_rows.append({
                    "opportunity_name": r.get("opportunity_name"),
                    "product": product,
                    "capability_category": category,
                    "amount": amount,
                })

    uncovered = (
        gap_df[
            (gap_df["status"] == "gap")
            & ~gap_df["capability_category"].isin(matched_categories)
        ][["obligation_id", "capability_category", "product_label"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    return {
        "whitespace_amount": matched_amount,
        "matched": pd.DataFrame(matched_rows),
        "uncovered": uncovered,
        "unresolved_products": sorted(set(unresolved)),
    }
