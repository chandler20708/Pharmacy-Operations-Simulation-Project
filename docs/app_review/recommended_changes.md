# Recommended Changes

## Recommended Phase Decision

Do **not** move to Phase 3 yet.

The app is now a strong read-only dashboard. The next iteration should complete a **Phase 2 hardening gate**:

1. Resolve executive overview page naming.
2. Browser-check all Streamlit pages.
3. Improve scenario classification in the strategy library.
4. Add interpretation logic to the steady-state page.
5. Make cost-effectiveness component-based enough for Group B and Group G.
6. Expand tests for the new multipage behavior.

After that, start Phase 3 custom scenario builder.

## Page Structure

Current structure:

```text
app/streamlit_app.py
app/pages/1_Strategy_Library.py
app/pages/2_Steady_State_Diagnostics.py
app/pages/3_Cost_Effectiveness.py
app/pages/4_Conceptual_Model.py
app/pages/5_Stakeholder_Export.py
```

Recommended final structure:

```text
app/streamlit_app.py                 # app shell or executive overview
app/pages/1_Executive_Overview.py    # if streamlit_app becomes a shell
app/pages/2_Strategy_Library.py
app/pages/3_Steady_State_Diagnostics.py
app/pages/4_Cost_Effectiveness.py
app/pages/5_Conceptual_Model.py
app/pages/6_Stakeholder_Export.py
```

If `streamlit_app.py` remains the first page, update the page title/caption so users see it as:

```text
Executive Overview
Pharmacy Flow Strategy Lab
```

## Strategy Library Improvements

Add a scenario classification helper in `scenario_manifest.py`.

Suggested labels:

- `Baseline`
- `Intervention`
- `Process improvement hypothesis`
- `Governance-sensitive role change`
- `Sensitivity test`
- `Stress test`
- `Recovery package`
- `Combined package`

Use it in `app/pages/1_Strategy_Library.py` instead of only:

```text
stress/sensitivity
intervention/package
```

## Steady-State Page Improvements

Add an interpretation block above the diagnostics table:

```text
Selected scenario: G1_practical_capacity_plus_it
Status: closest_to_steady_state
Late flow: balanced / not balanced
Traffic intensity: near capacity / overloaded / underloaded
Backlog movement: improving / worsening / unclear
Report use: acceptable scenario evidence / treat cautiously
```

Keep the raw diagnostic table and plots, but make the first readout stakeholder-readable.

## Conceptual Model Page Improvements

Add these sections:

1. **CPU And Roles**
   - CPU A uses MMPT; CPU B uses CPT.
   - CPT and MMPT differ in discharge-verification eligibility.
   - Juniors and seniors cover clinical tasks with named-worker independence constraints.

2. **Service-Time Assumptions**
   - Drug history: lognormal.
   - Medicines reconciliation: lognormal.
   - Discrepancy/error resolution: triangular placeholder.
   - Prescription verification: lognormal.
   - Discharge writing: gamma.
   - Discharge verification: gamma.
   - Counselling: gamma.

3. **Evidence Hierarchy**
   - Sample journeys and animation are single-run explanatory artifacts.
   - Scenario rankings use 30-replication scenario summaries when available.
   - Validation caveats still apply.

## Cost-Effectiveness Hardening

Move from family-level mapping to component-level assumptions.

For Group B:

```text
implementation_score =
  role_cost_weight
+ headcount_count
+ recruitment_feasibility
+ onboarding_time
```

For Group G:

```text
G1 = technician staffing + junior staffing + IT/process improvement
G2 = technician scope/training + IT/process improvement
G3 = busy-month stress-test + technician staffing + junior staffing + senior staffing + IT/process improvement
G4 = 09:00-17:00 sensitivity + technician staffing + junior staffing + IT/process improvement
```

The page should show these components, not only the final score.

## Phase 3 Entry Criteria

Start custom scenario builder only when:

- browser smoke check passes;
- executive overview naming is resolved;
- strategy library classifies scenario types accurately;
- steady-state diagnostics provide a plain-English interpretation;
- cost-effectiveness is component-based for staffing and combined packages;
- tests cover the new page-level service behavior.

## Custom Scenario Builder Scope

When Phase 3 starts, keep it bounded:

- demand multipliers;
- operating hours;
- staffing deltas;
- role eligibility toggles;
- service-time mean/SD multipliers;
- routing probabilities;
- cost assumptions;
- export to YAML/JSON;
- preview changed assumptions vs baseline.

Do not expose:

- Python model code editing;
- event loop mechanics;
- event-log schema changes;
- random stream changes;
- validation logic edits.

## Test Plan

Add tests for:

- latest full run metadata includes scenario definitions;
- strategy library scenario classification;
- `A2_no_upstream_discrepancy` assumption delta includes discrepancy probability `0.6 -> 0`;
- `G1/G2/G3/G4` component cost assumptions;
- stress tests are not treated as normal implementation options;
- steady-state interpretation for `approximately_steady_state`, `closest_to_steady_state`, and `not_steady_state`;
- sample-output discovery returns available plots and handles missing files;
- stakeholder summary includes scenario description, assumption changes, evidence basis, and caveats.

Manual checks:

```bash
./.venv/bin/python -m compileall app
./.venv/bin/python -m pytest tests/test_app_services.py
.venv/bin/streamlit run app/streamlit_app.py
```

Then inspect every page in the browser.
