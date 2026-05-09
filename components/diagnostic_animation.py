from __future__ import annotations

import html

import polars as pl
import streamlit as st


AXIS_LEFT = 22.0
AXIS_RIGHT = 98.0

LANES = {
    "queue": 58,
    "technician": 124,
    "junior": 190,
    "senior": 256,
}


def render_window_animation(events: pl.DataFrame, *, start_day: int, end_day: int) -> None:
    if events.height == 0:
        st.info("No task events found in the selected window.")
        return

    start_minute = start_day * 1440
    end_minute = (end_day + 1) * 1440
    span = max(end_minute - start_minute, 1)
    rows = events.sort("started_at").head(36).to_dicts()
    bars = []
    handoffs = []
    lane_counts = {lane: 0 for lane in LANES}
    for index, row in enumerate(rows):
        role = _role_lane(row.get("worker_role"))
        queue_offset = (lane_counts["queue"] % 3) * 15
        lane_counts["queue"] += 1
        service_offset = (lane_counts[role] % 3) * 15
        lane_counts[role] += 1
        wait_left = _pct(row.get("queued_at"), start_minute, span)
        wait_right = _pct(row.get("started_at"), start_minute, span)
        service_left = _pct(row.get("started_at"), start_minute, span)
        service_right = _pct(row.get("finished_at"), start_minute, span)
        patient = f"P{row.get('entity_id')}"
        task = str(row.get("task_name", "task")).replace("_", " ")
        worker = str(row.get("worker_name") or role)
        label = f"{patient}: {task}"
        wait_class = _wait_class(row.get("queue_wait_minutes"))
        bars.append(
            _bar(
                css_class=f"wait {wait_class}",
                top=LANES["queue"] + queue_offset,
                left=wait_left,
                width=max(wait_right - wait_left, 1.0),
                label=f"{label} waits {_safe_float(row.get('queue_wait_minutes')):.0f}m",
            )
        )
        handoffs.append(
            _handoff(
                left=service_left,
                top_a=LANES["queue"] + queue_offset + 13,
                top_b=LANES[role] + service_offset,
            )
        )
        bars.append(
            _bar(
                css_class=f"service {role}",
                top=LANES[role] + service_offset,
                left=service_left,
                width=max(service_right - service_left, 1.0),
                label=f"{label} with {worker} for {_safe_float(row.get('service_minutes')):.0f}m",
            )
        )
    ticks = _ticks(start_day, end_day, start_minute, span)

    st.html(
        f"""
<style>
  .timeline {{
    position: relative; height: 392px; border: 1px solid #d9e0e8; border-radius: 8px;
    background: #ffffff; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  }}
  .legend {{display:flex; gap:12px; font-size:12px; margin: 0 0 8px 2px; color:#475569;}}
  .swatch {{display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px;}}
  .axis {{position:absolute; left:{AXIS_LEFT}%; right:{100 - AXIS_RIGHT}%; top:26px; height:1px; background:#ccd6e2;}}
  .tick {{position:absolute; top:18px; width:1px; height:12px; background:#94a3b8;}}
  .tick-label {{position:absolute; top:4px; transform:translateX(-50%); font-size:10px; color:#64748b; white-space:nowrap;}}
  .playhead {{
    position:absolute; top:26px; bottom:22px; width:2px; background:#111827; opacity:.75;
    animation: sweep 12s linear infinite; z-index:4;
  }}
  @keyframes sweep {{0% {{left:{AXIS_LEFT}%}} 100% {{left:{AXIS_RIGHT}%}}}}
  .lane-label {{position:absolute; left:14px; width:18%; font-weight:700; color:#334155; font-size:13px;}}
  .lane-note {{display:block; font-weight:500; color:#64748b; font-size:10px; margin-top:2px; line-height:1.2;}}
  .lane-line {{position:absolute; left:{AXIS_LEFT}%; right:{100 - AXIS_RIGHT}%; height:1px; background:#edf2f7;}}
  .bar {{
    position:absolute; height:13px; border-radius:7px; color:white; font-size:10px; line-height:13px;
    padding-left:5px; overflow:hidden; white-space:nowrap; z-index:2; box-sizing:border-box;
  }}
  .handoff {{
    position:absolute; width:1px; border-left:1px dotted #94a3b8; opacity:.72; z-index:1;
  }}
  .wait {{background:#f59e0b; opacity:.88;}}
  .wait.long {{background:#dc2626;}}
  .wait.short {{background:#eab308;}}
  .service.technician {{background:#0f766e;}}
  .service.junior {{background:#2563eb;}}
  .service.senior {{background:#7c3aed;}}
  @media (prefers-reduced-motion: reduce) {{
    .playhead {{animation: none; left:{AXIS_LEFT}%;}}
  }}
</style>
<div class="legend">
  <span><i class="swatch" style="background:#dc2626"></i>long queue wait</span>
  <span><i class="swatch" style="background:#0f766e"></i>technician/MMPT/CPT service</span>
  <span><i class="swatch" style="background:#2563eb"></i>junior service</span>
  <span><i class="swatch" style="background:#7c3aed"></i>senior service</span>
</div>
<div class="timeline">
  <div class="axis"></div>
  <div class="playhead"></div>
  {''.join(ticks)}
  <div class="lane-label" style="top:52px">Task queue<span class="lane-note">patient task waiting</span></div>
  <div class="lane-label" style="top:118px">Technician<span class="lane-note">MMPT / CPT work</span></div>
  <div class="lane-label" style="top:184px">Junior<span class="lane-note">pharmacist work</span></div>
  <div class="lane-label" style="top:250px">Senior<span class="lane-note">clinical / writing work</span></div>
  <div class="lane-line" style="top:104px"></div>
  <div class="lane-line" style="top:170px"></div>
  <div class="lane-line" style="top:236px"></div>
  <div class="lane-line" style="top:302px"></div>
  {''.join(handoffs)}
  {''.join(bars)}
</div>
"""
    )


def _pct(value, start_minute: float, span: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = start_minute
    clamped = min(max(numeric, start_minute), start_minute + span)
    return AXIS_LEFT + ((clamped - start_minute) / span) * (AXIS_RIGHT - AXIS_LEFT)


def _role_lane(role: object) -> str:
    text = str(role or "").lower()
    if text in {"senior"}:
        return "senior"
    if text in {"junior"}:
        return "junior"
    return "technician"


def _wait_class(value) -> str:
    minutes = _safe_float(value)
    if minutes >= 240:
        return "long"
    if minutes <= 60:
        return "short"
    return ""


def _bar(*, css_class: str, top: float, left: float, width: float, label: str) -> str:
    safe_label = html.escape(label)
    safe_title = html.escape(label, quote=True)
    return (
        f'<div class="bar {css_class}" title="{safe_title}" '
        f'style="top:{top}px; left:{left:.2f}%; width:{width:.2f}%">{safe_label}</div>'
    )


def _handoff(*, left: float, top_a: float, top_b: float) -> str:
    top = min(top_a, top_b)
    height = max(abs(top_b - top_a), 12)
    return f'<div class="handoff" style="left:{left:.2f}%; top:{top:.1f}px; height:{height:.1f}px"></div>'


def _ticks(start_day: int, end_day: int, start_minute: int, span: int) -> list[str]:
    tick_days = sorted({start_day, (start_day + end_day) // 2, end_day + 1})
    result = []
    for day in tick_days:
        left = _pct(day * 1440, start_minute, span)
        result.append(
            f'<div class="tick" style="left:{left:.2f}%"></div>'
            f'<div class="tick-label" style="left:{left:.2f}%">day {day}</div>'
        )
    return result


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
