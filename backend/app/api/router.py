from fastapi import APIRouter

from app.api.routes.analyses import router as analyses_router
from app.api.routes.health import router as health_router
from app.api.routes.markets import router as markets_router
from app.api.routes.providers import router as providers_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(providers_router, tags=["providers"])
api_router.include_router(markets_router, tags=["markets"])
api_router.include_router(analyses_router, tags=["analyses"])
