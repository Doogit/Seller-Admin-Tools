# Plan — Port Seller-Admin-Tools UI to FastHTML + htmx + Tailwind (tools 1–3)

> Status: reviewed (6-persona doc review) + externally researched (FastHTML,
> python-pptx, htmx) + revised. Scope confirmed: all three tool pages, ported in
> order Forecast Narrative → QBR Assembler → Account Plan, on a shared FastHTML
> skeleton. Home/pipeline-import stays on Streamlit this branch.
> See "Changelog — review + research integration" at the end for the decision log.

## Stack decision

**FastHTML + htmx + Tailwind CSS (standalone CLI).** Rationale:

- **FastHTML over FastAPI** — same Starlette core, but purpose-built for
  htmx/hypermedia with Python-defined components; no Jinja layer, no JSON API
  (this tool has neither).
- **Tailwind over hand-CSS/Pico** — chosen for long-term consistency under a
  multi-agent editing workflow and stack parity with the sibling GridSignals
  project. Offline is preserved via the **standalone Tailwind CLI** (a single Go
  binary, no Node): it builds a tree-shaken `web/static/tailwind.css` that is
  **committed to the repo** and served locally. No CDN, no runtime network.
- **The one accepted cost:** Tailwind adds a build step (`make css`) and a
  non-Python binary — the only break from the repo's otherwise no-build,
  pip-only posture. This is deliberate and documented (see Task 0). The built
  CSS is committed so a fresh `pip install` clone still runs offline without the
  binary; the binary is only needed to *change* styles.

## Placeholders resolved

| Placeholder | Value |
|---|---|
| `{{TOOL_NAME}}` | Three tools: `forecast_narrative`, `qbr` (QBR Assembler), `account_plan` (ported in that order) |
| `{{TARGET_UI}}` | FastHTML + htmx + Tailwind (standalone CLI), all assets vendored/committed locally |
| `{{OLD_PAGE}}` | `app/pages/1_Forecast_Narrative.py`, `app/pages/2_QBR_Assembler.py`, `app/pages/3_Account_Plan.py` |
| `{{NEW_PAGE}}` | New `web/` package: `web/server.py` (skeleton), `web/routes/{forecast_narrative,qbr,account_plan}.py`, `web/components.py`, `web/static/` (vendored htmx + fasthtml.js + committed tailwind.css) |
| `{{CORE_MODULES}}` | `forecast`, `narrative`, `formatting`, `deck`, `crosswalk`, `plan`, `store` (+ the string/format logic currently in `app/ui.py`, and page-body string transforms, which fold into view models) |
| view models | `core/views/forecast_narrative.py`, `core/views/qbr.py`, `core/views/account_plan.py` (additive; no existing core file edited) |
| `{{BRANCH}}` | `feat/fasthtml-port-tools` |

## Repo reality (verified pre-flight facts)

- `core/` imports no Streamlit (`grep -rn "import streamlit\|from streamlit" core/` → none).
- Working tree clean at planning time.
- Three separate Streamlit tool scripts + a shared pipeline-import entry point (`Home.py`) + shared render helpers (`app/ui.py`, `app/mapping_ui.py`).
- `st.` call counts (clean, `grep -oE "\bst\.[a-z_]+"`): page 1 = 23, page 2 = 24, page 3 = 49; `Home.py` = 34, `ui.py` = 9, `mapping_ui.py` = 19.
- No `altair`; no `@st.cache_*`.
- **Determinism of outputs (verified in code):** `narrative.assemble_markdown`, `deck.build_md`, and `plan.plan_md` embed **no date** → all `.md` outputs are byte-deterministic. Only `.pptx` outputs are non-deterministic: python-pptx stamps every ZIP entry with save-time clock and sets `core_properties.modified = now()`, and `deck.py:99` additionally embeds `Generated <today>` on a slide.
- Seed data (`sample_data/seed_snapshots.py` + account-facts fixtures) exercises all three tools headlessly.

## How this deviates from the one-tool template (and why)

1. **Task 0 added — one-time FastHTML skeleton + Tailwind build.** FastHTML is one ASGI app, not per-file scripts. The first tool also stands up the server, base layout, static route, the Tailwind build, and locally vendored JS. `fast_app()` injects **five** assets from a CDN by default (htmx, `fasthtml.js`, surreal.js, css-scope-inline, a third-party Pico fork — two pinned to moving `@main`/`@latest`); the skeleton disables all of them and serves local copies.
2. **Tasks 1–4 run three times** (once per tool); the skeleton, `web/components.py`, the Tailwind setup, and the view-model *pattern* are built with tool 1 and reused.
3. **Task 5 is partial.** Retire only `pages/1..3` and helpers only they use (`app/ui.py` dissolves into view models). **`Home.py`, `mapping_ui.py`, and `streamlit` stay** — pipeline import is out of scope this branch. Full Streamlit removal is a scheduled follow-up branch (port Home). `CLAUDE.md`'s "thin Streamlit wrappers" architecture note must be updated post-merge to describe two parallel UI layers during the interim.
4. **`ui.py` and page-body string glue dissolve into view models.** Load-bearing strings/formatting (`fmt_money`, coverage `x`, derived/unclassified captions, unmatched-warning text) **and** page-level transforms (e.g. the period label derived as `labels[current_id].split(" ")[0]`, `ui.snapshot_labels` formatting) must live in the view model — otherwise they escape the parity diff.
5. **No `altair`, no `@st.cache_*`** — template cleanup notes for those are no-ops.

## Pre-flight (stop-and-report on any failure)

- `git status --porcelain` → empty. (confirmed clean)
- `python -m pytest` → all green.
- `grep -rn "import streamlit\|from streamlit" core/` → none. (confirmed)
- `grep -oE "\bst\.[a-z_]+" app/pages/1_Forecast_Narrative.py app/pages/2_QBR_Assembler.py app/pages/3_Account_Plan.py` → counts 23 / 24 / 49.
- `grep -rn "@st.cache\|st\.cache" app/` → none.
- Confirm the pinned `python-fasthtml==0.14.11` `fast_app(default_hdrs=False, pico=False, hdrs=...)` emits **no** external URL (verify against the `0.14.11` tag specifically — research was read off `main`).
- Confirm the Tailwind standalone CLI version to pin and that `make css` produces a byte-stable `web/static/tailwind.css` for unchanged input.
- `python sample_data/seed_snapshots.py` + load account facts (per `tests/test_crosswalk.py` fixtures) so all tools render headlessly.

## Task 0 — FastHTML skeleton + Tailwind build (once)

`web/server.py`:

```python
app, rt = fast_app(
    pico=False,            # suppress the third-party Pico CDN fork
    default_hdrs=False,    # suppress htmx/fasthtml.js/surreal/scope-inline CDN scripts + default meta
    static_path="web/static",
    hdrs=(
        Meta(charset="utf-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Script(src="/htmx.min.js"),
        Script(src="/fasthtml.js"),        # load-bearing: FastHTML OOB/boost conveniences
        Link(rel="stylesheet", href="/tailwind.css"),
    ),
)
```

- **Vendor into `web/static/`:** `htmx.min.js` **and** `fasthtml.js` (surreal.js + css-scope-inline only if a template uses `me()`/scoped `<style>` — default: omit). `default_hdrs=False` also drops the charset/viewport meta, so they are re-added above.
- **Tailwind:** commit the standalone CLI binary path/version to the repo tooling; add a `make css` target (`tailwindcss -i web/static/app.src.css -o web/static/tailwind.css --minify`) scanning `web/**/*.py`. Commit the built `web/static/tailwind.css`.
- **Startup assert:** iterate the resolved header tags and assert no `src`/`href` matches `^https?://` — fail fast if a CDN link reappears.
- **`requirements.txt`:** add `python-fasthtml==0.14.11` with a comment that the pin is load-bearing for offline header behavior; add a comment pointing to the Tailwind CLI version + `make css` (the binary is not a pip dep).
- Base layout in `web/components.py`; landing route listing the three tools.

## Tasks 1–4, repeated per tool (Forecast → QBR → Account Plan)

**Task 1 — Inventory** → `docs/migration/<tool>-inventory.md`, one row per `st.*` call, **plus** a sweep of string transforms in the page body (not just `ui.py`) so nothing user-visible escapes the view model. Then the two required lists.

- **1a. Workarounds to DELETE (not reimplemented):**
  - *Forecast:* `draft_key` `session_state` hydration + the "Discard my edits and regenerate" confirm-checkbox + disabled-Regenerate + `st.rerun()` — a rerun artifact. In htmx, edits live in the DOM; see Interaction contract below.
  - `st.code(md, language="markdown")` as a copy affordance → native `<pre>` + download link.
  - `st.stop()` early-exits → render the info/empty state and return.
  - *Account Plan:* `st.rerun()` after import / alias-confirm / product-assign → htmx region swap.
- **1b. Requirements that PORT VERBATIM (string-for-string):** "Buckets derived from stage — map forecast_category for accuracy." · "{money} open in unmapped stages is excluded from coverage." · "No risk flags." · risk `Note:` lines · "{n} opportunities couldn't be matched to last week — renamed or ID missing? See the movement table." · "Numbers identical to Forecast Narrative for the same snapshot." · "Sub-vertical split unavailable — field not mapped in this snapshot." · the three per-tool draft/read-only footers (each worded differently) · coverage `—` empty state · alias/product provenance + the obligation-map disclaimer.

**→ Stop and show tool 1's inventory before writing any UI code.**

**Task 2 — View model** `core/views/<tool>.py`: pure functions, no UI imports; **all formatting and all user-facing string generation done here once** (routes render values verbatim, no inline literals except static labels). Tests `tests/test_<tool>_view.py`: happy path, missing-optional-field degradation, empty/insufficient data, each conditional note. **These view tests are part of the green-suite gate**, distinct from the Task 4 parity tests (which compare the same view model to a frozen golden).

**Task 3 — FastHTML route** `web/routes/<tool>.py`: renders strictly from the view model; same selectors/defaults/ordering/grouping. Tool-specific notes:
- *QBR `.pptx`/`.md`:* reuse `deck.build_pptx/build_md` unchanged and stream bytes via a download route. `.md` is deterministic (byte-stable). `.pptx` is **not** byte-stable (ZIP timestamps + embedded date) — parity is asserted at the parsed-content layer (Task 4), never as raw bytes.
- *QBR chart:* `st.bar_chart` → server-rendered SVG/HTML bars (Tailwind-styled) from view-model data. Since there is no hover tooltip, **render the exact bucket dollar value as a visible label** on/beside each bar; define the **empty state** (zero open rows). Chart *rendering* is explicitly out of parity scope; the underlying values are covered by view-model parity.
- *Account Plan (Q2 — port the import grid to htmx):* the account-facts CSV import (upload → suggested mapping → per-field live preview → date-format preview → validation → import) is reimplemented in htmx. Its logic is already pure core (`mapping.suggest_mapping`, `ingest.infer_date_format`, `ingest.parse_date_series`); only the rendering is new. The reactive per-field preview uses `hx-trigger="change delay:200ms from:closest form"` + `hx-include` (send all field values) + `hx-sync="closest form:replace"` (cancel stale in-flight requests). Note: htmx's own docs flag many-interdependent-field reactivity as a weak spot — budget real effort here; this is the hardest interaction in the branch. `alias-confirm` (`aliases.yaml`) and `product-assign` (`product_map.yaml`) are simple single-action POSTs. These config writes are existing behavior (config, not snapshot store, not network); preserved.

**Interaction contract (applies to all mutating/partial interactions):**
- **Preserve edits across an unrelated swap via `hx-target` scoping**, not `hx-preserve` (research: `hx-preserve` cannot retain a live input's value/caret). A quota-change swaps only the metrics/coverage panel; the draft textarea, outside that target subtree, is untouched.
- **Snapshot change → regenerate the draft, discarding edits (Q1).** The draft is keyed to the snapshot's numbers; a snapshot change swaps the whole draft region with a freshly generated draft so narrative and metrics never disagree.
- **Regenerate → dirty-guarded overwrite (Q3).** `hx-post` + `hx-target="#draft"` + `hx-swap="innerHTML"`. App-level dirty tracking: fire `hx-confirm` **only if** the draft differs from the last generated text; otherwise overwrite silently (htmx has no native "warn on unsaved").
- **In-flight / double-submit protection on every mutating POST:** `hx-sync="this:drop"` (drop overlapping requests) + `hx-disabled-elt="this"` + `hx-indicator`.
- **Accessibility:** real `<label>` (or `aria-label`) on every `<select>`/input — the current UI relies on Streamlit's implicit labels (several use `label_visibility="collapsed"`); raw HTML must carry the accessible name explicitly. Keyboard-reachable controls, no color-only signaling.

**Task 4 — Parity gate** `tests/test_<tool>_parity.py`:
- **Goldens come from the core functions directly** (`narrative.draft`/`assemble_markdown`, `deck.gather`/`build_md`, `plan.compose`/`plan_md`) against seed fixtures **at the current commit, captured before the view model is written**, then frozen. (The live Streamlit page cannot be the golden source: the view model doesn't exist there, and the pages run `st.*` at module top so they're not importable headless.)
- Assert new view-model output == frozen golden per fixture (full / minimal-required / empty).
- `.md` exports: byte-identical (`cmp`) — deterministic, no masking needed.
- `.pptx` exports: **parse both decks and compare extracted slide texts / table cells / chart series values** (the `test_deck.py` approach) — never raw `cmp`. `deck.py:99`'s embedded date and python-pptx ZIP timestamps make raw bytes inherently unstable; the oracle **normalizes/ignores the generation date rather than editing `deck.py`**, preserving the zero-core-edit invariant.
- Any intentional difference → explicit allowlist entry with a one-line justification. Empty allowlist expected. Fail → stop and report; never edit the golden to match.

## Task 5 — Partial retirement (only after all three parity + edit-durability gates pass)

Delete `pages/1..3` and `app/ui.py` (dissolved into view models; verify no remaining importers). **Keep** `Home.py`, `mapping_ui.py` (still used by Home), `streamlit`, `pandas`, `python-pptx`, `PyYAML`. Update README run instructions (add `uvicorn web.server:app` / FastHTML launch + `make css`; note Home still on Streamlit). Update `CLAUDE.md` architecture note to describe the interim two-UI state. Retarget parity goldens as the ongoing regression baseline.

## Done criteria (two co-equal gates)

1. **Parity** — view-model == frozen golden; `.md` byte-identical; `.pptx` content-identical. Proves "we broke nothing."
2. **Edit durability + interaction wins** — quota-change preserves edits; snapshot-change regenerates cleanly; Regenerate is dirty-guarded; no double-submit. Proves "we delivered the reason for the port." A port with parity green but interaction regressed is **not** done.

## Verification checklist (each with its proof command)

- Core untouched: `git diff --stat feat/fasthtml-port-tools -- core/` → only additive `core/views/*`, zero modified lines in existing core modules.
- `python -m pytest` → all pass (incl. `tests/test_<tool>_view.py` and pre-existing core tests unmodified).
- Parity: `python -m pytest tests/test_forecast_narrative_parity.py tests/test_qbr_parity.py tests/test_account_plan_parity.py -v` → pass, allowlists empty.
- Cold start: launch FastHTML, hit each tool → first render < 2s (record actual; `risk_flags` walks every prior snapshot, so watch tool 1/2 at higher snapshot counts).
- Traceability: pick a dollar/count figure → matches a direct `sqlite3 data/agents.db` query (paste both).
- Degradation: minimal-required-fields snapshot → renders, optional features skipped with the visible note intact, no traceback.
- **Edit durability:** type into the draft; change quota → edit survives; change snapshot → draft regenerates (documented); click Regenerate on a dirty draft → confirm fires; on a clean draft → no confirm; double-click Regenerate → one POST. Report any interaction that discards edits unexpectedly.
- Offline: kill network, restart, full flow → works. `grep -rniE "https?://|cdn|unpkg|jsdelivr" web/server.py web/routes/ web/components.py` (source) and `grep -rniL . web/static/` for external origins in vendored assets → none. Startup assert (Task 0) already guards header URLs.
- Tailwind freshness: `make css && git diff --exit-code web/static/tailwind.css` → no diff (committed CSS matches source).
- Export: `.md` from old and new → `cmp` → identical. `.pptx` from old and new → parse both, compare slide texts/table cells/chart series → identical (do **not** `cmp` raw `.pptx`).
- Streamlit residue (tools only): `grep -rn "streamlit" app/pages/` → none (Home retains it intentionally).

## Sequencing checkpoint

After tool 1's parity **and** edit-durability gates pass, pause and confirm the view-model + interaction pattern before porting tools 2–3 (they build on the same branch). Tool 3 is the largest (49 `st.` calls) and carries the hardest interaction (the reactive import grid) — validate the pattern on the smallest tool first.

## Decisions / risks log

- **Offline is the #1 risk** — lives in Task 0: `default_hdrs=False` + `pico=False` + vendored htmx/`fasthtml.js` + committed Tailwind CSS + startup assert. Verify against the `0.14.11` tag.
- **`.pptx` byte-identity is impossible** (python-pptx ZIP timestamps + `core_properties.modified=now()` + `deck.py:99` date). Parity is at the parsed-content layer; oracle normalizes the date; `core` stays untouched.
- **Goldens are frozen at the branch base commit** from core functions — this also removes the "golden drifts if core changes mid-branch" risk (treat `core/` as frozen for the branch; re-baseline only on an intentional core change).
- **Tailwind adds a build step** (`make css` + standalone binary) — the one break from no-build; mitigated by committing the built CSS so runtime/clone stays offline and pip-only.
- **Reactive import grid (tool 3)** is a documented htmx weak spot — real effort, not a one-attribute port. Hardest item; front-loaded awareness via the sequencing checkpoint.
- **FYI:** concurrent config-write race — a single ASGI process handles requests concurrently, so `hx-sync` serializes a given trigger but not two different triggers; acceptable for a single-user local tool, noted not fixed. QBR chart rendering is out of parity scope (values are in). Interim two-launch workflow (Streamlit import + FastHTML tools) and the unscheduled-until-now Home port are real coexistence costs — Home port is the committed next branch.
- View-model pattern established in `core/views/forecast_narrative.py` is the template the other two mirror; `web/components.py` + the Tailwind setup are shared, reused not reinvented.

## Recommended next step

Create branch `feat/fasthtml-port-tools`, run the full pre-flight (incl. the `0.14.11`-tag offline verification and Tailwind CLI pin), then produce the Task 1 inventory for Forecast Narrative — stop for review before any UI code.

---

## Changelog — review + research integration (2026-08-12)

Revised after a 6-persona `ce-doc-review` pass + external research (FastHTML, python-pptx, htmx) + user decisions.

**Findings integrated:**
- **[P0] `.pptx` "byte-identical by construction" was false** (feasibility + coherence + adversarial, conf 100; confirmed at `deck.py:99` and via python-pptx source) → parity redefined as parsed-content comparison; `.md` stays byte-diff (verified deterministic); date normalized in oracle, `core` untouched.
- **[P1] Golden-from-live-Streamlit-path unworkable** (adversarial) → goldens captured from core functions at the base commit, pre-view-model.
- **[P1] FastHTML CDN defaults** (feasibility + research) → `default_hdrs=False`+`pico=False`, vendor htmx **and `fasthtml.js`**, pin `python-fasthtml==0.14.11`.
- **[P1] Edit-durability conflated quota vs snapshot change** (feasibility + design) → split: quota preserves (hx-target scoping), snapshot regenerates.
- **[P1] Tool-3 import/mapping_ui collision** (design + adversarial) → per Q2, port the import grid to htmx (research-backed pattern + effort flagged).
- **[P2] Page-level string glue outside parity boundary** (adversarial) → Task 1 inventory sweeps page-body transforms into the view model.
- **[P1/P2] Regenerate/loading/double-submit states undefined** (design) → `hx-confirm` (dirty-guarded, Q3) + `hx-sync`/`hx-disabled-elt`/`hx-indicator`.
- **[P1] Done-criteria couldn't prove the port's value** (product) → edit-durability elevated to a co-equal gate.
- **safe_auto:** `st.` counts corrected; "by construction" removed; offline `grep` made concrete. **FYI:** concurrent-write caveat, accessibility labels, coexistence/architecture-doc note, sequencing checkpoint.

**User decisions:** stack = FastHTML + htmx + Tailwind (standalone CLI, offline, committed CSS); Q1 = regenerate draft on snapshot change; Q2 = port the account-facts import grid to htmx now; Q3 = confirm-on-dirty for Regenerate.

**Research caveats to re-verify at build time:** FastHTML source was read off `main` — confirm header behavior against the `0.14.11` tag. Pin and smoke-test the Tailwind standalone CLI version for stable `make css` output.
