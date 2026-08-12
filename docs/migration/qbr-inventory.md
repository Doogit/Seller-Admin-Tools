# Task 1 Inventory — QBR Assembler (tool 2)

Source: `app/pages/2_QBR_Assembler.py` (~24 `st.*`), shared `app/ui.py`
(`snapshot_labels`, `metric_row`, `risk_table`), and core `deck.py`
(`gather`/`build_md`/`build_pptx`) + `styles.py`. Downloads reuse `deck`
**unchanged**; the on-screen view is driven by one `deck.gather` pass.

Legend as in the forecast inventory: **VM** (`core/views/qbr.py` + shared
`core/views/common.py`), **route** (`web/routes/qbr.py`), **layout**, **DELETE**.

## A. `st.*` calls (page body)

| Line | Call | Purpose | Port target |
|------|------|---------|-------------|
| 19 | `set_page_config` | chrome | layout |
| 20 | `title("QBR assembler")` | H1 | route (static) |
| 23 | `info("No snapshots yet …")` | empty state | route + **VM.EMPTY_STATE** (shared, verbatim) |
| 25 | `stop()` | halt | **DELETE** → empty state + return |
| 30 | `columns(5)` | control row | layout (grid) |
| 32 | `selectbox Snapshot` | current | route `<select>` + VM options |
| 35 | `selectbox Prior snapshot` | prior | route `<select>` + `— none —` (shared) |
| 41 | `text_input Period label` (default `snaps.iloc[0]["label"]`) | deck period | route `<input>`; default in **VM** |
| 43 | `text_input Team / segment` (default `"Energy Team"`) | deck team | route `<input>`; **VM.DEFAULT_TEAM** |
| 45 | `number_input Quota` | coverage + deck | route `<input>` |
| 54 | `ui.metric_row(...)` | 4 metrics + captions | **common.metric_block** + route cards |
| 55 | `caption` "Numbers identical to Forecast Narrative for the same snapshot." | reassurance | **VM** (verbatim §1b) |
| 57 | `subheader "Pipeline by stage"` | header | route (static) |
| 61 | `bar_chart(open_dist)` | stage chart | **DELETE st.bar_chart** → route server-rendered bars from **VM.stage** (dollar labels + empty state) |
| 65 | `caption` sub-vertical unavailable | degradation | **VM** (verbatim §1b) |
| 67 | `subheader "Sub-vertical split"` | header | route (static) |
| 68 | `dataframe sv` | sub-vertical table | **VM.sub_vertical** rows + route table |
| 70 | `subheader "Top deals"` | header | route (static) |
| 71 | `dataframe top` | top deals table | **VM.top** rows + route table |
| 73 | `subheader "Risks"` | header | route (static) |
| 74 | `ui.risk_table(flags)` | notes + table | **common.risk_block** + route |
| 76 | `subheader "Downloads"` | header | route (static) |
| 83 | `download_button .pptx` | export | **DELETE** → route `GET /qbr/export.pptx` streams `deck.build_pptx` |
| 88 | `download_button .md` | export | **DELETE** → route `GET /qbr/export.md` streams `deck.build_md` |
| 91 | `caption` footer | footer | **VM.FOOTER** (verbatim §1b) |

## B. String / transform sweep → view model

1. `meta = {"period", "team", "quota"}` assembled in the page → VM builds `meta`.
2. Period default `snaps.iloc[0]["label"]` (raw label of most-recent snapshot) → **VM.default_period**.
3. Team default `"Energy Team"` → **VM.DEFAULT_TEAM**.
4. Open-stage filter `~stage_dist["bucket"].isin(["closed_won","closed_lost"])` (both chart and page) → **VM.stage** (open buckets only).
5. Download filename glue: `stamp = today.strftime("%Y%m%d")`, `safe_period = period.replace(" ","_")`, `f"qbr_{safe_period}_{stamp}.{ext}"`. The stamp is **today** (non-deterministic) → computed in the **route** at request time; `safe_period` in VM helper.
6. Metric strings, coverage, derived/unclassified captions → **common.metric_block** (identical to tool 1 — that IS the "numbers identical" guarantee).
7. Risk notes / "No risk flags." / drop `opportunity_id` → **common.risk_block**.

## §1a Workarounds to DELETE
- `st.stop()` → empty state + return.
- `st.bar_chart` → server-rendered HTML/CSS bars (Tailwind), exact dollar value labelled per bar; **empty state** when all open buckets are 0. Chart *rendering* is out of parity scope; the values are covered by VM parity.
- Two `st.download_button`s → `GET` download routes streaming `deck.build_pptx`/`build_md` bytes (deck reused **unchanged**).
- `set_page_config` → base layout.

## §1b Verbatim-port strings (tool 2)
| String | Source |
|---|---|
| `Numbers identical to Forecast Narrative for the same snapshot.` | caption L55 |
| `Sub-vertical split unavailable — field not mapped in this snapshot.` | caption L65 |
| Tool-2 footer: `Draft — review before presenting. Read-only: nothing is sent anywhere.` | caption L91 |
| `No snapshots yet — import a pipeline CSV on the Home page first.` | shared empty state |
| risk `Note:` lines / `No risk flags.` | shared `risk_block` |
| metric captions (derived / unmapped-stage) | shared `metric_block` |
| `DRAFT — generated locally; review before presenting` (`styles.DRAFT_FOOTER`) | inside `.pptx`/`.md` — core, parity-covered |

## §C Interaction contract (tool 2)
No editable draft → no edit-durability concern. Controls form (`#controls`) is
**static** (never swapped) so typed **Period/Team** survive. Snapshot / Prior /
Quota change → `hx-get /qbr/body` swaps only `#qbr-data` (metrics, chart, tables,
downloads). Period/Team change → no on-screen effect (they only parameterise the
deck); their current values ride along on the download submit. Downloads are
`GET` form submits (read-only) carrying all control values; filename stamped with
today's date in the route.

## Parity plan (Task 4)
- `deck.build_md(current, prior, meta)` → **byte-identical** golden (no embedded date; deterministic).
- `deck.build_pptx(...)` → **parsed-content** compare (slide texts / table cells / chart series), **normalizing the `Generated <date>` subtitle line** (deck.py:99) — never raw `cmp`, never edit `deck.py`.
- VM structured on-screen output == frozen golden per fixture.
- Fixtures: sample-CSV snapshot (has sub-vertical + 10+ deals) for `full`; a with-prior pair for arrows + two-series chart; a no-sub-vertical minimal.
