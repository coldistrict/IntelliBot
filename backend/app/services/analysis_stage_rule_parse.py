from __future__ import annotations

from typing import TYPE_CHECKING

from app.models import AnalysisRequest, AnalysisRun, Market, RuleParse

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.analysis_pipeline import AnalysisProcessor


def run_rule_parse_stage(
    processor: "AnalysisProcessor",
    *,
    session: "Session",
    request: AnalysisRequest,
) -> tuple[Market | None, RuleParse, AnalysisRun]:
    market = processor._resolve_market(session, request)
    rule_parse_draft = processor._build_rule_parse(session, request, market)
    rule_parse = processor._persist_rule_parse(session, request, market, rule_parse_draft)
    analysis_run = processor._create_run(session, request, market, rule_parse)
    return market, rule_parse, analysis_run

