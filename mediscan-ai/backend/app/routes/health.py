"""GET /api/v1/health — used by Render health checks and the frontend status badge."""

from fastapi import APIRouter

from app.core.config import get_settings
from app import __version__
from app.schemas.response import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version=__version__,
        gemini_configured=bool(settings.gemini_api_key),
        openrouter_configured=bool(settings.openrouter_api_key),
    )
