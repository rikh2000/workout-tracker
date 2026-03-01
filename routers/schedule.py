from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import get_connection
from typing import Optional
from datetime import date, timedelta
import calendar

router = APIRouter(prefix="/schedule")
templates = Jinja2Templates(directory="templates")


def get_week_days(year: int, month: int, day: int):
    d = date(year, month, day)
    monday = d - timedelta(days=d.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def get_month_weeks(year: int, month: int):
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)
    return weeks


def get_workouts_for_dates(conn, date_strs):
    placeholders = ",".join("?" * len(date_strs))

    scheduled = conn.execute(f"""
        SELECT sw.*, gt.name as gym_template_name, rt.name as run_template_name
        FROM scheduled_workouts sw
        LEFT JOIN gym_templates gt ON gt.id = sw.gym_template_id
        LEFT JOIN run_templates rt ON rt.id = sw.run_template_id
        WHERE sw.date IN ({placeholders})
    """, date_strs).fetchall()

    completed_gym = conn.execute(f"""
        SELECT cgw.*, gt.name as template_name, 'gym' as workout_type
        FROM completed_gym_workouts cgw
        LEFT JOIN gym_templates gt ON gt.id = cgw.gym_template_id
        WHERE cgw.date IN ({placeholders})
    """, date_strs).fetchall()

    completed_run = conn.execute(f"""
        SELECT crw.*, rt.name as template_name, 'run' as workout_type
        FROM completed_run_workouts crw
        LEFT JOIN run_templates rt ON rt.id = crw.run_template_id
        WHERE crw.date IN ({placeholders})
    """, date_strs).fetchall()

    # group by date
    by_date = {d: {"scheduled": [], "completed": []} for d in date_strs}

    for s in scheduled:
        by_date[s["date"]]["scheduled"].append(dict(s))
    for c in completed_gym:
        by_date[c["date"]]["completed"].append(dict(c))
    for c in completed_run:
        by_date[c["date"]]["completed"].append(dict(c))

    return by_date


@router.get("", response_class=HTMLResponse)
def schedule_view(
    request: Request,
    view: str = "month",
    year: Optional[int] = None,
    month: Optional[int] = None,
    day: Optional[int] = None
):
    today = date.today()
    year = year or today.year
    month = month or today.month
    day = day or today.day

    conn = get_connection()
    gym_templates = conn.execute("SELECT * FROM gym_templates ORDER BY name").fetchall()
    run_templates = conn.execute("SELECT * FROM run_templates ORDER BY name").fetchall()

    if view == "week":
        days = get_week_days(year, month, day)
        date_strs = [d.isoformat() for d in days]
        by_date = get_workouts_for_dates(conn, date_strs)
        prev_day = days[0] - timedelta(weeks=1)
        next_day = days[0] + timedelta(weeks=1)
        conn.close()
        return templates.TemplateResponse("schedule/calendar.html", {
            "request": request,
            "view": "week",
            "days": days,
            "by_date": by_date,
            "today": today,
            "year": year, "month": month, "day": day,
            "prev_year": prev_day.year, "prev_month": prev_day.month, "prev_day": prev_day.day,
            "next_year": next_day.year, "next_month": next_day.month, "next_day": next_day.day,
            "gym_templates": gym_templates,
            "run_templates": run_templates,
            "month_name": today.strftime("%B %Y")
        })
    else:
        weeks = get_month_weeks(year, month)
        all_days = [d for week in weeks for d in week]
        date_strs = [d.isoformat() for d in all_days]
        by_date = get_workouts_for_dates(conn, date_strs)
        # prev/next month
        first = date(year, month, 1)
        prev = first - timedelta(days=1)
        next_m = first + timedelta(days=32)
        conn.close()
        return templates.TemplateResponse("schedule/calendar.html", {
            "request": request,
            "view": "month",
            "weeks": weeks,
            "by_date": by_date,
            "today": today,
            "year": year, "month": month, "day": day,
            "prev_year": prev.year, "prev_month": prev.month, "prev_day": 1,
            "next_year": next_m.year, "next_month": next_m.month, "next_day": 1,
            "gym_templates": gym_templates,
            "run_templates": run_templates,
            "month_name": date(year, month, 1).strftime("%B %Y")
        })


@router.post("/add", response_class=HTMLResponse)
def add_scheduled(
    request: Request,
    date: str = Form(...),
    workout_type: str = Form(...),
    gym_template_id: Optional[int] = Form(None),
    run_template_id: Optional[int] = Form(None),
    notes: str = Form(""),
    redirect_view: str = Form("month"),
    redirect_year: int = Form(...),
    redirect_month: int = Form(...),
    redirect_day: int = Form(1)
):
    conn = get_connection()
    conn.execute("""
        INSERT INTO scheduled_workouts
            (date, workout_type, gym_template_id, run_template_id, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (date, workout_type,
          gym_template_id if workout_type == "gym" else None,
          run_template_id if workout_type == "run" else None,
          notes.strip()))
    conn.commit()
    conn.close()
    return RedirectResponse(
        url=f"/schedule?view={redirect_view}&year={redirect_year}&month={redirect_month}&day={redirect_day}",
        status_code=303
    )


@router.post("/{scheduled_id}/delete", response_class=HTMLResponse)
def delete_scheduled(
    request: Request,
    scheduled_id: int,
    redirect_view: str = Form("month"),
    redirect_year: int = Form(...),
    redirect_month: int = Form(...),
    redirect_day: int = Form(1)
):
    conn = get_connection()
    conn.execute("DELETE FROM scheduled_workouts WHERE id = ?", (scheduled_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(
        url=f"/schedule?view={redirect_view}&year={redirect_year}&month={redirect_month}&day={redirect_day}",
        status_code=303
    )