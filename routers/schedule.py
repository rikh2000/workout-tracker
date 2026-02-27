from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from database import get_connection
from typing import Optional
from datetime import date

router = APIRouter(prefix="/schedule")
templates = Jinja2Templates(directory="templates")


# ── Schedule overview ─────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def schedule_view(request: Request):
    conn = get_connection()
    scheduled = conn.execute("""
        SELECT
            sw.*,
            gt.name as gym_template_name,
            rt.name as run_template_name
        FROM scheduled_workouts sw
        LEFT JOIN gym_templates gt ON gt.id = sw.gym_template_id
        LEFT JOIN run_templates rt ON rt.id = sw.run_template_id
        ORDER BY sw.date ASC
    """).fetchall()
    gym_templates = conn.execute(
        "SELECT * FROM gym_templates ORDER BY name"
    ).fetchall()
    run_templates = conn.execute(
        "SELECT * FROM run_templates ORDER BY name"
    ).fetchall()
    conn.close()
    return templates.TemplateResponse("schedule/list.html", {
        "request": request,
        "scheduled": scheduled,
        "gym_templates": gym_templates,
        "run_templates": run_templates,
        "today": date.today().isoformat()
    })


# ── Add a scheduled workout ───────────────────────────────────────────────────

@router.post("/add", response_class=HTMLResponse)
def add_scheduled(
    request: Request,
    date: str = Form(...),
    workout_type: str = Form(...),
    gym_template_id: Optional[int] = Form(None),
    run_template_id: Optional[int] = Form(None),
    notes: str = Form("")
):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO scheduled_workouts
                (date, workout_type, gym_template_id, run_template_id, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (date, workout_type,
              gym_template_id if workout_type == "gym" else None,
              run_template_id if workout_type == "run" else None,
              notes.strip()))
        conn.commit()
        scheduled = conn.execute("""
            SELECT
                sw.*,
                gt.name as gym_template_name,
                rt.name as run_template_name
            FROM scheduled_workouts sw
            LEFT JOIN gym_templates gt ON gt.id = sw.gym_template_id
            LEFT JOIN run_templates rt ON rt.id = sw.run_template_id
            ORDER BY sw.date ASC
        """).fetchall()
        conn.close()
        return templates.TemplateResponse("schedule/partials/schedule_table.html", {
            "request": request,
            "scheduled": scheduled
        })
    except Exception as e:
        conn.close()
        return HTMLResponse(f'<p class="error">Error: {e}</p>', status_code=400)


# ── Delete a scheduled workout ────────────────────────────────────────────────

@router.delete("/{scheduled_id}", response_class=HTMLResponse)
def delete_scheduled(request: Request, scheduled_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM scheduled_workouts WHERE id = ?", (scheduled_id,))
    conn.commit()
    scheduled = conn.execute("""
        SELECT
            sw.*,
            gt.name as gym_template_name,
            rt.name as run_template_name
        FROM scheduled_workouts sw
        LEFT JOIN gym_templates gt ON gt.id = sw.gym_template_id
        LEFT JOIN run_templates rt ON rt.id = sw.run_template_id
        ORDER BY sw.date ASC
    """).fetchall()
    conn.close()
    return templates.TemplateResponse("schedule/partials/schedule_table.html", {
        "request": request,
        "scheduled": scheduled
    })