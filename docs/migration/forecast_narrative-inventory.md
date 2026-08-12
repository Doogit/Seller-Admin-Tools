# Task 1 Inventory — Forecast Narrative (tool 1)

Source of truth for the port. One row per `st.*` call in the page body, the
shared `app/ui.py` helpers it uses, and a **sweep of every user-facing string /
transform** so nothing escapes the view model (`core/views/forecast_narrative.py`)
and the parity gate.

**Files inventoried**

- `app/pages/1_Forecast_Narrative.py` — page body (23 `st.*` calls, matches plan)
- `app/ui.py` — shared render helpers used by this page (`snapshot_labels`,
  `metric_row`, `risk_table`, `deltas_expander`, `unmatched_warning`)
- Core (read-only, NOT reimplemented — the view model *calls* these):
  `core/forecast.py` (`bucket_rollup`, `wow_delta`, `risk_flags`,
  `at_risk_total`, `dedup_flags`), `core/narrative.py` (`draft`,
  `assemble_markdown`), `core/formatting.py` (`fmt_money`).

Legend for **Port target**: **VM** = value/string produced in the view model ·
**route** = structural HTML in `web/routes/forecast_narrative.py` · **layout** =
handled by the Task 0 skeleton (`web/components.py`) · **DELETE** = Streamlit
rerun/exec artifact, not reimplemented (see §1a).

---

## A. `st.*` calls — page body (`1_Forecast_Narrative.py`)

| # | Line | Call | Purpose | Port target |
|---|------|------|---------|-------------|
| 1 | 18 | `st.set_page_config(page_title=…, layout="wide")` | page chrome | **layout** (base `page()` sets `<title>`) |
| 2 | 19 | `st.title("Forecast narrative")` | H1 | **route** `H1` (static label) |
| 3 | 23 | `st.info("No snapshots yet — import a pipeline CSV on the Home page first.")` | empty state | **route** empty-state render + return; string in **VM** (verbatim, see §B-1) |
| 4 | 24 | `st.stop()` | halt when no snapshots | **DELETE** → early `return` after empty state |
| 5 | 29 | `st.columns(3)` | 3-up selector row | **layout** (Tailwind grid) |
| 6 | 31 | `st.selectbox("Snapshot", ids, format_func=labels.get)` | pick current snapshot | **route** `<select name="current_id">`; options + labels from **VM**; `<label>` explicit (a11y) |
| 7 | 34 | `st.selectbox("Compare against", [None]+prior, format_func=…)` | pick prior snapshot | **route** `<select name="prior_id">`; `— none —` option string in **VM** |
| 8 | 40 | `st.number_input("Quota (optional, session-only)", …)` | session-only quota | **route** `<input type="number" name="quota">`; scoped interaction (§C) |
| 9 | 50 | `ui.metric_row(rollup, prior_rollup, quota, at_risk)` | 4 metrics + captions | **VM** (see §D helpers) + **route** cards |
| 10 | 51 | `ui.unmatched_warning(deltas)` | unmatched banner | **VM** count+string + **route** banner |
| 11 | 57–58 | `st.session_state[draft_key]` hydration | persist draft across reruns | **DELETE** (rerun artifact; edits live in the DOM) |
| 12 | 60 | `st.subheader("Draft — review before submitting")` | section header | **route** `H2` (static label) |
| 13 | 64 | `st.text_area(f"{emoji} {section.title()}", value=…, …)` ×3 | editable draft sections | **route** `<textarea>`×3; values + labels from **VM** (§B-3) |
| 14 | 67 | `st.session_state[draft_key][section]` (textarea value) | draft value | **VM** `draft.commit/upside/risk` |
| 15 | 70 | `st.checkbox("Discard my edits and regenerate from current data")` | regen confirm gate | **DELETE** → dirty-guarded `hx-confirm` (§C) |
| 16 | 71 | `st.button("Regenerate", disabled=not confirm)` | regenerate draft | **route** `hx-post` button (§C) |
| 17 | 72–74 | `st.session_state[…]=…` / `.pop(…)` | reset draft state | **DELETE** (rerun artifact) |
| 18 | 75 | `st.rerun()` | force rerun after regen | **DELETE** → htmx swap of `#draft` |
| 19 | 77 | `st.subheader("Risk detail (coaching view)")` | section header | **route** `H2` (static label) |
| 20 | 78 | `ui.risk_table(flags)` | notes + table / empty | **VM** notes+rows + **route** table |
| 21 | 79 | `ui.deltas_expander(deltas)` | movement detail | **VM** rows + **route** `<details>` |
| 22 | 81 | `st.subheader("Export")` | section header | **route** `H2` (static label) |
| 23 | 83 | `st.code(md, language="markdown")` | copy affordance | **DELETE** st.code → native `<pre>` |
| 24 | 84 | `st.download_button("Download .md", md, file_name=…)` | export `.md` | **route** download route streaming `narrative.assemble_markdown(...)` |
| 25 | 86 | `st.caption("Draft — review before submitting. Read-only: nothing is sent anywhere.")` | footer | **route** footer; string in **VM** (verbatim, §B) |

> Rows 11/14/17 are the same `st.session_state` mechanism counted at its
> distinct call sites (part of the 23). All are DELETE — see §1a.

## B. Shared helpers — `app/ui.py` (used by this page; `ui.py` dissolves into the VM)

| Helper | Internal `st.*` | Produces | Port target |
|--------|------------------|----------|-------------|
| `snapshot_labels(snaps)` | — | `{id: "{label} (as of {as_of_date}, {n_rows} rows)"}` | **VM** option-label map (§B-2) |
| `metric_row(...)` | `st.columns`, `m*.metric` ×4, `st.caption` ×2 | Commit/Upside/Coverage/At-risk values, deltas, derived + unclassified captions | **VM** metrics dict + **route** cards |
| `risk_table(flags)` | `st.caption` (per note), `st.write`, `st.dataframe` | `Note:` lines, `No risk flags.`, table (drops `opportunity_id`) | **VM** + **route** table |
| `deltas_expander(deltas)` | `st.expander`, `st.dataframe` | "Week-over-week movement detail" rows | **VM** rows + **route** `<details>` |
| `unmatched_warning(deltas)` | `st.warning` | unmatched count + warning string | **VM** + **route** banner |

---

## C. String / transform sweep (parity boundary — MUST live in the view model)

Every user-visible string or derived value below is generated in the page body
or `ui.py` today. If it stays in the route it escapes the golden diff, so each
moves into `core/views/forecast_narrative.py`.

1. **Empty-state:** `"No snapshots yet — import a pipeline CSV on the Home page first."` (page L23).
2. **Snapshot option label:** `f"{label} (as of {as_of_date}, {n_rows} rows)"` (`ui.snapshot_labels`).
3. **"Compare against" none option:** `"— none —"` (page L37).
4. **Draft section labels:** `colors = {"commit":"🟢","upside":"🟡","risk":"🔴"}` + `f"{colors[section]} {section.title()}"` → `🟢 Commit` / `🟡 Upside` / `🔴 Risk` (page L62–66).
5. **Metric values & deltas:** `fmt_money(rollup["commit"])`, delta `fmt_money(rollup["commit"] - prior_rollup["commit"])` (same for Upside); `fmt_money(at_risk)` (`ui.metric_row`).
6. **Coverage value + empty state:** `f"{rollup['total_open']/quota:.1f}x"` else `"—"` (`ui.metric_row`).
7. **Derived caption:** `"Buckets derived from stage — map forecast_category for accuracy."` (`ui.metric_row`, on `rollup.derived`).
8. **Unclassified caption:** `f"{fmt_money(rollup['unclassified'])} open in unmapped stages is excluded from coverage."` (`ui.metric_row`, on `rollup.unclassified_count`).
9. **Unmatched warning:** count `int((deltas["change_type"]=="unmatched").sum())` + `f"{n} opportunities couldn't be matched to last week — renamed or ID missing? See the movement table."` (`ui.unmatched_warning`).
10. **Risk notes:** `f"Note: {note}"` for each `flags.attrs["notes"]`; `"No risk flags."` when empty (`ui.risk_table`).
11. **Risk table shape:** drop `opportunity_id` column (`ui.risk_table`).
12. **Period label (critical):** `labels[current_id].split(" ")[0]` → the `period` passed to `narrative.assemble_markdown` (page L82). Pure page-body transform; **highest escape risk** — flagged by the plan.
13. **Draft section text:** the three strings from `narrative.draft(rollup, deltas, flags, prior_rollup=…, quota=…)` — **generated by core, not reimplemented**; the VM calls `draft()` and exposes `{commit, upside, risk}`.
14. **`.md` export body:** `narrative.assemble_markdown(edited, period=…)` — core, deterministic; the export route posts the (possibly edited) textarea values + VM `period`.

Static labels that may stay as route literals (not derived, no parity risk):
`Forecast narrative` (H1), metric labels `Commit`/`Upside`/`Coverage`/`At risk`,
`Snapshot`/`Compare against`/`Quota (optional, session-only)` (selector labels —
must become explicit `<label>`s for a11y), `Draft — review before submitting`,
`Risk detail (coaching view)`, `Export`, `Regenerate`, `Download .md`,
`Week-over-week movement detail`. (Listing them here so the reviewer can veto any
into the VM instead.)

---

## §1a. Workarounds to DELETE (not reimplemented)

- **`draft_key` `session_state` hydration** (L56–58) — a rerun-persistence
  artifact. In htmx the edited text lives in the `<textarea>` DOM; no server
  session copy.
- **"Discard my edits and regenerate" confirm-checkbox** (L70) **+ disabled
  `Regenerate`** (L71) **+ `session_state.pop`** (L72–74) **+ `st.rerun()`**
  (L75) — the whole rerun-guard dance. Replaced by a **dirty-guarded
  `hx-confirm`** on Regenerate (§C).
- **`st.code(md, language="markdown")`** (L83) as a copy affordance → native
  `<pre>` + the existing download link.
- **`st.stop()`** (L24) early-exit → render the empty state and `return`.
- **`st.set_page_config`** (L18) → the base layout owns page chrome.

## §1b. Requirements that PORT VERBATIM (string-for-string)

Tool-1 applicability marked. (Plan lists these across all three tools; the rest
belong to QBR / Account Plan and are out of scope this task.)

| Verbatim string | Applies to tool 1? | Source |
|---|---|---|
| `Buckets derived from stage — map forecast_category for accuracy.` | ✅ | metric caption **and** narrative `derived_note` |
| `{money} open in unmapped stages is excluded from coverage.` | ✅ | unclassified caption **and** narrative `unclassified_note` |
| `No risk flags.` | ✅ | `ui.risk_table` empty |
| risk `Note:` lines (`Note: {note}`) | ✅ | `ui.risk_table` over `flags.attrs["notes"]` |
| `{n} opportunities couldn't be matched to last week — renamed or ID missing? See the movement table.` | ✅ | `ui.unmatched_warning` |
| coverage `—` empty state | ✅ | `ui.metric_row` |
| Tool-1 footer: `Draft — review before submitting. Read-only: nothing is sent anywhere.` | ✅ | page caption L86 **and** `assemble_markdown` `.md` trailer |
| `Numbers identical to Forecast Narrative for the same snapshot.` | ❌ (QBR) | — |
| `Sub-vertical split unavailable — field not mapped in this snapshot.` | ❌ (QBR) | — |
| alias/product provenance + obligation-map disclaimer | ❌ (Account Plan) | — |

> The narrative body sentences themselves live in
> `config/narrative_templates.yaml` and are emitted by `narrative.draft()`. The
> VM must **call** `draft()`, never restate template text — the Task 4 golden
> (draft output at the base commit) covers them byte-for-byte.

---

## §C. Interaction contract → tool 1 (how the deleted reruns are replaced)

| Trigger | htmx behavior | Rationale |
|---|---|---|
| **Quota** change | `hx-post` → swap **only** `#metrics` (`hx-target="#metrics"`, coverage panel). Draft `<textarea>` is outside that subtree → **edits preserved**. | Plan Q: quota preserves edits (hx-target scoping, not hx-preserve). |
| **Snapshot** or **Compare-against** change | swap the **whole** `#draft` region with a freshly generated draft → **discards edits**. | Draft is keyed to the snapshot/prior numbers (wow line, movers, deltas). Regenerate so narrative and metrics never disagree. |
| **Regenerate** button | `hx-post` + `hx-target="#draft"` + `hx-swap="innerHTML"`, **`hx-confirm` fired only when the draft differs from the last generated text**; clean draft overwrites silently. | Plan Q3: confirm-on-dirty. |
| **Every mutating POST** | `hx-sync="this:drop"` + `hx-disabled-elt="this"` + `hx-indicator`. | Double-submit / in-flight protection. |

**Flagged consequence for confirmation (deliberate behavior change):** in
Streamlit, changing **Quota** re-ran `narrative.draft(quota=…)` and live-updated
the *commit* section's coverage sentence. Under the plan's "quota preserves
edits" rule, a quota change now updates **only the metrics/coverage panel**; the
narrative's coverage sentence refreshes on the next draft (re)generation
(snapshot/compare change or Regenerate). View-model parity is unaffected
(`draft()` still receives `quota` at generation time and matches the golden);
only *when* the user sees quota reflected in the narrative text changes. This
follows the reviewed plan — flagging it, not re-deciding it.

---

## §D. Proposed view-model surface (`core/views/forecast_narrative.py`) — for approval before I write it

Pure functions, no UI imports; all §C strings produced here once.

```
empty_state() -> str                      # C-1
snapshot_options(snaps) -> list[(id,label)]   # C-2
PRIOR_NONE_LABEL = "— none —"             # C-3

build(current_id, prior_id, quota) -> ForecastView:
    .snapshot_options / .prior_options
    .metrics: {commit, upside, coverage, at_risk,  # all fmt_money'd strings; C-5/6
               commit_delta, upside_delta,          # or None when no prior
               derived_note|None, unclassified_note|None}   # C-7/8
    .unmatched: {n, warning|None}                    # C-9
    .draft: {commit, upside, risk}                   # C-13 via narrative.draft()
    .draft_labels: {commit:"🟢 Commit", ...}         # C-4
    .risk: {notes:[...], rows:[...]|[], empty_text}  # C-10/11
    .movement_rows: [...]                            # deltas_expander
    .period: str                                     # C-12  labels[id].split(" ")[0]

metrics_partial(current_id, prior_id, quota) -> metrics dict   # for the quota-scoped #metrics swap

# export route uses core directly:
#   narrative.assemble_markdown(posted_sections, period=view.period)
```

Tests (`tests/test_forecast_narrative_view.py`, part of the green-suite gate):
happy path (full snapshot + prior + quota), missing-optional degradation (no
prior → deltas None, coverage `—`), empty/insufficient (no flags → `No risk
flags.`; unmatched present → warning), each conditional note (derived,
unclassified, risk notes). Distinct from the Task 4 parity golden.

---

## Checkpoint

**STOP — awaiting go-ahead before writing any tool UI code (Tasks 2–4 for tool
1).** Task 0 skeleton + Tailwind build are in place; core untouched
(`git diff --stat -- core/` empty); suite green (88 passed).
