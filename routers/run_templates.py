from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from database import get_connection
from typing import Optional

router = APIRouter(prefix="/run-templates")
templates = Jinja2Templates(directory="templates")

RUN_TYPES = ["intervals", "tempo", "steady_state", "endurance", "recovery"]
SEGMENT_TYPES = ["warmup", "work", "recovery", "cooldown"]


# ── List all templates ────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def template_list(request: Request):
    conn = get_connection()
    run_templates = conn.execute(
        "SELECT * FROM run_templates ORDER BY name"
    ).fetchall()
    conn.close()
    return templates.TemplateResponse("run_templates/list.html", {
        "request": request,
        "run_templates": run_templates,
        "run_types": RUN_TYPES
    })


# ── Create a new template ─────────────────────────────────────────────────────

@router.post("/add", response_class=HTMLResponse)
def add_template(
    request: Request,
    name: str = Form(...),
    run_type: str = Form(...),
    notes: str = Form("")
):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO run_templates (name, run_type, notes) VALUES (?, ?, ?)",
            (name.strip(), run_type, notes.strip())
        )
        conn.commit()
        run_templates = conn.execute(
            "SELECT * FROM run_templates ORDER BY name"
        ).fetchall()
        conn.close()
        return templates.TemplateResponse("run_templates/partials/template_table.html", {
            "request": request,
            "run_templates": run_templates
        })
    except Exception as e:
        conn.close()
        return HTMLResponse(f'<p class="error">Error: {e}</p>', status_code=400)


# ── Delete a template ─────────────────────────────────────────────────────────

@router.delete("/{template_id}", response_class=HTMLResponse)
def delete_template(request: Request, template_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM run_templates WHERE id = ?", (template_id,))
    conn.commit()
    run_templates = conn.execute(
        "SELECT * FROM run_templates ORDER BY name"
    ).fetchall()
    conn.close()
    return templates.TemplateResponse("run_templates/partials/template_table.html", {
        "request": request,
        "run_templates": run_templates
    })


# ── Template detail page ──────────────────────────────────────────────────────

@router.get("/{template_id}", response_class=HTMLResponse)
def template_detail(request: Request, template_id: int):
    conn = get_connection()
    template = conn.execute(
        "SELECT * FROM run_templates WHERE id = ?", (template_id,)
    ).fetchone()
    if not template:
        conn.close()
        return HTMLResponse("Template not found", status_code=404)
    segments = conn.execute("""
        SELECT * FROM run_template_segments
        WHERE template_id = ?
        ORDER BY order_index
    """, (template_id,)).fetchall()
    conn.close()
    return templates.TemplateResponse("run_templates/detail.html", {
        "request": request,
        "template": template,
        "segments": segments,
        "segment_types": SEGMENT_TYPES,
        "template_id": template_id
    })


# ── Add a segment to a template ───────────────────────────────────────────────

@router.post("/{template_id}/add-segment", response_class=HTMLResponse)
def add_segment(
    request: Request,
    template_id: int,
    segment_type: str = Form(...),
    duration_minutes: Optional[int] = Form(None),
    duration_seconds: Optional[int] = Form(None),
    distance_value: Optional[float] = Form(None),
    distance_unit: str = Form("km"),
    pace_minutes: Optional[int] = Form(None),
    pace_seconds: Optional[int] = Form(None),
    target_rpe: Optional[float] = Form(None),
    notes: str = Form("")
):
    # convert duration to total seconds
    total_duration = None
    if duration_minutes or duration_seconds:
        total_duration = (duration_minutes or 0) * 60 + (duration_seconds or 0)

    # convert distance to meters
    total_distance = None
    if distance_value:
        total_distance = distance_value * 1000 if distance_unit == "km" else distance_value

    # convert pace to decimal min/km
    pace = None
    if pace_minutes or pace_seconds:
        pace = (pace_minutes or 0) + (pace_seconds or 0) / 60

    conn = get_connection()
    max_order = conn.execute(
        "SELECT MAX(order_index) FROM run_template_segments WHERE template_id = ?",
        (template_id,)
    ).fetchone()[0]
    next_order = (max_order or 0) + 1

    conn.execute("""
        INSERT INTO run_template_segments
            (template_id, order_index, segment_type,
             target_duration_seconds, target_distance_meters,
             target_pace_min_per_km, target_rpe, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (template_id, next_order, segment_type,
          total_duration, total_distance, pace, target_rpe, notes.strip()))
    conn.commit()

    segments = conn.execute("""
        SELECT * FROM run_template_segments
        WHERE template_id = ?
        ORDER BY order_index
    """, (template_id,)).fetchall()
    conn.close()
    return templates.TemplateResponse("run_templates/partials/segment_list.html", {
        "request": request,
        "segments": segments,
        "template_id": template_id
    })


# ── Remove a segment ──────────────────────────────────────────────────────────

@router.delete("/{template_id}/segments/{segment_id}", response_class=HTMLResponse)
def remove_segment(request: Request, template_id: int, segment_id: int):
    conn = get_connection()
    conn.execute(
        "DELETE FROM run_template_segments WHERE id = ?", (segment_id,)
    )
    conn.commit()
    segments = conn.execute("""
        SELECT * FROM run_template_segments
        WHERE template_id = ?
        ORDER BY order_index
    """, (template_id,)).fetchall()
    conn.close()
    return templates.TemplateResponse("run_templates/partials/segment_list.html", {
        "request": request,
        "segments": segments,
        "template_id": template_id
    })


@router.post("/{template_id}/reorder", response_class=HTMLResponse)
async def reorder_segments(request: Request, template_id: int):
    data = await request.json()
    ordered_ids = data.get("ordered_ids", [])
    conn = get_connection()
    for index, segment_id in enumerate(ordered_ids):
        conn.execute(
            "UPDATE run_template_segments SET order_index = ? WHERE id = ?",
            (index, segment_id)
        )
    conn.commit()
    conn.close()
    return HTMLResponse("OK")