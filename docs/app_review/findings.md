# Findings

## P1: Do Not Move To Phase 3 Yet

Brief reference:

- `docs/pharmacy_flow_strategy_lab_mvp_brief.md:966`
- `docs/pharmacy_flow_strategy_lab_mvp_brief.md:1103`
- `docs/pharmacy_flow_strategy_lab_mvp_brief.md:1173`

The app has made strong progress and is now a credible read-only dashboard. It is still not ready for Phase 3 custom scenario building.

Why:

- Phase 2 ranking is still proxy-heavy.
- Browser-level verification has not been completed.
- Custom scenario config creation/export is not implemented.
- More tests are needed before adding user-generated scenario inputs.

Recommendation:

Complete Phase 2 hardening first. Treat Phase 3 as the next major feature after ranking, diagnostics, and page navigation are stable.

## P1: Executive Overview Naming Is Still Not Clean

Files:

- `app/streamlit_app.py`
- `app/pages/`
- `app/README.md`

The app now has multiple pages, but the executive overview still lives in `streamlit_app.py`. The visible root page title is `Pharmacy Flow Strategy Lab`, while future pages are named clearly.

Current files:

```text
app/streamlit_app.py
app/pages/1_Strategy_Library.py
app/pages/2_Steady_State_Diagnostics.py
app/pages/3_Cost_Effectiveness.py
app/pages/4_Conceptual_Model.py
app/pages/5_Stakeholder_Export.py
```

Problem:

This is workable, but it does not fully satisfy the user's intended page model. The first page is effectively `Executive Overview`, but that name is not visible in the file structure.

Recommendation:

Either:

1. Keep `streamlit_app.py` as the root page but change the displayed page title/caption to clearly say `Executive Overview`; or
2. Make `streamlit_app.py` a minimal shell and create `app/pages/1_Executive_Overview.py`.

Option 2 is cleaner if more explanatory pages are expected.

## P1: Cost-Effectiveness Is Still Not Mature Enough

Files:

- `app/core/cost_effectiveness.py`
- `outputs/scenario_strategy_effort_cost_proxy.csv`
- `app/pages/3_Cost_Effectiveness.py`

The cost-effectiveness page is now useful: it shows benefit components, implementation assumptions, governance risk, cost source, and normalized weights.

The main remaining issue is scoring quality:

- Group B staffing scenarios are adjusted by headcount, but not by role-specific cost and feasibility.
- Group G combined packages are still mapped too broadly, mostly through family-level rules.
- `G3_busy_month_resilience_package` and `G4_0900_1700_capacity_recovery_package` mix stress-test assumptions with interventions, but this mixture is not decomposed clearly in the score.
- Category thresholds are fixed, so near-threshold scenarios can flip labels without showing uncertainty.

Impact:

The page is good enough for exploratory ranking, but not strong enough for final recommendations.

Recommendation:

Move from family-level scoring to component-level scoring:

```text
staffing component
+ IT/process component
+ role-scope component
+ demand/stress-test component
+ working-hours sensitivity component
+ governance/training component
```

Then show component scores in the page.

## P1: Browser/UI Verification Is Still Missing

The service layer works, tests pass, and Streamlit starts. However, the review did not verify rendered pages in a browser because the sandbox could not connect to the local Streamlit port with `curl`.

Impact:

There may still be page-level issues that service tests cannot catch:

- large tables overflowing;
- Graphviz rendering problems;
- local image/GIF rendering problems;
- page sidebar state confusion;
- Streamlit navigation naming issues.

Recommendation:

Before claiming Phase 1 complete, manually open the app and check every page:

```bash
.venv/bin/streamlit run app/streamlit_app.py
```

Use the sidebar to select the latest full `smart_dynamic` run and verify:

- root overview page loads;
- strategy library filters families correctly;
- steady-state page shows raw diagnostics and images;
- cost-effectiveness page shows ranking and components;
- conceptual model page shows graph, sample journeys, and task events;
- stakeholder export contains scenario description, assumptions, evidence basis, and caveats.

## P2: Strategy Library Exists But Needs Intervention Classification

File:

- `app/pages/1_Strategy_Library.py`

The strategy library page is a good addition. It groups scenarios and shows label, description, caveat, and a simple scenario type.

Remaining issue:

The current type label is broad:

```text
Group E -> stress/sensitivity
everything else -> intervention/package
```

This is too blunt for stakeholder use. Group G packages can contain stress-test components, and Group A scenarios are mechanism-removal scenarios rather than immediately implementable interventions.

Recommendation:

Add a richer scenario type:

- baseline;
- intervention;
- process-improvement hypothesis;
- governance-sensitive role change;
- sensitivity test;
- stress test;
- recovery package;
- combined implementation package.

## P2: Steady-State Diagnostics Page Exists But Needs Interpretation Logic

File:

- `app/pages/2_Steady_State_Diagnostics.py`

This page now explains `N(t)`, rate balance, and drain-period caveats. It also shows diagnostics and sample plots.

Remaining issue:

The page does not yet translate diagnostic values into a clear interpretation for the selected scenario.

Recommendation:

Add a short computed interpretation block:

```text
Selected scenario status: closest_to_steady_state
Late flow balance: completions and arrivals are approximately balanced / not balanced
Traffic intensity: near capacity / overloaded / underloaded
Backlog signal: improving / worsening / unclear
Use in report: acceptable as scenario evidence / treat as stress-test only
```

## P2: Conceptual Model Page Is Useful But Still Thin For Academic Explanation

File:

- `app/pages/4_Conceptual_Model.py`

The page now includes a pathway graph, assignment policy explanation, sample plots, animation, patient journeys, and task events.

Remaining gaps:

- It does not yet explain CPU A vs CPU B role differences in enough detail.
- It does not list the task service-time distributions.
- It does not clearly separate single-run sample visuals from 30-replication scenario evidence until lower on the page.
- It does not link directly to model foundation or validation docs.

Recommendation:

Add sections for:

- CPU A / CPU B staffing and technician role differences;
- service-time distribution assumptions;
- evidence hierarchy: single-run example vs 30-replication results;
- validation caveats from the report-readiness notes.

## P2: Tests Need To Catch New Page/Phase Behavior

File:

- `tests/test_app_services.py`

The current four tests pass and cover core loading/ranking/summary behavior. They are no longer enough for the expanded multipage app.

Add tests for:

- scenario library classification;
- steady-state interpretation;
- conceptual sample-output discovery;
- Group G component cost assumptions;
- `A2_no_upstream_discrepancy` assumption delta;
- root overview context generation;
- stakeholder export including scenario description, evidence basis, and caveats.

## P3: Custom Scenario Builder Is Still Missing From Full MVP Acceptance

Brief reference:

- `docs/pharmacy_flow_strategy_lab_mvp_brief.md:1114`
- `docs/pharmacy_flow_strategy_lab_mvp_brief.md:1115`

The app does not yet meet full MVP acceptance criteria because it cannot:

- create a custom scenario config using bounded controls;
- export the custom scenario config.

Recommendation:

Do not implement this immediately. First harden Phase 2. Then build Phase 3 as a bounded form that exports YAML/JSON and previews assumption changes before any run-on-demand integration.
