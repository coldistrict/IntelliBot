from __future__ import annotations

from typing import TYPE_CHECKING

from app.models import AnalysisRequest, AnalysisRun, FactClaim, Factor, RuleParse

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.analysis_pipeline import AnalysisProcessor, SourceContext


def run_fact_pipeline_stage(
    processor: "AnalysisProcessor",
    *,
    session: "Session",
    request: AnalysisRequest,
    rule_parse: RuleParse,
    analysis_run: AnalysisRun,
    source_contexts: list["SourceContext"],
) -> tuple[list[FactClaim], list[Factor]]:
    facts = processor._extract_and_verify_facts(
        session,
        request,
        rule_parse,
        analysis_run,
        source_contexts,
    )
    facts = processor._classify_evidence_roles(
        session,
        request,
        rule_parse,
        analysis_run,
        facts,
    )
    factors = processor._map_factors(session, request, rule_parse, analysis_run, facts)
    return facts, factors
