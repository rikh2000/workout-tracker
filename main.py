from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from database import init_db, get_connection
from datetime import date, timedelta
from routers import exercises
from routers import gym_templates
from routers import run_templates
from routers import schedule
from routers import completed_gym
from routers import completed_run
from routers import log
from routers import stats

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

app.include_router(exercises.router)
app.include_router(gym_templates.router)
app.include_router(run_templates.router)
app.include_router(schedule.router)
app.include_router(completed_gym.router)
app.include_router(completed_run.router)
app.include_router(log.router)
app.include_router(stats.router)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)             # Sunday

    conn = get_connection()

    # Recent workouts (last 4 of each, then merge and trim)
    gym_rows = conn.execute("""
        SELECT cgw.id, cgw.date, cgw.notes, gt.name as template_name
        FROM completed_gym_workouts cgw
        LEFT JOIN gym_templates gt ON gt.id = cgw.gym_template_id
        ORDER BY cgw.date DESC LIMIT 4
    """).fetchall()
    run_rows = conn.execute("""
        SELECT crw.id, crw.date, crw.notes, crw.run_type,
               crw.total_distance_meters,
               rt.name as template_name
        FROM completed_run_workouts crw
        LEFT JOIN run_templates rt ON rt.id = crw.run_template_id
        ORDER BY crw.date DESC LIMIT 4
    """).fetchall()

    recent = []
    for w in gym_rows:
        recent.append({**dict(w), "workout_type": "gym"})
    for w in run_rows:
        recent.append({**dict(w), "workout_type": "run"})
    recent.sort(key=lambda x: x["date"], reverse=True)
    recent = recent[:4]

    # Upcoming scheduled workouts (today → +6 days)
    upcoming_rows = conn.execute("""
        SELECT sw.date, sw.workout_type, sw.notes,
               gt.name as gym_template_name,
               rt.name as run_template_name
        FROM scheduled_workouts sw
        LEFT JOIN gym_templates gt ON gt.id = sw.gym_template_id
        LEFT JOIN run_templates rt ON rt.id = sw.run_template_id
        WHERE sw.date >= ? AND sw.date <= ?
        ORDER BY sw.date
    """, (today.isoformat(), (today + timedelta(days=6)).isoformat())).fetchall()

    upcoming = []
    for row in upcoming_rows:
        d = date.fromisoformat(row["date"])
        if d == today:
            label = "Today"
        elif d == today + timedelta(days=1):
            label = "Tomorrow"
        else:
            label = d.strftime("%A")  # Mon, Tue, …
        name = (row["gym_template_name"] if row["workout_type"] == "gym"
                else row["run_template_name"]) or row["workout_type"].capitalize()
        upcoming.append({"label": label, "date": row["date"],
                         "workout_type": row["workout_type"], "name": name})

    # This-week quick stats
    weekly_km = conn.execute("""
        SELECT COALESCE(SUM(total_distance_meters), 0) / 1000.0 as km
        FROM completed_run_workouts WHERE date >= ? AND date <= ?
    """, (week_start.isoformat(), week_end.isoformat())).fetchone()["km"]

    weekly_gym = conn.execute("""
        SELECT COUNT(*) as cnt FROM completed_gym_workouts
        WHERE date >= ? AND date <= ?
    """, (week_start.isoformat(), week_end.isoformat())).fetchone()["cnt"]

    conn.close()

    return templates.TemplateResponse("home.html", {
        "request": request,
        "today": today.isoformat(),
        "yesterday": (today - timedelta(days=1)).isoformat(),
        "recent": recent,
        "upcoming": upcoming,
        "weekly_km": round(weekly_km, 1),
        "weekly_gym": weekly_gym,
    })