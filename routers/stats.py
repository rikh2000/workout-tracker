from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from database import get_connection
from datetime import date, timedelta
from typing import Optional

router = APIRouter(prefix="/stats")
templates = Jinja2Templates(directory="templates")


def fill_weeks(data: list, week_field: str, defaults: dict, since_str: str) -> list:
    """Fill missing weeks with default values so charts have no gaps."""
    today = date.today()
    if since_str == "2000-01-01":
        if not data:
            return []
        year = int(data[0][week_field].split('-W')[0])
        start = date(year, 1, 1)
    else:
        start = date.fromisoformat(since_str)
    seen, all_weeks = set(), []
    d = start
    while d <= today:
        w = d.strftime('%Y-W%W')
        if w not in seen:
            seen.add(w)
            all_weeks.append(w)
        d += timedelta(days=7)
    lookup = {r[week_field]: r for r in data}
    return [lookup.get(w, {week_field: w, **defaults}) for w in all_weeks]


def get_since_date(window: str) -> str:
    today = date.today()
    if window == "4w":
        return (today - timedelta(weeks=4)).isoformat()
    elif window == "3m":
        return (today - timedelta(days=90)).isoformat()
    elif window == "12m":
        return (today - timedelta(days=365)).isoformat()
    else:
        return "2000-01-01"


@router.get("", response_class=HTMLResponse)
def stats_page(request: Request, window: str = "12m",
               tab: str = "running", exercise_id: Optional[int] = None):
    since = get_since_date(window)
    conn = get_connection()

    # ── Running: summary ──────────────────────────────────────────────────────
    run_summary = conn.execute("""
        SELECT
            COUNT(*) as total_runs,
            COALESCE(SUM(total_distance_meters) / 1000.0, 0) as total_km
        FROM completed_run_workouts
        WHERE date >= ?
    """, (since,)).fetchone()

    # ── Running: weekly mileage ───────────────────────────────────────────────
    mileage_rows = conn.execute("""
        SELECT
            strftime('%Y-W%W', date) as week,
            COALESCE(SUM(total_distance_meters) / 1000.0, 0) as km
        FROM completed_run_workouts
        WHERE date >= ?
        GROUP BY week
        ORDER BY week ASC
    """, (since,)).fetchall()

    # ── Running: RPE zones by time (compute duration from pace+dist if needed) ─
    rpe_rows = conn.execute("""
        SELECT
            strftime('%Y-W%W', crw.date) as week,
            CASE
                WHEN crs.actual_rpe <= 4 THEN 'Easy'
                WHEN crs.actual_rpe <= 6 THEN 'Moderate'
                WHEN crs.actual_rpe <= 8 THEN 'Hard'
                ELSE 'Max'
            END as zone,
            SUM(
                CASE
                    WHEN crs.actual_duration_seconds IS NOT NULL
                        THEN crs.actual_duration_seconds / 60.0
                    WHEN crs.actual_distance_meters IS NOT NULL
                         AND crs.actual_pace_min_per_km IS NOT NULL
                        THEN (crs.actual_distance_meters / 1000.0) * crs.actual_pace_min_per_km
                    ELSE 0
                END
            ) as minutes
        FROM completed_run_segments crs
        JOIN completed_run_workouts crw ON crw.id = crs.workout_id
        WHERE crw.date >= ?
          AND crs.actual_rpe IS NOT NULL
        GROUP BY week, zone
        ORDER BY week ASC
    """, (since,)).fetchall()

    # ── Running: run type breakdown ───────────────────────────────────────────
    run_type_rows = conn.execute("""
        SELECT run_type,
               COUNT(*) as count,
               COALESCE(SUM(total_distance_meters) / 1000.0, 0) as km
        FROM completed_run_workouts
        WHERE date >= ?
        GROUP BY run_type
        ORDER BY km DESC
    """, (since,)).fetchall()

    # ── Gym: exercise list for picker ─────────────────────────────────────────
    all_exercises = conn.execute(
        "SELECT id, name, type FROM exercises ORDER BY name"
    ).fetchall()

    # ── Gym: muscle group distribution ───────────────────────────────────────
    muscle_rows = conn.execute("""
        SELECT e.muscle_groups, COUNT(*) as sets
        FROM completed_gym_sets cgs
        JOIN exercises e ON e.id = cgs.exercise_id
        JOIN completed_gym_workouts cgw ON cgw.id = cgs.workout_id
        WHERE cgw.date >= ?
          AND e.muscle_groups IS NOT NULL AND e.muscle_groups != ''
        GROUP BY e.muscle_groups
    """, (since,)).fetchall()

    # ── Gym: workout frequency per week ──────────────────────────────────────
    freq_rows = conn.execute("""
        SELECT strftime('%Y-W%W', date) as week, COUNT(*) as sessions
        FROM completed_gym_workouts
        WHERE date >= ?
        GROUP BY week
        ORDER BY week ASC
    """, (since,)).fetchall()

    # ── Gym: total sets per week ──────────────────────────────────────────────
    vol_rows = conn.execute("""
        SELECT strftime('%Y-W%W', cgw.date) as week,
               COUNT(*) as total_sets
        FROM completed_gym_sets cgs
        JOIN completed_gym_workouts cgw ON cgw.id = cgs.workout_id
        WHERE cgw.date >= ?
        GROUP BY week
        ORDER BY week ASC
    """, (since,)).fetchall()

    # ── Gym: rep range distribution per week ─────────────────────────────────
    rep_range_rows = conn.execute("""
        SELECT strftime('%Y-W%W', cgw.date) as week,
               CASE
                   WHEN cgs.reps BETWEEN 1 AND 5 THEN 'Strength (1-5)'
                   WHEN cgs.reps BETWEEN 6 AND 12 THEN 'Hypertrophy (6-12)'
                   ELSE 'Endurance (13+)'
               END as rep_range,
               COUNT(*) as sets
        FROM completed_gym_sets cgs
        JOIN completed_gym_workouts cgw ON cgw.id = cgs.workout_id
        WHERE cgw.date >= ? AND cgs.reps IS NOT NULL
        GROUP BY week, rep_range
        ORDER BY week ASC
    """, (since,)).fetchall()

    # ── Gym: all-time PRs board ───────────────────────────────────────────────
    pr_rows = conn.execute("""
        SELECT e.name, cgs.reps, cgs.weight_kg
        FROM completed_gym_sets cgs
        JOIN exercises e ON e.id = cgs.exercise_id
        WHERE cgs.weight_kg IS NOT NULL AND cgs.reps IS NOT NULL AND cgs.reps > 0
        ORDER BY e.name, cgs.reps
    """).fetchall()

    conn.close()

    # ── Process muscle groups (expand comma-separated) ────────────────────────
    muscle_totals: dict = {}
    for row in muscle_rows:
        for g in (row["muscle_groups"] or "").split(","):
            g = g.strip()
            if g:
                muscle_totals[g] = muscle_totals.get(g, 0) + row["sets"]
    muscle_sorted = sorted(muscle_totals.items(), key=lambda x: x[1], reverse=True)

    # ── Process weekly mileage + rolling 4-week average ───────────────────────
    mileage_raw = [{"week": r["week"], "km": round(r["km"] or 0, 2)} for r in mileage_rows]
    mileage = fill_weeks(mileage_raw, "week", {"km": 0.0}, since)
    for i, d in enumerate(mileage):
        vals = [mileage[j]["km"] for j in range(max(0, i - 3), i + 1)]
        d["rolling_avg"] = round(sum(vals) / len(vals), 2)

    # ── Process RPE zones into week×zone structure ────────────────────────────
    zone_order = ["Easy", "Moderate", "Hard", "Max"]
    rpe_by_week: dict = {}
    for row in rpe_rows:
        w = row["week"]
        if w not in rpe_by_week:
            rpe_by_week[w] = {z: 0 for z in zone_order}
        rpe_by_week[w][row["zone"]] = round(row["minutes"] or 0, 1)
    rpe_weeks = [{"week": w, **zones} for w, zones in sorted(rpe_by_week.items())]

    total_km = run_summary["total_km"] or 0
    total_runs = run_summary["total_runs"] or 0
    avg_weekly_km = round(total_km / max(1, len(mileage)), 1) if mileage else 0.0

    # ── Process gym frequency + volume ───────────────────────────────────────
    gym_freq = fill_weeks(
        [{"week": r["week"], "sessions": r["sessions"]} for r in freq_rows],
        "week", {"sessions": 0}, since)
    gym_volume = fill_weeks(
        [{"week": r["week"], "total_sets": r["total_sets"]} for r in vol_rows],
        "week", {"total_sets": 0}, since)

    # ── Process rep range distribution ───────────────────────────────────────
    range_order = ["Strength (1-5)", "Hypertrophy (6-12)", "Endurance (13+)"]
    rep_range_by_week: dict = {}
    for row in rep_range_rows:
        w = row["week"]
        if w not in rep_range_by_week:
            rep_range_by_week[w] = {r: 0 for r in range_order}
        rep_range_by_week[w][row["rep_range"]] = row["sets"]
    # Convert to percentages
    rep_range_weeks = []
    for w, ranges in sorted(rep_range_by_week.items()):
        total = sum(ranges.values())
        rep_range_weeks.append({
            "week": w,
            **{r: round(ranges[r] / total * 100, 1) for r in range_order}
        })

    # ── Process PRs board (best est. 1RM per exercise) ────────────────────────
    pr_dict: dict = {}
    for row in pr_rows:
        name = row["name"]
        e1rm = row["weight_kg"] * (1 + row["reps"] / 30.0)
        if name not in pr_dict or e1rm > pr_dict[name]["est_1rm"]:
            pr_dict[name] = {
                "exercise": name,
                "weight_kg": row["weight_kg"],
                "reps": row["reps"],
                "est_1rm": round(e1rm, 1),
            }
    prs_board = sorted(pr_dict.values(), key=lambda x: x["exercise"])

    return templates.TemplateResponse("stats/index.html", {
        "request": request,
        "window": window,
        "tab": tab,
        "exercise_id": exercise_id,
        # Running
        "total_runs": total_runs,
        "total_km": round(total_km, 1),
        "avg_weekly_km": avg_weekly_km,
        "mileage": mileage,
        "rpe_weeks": rpe_weeks,
        "run_types": [dict(r) for r in run_type_rows],
        # Gym
        "all_exercises": [dict(e) for e in all_exercises],
        "muscle_groups": muscle_sorted,
        "gym_freq": gym_freq,
        "gym_volume": gym_volume,
        "rep_range_weeks": rep_range_weeks,
        "prs_board": prs_board,
    })


@router.get("/exercise/{exercise_id}")
def exercise_stats(request: Request, exercise_id: int, window: str = "12m"):
    since = get_since_date(window)
    conn = get_connection()

    exercise = conn.execute(
        "SELECT * FROM exercises WHERE id = ?", (exercise_id,)
    ).fetchone()
    if not exercise:
        conn.close()
        return JSONResponse({"error": "Not found"}, status_code=404)

    rows = conn.execute("""
        SELECT cgw.date, cgw.id as workout_id,
               cgs.set_number, cgs.reps, cgs.weight_kg
        FROM completed_gym_sets cgs
        JOIN completed_gym_workouts cgw ON cgw.id = cgs.workout_id
        WHERE cgs.exercise_id = ?
          AND cgw.date >= ?
          AND cgs.weight_kg IS NOT NULL
          AND cgs.reps IS NOT NULL
        ORDER BY cgw.date ASC, cgs.set_number ASC
    """, (exercise_id, since)).fetchall()
    conn.close()

    # Group by session
    sessions_dict: dict = {}
    for row in rows:
        key = (row["date"], row["workout_id"])
        if key not in sessions_dict:
            sessions_dict[key] = {"date": row["date"], "sets": []}
        sessions_dict[key]["sets"].append({
            "reps": row["reps"],
            "weight_kg": row["weight_kg"]
        })

    # Per-session: best estimated 1RM (Epley), total volume
    sessions = []
    all_sets_flat = []
    for s in sessions_dict.values():
        best_1rm = 0.0
        total_volume = 0.0
        for st in s["sets"]:
            e1rm = st["weight_kg"] * (1 + st["reps"] / 30)
            best_1rm = max(best_1rm, e1rm)
            total_volume += st["weight_kg"] * st["reps"]
        sessions.append({
            "date": s["date"],
            "estimated_1rm": round(best_1rm, 1),
            "volume_kg": round(total_volume, 1),
        })
        all_sets_flat.extend(s["sets"])

    # PRs: heaviest weight per rep count
    pr_by_reps: dict = {}
    for st in all_sets_flat:
        r = st["reps"]
        if r not in pr_by_reps or st["weight_kg"] > pr_by_reps[r]:
            pr_by_reps[r] = st["weight_kg"]
    prs = [{"reps": r, "weight_kg": pr_by_reps[r]} for r in sorted(pr_by_reps)]

    return JSONResponse({
        "exercise_name": exercise["name"],
        "exercise_type": exercise["type"],
        "sessions": sessions,
        "prs": prs,
    })
