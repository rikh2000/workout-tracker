from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from database import get_connection

router = APIRouter(prefix="/exercises")
templates = Jinja2Templates(directory="templates")

CATEGORIES = ["push", "pull", "legs", "core", "other"]
TYPES = ["reps", "timed"]


@router.get("", response_class=HTMLResponse)
def exercise_list(request: Request):
    conn = get_connection()
    exercises = conn.execute("SELECT * FROM exercises ORDER BY category, name").fetchall()
    conn.close()
    return templates.TemplateResponse("exercises/list.html", {
        "request": request,
        "exercises": exercises,
        "categories": CATEGORIES,
        "types": TYPES
    })


@router.post("/add", response_class=HTMLResponse)
def add_exercise(
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    notes: str = Form("")
):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO exercises (name, category, type, notes) VALUES (?, ?, ?, ?)",
            (name.strip(), category, type, notes.strip())
        )
        conn.commit()
        exercises = conn.execute("SELECT * FROM exercises ORDER BY category, name").fetchall()
        conn.close()
        return templates.TemplateResponse("exercises/partials/exercise_table.html", {
            "request": request,
            "exercises": exercises
        })
    except Exception as e:
        conn.close()
        return HTMLResponse(f'<p class="error">Error: {e}</p>', status_code=400)


@router.delete("/{exercise_id}", response_class=HTMLResponse)
def delete_exercise(request: Request, exercise_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM exercises WHERE id = ?", (exercise_id,))
    conn.commit()
    exercises = conn.execute("SELECT * FROM exercises ORDER BY category, name").fetchall()
    conn.close()
    return templates.TemplateResponse("exercises/partials/exercise_table.html", {
        "request": request,
        "exercises": exercises
    })


@router.get("/{exercise_id}/edit", response_class=HTMLResponse)
def edit_exercise_form(request: Request, exercise_id: int):
    conn = get_connection()
    exercise = conn.execute(
        "SELECT * FROM exercises WHERE id = ?", (exercise_id,)
    ).fetchone()
    conn.close()
    if not exercise:
        return HTMLResponse("Exercise not found", status_code=404)
    return templates.TemplateResponse("exercises/edit.html", {
        "request": request,
        "exercise": exercise,
        "categories": CATEGORIES,
        "types": TYPES
    })


@router.post("/{exercise_id}/edit", response_class=HTMLResponse)
def save_exercise_edit(
    request: Request,
    exercise_id: int,
    name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    notes: str = Form("")
):
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE exercises
            SET name = ?, category = ?, type = ?, notes = ?
            WHERE id = ?
        """, (name.strip(), category, type, notes.strip(), exercise_id))
        conn.commit()
        conn.close()
        return RedirectResponse(url="/exercises", status_code=303)
    except Exception as e:
        conn.close()
        return HTMLResponse(f'<p class="error">Error: {e}</p>', status_code=400)