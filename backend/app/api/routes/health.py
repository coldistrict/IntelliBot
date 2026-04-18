from datetime import UTC, datetime

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="backend",
        version="0.1.0",
        timestamp_utc=datetime.now(UTC),
    )

