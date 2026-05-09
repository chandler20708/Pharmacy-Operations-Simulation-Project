# Phase Maturity Review

Date: 2026-05-09

## Brief Phase Definitions

From `docs/pharmacy_flow_strategy_lab_mvp_brief.md`:

| Phase | Goal | Current assessment |
| --- | --- | --- |
| Phase 0 | Make outputs app-readable | Complete enough for MVP |
| Phase 1 | Static dashboard over existing outputs | Largely complete |
| Phase 2 | Cost-effectiveness ranking | Implemented, needs hardening |
| Phase 3 | Custom scenario builder | Not started, should wait |
| Phase 4 | Run-on-demand integration | Not started |
| Phase 5 | Strategy generator | Not started |

## What Changed Since Last Review

The app now has a real multipage structure:

```text
app/streamlit_app.py
app/pages/1_Strategy_Library.py
app/pages/2_Steady_State_Diagnostics.py
app/pages/3_Cost_Effectiveness.py
app/pages/4_Conceptual_Model.py
app/pages/5_Stakeholder_Export.py
```

It also has shared components:

```text
app/components/run_context.py
app/components/dashboard_views.py
```

This addresses several earlier issues:

- strategy library now exists;
- steady-state diagnostics page now exists;
- conceptual model page now exists;
- stakeholder export page now exists;
- shared run/scenario selection now exists;
- page duplication is gone.

## Current Phase

The app is currently **Phase 1 complete enough for MVP demonstration, with Phase 2 implemented but not yet mature enough for decision-grade use**.

It has:

- run discovery and policy filtering;
- Parquet-first and CSV-fallback loading;
- metadata-backed run provenance;
- scenario labels and assumption deltas;
- KPI comparison;
- bottleneck comparison;
- experiment plots;
- steady-state diagnostics page;
- strategy library page;
- conceptual model page with pathway graph and sample patient journeys;
- cost-effectiveness ranking page;
- stakeholder Markdown export;
- basic service tests.

It still lacks:

- a properly named `Executive Overview` page file;
- browser-level verification evidence;
- richer visual checks for all pages;
- mature component-based cost scoring;
- strong tests for the new multipage behaviors;
- custom scenario builder and YAML/JSON export.

## Is It Mature Enough For The Next Phase?

No, not for Phase 3.

The next brief phase is the custom scenario builder. That would add new user inputs, schema validation, config export, and eventually run-on-demand simulation. The current app should first make Phase 2 robust enough that users can trust the ranking and evidence framing.

Recommended next step:

```text
Finish Phase 2 hardening before starting Phase 3.
```

## Phase 1 Completion Status

Mostly complete.

Remaining Phase 1 cleanup:

- Add or rename the first page so Streamlit shows `Executive Overview` rather than relying on generic `streamlit_app.py`.
- Browser-check every page.
- Confirm tables fit at laptop width.
- Confirm images and GIFs load on the conceptual model / diagnostics pages.
- Confirm stale smoke runs are not selected without a visible warning.

## Phase 2 Completion Status

Implemented but not mature.

Remaining Phase 2 work:

- Make cost scoring scenario-level or component-level.
- Decompose Group G combined packages into their staffing, IT, demand, and role-scope components.
- Separate pure stress tests from implementation options in both scoring and UI.
- Show why a scenario receives its category, not only the category.
- Test ranking behavior for representative A-G scenarios.

## MVP Acceptance Criteria Status

From section 21:

| Criterion | Status |
| --- | --- |
| Open Streamlit app | Service start verified; browser render still unverified |
| Select baseline and scenario | Implemented |
| View headline KPI deltas | Implemented |
| Inspect bottleneck movement | Implemented |
| Inspect role utilisation change | Implemented |
| Rank predefined scenarios by benefit/cost proxy | Implemented |
| Change KPI weights and see ranking update | Implemented |
| Create custom scenario config using bounded controls | Not implemented |
| Export custom scenario config | Not implemented |
| Export stakeholder summary | Implemented |

So the current app is a strong **read-only MVP**, but not the full MVP described in section 21 because custom scenario config creation/export is missing.

## Page Naming Recommendation

The remaining naming issue is now narrower:

- `streamlit_app.py` functions as the executive overview.
- The visible app title is `Pharmacy Flow Strategy Lab`, not `Executive Overview`.
- There is no `app/pages/1_Executive_Overview.py`; page numbering starts at `1_Strategy_Library.py`.

Recommendation:

Use one of these patterns:

```text
Option A:
streamlit_app.py             # minimal landing / app shell
pages/1_Executive_Overview.py
pages/2_Strategy_Library.py
...
```

or:

```text
Option B:
streamlit_app.py             # executive overview
pages/1_Strategy_Library.py
...
```

If using Option B, make the page title and README explicitly call the root page `Executive Overview`.

## Phase Gate

Start Phase 3 only after:

- browser smoke check passes for all pages;
- executive overview naming is resolved;
- cost-effectiveness scoring is component-based enough for Group B and Group G;
- stress tests are clearly separated from interventions;
- tests cover metadata, assumption deltas, ranking categories, diagnostics, and stakeholder exports.
