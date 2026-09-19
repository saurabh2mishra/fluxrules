"""FastAPI exception handlers for FluxRules custom exceptions.

Maps domain exceptions to structured HTTP error responses so that
clients receive consistent, machine-readable error payloads.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fluxrules.exceptions import (
    ConfigurationError,
    DSLParseError,
    EngineError,
    FluxRulesException,
    RepositoryError,
    RuleEvaluationError,
    RuleValidationError,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """

    @app.exception_handler(RuleValidationError)
    async def _rule_validation(request: Request, exc: RuleValidationError) -> JSONResponse:
        """Return 400 for rule validation failures."""
        return JSONResponse(
            status_code=400,
            content={
                "error": exc.code,
                "message": str(exc),
                "rule_id": exc.rule_id,
                "field": exc.field,
            },
        )

    @app.exception_handler(RuleEvaluationError)
    async def _rule_evaluation(request: Request, exc: RuleEvaluationError) -> JSONResponse:
        """Return 500 for rule evaluation failures."""
        logger.error("Rule evaluation error: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": exc.code,
                "message": str(exc),
                "rule_id": exc.rule_id,
            },
        )

    @app.exception_handler(DSLParseError)
    async def _dsl_parse(request: Request, exc: DSLParseError) -> JSONResponse:
        """Return 400 for DSL parse failures."""
        return JSONResponse(
            status_code=400,
            content={
                "error": exc.code,
                "message": str(exc),
                "detail": exc.detail,
            },
        )

    @app.exception_handler(ConfigurationError)
    async def _configuration(request: Request, exc: ConfigurationError) -> JSONResponse:
        """Return 500 for configuration errors."""
        logger.error("Configuration error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": exc.code, "message": str(exc)},
        )

    @app.exception_handler(RepositoryError)
    async def _repository(request: Request, exc: RepositoryError) -> JSONResponse:
        """Return 503 for repository / database errors."""
        logger.error("Repository error: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=503,
            content={"error": exc.code, "message": str(exc)},
        )

    @app.exception_handler(EngineError)
    async def _engine(request: Request, exc: EngineError) -> JSONResponse:
        """Return 500 for engine errors."""
        logger.error("Engine error: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": exc.code,
                "message": str(exc),
                "engine_type": exc.engine_type,
            },
        )

    @app.exception_handler(FluxRulesException)
    async def _generic_fluxrules(request: Request, exc: FluxRulesException) -> JSONResponse:
        """Catch-all for any other FluxRules exception."""
        logger.error("Unhandled FluxRules error: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": exc.code, "message": str(exc)},
        )
