from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse 
from fastapi.templating import Jinja2Templates
from database import get_connection
from typing import Optional

router = APIRouter(prefix="/gym-templates")
templates = Jinja2Templates(directory="templates")


# ── List all templates ────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def template_list(request: Request):
    conn = get_connection()
    gym_templates = conn.execute(
        "SELECT * FROM gym_templates ORDER BY name"
    ).fetchall()
    conn.close()
    return templates.TemplateResponse("gym_templates/list.html", {
        "request": request,
        "gym_templates": gym_templates
    })


# ── Create a new template ─────────────────────────────────────────────────────

@router.post("/add", response_class=HTMLResponse)
def add_template(
    request: Request,
    name: str = Form(...),
    notes: str = Form("")
):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO gym_templates (name, notes) VALUES (?, ?)",
            (name.strip(), notes.strip())
        )
        conn.commit()
        gym_templates = conn.execute(
            "SELECT * FROM gym_templates ORDER BY name"
        ).fetchall()
        conn.close()
        return templates.TemplateResponse("gym_templates/partials/template_table.html", {
            "request": request,
            "gym_templates": gym_templates
        })
    except Exception as e:
        conn.close()
        return HTMLResponse(f'<p class="error">Error: {e}</p>', status_code=400)


# ── Delete a template ─────────────────────────────────────────────────────────

@router.delete("/{template_id}", response_class=HTMLResponse)
def delete_template(request: Request, template_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM gym_templates WHERE id = ?", (template_id,))
    conn.commit()
    gym_templates = conn.execute(
        "SELECT * FROM gym_templates ORDER BY name"
    ).fetchall()
    conn.close()
    return templates.TemplateResponse("gym_templates/partials/template_table.html", {
        "request": request,
        "gym_templates": gym_templates,
    })


# ── Template detail page (exercises within a template) ────────────────────────

@router.get("/{template_id}", response_class=HTMLResponse)
def template_detail(request: Request, template_id: int):
    conn = get_connection()
    template = conn.execute(
        "SELECT * FROM gym_templates WHERE id = ?", (template_id,)
    ).fetchone()
    if not template:
        conn.close()
        return HTMLResponse("Template not found", status_code=404)
    exercises_in_template = conn.execute("""
        SELECT gte.*, e.name as exercise_name, e.type as exercise_type
        FROM gym_template_exercises gte
        JOIN exercises e ON e.id = gte.exercise_id
        WHERE gte.template_id = ?
        ORDER BY gte.order_index
    """, (template_id,)).fetchall()
    all_exercises = conn.execute(
        "SELECT * FROM exercises ORDER BY category, name"
    ).fetchall()
    conn.close()
    return templates.TemplateResponse("gym_templates/detail.html", {
        "request": request,
        "template": template,
        "exercises_in_template": exercises_in_template,
        "all_exercises": all_exercises,
        "template_id": template_id    # add this line
    })


# ── Add an exercise to a template ─────────────────────────────────────────────

@router.post("/{template_id}/add-exercise", response_class=HTMLResponse)
def add_exercise_to_template(
    request: Request,
    template_id: int,
    exercise_id: int = Form(...),
    target_sets: int = Form(...),
    target_reps: Optional[int] = Form(None),
    target_seconds: Optional[int] = Form(None),
    target_rpe: Optional[float] = Form(None),
    target_rir: Optional[int] = Form(None),
    target_weight_kg: Optional[float] = Form(None),    # fix: float not int
    notes: str = Form("")
):
    conn = get_connection()
    max_order = conn.execute(
        "SELECT MAX(order_index) FROM gym_template_exercises WHERE template_id = ?",
        (template_id,)
    ).fetchone()[0]
    next_order = (max_order or 0) + 1

    conn.execute("""
        INSERT INTO gym_template_exercises
            (template_id, exercise_id, order_index, target_sets,
             target_reps, target_seconds, target_rpe, target_rir, target_weight_kg, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (template_id, exercise_id, next_order, target_sets,
          target_reps, target_seconds, target_rpe, target_rir, target_weight_kg, notes.strip()))
    conn.commit()

    exercises_in_template = conn.execute("""
        SELECT gte.*, e.name as exercise_name, e.type as exercise_type
        FROM gym_template_exercises gte
        JOIN exercises e ON e.id = gte.exercise_id
        WHERE gte.template_id = ?
        ORDER BY gte.order_index
    """, (template_id,)).fetchall()
    conn.close()
    return templates.TemplateResponse("gym_templates/partials/exercise_list.html", {
        "request": request,
        "exercises_in_template": exercises_in_template,
        "template_id": template_id
    })


# ── Remove an exercise from a template ────────────────────────────────────────

@router.delete("/{template_id}/exercises/{entry_id}", response_class=HTMLResponse)
def remove_exercise_from_template(
    request: Request,
    template_id: int,
    entry_id: int
):
    conn = get_connection()
    conn.execute(
        "DELETE FROM gym_template_exercises WHERE id = ?", (entry_id,)
    )
    conn.commit()
    exercises_in_template = conn.execute("""
        SELECT gte.*, e.name as exercise_name, e.type as exercise_type
        FROM gym_template_exercises gte
        JOIN exercises e ON e.id = gte.exercise_id
        WHERE gte.template_id = ?
        ORDER BY gte.order_index
    """, (template_id,)).fetchall()
    conn.close()
    return templates.TemplateResponse("gym_templates/partials/exercise_list.html", {
        "request": request,
        "exercises_in_template": exercises_in_template,
        "template_id": template_id
    })


@router.post("/{template_id}/reorder", response_class=HTMLResponse)
async def reorder_exercises(request: Request, template_id: int):
    data = await request.json()
    ordered_ids = data.get("ordered_ids", [])
    conn = get_connection()
    for index, entry_id in enumerate(ordered_ids):
        conn.execute(
            "UPDATE gym_template_exercises SET order_index = ? WHERE id = ?",
            (index, entry_id)
        )
    conn.commit()
    conn.close()
    return HTMLResponse("OK")