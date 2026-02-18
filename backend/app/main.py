from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import settings
from app.api.routes.auth import router as auth_router
from app.api.routes.rules import router as rules_router
from app.api.routes.events import router as events_router
from app.api.routes.metrics import router as metrics_router
from app.database import init_db


BASE_DIR = Path(__file__).resolve().parent.parent.parent

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(rules_router, prefix=settings.API_V1_STR)
app.include_router(events_router, prefix=settings.API_V1_STR)
app.include_router(metrics_router, prefix=settings.API_V1_STR)

@app.on_event("startup")
def startup_event():
    init_db()

# Serve entire frontend (index.html, login.html, css, js, etc.)
app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")

@app.get("/health", tags=["API"])
def health():
    return {"status": "healthy"}
