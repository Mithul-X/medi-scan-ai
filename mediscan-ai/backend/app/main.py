"""
FastAPI app factory: CORS, lifespan (DB init/teardown), global exception
handling, and route registration.

Deliberately a thin file — every concern lives in its own module so this
stays readable as the single place that wires everything together.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.exceptions import MediScanError
from app.core.logging import configure_logging, get_logger
from app.db.database import close_db, init_db
from app.routes import analyze, health, history

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info("startup_begin")
    await init_db()
    logger.info("startup_complete")
    yield
    logger.info("shutdown_begin")
    await close_db()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(MediScanError)
    async def handle_mediscan_error(request: Request, exc: MediScanError) -> JSONResponse:
        logger.warning(
            "request_error",
            extra={"error_code": exc.code, "error_message": exc.message, "path": request.url.path},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "details": exc.details},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            extra={"path": request.url.path, "error": str(exc)},
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "details": {},
            },
        )

    app.include_router(analyze.router, prefix=settings.api_v1_prefix)
    app.include_router(history.router, prefix=settings.api_v1_prefix)
    app.include_router(health.router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
