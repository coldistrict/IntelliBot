import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config.settings import get_settings
from app.services.analysis_dispatch import get_analysis_dispatcher
from app.services.analysis_pipeline import get_analysis_processor
from app.services.outcome_refresh_scheduler import start_outcome_scheduler

# Uvicorn configures this logger with the server's visible stderr handler.
# Keeping application lifecycle events below it makes them operator-visible
# without replacing the host process's logging configuration.
logger = logging.getLogger("uvicorn.error").getChild("intellibot")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    processor = get_analysis_processor()
    dispatcher = get_analysis_dispatcher()
    reconciled = dispatcher.reconcile_stale_requests(
        processor=processor,
        session_factory=processor.session_factory,
    )
    if reconciled:
        logger.info("Requeued %s stale analysis request(s) during startup.", len(reconciled))
    scheduler = None
    if settings.outcome_refresh_enabled:
        scheduler = start_outcome_scheduler(
            session_factory=processor.session_factory,
            interval_minutes=settings.outcome_refresh_interval_minutes,
            cooldown_seconds=settings.outcome_refresh_cooldown_seconds,
            startup_retry_seconds=settings.outcome_refresh_startup_retry_seconds,
        )
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Shadow-mode research copilot backend scaffold",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
