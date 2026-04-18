import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config.settings import get_settings
from app.services.analysis_dispatch import get_analysis_dispatcher
from app.services.analysis_pipeline import get_analysis_processor

logger = logging.getLogger(__name__)

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
    yield


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
