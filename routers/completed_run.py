from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import get_connection
from typing import Optional

router = APIRouter(prefix="/log/run")
templates = Jinja2Templates(directory="templates")

SEGMENT_TYPES = ["warmup", "work", "recovery", "cooldown"]


# ── Start logging a run workout ───────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
def new_run_log(request: Request, template_id: Optional[int] = None):
    conn = get_connection()
    template = None
    prefilled_segments = []

    if template_id:
        template = conn.execute(
            "SELECT * FROM run_templates WHERE id = ?", (template_id,)
        ).fetchone()
        prefilled_segments = conn.execute("""
            SELECT * FROM run_template_segments
            WHERE template_id = ?
            ORDER BY order_index
        """, (template_id,)).fetchall()

    conn.close()

    from datetime import date
    return templates.TemplateResponse("completed_run/log.html", {
        "request": request,
        "template": template,
        "prefilled_segments": prefilled_segments,
        "segment_types": SEGMENT_TYPES,
        "today": date.today().isoformat()
    })


# ── Save a completed run workout ──────────────────────────────────────────────

@router.post("/save", response_class=HTMLResponse)
async def save_run_log(request: Request):
    form = await request.form()

    date = form.get("date")
    run_template_id = form.get("run_template_id") or None
    run_type = form.get("run_type", "endurance")
    notes = form.get("notes", "").strip()
    garmin_activity_id = form.get("garmin_activity_id", "").strip() or None

    # compute totals from segments
    segments = []
    i = 0
    while f"segment_type_{i}" in form:
        dur_min = form.get(f"duration_minutes_{i}")
        dur_sec = form.get(f"duration_seconds_{i}")
        dist_val = form.get(f"distance_value_{i}")
        dist_unit = form.get(f"distance_unit_{i}", "km")
        pace_min = form.get(f"pace_minutes_{i}")
        pace_sec = form.get(f"pace_seconds_{i}")

        total_duration = None
        if dur_min or dur_sec:
            total_duration = (int(dur_min) if dur_min else 0) * 60 + (int(dur_sec) if dur_sec else 0)

        total_distance = None
        if dist_val:
            total_distance = float(dist_val) * 1000 if dist_unit == "km" else float(dist_val)

        pace = None
        if pace_min or pace_sec:
            pace = (int(pace_min) if pace_min else 0) + (int(pace_sec) if pace_sec else 0) / 60

        segments.append({
            "order_index": i,
            "segment_type": form.get(f"segment_type_{i}"),
            "actual_duration_seconds": total_duration,
            "actual_distance_meters": total_distance,
            "actual_pace_min_per_km": pace,
            "actual_rpe": float(form[f"rpe_{i}"]) if form.get(f"rpe_{i}") else None,
            "notes": form.get(f"seg_notes_{i}", "").strip()
        })
        i += 1

    # compute totals
    total_distance = sum(s["actual_distance_meters"] for s in segments if s["actual_distance_meters"])
    total_duration = sum(s["actual_duration_seconds"] for s in segments if s["actual_duration_seconds"])

    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO completed_run_workouts
            (date, run_template_id, run_type, total_distance_meters,
             total_duration_seconds, garmin_activity_id, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (date, run_template_id, run_type,
          total_distance or None, total_duration or None,
          garmin_activity_id, notes))
    workout_id = cursor.lastrowid

    for seg in segments:
        conn.execute("""
            INSERT INTO completed_run_segments
                (workout_id, order_index, segment_type,
                 actual_duration_seconds, actual_distance_meters,
                 actual_pace_min_per_km, actual_rpe, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (workout_id, seg["order_index"], seg["segment_type"],
              seg["actual_duration_seconds"], seg["actual_distance_meters"],
              seg["actual_pace_min_per_km"], seg["actual_rpe"], seg["notes"]))

    conn.commit()
    conn.close()

    return RedirectResponse(url="/log/run", status_code=303)


# ── List completed run workouts ───────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def list_run_logs(request: Request):
    conn = get_connection()
    workouts = conn.execute("""
        SELECT crw.*, rt.name as template_name
        FROM completed_run_workouts crw
        LEFT JOIN run_templates rt ON rt.id = crw.run_template_id
        ORDER BY crw.date DESC
    """).fetchall()
    conn.close()
    return templates.TemplateResponse("completed_run/list.html", {
        "request": request,
        "workouts": workouts
    })


# ── Delete a completed run workout ────────────────────────────────────────────

@router.delete("/{workout_id}", response_class=HTMLResponse)
def delete_run_log(request: Request, workout_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM completed_run_workouts WHERE id = ?", (workout_id,))
    conn.commit()
    workouts = conn.execute("""
        SELECT crw.*, rt.name as template_name
        FROM completed_run_workouts crw
        LEFT JOIN run_templates rt ON rt.id = crw.run_template_id
        ORDER BY crw.date DESC
    """).fetchall()
    conn.close()
    return templates.TemplateResponse("completed_run/partials/workout_table.html", {
        "request": request,
        "workouts": workouts
    })


# ── View a completed run workout ──────────────────────────────────────────────

@router.get("/{workout_id}", response_class=HTMLResponse)
def view_run_log(request: Request, workout_id: int):
    conn = get_connection()
    workout = conn.execute("""
        SELECT crw.*, rt.name as template_name
        FROM completed_run_workouts crw
        LEFT JOIN run_templates rt ON rt.id = crw.run_template_id
        WHERE crw.id = ?
    """, (workout_id,)).fetchone()
    if not workout:
        conn.close()
        return HTMLResponse("Workout not found", status_code=404)
    segments = conn.execute("""
        SELECT * FROM completed_run_segments
        WHERE workout_id = ?
        ORDER BY order_index
    """, (workout_id,)).fetchall()
    conn.close()
    return templates.TemplateResponse("completed_run/view.html", {
        "request": request,
        "workout": workout,
        "segments": segments
    })