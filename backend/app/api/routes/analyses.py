from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db.session import get_db_session
from app.models import AnalysisRequest, AnalysisRun, JournalEvent, Market, Review, RuleParse
from app.models.enums import (
    InputTypeEnum,
    JournalEventTypeEnum,
    ModeEnum,
    RequestStatusEnum,
    RunQualityEnum,
    SourceKindEnum,
    TemplateKey,
)
from app.schemas.analysis import (
    AnalysisAuditResponse,
    AnalysisLedgerResponse,
    AnalysisDetailResponse,
    AnalysisListResponse,
    AnalysisProgressResponse,
    AnalysisPresentationResponse,
    AnalysisProgressPollResponse,
    AnalysisProgressPresentationResponse,
    AnalysisQueuedResponse,
    AnalysisRequestSummary,
    ExecutionEventResponse,
    ExecutionTotalsResponse,
    AutoScanRunRequest,
    DocumentResponse,
    FactorResponse,
    FactClaimResponse,
    ManualAnalysisCreateRequest,
    JournalAfterRequest,
    JournalBeforeRequest,
    JournalEventResponse,
    JournalResponse,
    PassageResponse,
    RecommendationResponse,
    ReviewCreateRequest,
    ReviewResponse,
    RuleParseResponse,
    AnalysisRunResponse,
    PresentationArtifactStatusResponse,
    SocialIntelSummaryResponse,
    SourceResponse,
)
from app.schemas.market import MarketResponse
from app.services.analysis_artifacts import build_artifact_statuses
from app.services.analysis_audit import build_analysis_audit, build_display_summary
from app.services.analysis_dispatch import AnalysisDispatcher, get_analysis_dispatcher, reset_request_to_queue
from app.services.analysis_presentation import build_analysis_presentation
from app.services.analysis_pipeline import AnalysisProcessor, get_analysis_processor
from app.services.analysis_progress import build_progress_snapshot, initial_progress_payload
from app.services.analysis_social_trust import social_metadata_is_trusted

router = APIRouter(prefix="/analyses")
ACTIVE_REQUEST_STATUSES = {RequestStatusEnum.QUEUED, RequestStatusEnum.RUNNING}


def _latest_rule_parse(request: AnalysisRequest) -> RuleParse | None:
    if not request.rule_parses:
        return None
    return max(request.rule_parses, key=lambda item: item.created_at)


def _latest_run(request: AnalysisRequest) -> AnalysisRun | None:
    if not request.analysis_runs:
        return None
    return max(request.analysis_runs, key=lambda item: item.created_at)


def _latest_completed_run(request: AnalysisRequest) -> AnalysisRun | None:
    completed_runs = [
        run
        for run in request.analysis_runs
        if run.final_summary
        or run.p_hat is not None
        or run.recommendation is not None
        or bool(run.factors)
    ]
    if not completed_runs:
        return None
    return max(completed_runs, key=lambda item: item.created_at)


def _artifact_belongs_to_current_attempt(
    request: AnalysisRequest,
    artifact_created_at: datetime,
) -> bool:
    if request.started_at is None:
        return False
    return artifact_created_at >= request.started_at


def _current_rule_parse(request: AnalysisRequest) -> RuleParse | None:
    latest_rule_parse = _latest_rule_parse(request)
    if latest_rule_parse is None:
        return None
    if request.status == RequestStatusEnum.COMPLETE:
        return latest_rule_parse
    if _artifact_belongs_to_current_attempt(request, latest_rule_parse.created_at):
        return latest_rule_parse
    return None


def _current_run(request: AnalysisRequest) -> AnalysisRun | None:
    latest_run = _latest_run(request)
    if latest_run is None:
        return None
    if request.status == RequestStatusEnum.COMPLETE:
        return _latest_completed_run(request) or latest_run
    if _artifact_belongs_to_current_attempt(request, latest_run.created_at):
        return latest_run
    return None


def _build_summary(request: AnalysisRequest) -> AnalysisRequestSummary:
    active_run = _current_run(request) if request.status == RequestStatusEnum.COMPLETE else None
    review_count = len(active_run.reviews) if active_run else 0
    progress = build_progress_snapshot(request)
    display_summary = build_display_summary(request, analysis_run=active_run)
    execution_events = active_run.execution_events if active_run else []
    journal_events = active_run.journal_events if active_run else []

    return AnalysisRequestSummary.model_validate(request).model_copy(
        update={
            "market_title": request.market.title if request.market else None,
            "latest_recommendation_label": (
                active_run.recommendation_label if active_run else None
            ),
            "latest_confidence_label": active_run.confidence_label if active_run else None,
            "review_count": review_count,
            "progress_percent": progress["percent_complete"],
            "current_stage_label": progress["current_label"],
            "current_stage_note": progress["current_note"],
            "display_summary": display_summary,
            "qualitative_label": active_run.qualitative_label if active_run else None,
            "quality_state": active_run.quality_state if active_run else RunQualityEnum.UNKNOWN,
            "quality_reasons": active_run.quality_reasons if active_run else [],
            "journal_event_count": len(journal_events),
            "estimated_cost_usd": round(
                sum(event.estimated_cost_usd for event in execution_events), 8
            ),
            "market_match_confidence": (
                (active_run.market_match_json or {}).get("confidence") if active_run else None
            ),
        },
    )


def _manual_input_payload(submission: ManualAnalysisCreateRequest) -> dict:
    return {
        "polymarket_url": str(submission.polymarket_url) if submission.polymarket_url else None,
        "polymarket_market_id": submission.polymarket_market_id,
        "custom_claim": submission.custom_claim,
        "deadline_text": submission.deadline_text,
        "include_premium": submission.include_premium,
        "include_live_x_intelligence": submission.include_live_x_intelligence,
        "confirmed_polymarket_market_id": submission.confirmed_polymarket_market_id,
    }


def _find_linked_market(session: Session, submission: ManualAnalysisCreateRequest) -> Market | None:
    if submission.polymarket_market_id:
        return session.scalar(
            select(Market).where(Market.polymarket_id == submission.polymarket_market_id)
        )
    if submission.polymarket_url:
        return session.scalar(select(Market).where(Market.url == str(submission.polymarket_url)))
    return None


def _queue_request(
    *,
    session: Session,
    request: AnalysisRequest,
    processor: AnalysisProcessor,
    dispatcher: AnalysisDispatcher,
    pre_reserved: bool = False,
) -> AnalysisQueuedResponse:
    session.add(request)
    session.commit()
    session.refresh(request)
    dispatcher.dispatch(processor, request.id, pre_reserved=pre_reserved)
    return AnalysisQueuedResponse(request=_build_summary(request))


def _build_progress_presentation(
    request: AnalysisRequest,
    *,
    latest_rule_parse: RuleParse | None,
    latest_run: AnalysisRun | None,
) -> AnalysisProgressPresentationResponse:
    progress = build_progress_snapshot(request)
    latest_sources = latest_run.sources if latest_run else []
    latest_factors = latest_run.factors if latest_run else []

    return AnalysisProgressPresentationResponse(
        artifact_statuses=[
            PresentationArtifactStatusResponse.model_validate(item)
            for item in build_artifact_statuses(
                progress=progress,
                has_rule_parse=latest_rule_parse is not None,
                has_sources=bool(latest_sources),
                has_social_sources=bool(latest_run and latest_run.social_intel_summary),
                has_factors=bool(latest_factors),
                has_analysis_run=latest_run is not None,
                has_final_summary=bool(latest_run and latest_run.final_summary),
            )
        ]
    )


@router.post("/manual", response_model=AnalysisQueuedResponse, status_code=status.HTTP_202_ACCEPTED)
def create_manual_analysis(
    submission: ManualAnalysisCreateRequest,
    processor: AnalysisProcessor = Depends(get_analysis_processor),
    dispatcher: AnalysisDispatcher = Depends(get_analysis_dispatcher),
    session: Session = Depends(get_db_session),
) -> AnalysisQueuedResponse:
    linked_market = _find_linked_market(session, submission)

    request = AnalysisRequest(
        mode=ModeEnum.MANUAL,
        input_type=submission.resolved_input_type,
        input_text=submission.resolved_input_text,
        input_payload=_manual_input_payload(submission),
        progress_json=initial_progress_payload(),
        market_id=linked_market.id if linked_market else None,
        template_requested=submission.template_requested,
        status=RequestStatusEnum.QUEUED,
        current_stage="queued",
    )
    return _queue_request(
        session=session,
        request=request,
        processor=processor,
        dispatcher=dispatcher,
    )


@router.post("/auto-scan/run", response_model=AnalysisQueuedResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_auto_scan(
    payload: AutoScanRunRequest,
    processor: AnalysisProcessor = Depends(get_analysis_processor),
    dispatcher: AnalysisDispatcher = Depends(get_analysis_dispatcher),
    session: Session = Depends(get_db_session),
) -> AnalysisQueuedResponse:
    request = AnalysisRequest(
        mode=ModeEnum.AUTO,
        input_type=InputTypeEnum.CUSTOM_CLAIM,
        input_text="AUTO_SCAN_TRIGGER",
        input_payload={"trigger": "manual_api", "note": payload.note},
        progress_json=initial_progress_payload(),
        template_requested=TemplateKey.OFFICIAL_EVENT,
        status=RequestStatusEnum.QUEUED,
        current_stage="queued",
    )
    return _queue_request(
        session=session,
        request=request,
        processor=processor,
        dispatcher=dispatcher,
    )


@router.get("", response_model=AnalysisListResponse)
def list_analyses(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    polymarket_id: str | None = Query(default=None, max_length=255),
    session: Session = Depends(get_db_session),
) -> AnalysisListResponse:
    count_query = select(func.count()).select_from(AnalysisRequest)
    items_query = (
        select(AnalysisRequest)
        .options(
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.reviews),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.execution_events),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.journal_events),
            selectinload(AnalysisRequest.market),
        )
        .order_by(AnalysisRequest.created_at.desc(), AnalysisRequest.id.desc())
    )
    if polymarket_id is not None:
        market_filter = (
            AnalysisRequest.market_id == Market.id,
            Market.polymarket_id == polymarket_id,
        )
        count_query = count_query.join(Market, market_filter[0]).where(market_filter[1])
        items_query = items_query.join(Market, market_filter[0]).where(market_filter[1])

    total = session.scalar(count_query) or 0
    status_query = select(AnalysisRequest.status, func.count()).group_by(AnalysisRequest.status)
    if polymarket_id is not None:
        status_query = status_query.join(Market, AnalysisRequest.market_id == Market.id).where(
            Market.polymarket_id == polymarket_id
        )
    status_counts = {status.value: count for status, count in session.execute(status_query).all()}
    items = session.scalars(items_query.limit(limit).offset(offset)).all()
    return AnalysisListResponse(
        items=[_build_summary(item) for item in items],
        total=total,
        status_counts=status_counts,
    )


@router.get("/{analysis_id}", response_model=AnalysisDetailResponse)
def get_analysis_detail(
    analysis_id: int,
    session: Session = Depends(get_db_session),
) -> AnalysisDetailResponse:
    request = session.scalar(
        select(AnalysisRequest)
        .where(AnalysisRequest.id == analysis_id)
        .options(
            selectinload(AnalysisRequest.market),
            selectinload(AnalysisRequest.rule_parses),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.recommendation),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.social_intel_summary),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.reviews),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.sources),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.documents),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.passages),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.fact_claims),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.factors),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.execution_events),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.journal_events),
        )
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Analysis request not found.")

    latest_rule_parse = _current_rule_parse(request)
    latest_run = _current_run(request)
    progress = build_progress_snapshot(request)
    trusted_social_sources = []
    if latest_run:
        trusted_social_sources = [
            SourceResponse.model_validate(source)
            for source in latest_run.sources
            if source.source_kind == SourceKindEnum.LIVE_SOCIAL
            and social_metadata_is_trusted(
                source_tier=source.source_tier,
                metadata=source.metadata_json,
            )
        ]
    recommendation = latest_run.recommendation if latest_run else None
    social_intel_summary = (
        SocialIntelSummaryResponse.model_validate(latest_run.social_intel_summary).model_copy(
            update={"trusted_accounts_count": len(trusted_social_sources)}
        )
        if latest_run and latest_run.social_intel_summary
        else None
    )
    display_summary = build_display_summary(
        request,
        rule_parse=latest_rule_parse,
        analysis_run=latest_run,
        recommendation=recommendation,
        factors=latest_run.factors if latest_run else None,
    )
    audit = (
        build_analysis_audit(
            request=request,
            rule_parse=latest_rule_parse,
            analysis_run=latest_run,
            recommendation=recommendation,
            sources=latest_run.sources if latest_run else [],
            facts=latest_run.fact_claims if latest_run else [],
            factors=latest_run.factors if latest_run else [],
            social_intel_summary=latest_run.social_intel_summary if latest_run else None,
        )
        if latest_run and latest_run.factors
        else None
    )
    presentation = build_analysis_presentation(
        request=request,
        rule_parse=latest_rule_parse,
        analysis_run=latest_run,
        recommendation=recommendation,
        sources=latest_run.sources if latest_run else [],
        facts=latest_run.fact_claims if latest_run else [],
        factors=latest_run.factors if latest_run else [],
    )

    return AnalysisDetailResponse(
        request=_build_summary(request),
        market=MarketResponse.model_validate(request.market) if request.market else None,
        latest_rule_parse=(
            RuleParseResponse.model_validate(latest_rule_parse) if latest_rule_parse else None
        ),
        latest_run=AnalysisRunResponse.model_validate(latest_run) if latest_run else None,
        recommendation=(
            RecommendationResponse.model_validate(recommendation)
            if recommendation
            else None
        ),
        progress=AnalysisProgressResponse.model_validate(progress),
        audit=AnalysisAuditResponse.model_validate(audit) if audit else None,
        presentation=AnalysisPresentationResponse.model_validate(presentation),
        display_summary=display_summary,
        last_updated_at=request.updated_at,
        social_intel_summary=social_intel_summary,
        sources=(
            [SourceResponse.model_validate(source) for source in latest_run.sources]
            if latest_run
            else []
        ),
        documents=(
            [DocumentResponse.model_validate(document) for document in latest_run.documents]
            if latest_run
            else []
        ),
        passages=(
            [
                PassageResponse.model_validate(passage)
                for passage in sorted(
                    latest_run.passages,
                    key=lambda item: (item.source_id, -item.relevance_score, item.passage_index),
                )
            ]
            if latest_run
            else []
        ),
        trusted_social_sources=trusted_social_sources,
        fact_claims=(
            [FactClaimResponse.model_validate(fact_claim) for fact_claim in latest_run.fact_claims]
            if latest_run
            else []
        ),
        factors=(
            [FactorResponse.model_validate(factor) for factor in latest_run.factors]
            if latest_run
            else []
        ),
        reviews=(
            [ReviewResponse.model_validate(review) for review in latest_run.reviews]
            if latest_run
            else []
        ),
    )


@router.get("/{analysis_id}/progress", response_model=AnalysisProgressPollResponse)
def get_analysis_progress(
    analysis_id: int,
    session: Session = Depends(get_db_session),
) -> AnalysisProgressPollResponse:
    request = session.scalar(
        select(AnalysisRequest)
        .where(AnalysisRequest.id == analysis_id)
        .options(
            selectinload(AnalysisRequest.rule_parses),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.reviews),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.sources),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.social_intel_summary),
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.factors),
        )
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Analysis request not found.")

    latest_rule_parse = _current_rule_parse(request)
    latest_run = _current_run(request)
    progress = build_progress_snapshot(request)

    return AnalysisProgressPollResponse(
        request=_build_summary(request),
        progress=AnalysisProgressResponse.model_validate(progress),
        presentation=_build_progress_presentation(
            request,
            latest_rule_parse=latest_rule_parse,
            latest_run=latest_run,
        ),
        last_updated_at=request.updated_at,
    )


@router.get("/{analysis_id}/ledger", response_model=AnalysisLedgerResponse)
def get_analysis_ledger(
    analysis_id: int,
    session: Session = Depends(get_db_session),
) -> AnalysisLedgerResponse:
    request = session.scalar(
        select(AnalysisRequest)
        .where(AnalysisRequest.id == analysis_id)
        .options(
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.execution_events)
        )
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Analysis request not found.")
    run = _current_run(request) or _latest_run(request)
    events = sorted(run.execution_events, key=lambda event: (event.created_at, event.id)) if run else []
    stages = [event for event in events if event.event_kind == "stage"]
    calls = [event for event in events if event.event_kind != "stage"]
    return AnalysisLedgerResponse(
        stages=[ExecutionEventResponse.model_validate(event) for event in stages],
        calls=[ExecutionEventResponse.model_validate(event) for event in calls],
        run_quality=run.quality_state if run else RunQualityEnum.UNKNOWN,
        quality_reasons=run.quality_reasons if run else [],
        totals=ExecutionTotalsResponse(
            calls=len([event for event in calls if event.event_kind == "model_call"]),
            cache_hits=sum(1 for event in calls if event.cache_hit),
            tokens=sum(event.prompt_tokens + event.completion_tokens for event in calls),
            estimated_cost_usd=round(sum(event.estimated_cost_usd for event in calls), 8),
        ),
    )


def _request_for_journal(session: Session, analysis_id: int) -> tuple[AnalysisRequest, AnalysisRun]:
    request = session.scalar(
        select(AnalysisRequest)
        .where(AnalysisRequest.id == analysis_id)
        .options(
            selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.journal_events)
        )
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Analysis request not found.")
    run = _current_run(request) or _latest_run(request)
    if run is None:
        raise HTTPException(status_code=409, detail="Analysis run has not started yet.")
    return request, run


@router.post("/{analysis_id}/journal/before", response_model=JournalEventResponse)
def journal_before(
    analysis_id: int,
    payload: JournalBeforeRequest,
    session: Session = Depends(get_db_session),
) -> JournalEventResponse:
    _, run = _request_for_journal(session, analysis_id)
    event = JournalEvent(
        analysis_run_id=run.id,
        event_type=JournalEventTypeEnum.BEFORE,
        payload_json=payload.model_dump(mode="json"),
        created_at=datetime.now(UTC),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return JournalEventResponse.model_validate(event)


@router.post("/{analysis_id}/journal/after", response_model=JournalEventResponse)
def journal_after(
    analysis_id: int,
    payload: JournalAfterRequest,
    session: Session = Depends(get_db_session),
) -> JournalEventResponse:
    request, run = _request_for_journal(session, analysis_id)
    if request.status != RequestStatusEnum.COMPLETE or run.published_forecast is None:
        raise HTTPException(status_code=409, detail="A published forecast is required first.")
    event = JournalEvent(
        analysis_run_id=run.id,
        event_type=JournalEventTypeEnum.AFTER,
        payload_json=payload.model_dump(mode="json"),
        created_at=datetime.now(UTC),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return JournalEventResponse.model_validate(event)


@router.get("/{analysis_id}/journal", response_model=JournalResponse)
def get_journal(
    analysis_id: int,
    session: Session = Depends(get_db_session),
) -> JournalResponse:
    _, run = _request_for_journal(session, analysis_id)
    events = sorted(run.journal_events, key=lambda event: (event.created_at, event.id))
    return JournalResponse(events=[JournalEventResponse.model_validate(event) for event in events])


@router.post("/{analysis_id}/review", response_model=ReviewResponse)
def review_analysis(
    analysis_id: int,
    payload: ReviewCreateRequest,
    session: Session = Depends(get_db_session),
) -> ReviewResponse:
    request = session.scalar(
        select(AnalysisRequest)
        .where(AnalysisRequest.id == analysis_id)
        .options(selectinload(AnalysisRequest.analysis_runs).selectinload(AnalysisRun.reviews))
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Analysis request not found.")

    if request.status != RequestStatusEnum.COMPLETE:
        raise HTTPException(
            status_code=409,
            detail="Analysis must be complete before it can be reviewed.",
        )

    latest_run = _current_run(request)
    if latest_run is None:
        raise HTTPException(
            status_code=409,
            detail="Analysis has not produced a run yet, so it cannot be reviewed.",
        )

    review = Review(
        analysis_run_id=latest_run.id,
        decision=payload.decision,
        note=payload.note,
        created_at=datetime.now(UTC),
    )
    session.add(review)
    session.commit()
    session.refresh(review)
    return ReviewResponse.model_validate(review)


@router.post("/{analysis_id}/rerun", response_model=AnalysisQueuedResponse, status_code=status.HTTP_202_ACCEPTED)
def rerun_analysis(
    analysis_id: int,
    processor: AnalysisProcessor = Depends(get_analysis_processor),
    dispatcher: AnalysisDispatcher = Depends(get_analysis_dispatcher),
    session: Session = Depends(get_db_session),
) -> AnalysisQueuedResponse:
    request = session.get(AnalysisRequest, analysis_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Analysis request not found.")
    if request.status in ACTIVE_REQUEST_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Analysis is already queued or running.",
        )
    if not dispatcher.reserve(request.id):
        raise HTTPException(
            status_code=409,
            detail="Analysis is already queued or running.",
        )

    try:
        reset_request_to_queue(request)
        return _queue_request(
            session=session,
            request=request,
            processor=processor,
            dispatcher=dispatcher,
            pre_reserved=True,
        )
    except Exception:
        dispatcher.release(request.id)
        raise
