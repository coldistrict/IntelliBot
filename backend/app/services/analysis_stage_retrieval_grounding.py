from __future__ import annotations

from typing import TYPE_CHECKING

from app.models import AnalysisRequest, AnalysisRun, Market, RuleParse

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.analysis_pipeline import AnalysisProcessor, RetrievalResult


def run_retrieval_grounding_stage(
    processor: "AnalysisProcessor",
    *,
    session: "Session",
    request: AnalysisRequest,
    market: Market | None,
    analysis_run: AnalysisRun,
    rule_parse: RuleParse,
) -> "RetrievalResult":
    return processor._retrieve_sources(
        session,
        request,
        market,
        analysis_run,
        rule_parse,
    )
