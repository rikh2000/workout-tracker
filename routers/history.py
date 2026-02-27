from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from database import get_connection
from typing import Optional

router = APIRouter(prefix="/history")
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
def history_index(request: Request, exercise_id: Optional[int] = None):
    conn = get_connection()
    all_exercises = conn.execute(
        "SELECT * FROM exercises ORDER BY category, name"
    ).fetchall()

    exercise = None
    sessions_serialisable = []

    if exercise_id:
        exercise = conn.execute(
            "SELECT * FROM exercises WHERE id = ?", (exercise_id,)
        ).fetchone()

        rows = conn.execute("""
            SELECT
                cgw.date,
                cgs.set_number,
                cgs.reps,
                cgs.seconds,
                cgs.weight_kg,
                cgs.notes,
                cgw.id as workout_id
            FROM completed_gym_sets cgs
            JOIN completed_gym_workouts cgw ON cgw.id = cgs.workout_id
            WHERE cgs.exercise_id = ?
            ORDER BY cgw.date ASC, cgs.set_number ASC
        """, (exercise_id,)).fetchall()

        # group by date/workout
        sessions_dict = {}
        for row in rows:
            key = (row["date"], row["workout_id"])
            if key not in sessions_dict:
                sessions_dict[key] = {
                    "date": row["date"],
                    "workout_id": row["workout_id"],
                    "sets": []
                }
            sessions_dict[key]["sets"].append(row)

        # compute best weight per session
        for session in sessions_dict.values():
            weights = [s["weight_kg"] for s in session["sets"] if s["weight_kg"]]
            session["best_weight"] = max(weights) if weights else None

        # convert to plain dicts for JSON serialisation
        sessions_serialisable = [
            {
                "date": s["date"],
                "workout_id": s["workout_id"],
                "best_weight": s["best_weight"],
                "sets": [
                    {
                        "set_number": row["set_number"],
                        "reps": row["reps"],
                        "seconds": row["seconds"],
                        "weight_kg": row["weight_kg"],
                        "notes": row["notes"]
                    }
                    for row in s["sets"]
                ]
            }
            for s in sessions_dict.values()
        ]

    conn.close()
    return templates.TemplateResponse("history/index.html", {
        "request": request,
        "all_exercises": all_exercises,
        "exercise": exercise,
        "sessions": sessions_serialisable,
        "exercise_id": exercise_id
    })