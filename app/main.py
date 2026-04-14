from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(
    title=os.environ.get("APP_NAME"),
    description="A Media Server to make education Fun",
    version=os.environ.get("APP_VERSION")
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Import and Include all the routers with the applications.
from app.routers import sessions

app.include_router(sessions.router)

@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "app": "SevakStream"}