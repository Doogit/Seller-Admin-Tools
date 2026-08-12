"""Tool 3: account plan generator — facts + pipeline -> structured account plan
with obligation/capability/gap crosswalk and whitespace estimate."""

from __future__ import annotations

import datetime as dt
import difflib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for p in (str(REPO_ROOT), str(REPO_ROOT / "app")):
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st

import mapping_ui
import ui
from core import crosswalk, importer, ingest, mapping, plan, schema, store

ALIASES_PATH = REPO_ROOT / "config" / "aliases.yaml"

st.set_page_config(page_title="Account Plan", layout="wide")
st.title("Account plan generator")

# --- 1. Import account facts (schema-parameterized mapping flow) ---
with st.expander("Import account-facts CSV", expanded=store.load_account_facts().empty):
    uploaded = st.file_uploader("Account facts CSV", type=["csv"], key="facts_upload")
    if uploaded is not None:
        try:
            df = ingest.load_csv(uploaded.getvalue())
        except ingest.IngestError as e:
            st.error(str(e))
            st.stop()
        st.dataframe(df.head(5), width="stretch")
        suggested = mapping.suggest_mapping(list(df.columns), schema.ACCOUNT_SCHEMA)
        facts_mapping = mapping_ui.render_mapping_grid(
            df, suggested, key_prefix="facts", target_schema=schema.ACCOUNT_SCHEMA
        )
        date_format = mapping_ui.render_date_format_choice(
            df, facts_mapping, key_prefix="facts", target_schema=schema.ACCOUNT_SCHEMA
        )
        missing = [f for f in schema.ACCOUNT_SCHEMA.required if not facts_mapping.get(f)]
        if missing:
            st.error("Required fields not mapped: " + ", ".join(missing))
        elif st.button("Import account facts", type="primary"):
            alias_index = ingest.load_alias_index(ALIASES_PATH)
            result = importer.import_account_facts(
                uploaded.getvalue(), facts_mapping, date_format,
                alias_index=alias_index,
            )
            if result.blocking:
                for b in result.blocking:
                    st.error(b)
            else:
                st.success(f"Imported {result.n_accounts} account(s).")
                for w in result.warnings:
                    st.warning(w)
                st.rerun()

facts = store.load_account_facts()
if facts.empty:
    st.info("Import an account-facts CSV to begin. "
            "Sample: sample_data/account_facts_sample.csv")
    st.stop()

# --- 2. Account + snapshot selection ---
snaps = store.list_snapshots()
col1, col2 = st.columns(2)
with col1:
    account_name = st.selectbox(
        "Account", facts["account_name"].tolist(),
        format_func=lambda a: facts.set_index("account_name")
        .at[a, "account_name_raw"] or a,
    )
with col2:
    if snaps.empty:
        st.warning("No pipeline snapshots — plan will render without pipeline.")
        snapshot_id = None
    else:
        labels = ui.snapshot_labels(snaps)
        snapshot_id = st.selectbox("Pipeline snapshot", list(labels),
                                   format_func=labels.get)

account_row = facts.set_index("account_name").loc[account_name].to_dict()
account_row["account_name"] = account_name

# --- 3. Facts <-> pipeline join on normalized account_name ---
pipeline_df = store.get_opportunities(snapshot_id) if snapshot_id else None
account_pipeline = None
if pipeline_df is not None and not pipeline_df.empty:
    account_pipeline = pipeline_df[pipeline_df["account_name"] == account_name]
    if account_pipeline.empty:
        st.warning(
            f"'{account_row.get('account_name_raw') or account_name}' matches zero "
            "pipeline rows in this snapshot — likely a name-spelling difference."
        )
        candidates = difflib.get_close_matches(
            account_name, pipeline_df["account_name"].dropna().unique().tolist(),
            n=3, cutoff=0.5,
        )
        if candidates:
            pick = st.selectbox(
                "Did you mean this pipeline account?", candidates, key="alias_pick"
            )
            if st.button(f"Confirm: '{account_name}' is the same as '{pick}'"):
                ingest.append_alias(pick, account_name, ALIASES_PATH)
                # facts row joins under the pipeline's canonical name from now on
                renamed = facts[facts["account_name"] == account_name].copy()
                renamed["account_name"] = pick
                store.upsert_account_facts(renamed)
                store.delete_account_facts(account_name)  # drop the old-name row
                st.success(
                    f"Alias saved to config/aliases.yaml — '{account_name}' now maps "
                    f"to '{pick}'."
                )
                st.rerun()
        else:
            st.caption("No near-name pipeline accounts found.")

# --- 4. Crosswalk + whitespace + plan ---
obligation_map = crosswalk.load_obligation_map()
gaps = crosswalk.gap_table(account_row, obligation_map)
for w in gaps.attrs.get("warnings", []):
    st.warning(w)
if gaps.empty:
    st.info("No obligations in scope — set regulatory_scope in the account facts "
            "to drive the crosswalk.")

ws = crosswalk.whitespace_estimate(gaps, account_pipeline)
sections = plan.compose(account_row, gaps, ws, account_pipeline)

st.subheader(f"Plan — {sections['account_display']}")
for b in sections["summary"]:
    st.caption(b)

m1, m2, m3 = st.columns(3)
m1.metric("Whitespace (gap-category pipeline)",
          f"${ws['whitespace_amount']:,.0f}")
m2.metric("Uncovered gaps (no play yet)", len(ws["uncovered"]))
m3.metric("Obligations in scope", len(gaps))
if ws.get("unmeasurable"):
    st.caption("No `product` field populated on this account's open pipeline — "
               "whitespace can't be measured (shown as $0, not a true zero). "
               "Map the product column on Home to enable it.")

if not gaps.empty:
    st.subheader("Obligation → capability → gap")
    status_color = {"landed": "🟢", "partial": "🟡", "gap": "🔴"}
    display = gaps.copy()
    display["status"] = display["status"].map(lambda s: f"{status_color[s]} {s}")
    st.dataframe(display, width="stretch", hide_index=True)

if not ws["uncovered"].empty:
    st.subheader("Uncovered gaps — no play exists yet")
    for _, u in ws["uncovered"].iterrows():
        st.write(f"- **{u['obligation_id']}**: {u['capability_category']} "
                 f"({u['product_label']})")

if ws["unresolved_products"]:
    st.subheader("Unresolved products (excluded from whitespace)")
    for product in ws["unresolved_products"]:
        c1, c2, c3 = st.columns([2, 2, 1])
        c1.write(product)
        categories = sorted((crosswalk.load_product_map().get("products") or {}).keys())
        cat = c2.selectbox("Category", categories, key=f"assign_{product}",
                           label_visibility="collapsed")
        if c3.button("Assign", key=f"assign_btn_{product}"):
            crosswalk.append_product_alias(product, cat)
            st.success(f"'{product}' → {cat} appended to config/product_map.yaml.")
            st.rerun()

if account_pipeline is not None and not account_pipeline.empty:
    st.subheader("Open pipeline for account")
    st.dataframe(sections["pipeline"], width="stretch", hide_index=True)

st.subheader("Next actions")
for a in sections["next_actions"]:
    st.write(f"- {a}")
st.caption(sections["relationship_map"])

# --- 5. Export ---
st.subheader("Downloads")
disclaimer = obligation_map.get("disclaimer", "")
stamp = dt.date.today().strftime("%Y%m%d")
safe = (sections["account_display"] or "account").replace(" ", "_").lower()
d1, d2 = st.columns(2)
with d1:
    st.download_button(
        "Download .pptx", plan.plan_pptx(sections, disclaimer),
        file_name=f"account_plan_{safe}_{stamp}.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
with d2:
    st.download_button("Download .md", plan.plan_md(sections, disclaimer),
                       file_name=f"account_plan_{safe}_{stamp}.md")

st.caption(disclaimer)
st.caption("Draft — review before use. Read-only: nothing is sent anywhere.")
