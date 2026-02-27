from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from database import init_db
from routers import exercises
from routers import gym_templates
from routers import run_templates
from routers import schedule
from routers import completed_gym
from routers import completed_run
from routers import history

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

app.include_router(exercises.router)
app.include_router(gym_templates.router)
app.include_router(run_templates.router)
app.include_router(schedule.router)
app.include_router(completed_gym.router)
app.include_router(completed_run.router)
app.include_router(history.router)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})