from __future__ import annotations

from fastapi import FastAPI

from fluxrules.api.routes.evaluate import router as evaluate_router
from fluxrules.api.routes.explain import router as explain_router
from fluxrules.api.routes.health import router as health_router
from fluxrules.api.routes.simulate import router as simulate_router
from fluxrules.api.routes.validate import router as validate_router


def create_app() -> FastAPI:
    app = FastAPI(title="fluxrules", version="0.1.0")
    app.include_router(health_router)
    app.include_router(evaluate_router)
    app.include_router(validate_router)
    app.include_router(explain_router)
    app.include_router(simulate_router)
    return app
