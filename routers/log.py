from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from database import get_connection

router = APIRouter(prefix="/log")
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
def log_list(request: Request):
    conn = get_connection()
    gym_rows = conn.execute("""
        SELECT cgw.id, cgw.date, cgw.notes, gt.name as template_name
        FROM completed_gym_workouts cgw
        LEFT JOIN gym_templates gt ON gt.id = cgw.gym_template_id
        ORDER BY cgw.date DESC
    """).fetchall()
    run_rows = conn.execute("""
        SELECT crw.id, crw.date, crw.notes, crw.run_type,
               crw.total_distance_meters, crw.total_duration_seconds,
               rt.name as template_name
        FROM completed_run_workouts crw
        LEFT JOIN run_templates rt ON rt.id = crw.run_template_id
        ORDER BY crw.date DESC
    """).fetchall()
    conn.close()

    workouts = []
    for w in gym_rows:
        workouts.append({**dict(w), "workout_type": "gym",
                         "run_type": None, "total_distance_meters": None,
                         "total_duration_seconds": None})
    for w in run_rows:
        workouts.append({**dict(w), "workout_type": "run"})

    workouts.sort(key=lambda x: x["date"], reverse=True)

    return templates.TemplateResponse("log/list.html", {
        "request": request,
        "workouts": workouts,
    })
