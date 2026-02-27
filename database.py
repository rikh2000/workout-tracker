import sqlite3
from pathlib import Path

DB_PATH = Path("workout_tracker.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets you access columns by name, not just index
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""

    -- Exercise library
    CREATE TABLE IF NOT EXISTS exercises (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL UNIQUE,
        category    TEXT NOT NULL,  -- push / pull / legs / core / other
        type        TEXT NOT NULL,  -- reps / timed
        notes       TEXT
    );

    -- Gym templates
    CREATE TABLE IF NOT EXISTS gym_templates (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        name    TEXT NOT NULL UNIQUE,
        notes   TEXT
    );

    CREATE TABLE IF NOT EXISTS gym_template_exercises (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id      INTEGER NOT NULL REFERENCES gym_templates(id) ON DELETE CASCADE,
        exercise_id      INTEGER NOT NULL REFERENCES exercises(id),
        order_index      INTEGER NOT NULL,
        target_sets      INTEGER NOT NULL,
        target_reps      INTEGER,
        target_seconds   INTEGER,
        target_rpe       REAL,
        target_rir       INTEGER,
        notes            TEXT
    );

    -- Run templates
    CREATE TABLE IF NOT EXISTS run_templates (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL UNIQUE,
        run_type    TEXT NOT NULL,  -- intervals / tempo / steady_state / endurance / recovery
        notes       TEXT
    );

    CREATE TABLE IF NOT EXISTS run_template_segments (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id             INTEGER NOT NULL REFERENCES run_templates(id) ON DELETE CASCADE,
        order_index             INTEGER NOT NULL,
        segment_type            TEXT NOT NULL,  -- warmup / work / recovery / cooldown
        target_duration_seconds INTEGER,
        target_distance_meters  REAL,
        target_pace_min_per_km  REAL,
        target_rpe              REAL,
        notes                   TEXT
    );

    -- Schedule
    CREATE TABLE IF NOT EXISTS scheduled_workouts (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        date             TEXT NOT NULL,  -- stored as ISO8601: YYYY-MM-DD
        workout_type     TEXT NOT NULL,  -- gym / run
        gym_template_id  INTEGER REFERENCES gym_templates(id),
        run_template_id  INTEGER REFERENCES run_templates(id),
        notes            TEXT
    );

    -- Completed gym workouts
    CREATE TABLE IF NOT EXISTS completed_gym_workouts (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        date             TEXT NOT NULL,
        gym_template_id  INTEGER REFERENCES gym_templates(id),  -- soft reference, nullable
        notes            TEXT
    );

    CREATE TABLE IF NOT EXISTS completed_gym_sets (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        workout_id  INTEGER NOT NULL REFERENCES completed_gym_workouts(id) ON DELETE CASCADE,
        exercise_id INTEGER NOT NULL REFERENCES exercises(id),
        order_index INTEGER NOT NULL,
        set_number  INTEGER NOT NULL,
        reps        INTEGER,
        seconds     INTEGER,
        weight_kg   REAL,
        notes       TEXT
    );

    -- Completed run workouts
    CREATE TABLE IF NOT EXISTS completed_run_workouts (
        id                     INTEGER PRIMARY KEY AUTOINCREMENT,
        date                   TEXT NOT NULL,
        run_template_id        INTEGER REFERENCES run_templates(id),  -- soft reference, nullable
        run_type               TEXT NOT NULL,
        total_distance_meters  REAL,
        total_duration_seconds INTEGER,
        garmin_activity_id     TEXT,
        notes                  TEXT
    );

    CREATE TABLE IF NOT EXISTS completed_run_segments (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        workout_id              INTEGER NOT NULL REFERENCES completed_run_workouts(id) ON DELETE CASCADE,
        order_index             INTEGER NOT NULL,
        segment_type            TEXT NOT NULL,
        actual_duration_seconds INTEGER,
        actual_distance_meters  REAL,
        actual_pace_min_per_km  REAL,
        actual_rpe              REAL,
        notes                   TEXT
    );

    """)

    conn.commit()
    conn.close()
    print("Database initialised successfully.")

if __name__ == "__main__":
    init_db()