from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import get_connection
from typing import Optional

router = APIRouter(prefix="/log/gym")
templates = Jinja2Templates(directory="templates")


# ── Start logging a gym workout (pre-fill from template if given) ─────────────

@router.get("/new", response_class=HTMLResponse)
def new_gym_log(request: Request, template_id: Optional[int] = None):
    conn = get_connection()
    template = None
    prefilled_exercises = []

    if template_id:
        template = conn.execute(
            "SELECT * FROM gym_templates WHERE id = ?", (template_id,)
        ).fetchone()
        prefilled_exercises = conn.execute("""
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

    from datetime import date
    return templates.TemplateResponse("completed_gym/log.html", {
        "request": request,
        "template": template,
        "prefilled_exercises": prefilled_exercises,
        "all_exercises": all_exercises,
        "today": date.today().isoformat()
    })


# ── Save a completed gym workout ──────────────────────────────────────────────

@router.post("/save", response_class=HTMLResponse)
async def save_gym_log(request: Request):
    form = await request.form()

    date = form.get("date")
    gym_template_id = form.get("gym_template_id") or None
    notes = form.get("notes", "").strip()

    # parse exercises and sets from form
    # form fields are named like:
    #   exercise_id_0, set_count_0, weight_0_0, reps_0_0, notes_0_0
    #   exercise_id_1, set_count_1, weight_1_0, reps_1_0, notes_1_0, weight_1_1 ...

    exercises = []
    i = 0
    while f"exercise_id_{i}" in form:
        exercise_id = int(form[f"exercise_id_{i}"])
        set_count = int(form.get(f"set_count_{i}", 1))
        sets = []
        for s in range(set_count):
            sets.append({
                "set_number": s + 1,
                "weight_kg": float(form[f"weight_{i}_{s}"]) if form.get(f"weight_{i}_{s}") else None,
                "reps": int(form[f"reps_{i}_{s}"]) if form.get(f"reps_{i}_{s}") else None,
                "seconds": int(form[f"seconds_{i}_{s}"]) if form.get(f"seconds_{i}_{s}") else None,
                "notes": form.get(f"set_notes_{i}_{s}", "").strip()
            })
        exercises.append({
            "exercise_id": exercise_id,
            "order_index": i,
            "sets": sets
        })
        i += 1

    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO completed_gym_workouts (date, gym_template_id, notes) VALUES (?, ?, ?)",
        (date, gym_template_id, notes)
    )
    workout_id = cursor.lastrowid

    for ex in exercises:
        for s in ex["sets"]:
            conn.execute("""
                INSERT INTO completed_gym_sets
                    (workout_id, exercise_id, order_index, set_number,
                     reps, seconds, weight_kg, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (workout_id, ex["exercise_id"], ex["order_index"],
                  s["set_number"], s["reps"], s["seconds"],
                  s["weight_kg"], s["notes"]))

    conn.commit()
    conn.close()

    return RedirectResponse(url="/log/gym", status_code=303)


# ── List completed gym workouts ───────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def list_gym_logs(request: Request):
    conn = get_connection()
    workouts = conn.execute("""
        SELECT cgw.*, gt.name as template_name
        FROM completed_gym_workouts cgw
        LEFT JOIN gym_templates gt ON gt.id = cgw.gym_template_id
        ORDER BY cgw.date DESC
    """).fetchall()
    conn.close()
    return templates.TemplateResponse("completed_gym/list.html", {
        "request": request,
        "workouts": workouts
    })


# ── View a completed gym workout ──────────────────────────────────────────────

@router.get("/{workout_id}", response_class=HTMLResponse)
def view_gym_log(request: Request, workout_id: int):
    conn = get_connection()
    workout = conn.execute("""
        SELECT cgw.*, gt.name as template_name
        FROM completed_gym_workouts cgw
        LEFT JOIN gym_templates gt ON gt.id = cgw.gym_template_id
        WHERE cgw.id = ?
    """, (workout_id,)).fetchone()
    if not workout:
        conn.close()
        return HTMLResponse("Workout not found", status_code=404)
    sets = conn.execute("""
        SELECT cgs.*, e.name as exercise_name, e.type as exercise_type
        FROM completed_gym_sets cgs
        JOIN exercises e ON e.id = cgs.exercise_id
        WHERE cgs.workout_id = ?
        ORDER BY cgs.order_index, cgs.set_number
    """, (workout_id,)).fetchall()
    conn.close()

    # group sets by exercise
    exercises = {}
    for s in sets:
        key = (s["order_index"], s["exercise_name"])
        if key not in exercises:
            exercises[key] = {"name": s["exercise_name"], "type": s["exercise_type"], "sets": []}
        exercises[key]["sets"].append(s)

    return templates.TemplateResponse("completed_gym/view.html", {
        "request": request,
        "workout": workout,
        "exercises": list(exercises.values())
    })

@router.delete("/{workout_id}", response_class=HTMLResponse)
def delete_gym_log(request: Request, workout_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM completed_gym_workouts WHERE id = ?", (workout_id,))
    conn.commit()
    workouts = conn.execute("""
        SELECT cgw.*, gt.name as template_name
        FROM completed_gym_workouts cgw
        LEFT JOIN gym_templates gt ON gt.id = cgw.gym_template_id
        ORDER BY cgw.date DESC
    """).fetchall()
    conn.close()
    return templates.TemplateResponse("completed_gym/partials/workout_table.html", {
        "request": request,
        "workouts": workouts
    })