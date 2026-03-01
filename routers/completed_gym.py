from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import get_connection
from typing import Optional

router = APIRouter(prefix="/log/gym")
templates = Jinja2Templates(directory="templates")


# ── Start logging a gym workout (pre-fill from template if given) ─────────────

@router.get("/new", response_class=HTMLResponse)
def new_gym_log(request: Request, template_id: Optional[int] = None, date: Optional[str] = None):
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
        "SELECT * FROM exercises ORDER BY name"
    ).fetchall()

    all_gym_templates = conn.execute(
        "SELECT * FROM gym_templates ORDER BY name"
    ).fetchall()
    gym_templates_data = []
    for t in all_gym_templates:
        exs = conn.execute("""
            SELECT gte.*, e.name as exercise_name, e.type as exercise_type
            FROM gym_template_exercises gte
            JOIN exercises e ON e.id = gte.exercise_id
            WHERE gte.template_id = ?
            ORDER BY gte.order_index
        """, (t["id"],)).fetchall()
        gym_templates_data.append({
            "id": t["id"],
            "name": t["name"],
            "exercises": [dict(ex) for ex in exs]
        })

    conn.close()

    from datetime import date as date_mod
    return templates.TemplateResponse("completed_gym/log.html", {
        "request": request,
        "template": template,
        "prefilled_exercises": prefilled_exercises,
        "all_exercises": all_exercises,
        "gym_templates": gym_templates_data,
        "today": date or date_mod.today().isoformat()
    })


# ── Save a completed gym workout ──────────────────────────────────────────────

@router.post("/save", response_class=HTMLResponse)
async def save_gym_log(request: Request):
    form = await request.form()

    date = form.get("date")
    gym_template_id = form.get("gym_template_id") or None
    notes = form.get("notes", "").strip()

    # Collect exercise indices present in the form — handles gaps from deleted exercises
    form_keys = set(form.keys())
    all_exercise_indices = sorted(
        int(k[len("exercise_id_"):])
        for k in form_keys
        if k.startswith("exercise_id_") and k[len("exercise_id_"):].isdigit()
    )

    # Respect user-defined order if provided (from ↑/↓ reordering)
    order_str = form.get("exercise_order", "").strip()
    if order_str:
        ordered = [int(x) for x in order_str.split(",") if x.isdigit()]
        # keep only indices that exist, append any missing ones at the end
        seen = set(ordered)
        exercise_indices = [i for i in ordered if i in set(all_exercise_indices)]
        exercise_indices += [i for i in all_exercise_indices if i not in seen]
    else:
        exercise_indices = all_exercise_indices

    exercises = []
    for order_idx, i in enumerate(exercise_indices):
        exercise_id = int(form[f"exercise_id_{i}"])
        # Collect set indices present — handles gaps from deleted sets
        prefix = f"weight_{i}_"
        set_indices = sorted(
            int(k[len(prefix):])
            for k in form.keys()
            if k.startswith(prefix) and k[len(prefix):].isdigit()
        )
        sets = []
        for s in set_indices:
            sets.append({
                "set_number": len(sets) + 1,
                "weight_kg": float(form[f"weight_{i}_{s}"]) if form.get(f"weight_{i}_{s}") else None,
                "reps": int(form[f"reps_{i}_{s}"]) if form.get(f"reps_{i}_{s}") else None,
                "seconds": int(form[f"seconds_{i}_{s}"]) if form.get(f"seconds_{i}_{s}") else None,
                "notes": form.get(f"set_notes_{i}_{s}", "").strip()
            })
        exercises.append({
            "exercise_id": exercise_id,
            "order_index": order_idx,
            "sets": sets
        })

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

    return RedirectResponse(url="/log", status_code=303)


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

@router.post("/{workout_id}/delete", response_class=HTMLResponse)
def delete_gym_log_from_calendar(
    request: Request,
    workout_id: int,
    redirect_view: str = Form("month"),
    redirect_year: int = Form(...),
    redirect_month: int = Form(...),
    redirect_day: int = Form(...),
):
    conn = get_connection()
    conn.execute("DELETE FROM completed_gym_workouts WHERE id = ?", (workout_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(
        url=f"/schedule?view={redirect_view}&year={redirect_year}&month={redirect_month}&day={redirect_day}",
        status_code=303
    )


@router.get("/{workout_id}/edit", response_class=HTMLResponse)
def edit_gym_log(request: Request, workout_id: int):
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
    all_exercises = conn.execute(
        "SELECT * FROM exercises ORDER BY name"
    ).fetchall()
    conn.close()

    exercises = {}
    for s in sets:
        key = (s["order_index"], s["exercise_id"])
        if key not in exercises:
            exercises[key] = {
                "exercise_id": s["exercise_id"],
                "exercise_name": s["exercise_name"],
                "exercise_type": s["exercise_type"],
                "sets": []
            }
        exercises[key]["sets"].append(s)

    return templates.TemplateResponse("completed_gym/edit.html", {
        "request": request,
        "workout": workout,
        "exercises": list(exercises.values()),
        "all_exercises": all_exercises,
    })


@router.post("/{workout_id}/update", response_class=HTMLResponse)
async def update_gym_log(request: Request, workout_id: int):
    form = await request.form()

    date = form.get("date")
    gym_template_id = form.get("gym_template_id") or None
    notes = form.get("notes", "").strip()

    form_keys = set(form.keys())
    all_exercise_indices = sorted(
        int(k[len("exercise_id_"):])
        for k in form_keys
        if k.startswith("exercise_id_") and k[len("exercise_id_"):].isdigit()
    )

    order_str = form.get("exercise_order", "").strip()
    if order_str:
        ordered = [int(x) for x in order_str.split(",") if x.isdigit()]
        seen = set(ordered)
        exercise_indices = [i for i in ordered if i in set(all_exercise_indices)]
        exercise_indices += [i for i in all_exercise_indices if i not in seen]
    else:
        exercise_indices = all_exercise_indices

    exercises = []
    for order_idx, i in enumerate(exercise_indices):
        exercise_id = int(form[f"exercise_id_{i}"])
        prefix = f"weight_{i}_"
        set_indices = sorted(
            int(k[len(prefix):])
            for k in form.keys()
            if k.startswith(prefix) and k[len(prefix):].isdigit()
        )
        sets = []
        for s in set_indices:
            sets.append({
                "set_number": len(sets) + 1,
                "weight_kg": float(form[f"weight_{i}_{s}"]) if form.get(f"weight_{i}_{s}") else None,
                "reps": int(form[f"reps_{i}_{s}"]) if form.get(f"reps_{i}_{s}") else None,
                "seconds": int(form[f"seconds_{i}_{s}"]) if form.get(f"seconds_{i}_{s}") else None,
                "notes": form.get(f"set_notes_{i}_{s}", "").strip()
            })
        exercises.append({"exercise_id": exercise_id, "order_index": order_idx, "sets": sets})

    conn = get_connection()
    conn.execute(
        "UPDATE completed_gym_workouts SET date=?, gym_template_id=?, notes=? WHERE id=?",
        (date, gym_template_id, notes, workout_id)
    )
    conn.execute("DELETE FROM completed_gym_sets WHERE workout_id=?", (workout_id,))
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

    return RedirectResponse(url=f"/log/gym/{workout_id}", status_code=303)


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