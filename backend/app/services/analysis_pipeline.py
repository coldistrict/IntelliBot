from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from hashlib import sha256
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.clients.openai_client import get_openai_client
from app.clients.polymarket_client import PolymarketClient, ResolvedMarketRecord
from app.clients.tavily_client import TavilyClient
from app.clients.xai_client import get_xai_client
from app.db.session import get_session_factory
from app.models import (
    AnalysisRequest,
    AnalysisRun,
    Document,
    FactClaim,
    Factor,
    Market,
    Passage,
    RuleParse,
    SocialIntelSummary,
    Source,
)
from app.models.enums import (
    ClaimTypeEnum,
    ClaimFamilyEnum,
    ConfidenceLabelEnum,
    ConsensusLabelEnum,
    ConsensusStrengthEnum,
    DirectnessEnum,
    EvidenceRoleEnum,
    InputTypeEnum,
    NarrativePhaseEnum,
    PricedInRiskLabelEnum,
    QualitativeLabelEnum,
    RecommendationLabelEnum,
    RequestStatusEnum,
    SourceKindEnum,
    SourceTierEnum,
    StanceEnum,
    StrengthEnum,
    TemplateKey,
    VerifierStatusEnum,
)
from app.services.pipeline_models import (
    BriefDraft,
    EvidenceRoleDraft,
    ExtractedFactDraft,
    FactorMappingDraft,
    RecommendationDraft,
    RuleParseDraft,
    SearchSourceDraft,
    SocialIntelDraft,
    TrustedSocialPostDraft,
    VerifiedFactDraft,
)
from app.services.analysis_scoring import (
    BASE_UNCERTAINTY,
    DIRECTNESS_MULTIPLIERS,
    SOURCE_WEIGHTS,
    STRENGTH_MULTIPLIERS,
    TEMPLATE_MULTIPLIERS,
    VERIFICATION_MULTIPLIERS,
    capped_evidence_score,
    factor_used_in_scoring,
    has_contradictory_factors,
    logit,
    sigmoid,
    social_uncertainty_adjustment,
    source_is_factor_eligible,
)
from app.services.analysis_stage_briefing import run_briefing_stage
from app.services.analysis_stage_fact_pipeline import run_fact_pipeline_stage
from app.services.analysis_stage_retrieval_grounding import run_retrieval_grounding_stage
from app.services.analysis_stage_rule_parse import run_rule_parse_stage
from app.services.analysis_stage_scoring import run_scoring_stage
from app.services.analysis_progress import (
    STAGE_CONFIG_BY_KEY,
    initial_progress_payload,
    mark_stage_complete,
    mark_stage_failed,
    mark_stage_running,
    mark_stage_skipped,
)
from app.services.prompt_loader import load_prompt

POSITIVE_KEYWORDS = {
    "approve",
    "approved",
    "approval",
    "announced",
    "confirm",
    "confirmed",
    "filed",
    "cut",
    "lowered",
    "launched",
    "scheduled",
    "wins",
    "won",
}

STOPWORDS = {
    "a",
    "an",
    "against",
    "and",
    "by",
    "can",
    "could",
    "did",
    "does",
    "for",
    "her",
    "his",
    "is",
    "of",
    "on",
    "its",
    "should",
    "the",
    "their",
    "to",
    "will",
    "would",
}

LEADING_QUESTION_WORDS = {
    "can",
    "could",
    "did",
    "does",
    "is",
    "should",
    "will",
    "would",
}

SEARCH_ALIAS_REPLACEMENTS = {
    r"\bdod\b": "department of defense pentagon department of war",
    r"\bdept\.?\s+of defense\b": "department of defense pentagon department of war",
    r"\bdepartment of war\b": "department of defense pentagon",
    r"\bpentagon\b": "department of defense dod department of war",
    r"\bscotus\b": "supreme court",
    r"\beo\b": "executive order",
}

LEGAL_SEARCH_HINTS = (
    "lawsuit",
    "complaint",
    "injunction",
    "court",
    "judge",
)

LOW_SIGNAL_PHRASES = {
    "skip to main content",
    "official websites use .gov",
    "here's how you know",
    "subscribe to rss",
    "subscribe to email",
    "board of governors of the federal reserve system",
}

TIMING_KEYWORDS = {
    "expected by",
    "by the end of",
    "early july",
    "late june",
    "next week",
    "this week",
    "in 30 days",
    "on jan",
    "on april",
    "on june",
    "on july",
}

PROCEDURAL_KEYWORDS = {
    "oral argument",
    "oral arguments",
    "heard arguments",
    "hearing",
    "appeal",
    "petition",
    "certiorari",
    "challenge to",
    "class action",
    "injunction",
    "preliminary injunction",
    "lawsuit",
    "case now before",
    "before the court",
    "motion",
    "briefing",
}

LEGAL_MERITS_YES = {
    "unconstitutional",
    "likely to side against",
    "likely to strike down",
    "appeared skeptical",
    "skeptical of the eo",
    "skeptical of the order",
    "contradicts the fourteenth amendment",
    "flouts the constitution",
    "barred the trump administration from enforcing",
    "blocked the trump administration from implementing",
    "ruled that the order is unconstitutional",
    "would strike it down",
    "won a preliminary injunction",
    "wins preliminary injunction",
    "granted a preliminary injunction",
    "granted preliminary injunction",
    "prevailed against",
    "won the lawsuit",
    "wins the lawsuit",
    "upheld a block on",
    "upholds a block on",
    "upheld block on",
    "upholds block on",
    "blocked the executive order",
    "blocked the order",
    "violates the constitution",
    "conflicts with the constitution",
    "court sided with anthropic",
}

LEGAL_MERITS_NO = {
    "likely to uphold",
    "uphold the executive order",
    "constitutional",
    "lawful exercise",
    "side with trump",
    "allow enforcement",
    "reverse the injunction",
    "let the order take effect",
    "denied a preliminary injunction",
    "denied preliminary injunction",
    "dismissed the lawsuit",
    "dismissed the case",
    "lost the lawsuit",
    "loses the lawsuit",
    "court sided with the government",
}

LEGAL_BACKGROUND_KEYWORDS = {
    "signed an executive order",
    "issued the executive order",
    "would end birthright citizenship",
    "first day of his second term",
    "challenge to president donald trump",
    "trump floated the prospect",
    "executive order",
    "order declares",
    "order indicated",
    "section 1",
    "birthright citizenship does not extend",
    "protecting the meaning and value of american citizenship",
    "does not itself direct any immediate action",
}

LEGAL_COMMENTARY_CUES = {
    "appeared skeptical",
    "seemed likely",
    "likely to side",
    "likely to strike down",
    "likely to uphold",
    "expected to",
    "prediction",
    "forecast",
    "readout",
}

LEGAL_DECISION_SIGNALS = {
    "ruled",
    "held",
    "holding",
    "opinion",
    "decision",
    "unconstitutional",
    "constitutional",
    "invalid",
    "invalidate",
    "struck down",
    "strike down",
    "upheld",
    "uphold",
    "blocked enforcement",
    "barred the trump administration from enforcing",
    "enjoined",
    "contradicts the fourteenth amendment",
    "violates the fourteenth amendment",
    "likely to side",
    "appeared skeptical",
    "granted preliminary injunction",
    "denied preliminary injunction",
    "dismissed the lawsuit",
    "dismissed the case",
    "won the lawsuit",
    "lost the lawsuit",
    "prevailed against",
}

LEGAL_MERITS_DEFERRAL_CUES = {
    "did not weigh in on",
    "did not weigh in",
    "did not decide whether",
    "did not address whether",
    "did not rule on whether",
    "without reaching the merits",
    "without reaching the question",
    "without deciding whether",
}

LEGAL_INJUNCTION_SCOPE_CUES = {
    "nationwide injunction",
    "nationwide injunctions",
    "universal preliminary injunction",
    "universal preliminary injunctions",
    "scope of the injunction",
    "scope of injunction",
    "broader than necessary",
    "broader than required",
}

NUMERIC_REQUIRED_SOURCE_TIERS = {
    SourceTierEnum.OFFICIAL_PRIMARY,
    SourceTierEnum.OFFICIAL_STATEMENT,
    SourceTierEnum.EXPERT_ANALYSIS,
    SourceTierEnum.REPUTABLE_NEWS,
}

NEGATIVE_KEYWORDS = {
    "delay",
    "delayed",
    "denied",
    "held",
    "hold",
    "rejected",
    "unlikely",
    "paused",
    "canceled",
    "cancelled",
    "won't",
    "will not",
    "no cut",
}

MACRO_EASING_SUPPORT_PHRASES = {
    "cut odds",
    "cuts are priced",
    "cuts priced",
    "cuts later this year",
    "earlier easing",
    "easing path",
    "easing cycle",
    "easing bias",
    "sooner cut",
    "softer labor",
    "labor-market softening",
    "labor market softening",
    "cooling inflation",
    "inflation cools",
    "inflation cooled",
    "inflation easing",
    "disinflation",
    "dovish",
    "recession risk",
}

MACRO_EASING_CONTRADICTION_PHRASES = {
    "no cut",
    "no cuts",
    "no longer expected to cut",
    "cuts pushed back",
    "cuts are off the table",
    "higher for longer",
    "hawkish",
    "rate hike",
    "rate hikes",
    "hike odds",
    "hikes now > cuts",
    "hold rates",
    "holds rates",
    "held rates",
    "rates unchanged",
    "remain unchanged",
    "remains unchanged",
    "sticky inflation",
    "hot inflation",
}

MACRO_COOLING_CUES = {"cool", "cooled", "cooling", "ease", "eased", "easing", "slow", "slowed", "slowing", "soft", "softened", "softening"}
MACRO_HOT_CUES = {
    "accelerate",
    "accelerated",
    "accelerating",
    "heat",
    "heated",
    "heating",
    "hot",
    "resilient",
    "rise",
    "rising",
    "rose",
    "sticky",
    "strong",
}

SEARCH_LIMIT = 4
LIVE_SOCIAL_LIMIT = 6
SOCIAL_FACTOR_TIERS = {SourceTierEnum.OFFICIAL_SOCIAL, SourceTierEnum.HIGH_TRUST_SOCIAL}
MAX_GROUNDED_CONTEXTS = 12
MAX_DOCUMENT_CHARS = 18000
TARGET_PASSAGE_CHARS = 900
MIN_PASSAGE_CHARS = 160
MAX_PASSAGES_PER_SOURCE = 6
PASSAGES_FOR_EXTRACTION = 3


class FactExtractionResult(BaseModel):
    facts: list[ExtractedFactDraft] = Field(default_factory=list)


@dataclass
class SourceContext:
    source: Source
    possible_facts: list[str]
    document: Document | None = None
    passages: list[Passage] = field(default_factory=list)


@dataclass
class RetrievalResult:
    source_contexts: list[SourceContext]
    social_intel_summary: SocialIntelSummary | None


@dataclass
class ScoreOutcome:
    recommendation: RecommendationDraft
    priced_in_risk: PricedInRiskLabelEnum
    p_hat: float | None
    p_low: float | None
    p_high: float | None
    numeric_estimate_available: bool
    numeric_estimate_reason: str | None
    qualitative_label: QualitativeLabelEnum | None


class AnalysisProcessor:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
        enable_remote_calls: bool = True,
        openai_client: Any | None = None,
        xai_client: Any | None = None,
        tavily_client: TavilyClient | None = None,
        polymarket_client: PolymarketClient | None = None,
    ) -> None:
        self.session_factory = session_factory or get_session_factory()
        self.enable_remote_calls = enable_remote_calls
        self.openai_client = openai_client or get_openai_client(enabled=enable_remote_calls)
        self.xai_client = xai_client or get_xai_client(enabled=enable_remote_calls)
        self.tavily_client = tavily_client or TavilyClient(enabled=enable_remote_calls)
        self.polymarket_client = polymarket_client or PolymarketClient(enabled=enable_remote_calls)

    def process_request(self, request_id: int) -> None:
        try:
            with self.session_factory() as session:
                request = session.get(AnalysisRequest, request_id)
                if request is None:
                    return
                self._mark_running(session, request)

            with self.session_factory() as session:
                request = session.get(AnalysisRequest, request_id)
                if request is None:
                    return

                mark_stage_complete(
                    request,
                    "normalize",
                    "Request input normalized and the pipeline is ready to gather context.",
                )
                session.add(request)
                session.commit()
                market, rule_parse, analysis_run = run_rule_parse_stage(
                    self,
                    session=session,
                    request=request,
                )
                retrieval_result = run_retrieval_grounding_stage(
                    self,
                    session=session,
                    request=request,
                    market=market,
                    analysis_run=analysis_run,
                    rule_parse=rule_parse,
                )
                facts, factors = run_fact_pipeline_stage(
                    self,
                    session=session,
                    request=request,
                    rule_parse=rule_parse,
                    analysis_run=analysis_run,
                    source_contexts=retrieval_result.source_contexts,
                )
                score_outcome = run_scoring_stage(
                    self,
                    session=session,
                    request=request,
                    market=market,
                    rule_parse=rule_parse,
                    source_contexts=retrieval_result.source_contexts,
                    social_intel_summary=retrieval_result.social_intel_summary,
                    facts=facts,
                    factors=factors,
                )
                run_briefing_stage(
                    self,
                    session=session,
                    request=request,
                    market=market,
                    rule_parse=rule_parse,
                    analysis_run=analysis_run,
                    retrieval_result=retrieval_result,
                    factors=factors,
                    score_outcome=score_outcome,
                )
        except Exception as exc:  # pragma: no cover - exercised through API behavior
            with self.session_factory() as session:
                request = session.get(AnalysisRequest, request_id)
                if request is None:
                    return
                failed_stage = (
                    request.current_stage
                    if request.current_stage in STAGE_CONFIG_BY_KEY
                    else "normalize"
                )
                mark_stage_failed(
                    request,
                    failed_stage,
                    f"Stopped here because the pipeline raised an error: {str(exc)[:240]}",
                )
                request.status = RequestStatusEnum.FAILED
                request.error_message = str(exc)[:2000]
                request.completed_at = datetime.now(UTC)
                session.add(request)
                session.commit()

    def _mark_running(self, session: Session, request: AnalysisRequest) -> None:
        request.progress_json = initial_progress_payload()
        request.status = RequestStatusEnum.RUNNING
        request.error_message = None
        request.started_at = datetime.now(UTC)
        request.completed_at = None
        mark_stage_running(
            request,
            "normalize",
            "Normalizing the request and deciding which pipeline steps are required.",
        )
        session.add(request)
        session.commit()

    def _resolve_market(self, session: Session, request: AnalysisRequest) -> Market | None:
        if request.market_id:
            market = session.get(Market, request.market_id)
            if market is not None:
                mark_stage_skipped(
                    request,
                    "market_lookup",
                    "Using the market already linked to this request.",
                )
                session.add(request)
                session.commit()
                return market

        if request.input_type == InputTypeEnum.CUSTOM_CLAIM:
            mark_stage_skipped(
                request,
                "market_lookup",
                "No Polymarket lookup was required for a free-form custom claim.",
            )
            session.add(request)
            session.commit()
            return None

        session.add(request)
        session.flush()
        mark_stage_running(
            request,
            "market_lookup",
            "Resolving Polymarket market metadata and live pricing context.",
        )
        session.commit()

        resolved_market: ResolvedMarketRecord | None = None
        if request.input_type == InputTypeEnum.MARKET_ID:
            resolved_market = self.polymarket_client.get_market_by_id(request.input_text)
        elif request.input_type == InputTypeEnum.MARKET_URL:
            resolved_market = self.polymarket_client.get_market_by_url(request.input_text)

        if resolved_market is None:
            mark_stage_complete(
                request,
                "market_lookup",
                "No matching Polymarket market metadata was found, so the run will continue without linked market context.",
            )
            session.add(request)
            session.commit()
            return None

        market = session.scalar(
            select(Market).where(Market.polymarket_id == resolved_market.polymarket_id)
        )
        if market is None:
            market = Market(polymarket_id=resolved_market.polymarket_id, title=resolved_market.title)
            session.add(market)
            session.flush()

        market.title = resolved_market.title
        market.url = resolved_market.url
        market.rules_text = resolved_market.rules_text
        market.description = resolved_market.description
        market.yes_bid = resolved_market.yes_bid
        market.yes_ask = resolved_market.yes_ask
        market.no_bid = resolved_market.no_bid
        market.no_ask = resolved_market.no_ask
        market.liquidity = resolved_market.liquidity
        market.volume_24h = resolved_market.volume_24h
        market.spread = resolved_market.spread
        market.expiry_at = resolved_market.expiry_at
        market.status = resolved_market.status
        request.market_id = market.id
        session.add_all([market, request])
        mark_stage_complete(
            request,
            "market_lookup",
            f"Loaded market context for {market.title}.",
        )
        session.commit()
        session.refresh(market)
        return market

    def _build_rule_parse(
        self,
        session: Session,
        request: AnalysisRequest,
        market: Market | None,
    ) -> RuleParseDraft:
        context_parts = [
            f"request_mode: {request.mode.value}",
            f"input_type: {request.input_type.value}",
            f"input_text: {request.input_text}",
        ]
        if request.template_requested is not None:
            context_parts.append(f"template_requested: {request.template_requested.value}")
        input_payload = request.input_payload or {}
        if input_payload.get("deadline_text"):
            context_parts.append(f"deadline_text: {input_payload['deadline_text']}")
        if market is not None:
            context_parts.extend(
                [
                    f"market_title: {market.title}",
                    f"market_rules: {market.rules_text or ''}",
                    f"market_description: {market.description or ''}",
                    f"market_expiry: {market.expiry_at.isoformat() if market.expiry_at else ''}",
                ]
            )
        prompt = load_prompt("rule_parse_v1.txt").replace("{{context}}", "\n".join(context_parts))

        mark_stage_running(
            request,
            "rule_parse",
            "Interpreting the rules, deadline, and resolution logic.",
        )
        session.add(request)
        session.commit()

        if self.openai_client.is_configured:
            try:
                return self.openai_client.generate_structured(
                    session=session,
                    task_name="rule_parse",
                    prompt_version="rule_parse_v1",
                    system_prompt="Return conservative structured JSON only.",
                    user_prompt=prompt,
                    schema_model=RuleParseDraft,
                )
            except Exception:
                pass

        return self._fallback_rule_parse(request, market)

    def _persist_rule_parse(
        self,
        session: Session,
        request: AnalysisRequest,
        market: Market | None,
        rule_parse: RuleParseDraft,
    ) -> RuleParse:
        db_rule_parse = RuleParse(
            analysis_request_id=request.id,
            market_id=market.id if market else None,
            question_text=rule_parse.question_text,
            event=rule_parse.event,
            entity_names=rule_parse.entity_names,
            action=rule_parse.action,
            claim_family=rule_parse.claim_family,
            yes_condition=rule_parse.yes_condition,
            no_condition=rule_parse.no_condition,
            deadline_text=rule_parse.deadline_text,
            deadline_utc=rule_parse.deadline_utc,
            timezone_text=rule_parse.timezone_text,
            resolution_definition=rule_parse.resolution_definition,
            directional_scoring_policy=rule_parse.directional_scoring_policy,
            official_resolution_source=rule_parse.official_resolution_source,
            fallback_sources=rule_parse.fallback_sources,
            official_domains=rule_parse.official_domains,
            ambiguity_flags=rule_parse.ambiguity_flags,
            clarity_score=rule_parse.clarity_score,
            resolution_risk=rule_parse.resolution_risk,
            suitable_for_auto=rule_parse.suitable_for_auto,
            template_detected=rule_parse.template_detected,
            created_at=datetime.now(UTC),
        )
        session.add(db_rule_parse)
        session.commit()
        session.refresh(db_rule_parse)
        mark_stage_complete(
            request,
            "rule_parse",
            (
                f"Detected the {rule_parse.template_detected.value} template "
                f"with clarity {rule_parse.clarity_score:.2f}."
            ),
        )
        session.add(request)
        session.commit()
        return db_rule_parse

    def _create_run(
        self,
        session: Session,
        request: AnalysisRequest,
        market: Market | None,
        rule_parse: RuleParse,
    ) -> AnalysisRun:
        recommendation_label = (
            RecommendationLabelEnum.ANALYSIS_ONLY
            if market is None or market.yes_ask is None or market.no_ask is None
            else RecommendationLabelEnum.NEEDS_MORE_RESEARCH
        )
        run = AnalysisRun(
            request_id=request.id,
            market_id=market.id if market else None,
            rule_parse_id=rule_parse.id,
            template_selected=rule_parse.template_detected,
            market_mid_prob=self._market_prior(market),
            yes_exec_price=market.yes_ask if market else None,
            no_exec_price=market.no_ask if market else None,
            priced_in_risk_label=PricedInRiskLabelEnum.MEDIUM,
            numeric_estimate_available=False,
            numeric_estimate_reason="Scoring has not finished yet.",
            qualitative_label=None,
            p_hat=None,
            p_low=None,
            p_high=None,
            confidence_label=ConfidenceLabelEnum.LOW,
            recommendation_label=recommendation_label,
            created_at=datetime.now(UTC),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    def _retrieve_sources(
        self,
        session: Session,
        request: AnalysisRequest,
        market: Market | None,
        analysis_run: AnalysisRun,
        rule_parse: RuleParse,
    ) -> RetrievalResult:
        mark_stage_running(
            request,
            "retrieval",
            "Searching official, news, and supporting source lanes.",
        )
        session.add(request)
        session.commit()

        contexts: list[SourceContext] = []
        social_intel_summary: SocialIntelSummary | None = None
        now = datetime.now(UTC)

        if request.input_type == InputTypeEnum.CUSTOM_CLAIM:
            source = Source(
                analysis_run_id=analysis_run.id,
                url=None,
                domain=None,
                title="Manual claim input",
                source_kind=SourceKindEnum.MANUAL_INPUT,
                source_tier=SourceTierEnum.GENERIC_SOCIAL,
                fetched_at=now,
                content_hash=self._hash_text(request.input_text),
                excerpt=request.input_text,
                canonical_url=None,
                is_paywalled=False,
                metadata_json={"input_context_only": True},
                created_at=now,
            )
            session.add(source)
            session.flush()
            contexts.append(SourceContext(source=source, possible_facts=[]))

        if market is not None and (market.rules_text or market.description):
            excerpt = "\n".join(part for part in [market.rules_text, market.description] if part)
            source = Source(
                analysis_run_id=analysis_run.id,
                url=market.url,
                domain=self._domain_from_url(market.url),
                title=f"Market context: {market.title}",
                source_kind=SourceKindEnum.MANUAL_INPUT,
                source_tier=SourceTierEnum.OFFICIAL_STATEMENT,
                fetched_at=now,
                content_hash=self._hash_text(excerpt),
                excerpt=excerpt,
                canonical_url=market.url,
                is_paywalled=False,
                metadata_json={"market_source": True},
                created_at=now,
            )
            session.add(source)
            session.flush()
            contexts.append(SourceContext(source=source, possible_facts=[]))

        if self._should_run_live_x_intelligence(request, rule_parse):
            social_intel_summary, live_social_contexts = self._retrieve_live_social_intelligence(
                session,
                request=request,
                analysis_run=analysis_run,
                rule_parse=rule_parse,
            )
            contexts.extend(live_social_contexts)
        else:
            mark_stage_skipped(
                request,
                "social_intelligence",
                "Live X intelligence was not requested for this run.",
            )
            session.add(request)
            session.commit()

        search_results = self._search_results_for_rule_parse(rule_parse)
        for result in search_results:
            if not self._should_include_search_result(request, result):
                continue
            source_tier = result.source_tier
            source_kind = (
                SourceKindEnum.OFFICIAL
                if source_tier in {SourceTierEnum.OFFICIAL_PRIMARY, SourceTierEnum.OFFICIAL_STATEMENT}
                else (
                    SourceKindEnum.PREMIUM_NEWS
                    if source_tier == SourceTierEnum.PREMIUM_NEWS
                    else SourceKindEnum.NEWS
                )
            )
            source = Source(
                analysis_run_id=analysis_run.id,
                url=result.url,
                domain=result.domain or self._domain_from_url(result.url),
                title=result.title,
                source_kind=source_kind,
                source_tier=source_tier,
                published_at=result.published_at,
                fetched_at=now,
                content_hash=self._hash_text(result.excerpt),
                excerpt=result.excerpt,
                canonical_url=result.url,
                is_paywalled=result.is_paywalled,
                metadata_json=result.metadata_json,
                created_at=now,
            )
            session.add(source)
            session.flush()
            contexts.append(SourceContext(source=source, possible_facts=[]))

        grounded_contexts = self._ground_source_contexts(
            session=session,
            request=request,
            analysis_run=analysis_run,
            rule_parse=rule_parse,
            contexts=contexts[:MAX_GROUNDED_CONTEXTS],
        )
        source_kind_counts = Counter(
            source_context.source.source_kind.value for source_context in grounded_contexts
        )
        grounded_passage_count = sum(len(source_context.passages) for source_context in grounded_contexts)
        retrieval_note = (
            f"Collected {len(grounded_contexts)} source(s): "
            f"{source_kind_counts.get('official', 0)} official, "
            f"{source_kind_counts.get('news', 0)} news, "
            f"{source_kind_counts.get('premium_news', 0)} premium, "
            f"{source_kind_counts.get('live_social', 0) + source_kind_counts.get('manual_social', 0)} social. "
            f"Grounded them into {grounded_passage_count} ranked passage(s) for extraction."
        )
        mark_stage_complete(request, "retrieval", retrieval_note)
        session.commit()
        return RetrievalResult(
            source_contexts=grounded_contexts,
            social_intel_summary=social_intel_summary,
        )

    def _search_results_for_rule_parse(
        self,
        rule_parse: RuleParse,
    ) -> list[SearchSourceDraft]:
        ranked_by_url: dict[str, tuple[float, SearchSourceDraft]] = {}

        for search_request in self._search_requests(rule_parse):
            results = self.tavily_client.search(
                query=search_request["query"],
                max_results=search_request["max_results"],
                include_domains=search_request.get("include_domains"),
                topic=search_request["topic"],
            )
            for result in results:
                score = self._search_result_relevance(rule_parse, result)
                current = ranked_by_url.get(result.url)
                if current is None or score > current[0]:
                    ranked_by_url[result.url] = (score, result)

        ranked = sorted(
            ranked_by_url.values(),
            key=lambda item: (
                -item[0],
                item[1].source_tier
                not in {SourceTierEnum.OFFICIAL_PRIMARY, SourceTierEnum.OFFICIAL_STATEMENT},
                item[1].is_paywalled,
            ),
        )
        return [result for _, result in ranked[:SEARCH_LIMIT]]

    def _search_requests(self, rule_parse: RuleParse) -> list[dict[str, Any]]:
        topic = "news" if rule_parse.template_detected == TemplateKey.MACRO_POLICY else "general"
        if rule_parse.template_detected == TemplateKey.LEGAL_CASE:
            legal_query = self._legal_search_query(rule_parse)
            official_domains = rule_parse.official_domains[:4]
            return [
                {
                    "query": legal_query,
                    "max_results": max(SEARCH_LIMIT + 2, 6),
                    "include_domains": None,
                    "topic": "general",
                },
                {
                    "query": f"{legal_query} docket order filing",
                    "max_results": SEARCH_LIMIT,
                    "include_domains": official_domains,
                    "topic": "general",
                },
            ]

        include_domains = (
            rule_parse.official_domains[:4]
            if rule_parse.template_detected in {TemplateKey.OFFICIAL_EVENT, TemplateKey.MACRO_POLICY}
            else None
        )
        return [
            {
                "query": rule_parse.question_text,
                "max_results": SEARCH_LIMIT,
                "include_domains": include_domains,
                "topic": topic,
            }
        ]

    def _legal_search_query(self, rule_parse: RuleParse) -> str:
        question = self._expand_search_aliases(rule_parse.question_text.rstrip("?"))
        parties = self._extract_legal_parties(rule_parse.question_text)
        if parties is None:
            return " ".join([question, *LEGAL_SEARCH_HINTS])

        plaintiff, defendant = parties
        defendant_aliases = self._expand_search_aliases(defendant)
        plaintiff_aliases = self._expand_search_aliases(plaintiff)
        return " ".join([plaintiff_aliases, defendant_aliases, *LEGAL_SEARCH_HINTS])

    def _search_result_relevance(
        self,
        rule_parse: RuleParse,
        result: SearchSourceDraft,
    ) -> float:
        haystack = self._normalize_source_text(result.title, result.excerpt, result.url)
        expanded_haystack = self._expand_search_aliases(haystack)
        lowered = expanded_haystack.lower()
        result_terms = self._signal_terms(expanded_haystack)
        question_terms = self._signal_terms(self._expand_search_aliases(rule_parse.question_text))
        yes_terms = self._signal_terms(self._expand_search_aliases(rule_parse.yes_condition))
        no_terms = self._signal_terms(self._expand_search_aliases(rule_parse.no_condition))

        score = 0.0
        score += len(result_terms.intersection(question_terms)) * 0.35
        score += len(result_terms.intersection(yes_terms)) * 0.2
        score += len(result_terms.intersection(no_terms)) * 0.2

        if rule_parse.action and rule_parse.action.lower() in lowered:
            score += 0.35

        for entity in rule_parse.entity_names:
            expanded = self._expand_search_aliases(entity).lower()
            if expanded and expanded in lowered:
                score += 0.65

        if rule_parse.template_detected == TemplateKey.LEGAL_CASE:
            for keyword in LEGAL_SEARCH_HINTS:
                if keyword in lowered:
                    score += 0.12

        if result.source_tier in {SourceTierEnum.OFFICIAL_PRIMARY, SourceTierEnum.OFFICIAL_STATEMENT}:
            score += 0.1

        return round(score, 4)

    @staticmethod
    def _should_include_search_result(
        request: AnalysisRequest,
        result: SearchSourceDraft,
    ) -> bool:
        if result.source_tier != SourceTierEnum.PREMIUM_NEWS:
            return True
        payload = request.input_payload or {}
        return bool(payload.get("include_premium"))

    def _ground_source_contexts(
        self,
        *,
        session: Session,
        request: AnalysisRequest,
        analysis_run: AnalysisRun,
        rule_parse: RuleParse,
        contexts: list[SourceContext],
    ) -> list[SourceContext]:
        if not contexts:
            return []

        mark_stage_running(
            request,
            "retrieval",
            f"Grounding {len(contexts)} source(s) into cleaned documents and ranked passages.",
        )
        session.add(request)
        session.commit()

        grounded_contexts: list[SourceContext] = []
        for context in contexts:
            document_text, extractor = self._build_grounded_document_text(context.source)
            document = Document(
                analysis_run_id=analysis_run.id,
                source_id=context.source.id,
                canonical_url=context.source.canonical_url or context.source.url,
                title=context.source.title,
                domain=context.source.domain,
                extractor=extractor,
                content_text=document_text,
                content_hash=self._hash_text(document_text),
                word_count=len(document_text.split()),
                fetched_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
            session.add(document)
            session.flush()

            ranked_passages = self._ranked_passage_texts(
                rule_parse=rule_parse,
                source=context.source,
                document_text=document_text,
            )
            passages: list[Passage] = []
            for passage_index, (passage_text, relevance_score) in enumerate(
                ranked_passages,
                start=1,
            ):
                passage = Passage(
                    analysis_run_id=analysis_run.id,
                    source_id=context.source.id,
                    document_id=document.id,
                    passage_index=passage_index,
                    relevance_score=relevance_score,
                    text=passage_text,
                    created_at=datetime.now(UTC),
                )
                session.add(passage)
                session.flush()
                passages.append(passage)

            context.document = document
            context.passages = passages
            grounded_contexts.append(context)

        session.commit()
        return grounded_contexts

    def _build_grounded_document_text(self, source: Source) -> tuple[str, str]:
        raw_text = (
            source.metadata_json.get("raw_text")
            if isinstance(source.metadata_json, dict)
            else None
        )
        fallback_text = self._normalize_source_text(
            raw_text,
            source.excerpt,
            source.title,
            source.url,
        )
        should_fetch_remote = (
            self.enable_remote_calls
            and bool(source.url)
            and source.source_kind
            in {
                SourceKindEnum.OFFICIAL,
                SourceKindEnum.NEWS,
                SourceKindEnum.PREMIUM_NEWS,
            }
        )
        if not should_fetch_remote or not source.url:
            return fallback_text, "excerpt_fallback"

        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=6.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; PolymarketCopilot/0.1; +https://polymarket.com)"
                    )
                },
            ) as client:
                response = client.get(source.url)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                candidate_text = ""
                if "html" in content_type or "xml" in content_type or content_type.startswith("text/"):
                    extracted = trafilatura.extract(
                        response.text,
                        include_comments=False,
                        include_tables=False,
                        include_formatting=False,
                        favor_recall=True,
                        url=source.url,
                    )
                    candidate_text = self._normalize_source_text(extracted)
                    if not candidate_text and content_type.startswith("text/plain"):
                        candidate_text = self._normalize_source_text(response.text)
                if len(candidate_text) >= max(300, len(fallback_text) // 2):
                    return candidate_text, "trafilatura"
        except Exception:
            pass

        return fallback_text, "excerpt_fallback"

    def _ranked_passage_texts(
        self,
        *,
        rule_parse: RuleParse,
        source: Source,
        document_text: str,
    ) -> list[tuple[str, float]]:
        chunks = self._chunk_grounded_text(document_text)
        if not chunks:
            chunks = [self._normalize_source_text(source.excerpt)]
        ranked = [
            (
                chunk,
                self._score_passage_relevance(
                    rule_parse=rule_parse,
                    source=source,
                    passage_text=chunk,
                ),
            )
            for chunk in chunks
            if chunk
        ]
        ranked.sort(key=lambda item: (-item[1], -len(item[0])))
        return ranked[:MAX_PASSAGES_PER_SOURCE]

    def _chunk_grounded_text(self, text: str) -> list[str]:
        normalized = self._normalize_source_text(text)
        if not normalized:
            return []

        segments = [
            segment.strip()
            for segment in re.split(r"\n{2,}", normalized)
            if segment and segment.strip()
        ]
        if not segments:
            segments = [
                segment.strip()
                for segment in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", normalized)
                if segment and segment.strip()
            ]

        expanded_segments: list[str] = []
        for segment in segments:
            if len(segment) <= TARGET_PASSAGE_CHARS * 1.4:
                expanded_segments.append(segment)
                continue
            sentences = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", segment)
                if sentence and sentence.strip()
            ]
            if len(sentences) <= 1:
                expanded_segments.append(segment)
            else:
                expanded_segments.extend(sentences)

        chunks: list[str] = []
        current: list[str] = []
        current_length = 0
        for segment in expanded_segments:
            segment_length = len(segment)
            if current and current_length + segment_length + 2 > TARGET_PASSAGE_CHARS:
                chunk = " ".join(current).strip()
                if chunk:
                    chunks.append(chunk)
                current = [segment]
                current_length = segment_length
                continue
            current.append(segment)
            current_length += segment_length + (2 if current_length else 0)

        if current:
            chunk = " ".join(current).strip()
            if chunk:
                chunks.append(chunk)

        deduped: list[str] = []
        seen_chunks: set[str] = set()
        for chunk in chunks or [normalized[:TARGET_PASSAGE_CHARS]]:
            cleaned = self._normalize_source_text(chunk)
            if not cleaned:
                continue
            if len(cleaned) < MIN_PASSAGE_CHARS and deduped:
                deduped[-1] = self._normalize_source_text(f"{deduped[-1]} {cleaned}")
                continue
            if cleaned in seen_chunks:
                continue
            seen_chunks.add(cleaned)
            deduped.append(cleaned)
        return deduped[:MAX_PASSAGES_PER_SOURCE]

    def _score_passage_relevance(
        self,
        *,
        rule_parse: RuleParse,
        source: Source,
        passage_text: str,
    ) -> float:
        passage_terms = self._signal_terms(self._expand_search_aliases(passage_text))
        question_terms = self._signal_terms(self._expand_search_aliases(rule_parse.question_text))
        yes_terms = self._signal_terms(self._expand_search_aliases(rule_parse.yes_condition))
        no_terms = self._signal_terms(self._expand_search_aliases(rule_parse.no_condition))
        score = 0.0
        score += len(passage_terms.intersection(question_terms)) * 0.35
        score += len(passage_terms.intersection(yes_terms)) * 0.55
        score += len(passage_terms.intersection(no_terms)) * 0.55

        lowered = self._expand_search_aliases(passage_text).lower()
        if rule_parse.action and rule_parse.action.lower() in lowered:
            score += 0.3
        for entity in rule_parse.entity_names:
            if self._expand_search_aliases(entity).lower() in lowered:
                score += 0.35
        if source.source_tier in {
            SourceTierEnum.OFFICIAL_PRIMARY,
            SourceTierEnum.OFFICIAL_STATEMENT,
        }:
            score += 0.15
        return round(score, 4)

    def _passage_context_text(self, source_context: SourceContext) -> str:
        if source_context.passages:
            return "\n\n".join(
                [
                    (
                        f"[passage {passage.passage_index} | relevance {passage.relevance_score:.2f}] "
                        f"{passage.text}"
                    )
                    for passage in source_context.passages[:PASSAGES_FOR_EXTRACTION]
                ]
            )
        return source_context.source.excerpt

    def _best_matching_passage(
        self,
        source_context: SourceContext,
        fact_text: str,
        quote_text: str | None = None,
    ) -> Passage | None:
        if not source_context.passages:
            return None

        best_passage: Passage | None = None
        best_score = -1.0
        for passage in source_context.passages:
            score = self._passage_match_score(passage.text, fact_text, quote_text or "")
            if score > best_score:
                best_score = score
                best_passage = passage

        return best_passage or source_context.passages[0]

    @classmethod
    def _passage_match_score(cls, passage_text: str, fact_text: str, quote_text: str) -> float:
        lowered_passage = passage_text.lower()
        lowered_quote = quote_text.lower().strip()
        score = 0.0
        if lowered_quote and lowered_quote in lowered_passage:
            score += 5.0
        fact_terms = cls._signal_terms(fact_text)
        quote_terms = cls._signal_terms(quote_text)
        passage_terms = cls._signal_terms(passage_text)
        score += len(fact_terms.intersection(passage_terms)) * 0.6
        score += len(quote_terms.intersection(passage_terms)) * 0.9
        return score

    def _extract_and_verify_facts(
        self,
        session: Session,
        request: AnalysisRequest,
        rule_parse: RuleParse,
        analysis_run: AnalysisRun,
        source_contexts: list[SourceContext],
    ) -> list[FactClaim]:
        mark_stage_running(
            request,
            "fact_extraction",
            "Extracting structured claims from the gathered sources.",
        )
        session.add(request)
        session.commit()

        extracted_fact_inputs: list[tuple[SourceContext, int, ExtractedFactDraft]] = []
        for context in source_contexts:
            extracted_facts = self._extract_facts_for_source(
                session,
                rule_parse=rule_parse,
                source_context=context,
            )
            for index, fact_draft in enumerate(extracted_facts):
                extracted_fact_inputs.append((context, index, fact_draft))

        mark_stage_complete(
            request,
            "fact_extraction",
            f"Extracted {len(extracted_fact_inputs)} claim candidate(s) from {len(source_contexts)} source(s).",
        )
        mark_stage_running(
            request,
            "fact_verification",
            "Verifying extracted claims against source context before scoring.",
        )
        session.add(request)
        session.commit()

        facts: list[FactClaim] = []
        for context, index, fact_draft in extracted_fact_inputs:
            verification = self._verify_fact(
                session,
                rule_parse=rule_parse,
                source_context=context,
                fact=fact_draft,
            )
            matched_passage = self._best_matching_passage(
                context,
                fact_draft.normalized_fact,
                fact_draft.exact_quote,
            )
            fact = FactClaim(
                analysis_run_id=analysis_run.id,
                source_id=context.source.id,
                passage_id=matched_passage.id if matched_passage else None,
                normalized_fact=fact_draft.normalized_fact,
                exact_quote=fact_draft.exact_quote,
                claim_type=fact_draft.claim_type,
                directness=fact_draft.directness,
                extracted_timestamp=fact_draft.extracted_timestamp,
                verifier_status=verification.verifier_status,
                verifier_notes=verification.verifier_notes,
                uniqueness_group=self._uniqueness_group(context.source, fact_draft, index),
                created_at=datetime.now(UTC),
            )
            session.add(fact)
            session.flush()
            facts.append(fact)

        mark_stage_complete(
            request,
            "fact_verification",
            f"Verified {len(facts)} extracted claim(s) and persisted the results.",
        )
        session.commit()
        return facts

    def _classify_evidence_roles(
        self,
        session: Session,
        request: AnalysisRequest,
        rule_parse: RuleParse,
        analysis_run: AnalysisRun,
        facts: list[FactClaim],
    ) -> list[FactClaim]:
        mark_stage_running(
            request,
            "evidence_classification",
            "Classifying verified claims by their role in the YES/NO proposition.",
        )
        session.add(request)
        session.commit()

        role_counts: Counter[str] = Counter()
        for fact in facts:
            source = session.get(Source, fact.source_id)
            if source is None:
                continue
            classification = self._classify_fact_role(
                session=session,
                rule_parse=rule_parse,
                source=source,
                fact=fact,
            )
            fact.evidence_role = self._normalize_evidence_role(
                rule_parse=rule_parse,
                source=source,
                fact=fact,
                proposed_role=classification.evidence_role,
            )
            session.add(fact)
            role_counts[fact.evidence_role.value] += 1

        mark_stage_complete(
            request,
            "evidence_classification",
            "Classified evidence roles: "
            + ", ".join(f"{count} {role}" for role, count in sorted(role_counts.items()))
            if role_counts
            else "No verified claims were available for evidence-role classification.",
        )
        session.commit()
        return facts

    def _map_factors(
        self,
        session: Session,
        request: AnalysisRequest,
        rule_parse: RuleParse,
        analysis_run: AnalysisRun,
        facts: list[FactClaim],
    ) -> list[Factor]:
        mark_stage_running(
            request,
            "factor_mapping",
            "Mapping verified claims into directional factors and weight multipliers.",
        )
        session.add(request)
        session.commit()

        seen_groups: Counter[str] = Counter()
        factors: list[Factor] = []

        for fact in facts:
            source = session.get(Source, fact.source_id)
            if source is None:
                continue
            mapping = self._map_fact_to_factor(rule_parse, source, fact)
            seen_groups[fact.uniqueness_group or ""] += 1
            uniqueness_multiplier = (
                1.0
                if not fact.uniqueness_group or seen_groups[fact.uniqueness_group] == 1
                else 0.25
            )
            factor = Factor(
                analysis_run_id=analysis_run.id,
                fact_claim_id=fact.id,
                stance=mapping.stance,
                strength=mapping.strength,
                evidence_role=mapping.evidence_role,
                used_in_scoring=mapping.used_in_scoring,
                exclusion_reason=mapping.exclusion_reason,
                source_weight=SOURCE_WEIGHTS[source.source_tier],
                freshness_multiplier=self._freshness_multiplier(source),
                uniqueness_multiplier=uniqueness_multiplier,
                template_multiplier=TEMPLATE_MULTIPLIERS[rule_parse.template_detected],
                final_weight=0.0,
                rationale=mapping.rationale,
                created_at=datetime.now(UTC),
            )
            factor.final_weight = (
                self._factor_weight(fact, factor) if mapping.used_in_scoring else 0.0
            )
            session.add(factor)
            session.flush()
            factors.append(factor)

        mark_stage_complete(
            request,
            "factor_mapping",
            f"Generated {len(factors)} weighted factor(s) for the probability model.",
        )
        session.commit()
        return factors

    def _retrieve_live_social_intelligence(
        self,
        session: Session,
        *,
        request: AnalysisRequest,
        analysis_run: AnalysisRun,
        rule_parse: RuleParse,
    ) -> tuple[SocialIntelSummary, list[SourceContext]]:
        mark_stage_running(
            request,
            "social_intelligence",
            "Scanning live X intelligence for trusted accounts and broader consensus.",
        )
        session.add(request)
        session.commit()

        social_draft = self._build_social_intelligence(
            session=session,
            rule_parse=rule_parse,
        )
        trusted_posts = [
            post
            for post in social_draft.trusted_posts
            if post.trust_tier in SOCIAL_FACTOR_TIERS
        ][:LIVE_SOCIAL_LIMIT]
        social_draft = self._normalize_social_intelligence(social_draft, trusted_posts)
        social_summary = SocialIntelSummary(
            analysis_run_id=analysis_run.id,
            consensus_label=social_draft.consensus_label,
            consensus_strength=social_draft.consensus_strength,
            narrative_phase=social_draft.narrative_phase,
            summary=social_draft.summary,
            key_themes=social_draft.key_themes,
            trusted_accounts_count=len(trusted_posts),
            broad_posts_sampled=social_draft.broad_posts_sampled,
            created_at=datetime.now(UTC),
        )
        session.add(social_summary)
        session.flush()

        contexts: list[SourceContext] = []
        for post in trusted_posts:
            excerpt = post.post_summary.strip()
            source = Source(
                analysis_run_id=analysis_run.id,
                url=post.post_url,
                domain=self._domain_from_url(post.post_url),
                title=f"{post.display_name} (@{post.handle})",
                source_kind=SourceKindEnum.LIVE_SOCIAL,
                source_tier=post.trust_tier,
                published_at=post.post_timestamp,
                fetched_at=datetime.now(UTC),
                content_hash=self._hash_text(post.post_url + post.post_summary),
                excerpt=excerpt,
                canonical_url=post.post_url,
                is_paywalled=False,
                metadata_json={
                    "handle": post.handle,
                    "display_name": post.display_name,
                    "account_category": post.account_category,
                    "trust_confidence": post.trust_confidence,
                    "relevance_reason": post.relevance_reason,
                    "trust_reason": post.trust_reason,
                    "citation_urls": post.citation_urls,
                    "possible_facts": post.possible_facts,
                    "source_scope": "trusted_timeline",
                },
                created_at=datetime.now(UTC),
            )
            session.add(source)
            session.flush()
            contexts.append(SourceContext(source=source, possible_facts=list(post.possible_facts)))

        session.commit()
        session.refresh(social_summary)
        mark_stage_complete(
            request,
            "social_intelligence",
            (
                f"Captured {len(trusted_posts)} trusted account post(s) "
                f"and sampled {social_draft.broad_posts_sampled} broader X post(s)."
            ),
        )
        session.add(request)
        session.commit()
        return social_summary, contexts

    def _score_analysis(
        self,
        request: AnalysisRequest,
        market: Market | None,
        rule_parse: RuleParse,
        source_contexts: list[SourceContext],
        social_intel_summary: SocialIntelSummary | None,
        facts: list[FactClaim],
        factors: list[Factor],
    ) -> ScoreOutcome:
        prior = self._market_prior(market)
        fact_lookup = {fact.id: fact for fact in facts}
        source_lookup = {source_context.source.id: source_context.source for source_context in source_contexts}
        evidence = self._capped_evidence_score(factors, fact_lookup, source_lookup)

        priced_in_risk = self._priced_in_risk(market, source_contexts, social_intel_summary)
        uncertainty = BASE_UNCERTAINTY[rule_parse.template_detected]
        uncertainty += max(0.0, 0.9 - rule_parse.clarity_score) * 0.12
        uncertainty += rule_parse.resolution_risk * 0.15
        if priced_in_risk == PricedInRiskLabelEnum.MEDIUM:
            uncertainty += 0.05
        elif priced_in_risk == PricedInRiskLabelEnum.HIGH:
            uncertainty += 0.10
        if not any(
            source_context.source.source_tier
            in {SourceTierEnum.OFFICIAL_PRIMARY, SourceTierEnum.OFFICIAL_STATEMENT}
            for source_context in source_contexts
        ):
            uncertainty += 0.07
        if any(source_context.source.source_kind == SourceKindEnum.MANUAL_SOCIAL for source_context in source_contexts):
            uncertainty += 0.03
        if market is None or market.yes_ask is None or market.no_ask is None:
            uncertainty += 0.04
        if market is not None and market.spread is not None and market.spread > 0.05:
            uncertainty += 0.04
        if self._has_contradictory_factors(factors):
            uncertainty += 0.05
        uncertainty += self._social_uncertainty_adjustment(social_intel_summary)
        uncertainty = min(max(uncertainty, 0.05), 0.40)

        raw_p_hat = self._sigmoid(self._logit(prior) + evidence)
        raw_p_low = max(0.01, round(raw_p_hat - uncertainty, 4))
        raw_p_high = min(0.99, round(raw_p_hat + uncertainty, 4))
        raw_p_hat = round(raw_p_hat, 4)

        confidence_label = self._confidence_label(raw_p_low, raw_p_high, factors)
        confidence_label = self._apply_social_confidence_modifier(
            confidence_label,
            social_intel_summary,
        )
        qualitative_label = self._qualitative_label(factors, evidence)
        numeric_estimate_available = True
        numeric_estimate_reason: str | None = None
        p_hat: float | None = raw_p_hat
        p_low: float | None = raw_p_low
        p_high: float | None = raw_p_high

        recommendation = self._recommendation(
            market=market,
            p_low=p_low,
            p_high=p_high,
            confidence_label=confidence_label,
            priced_in_risk=priced_in_risk,
            facts=facts,
            numeric_estimate_available=numeric_estimate_available,
            numeric_estimate_reason=numeric_estimate_reason,
            qualitative_label=qualitative_label,
        )
        return ScoreOutcome(
            recommendation=recommendation,
            priced_in_risk=priced_in_risk,
            p_hat=p_hat,
            p_low=p_low,
            p_high=p_high,
            numeric_estimate_available=numeric_estimate_available,
            numeric_estimate_reason=numeric_estimate_reason,
            qualitative_label=qualitative_label,
        )

    def _build_brief(
        self,
        session: Session,
        request: AnalysisRequest,
        market: Market | None,
        rule_parse: RuleParse,
        score_outcome: ScoreOutcome,
        source_contexts: list[SourceContext],
        factors: list[Factor],
        priced_in_risk: PricedInRiskLabelEnum,
        social_intel_summary: SocialIntelSummary | None,
    ) -> BriefDraft:
        scored_yes_factors = [
            factor
            for factor in factors
            if factor.used_in_scoring and factor.stance == StanceEnum.YES
        ][:2]
        scored_no_factors = [
            factor
            for factor in factors
            if factor.used_in_scoring and factor.stance == StanceEnum.NO
        ][:2]
        contextual_factors = [
            factor for factor in factors if not factor.used_in_scoring
        ][:4]

        context = "\n".join(
            [
                f"question: {rule_parse.question_text}",
                f"template: {rule_parse.template_detected.value}",
                f"claim_family: {rule_parse.claim_family.value}",
                f"yes_condition: {rule_parse.yes_condition}",
                f"no_condition: {rule_parse.no_condition}",
                f"market_title: {market.title if market else 'n/a'}",
                f"numeric_estimate_available: {score_outcome.numeric_estimate_available}",
                f"numeric_estimate_reason: {score_outcome.numeric_estimate_reason or 'n/a'}",
                f"qualitative_label: {score_outcome.qualitative_label.value if score_outcome.qualitative_label else 'n/a'}",
                f"p_hat: {score_outcome.p_hat}",
                f"p_low: {score_outcome.p_low}",
                f"p_high: {score_outcome.p_high}",
                f"confidence: {score_outcome.recommendation.confidence_label.value}",
                f"recommendation: {score_outcome.recommendation.recommendation_label.value}",
                f"priced_in_risk: {priced_in_risk.value}",
                f"sources: {[source_context.source.title or source_context.source.url for source_context in source_contexts]}",
                f"scored_yes_factors: {[factor.rationale for factor in scored_yes_factors]}",
                f"scored_no_factors: {[factor.rationale for factor in scored_no_factors]}",
                f"contextual_factors: {[factor.exclusion_reason or factor.rationale for factor in contextual_factors]}",
                f"social_summary: {social_intel_summary.summary if social_intel_summary else 'none'}",
                f"social_themes: {social_intel_summary.key_themes if social_intel_summary else []}",
            ]
        )

        if self.openai_client.is_configured:
            prompt = load_prompt("final_brief_v1.txt").replace("{{context}}", context)
            try:
                return self.openai_client.generate_structured(
                    session=session,
                    task_name="final_brief",
                    prompt_version="final_brief_v1",
                    system_prompt="Return concise JSON only.",
                    user_prompt=prompt,
                    schema_model=BriefDraft,
                    temperature=0.2,
                )
            except Exception:
                pass

        if score_outcome.p_hat is not None:
            yes_probability = self._format_probability(score_outcome.p_hat)
            no_probability = self._format_probability(1 - score_outcome.p_hat)
            final_summary = (
                f"{rule_parse.question_text} is currently assessed at YES {yes_probability} / "
                f"NO {no_probability}. "
                f"Top YES evidence: {self._join_factor_rationales(scored_yes_factors)}. "
                f"Top NO evidence: {self._join_factor_rationales(scored_no_factors)}."
            )
        else:
            qualitative = (
                score_outcome.qualitative_label.value.replace("_", " ")
                if score_outcome.qualitative_label
                else "analysis only"
            )
            provisional_read = ""
            if score_outcome.p_hat is not None:
                provisional_read = (
                    f"Provisional model read: YES {score_outcome.p_hat:.0%} / "
                    f"NO {1 - score_outcome.p_hat:.0%}."
                )
            lead = f"{rule_parse.question_text} currently reads as {qualitative}."
            if provisional_read:
                lead = f"{lead} {provisional_read}"
            final_summary = (
                f"{lead} "
                f"Scored YES evidence: {self._join_factor_rationales(scored_yes_factors)}. "
                f"Scored NO evidence: {self._join_factor_rationales(scored_no_factors)}. "
                f"No numeric estimate is shown because {score_outcome.numeric_estimate_reason or 'the directional evidence is still too weak or contextual'}."
            )
        why_wrong = (
            f"This could be wrong if the resolution wording is looser than expected, "
            f"if new official information arrives after the current sources, or if "
            f"the market has already priced in the visible evidence ({priced_in_risk.value} risk)."
        )
        return BriefDraft(final_summary=final_summary, why_wrong_summary=why_wrong)

    def _build_social_intelligence(
        self,
        *,
        session: Session,
        rule_parse: RuleParse,
    ) -> SocialIntelDraft:
        if self.xai_client.is_configured:
            playbook_context = self._social_playbook_context(rule_parse)
            prompt = load_prompt("social_intelligence_v1.txt").replace(
                "{{context}}",
                "\n".join(
                    [
                        f"question: {rule_parse.question_text}",
                        f"template: {rule_parse.template_detected.value}",
                        f"claim_family: {rule_parse.claim_family.value}",
                        f"yes_condition: {rule_parse.yes_condition}",
                        f"no_condition: {rule_parse.no_condition}",
                        f"playbook: {playbook_context}",
                        f"official_domains: {rule_parse.official_domains}",
                        f"ambiguity_flags: {rule_parse.ambiguity_flags}",
                    ]
                ),
            )
            try:
                return self.xai_client.generate_structured_with_tools(
                    session=session,
                    task_name="social_intelligence",
                    prompt_version="social_intelligence_v1",
                    system_prompt="Return structured social-intelligence JSON only.",
                    user_prompt=prompt,
                    schema_model=SocialIntelDraft,
                    tools=self._social_tools_for_template(rule_parse),
                )
            except Exception:
                pass

        return self._fallback_social_intelligence(rule_parse)

    def _extract_facts_for_source(
        self,
        session: Session,
        *,
        rule_parse: RuleParse,
        source_context: SourceContext,
    ) -> list[ExtractedFactDraft]:
        grounded_context = self._passage_context_text(source_context)
        context = "\n".join(
            [
                f"question: {rule_parse.question_text}",
                f"source_title: {source_context.source.title or ''}",
                f"source_kind: {source_context.source.source_kind.value}",
                f"source_tier: {source_context.source.source_tier.value}",
                f"source_excerpt: {source_context.source.excerpt}",
                f"grounded_passages: {grounded_context}",
            ]
        )

        if self.openai_client.is_configured and len(grounded_context) > 80:
            prompt = load_prompt("fact_extract_v1.txt").replace("{{context}}", context)
            try:
                result = self.openai_client.generate_structured(
                    session=session,
                    task_name="fact_extract",
                    prompt_version="fact_extract_v1",
                    system_prompt="Return JSON only. Extract up to five facts.",
                    user_prompt=prompt,
                    schema_model=FactExtractionResult,
                )
                return result.facts[:5]
            except Exception:
                pass

        return self._fallback_fact_extraction(source_context, rule_parse.question_text)

    def _verify_fact(
        self,
        session: Session,
        *,
        rule_parse: RuleParse,
        source_context: SourceContext,
        fact: ExtractedFactDraft,
    ) -> VerifiedFactDraft:
        matched_passage = self._best_matching_passage(
            source_context,
            fact.normalized_fact,
            fact.exact_quote,
        )
        context = "\n".join(
            [
                f"question: {rule_parse.question_text}",
                f"fact: {fact.normalized_fact}",
                f"quote: {fact.exact_quote}",
                f"source_excerpt: {source_context.source.excerpt}",
                f"grounded_passage: {matched_passage.text if matched_passage else self._passage_context_text(source_context)}",
            ]
        )
        if self.openai_client.is_configured and len(context) > 120:
            prompt = load_prompt("fact_verify_v1.txt").replace("{{context}}", context)
            try:
                return self.openai_client.generate_structured(
                    session=session,
                    task_name="fact_verify",
                    prompt_version="fact_verify_v1",
                    system_prompt="Return JSON only.",
                    user_prompt=prompt,
                    schema_model=VerifiedFactDraft,
                )
            except Exception:
                pass

        return self._fallback_fact_verification(source_context, fact)

    def _classify_fact_role(
        self,
        session: Session,
        *,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
    ) -> EvidenceRoleDraft:
        context = "\n".join(
            [
                f"question: {rule_parse.question_text}",
                f"claim_family: {rule_parse.claim_family.value}",
                f"yes_condition: {rule_parse.yes_condition}",
                f"no_condition: {rule_parse.no_condition}",
                f"source_kind: {source.source_kind.value}",
                f"source_tier: {source.source_tier.value}",
                f"fact: {fact.normalized_fact}",
                f"quote: {fact.exact_quote}",
                f"verification: {fact.verifier_status.value}",
            ]
        )
        if self.openai_client.is_configured and len(source.excerpt) > 80:
            prompt = load_prompt("evidence_role_v1.txt").replace("{{context}}", context)
            try:
                return self.openai_client.generate_structured(
                    session=session,
                    task_name="evidence_role",
                    prompt_version="evidence_role_v1",
                    system_prompt="Return JSON only.",
                    user_prompt=prompt,
                    schema_model=EvidenceRoleDraft,
                )
            except Exception:
                pass

        return self._fallback_evidence_role(rule_parse, source, fact)

    def _map_fact_to_factor(
        self,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
    ) -> FactorMappingDraft:
        return self._deterministic_factor_mapping(rule_parse, source, fact)

    def _normalize_evidence_role(
        self,
        *,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
        proposed_role: EvidenceRoleEnum,
    ) -> EvidenceRoleEnum:
        if fact.claim_type == ClaimTypeEnum.RULE_NOTE or source.source_kind == SourceKindEnum.MANUAL_INPUT:
            return EvidenceRoleEnum.BACKGROUND

        if source.source_kind in {SourceKindEnum.MANUAL_SOCIAL, SourceKindEnum.LIVE_SOCIAL} and source.source_tier in {
            SourceTierEnum.GENERIC_SOCIAL,
            SourceTierEnum.REPORTER_SOCIAL,
        }:
            return EvidenceRoleEnum.SENTIMENT

        if rule_parse.claim_family == ClaimFamilyEnum.LEGAL_CASE:
            return self._normalize_legal_evidence_role(rule_parse, source, fact, proposed_role)

        text = fact.normalized_fact.lower()
        if any(keyword in text for keyword in TIMING_KEYWORDS):
            return EvidenceRoleEnum.TIMING
        if any(keyword in text for keyword in PROCEDURAL_KEYWORDS):
            return EvidenceRoleEnum.PROCEDURAL
        return proposed_role

    def _normalize_legal_evidence_role(
        self,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
        proposed_role: EvidenceRoleEnum,
    ) -> EvidenceRoleEnum:
        text = fact.normalized_fact.lower()
        if self._legal_merits_deferral(text) or self._legal_injunction_scope_only(text):
            return EvidenceRoleEnum.PROCEDURAL

        has_injunction_outcome = self._legal_injunction_outcome(text) is not None
        has_decision_signal = has_injunction_outcome or any(
            keyword in text for keyword in LEGAL_DECISION_SIGNALS
        )
        has_commentary_cue = any(keyword in text for keyword in LEGAL_COMMENTARY_CUES)
        has_background_signal = any(keyword in text for keyword in LEGAL_BACKGROUND_KEYWORDS)
        heuristic_role = self._fallback_legal_evidence_role(rule_parse, fact, text)

        if has_background_signal and not has_decision_signal:
            return EvidenceRoleEnum.BACKGROUND
        if any(keyword in text for keyword in TIMING_KEYWORDS) and not has_decision_signal:
            return EvidenceRoleEnum.TIMING
        if any(keyword in text for keyword in PROCEDURAL_KEYWORDS) and not has_decision_signal:
            return EvidenceRoleEnum.PROCEDURAL

        if has_decision_signal:
            if fact.claim_type in {ClaimTypeEnum.OPINION, ClaimTypeEnum.FORECAST} or has_commentary_cue:
                return EvidenceRoleEnum.COMMENTARY
            if proposed_role in {
                EvidenceRoleEnum.BACKGROUND,
                EvidenceRoleEnum.TIMING,
                EvidenceRoleEnum.PROCEDURAL,
            }:
                return heuristic_role
            return proposed_role

        if proposed_role in {
            EvidenceRoleEnum.OUTCOME,
            EvidenceRoleEnum.DIRECT_SUPPORT,
            EvidenceRoleEnum.DIRECT_CONTRADICTION,
        }:
            return heuristic_role
        return proposed_role

    def _fallback_rule_parse(
        self,
        request: AnalysisRequest,
        market: Market | None,
    ) -> RuleParseDraft:
        question_text = market.title if market else request.input_text
        if market and market.rules_text:
            question_text = market.title

        template = request.template_requested or self._detect_template(question_text)
        claim_family = ClaimFamilyEnum(template.value)
        ambiguity_flags: list[str] = []
        if " or " in question_text.lower():
            ambiguity_flags.append("contains_or_clause")
        if not self._looks_binary(question_text):
            ambiguity_flags.append("question_may_not_be_binary")
        clarity_score = 0.85 if template == TemplateKey.OFFICIAL_EVENT else 0.68
        clarity_score -= min(len(ambiguity_flags) * 0.08, 0.2)
        clarity_score = max(0.35, round(clarity_score, 2))
        resolution_risk = round(max(0.1, 1 - clarity_score), 2)

        official_domains = self._official_domains_for_template(template)
        resolution_source = market.rules_text if market and market.rules_text else None

        deadline_text = (request.input_payload or {}).get("deadline_text")
        if deadline_text is None and market and market.expiry_at:
            deadline_text = market.expiry_at.date().isoformat()

        entity_names = self._entity_names(question_text)
        action = self._detect_action(question_text)
        yes_condition, no_condition = self._yes_no_conditions(question_text, claim_family)
        scoring_policy = self._default_scoring_policy(claim_family)

        return RuleParseDraft(
            question_text=question_text,
            event=question_text,
            entity_names=entity_names,
            action=action,
            claim_family=claim_family,
            yes_condition=yes_condition,
            no_condition=no_condition,
            deadline_text=deadline_text,
            timezone_text="UTC" if deadline_text else None,
            resolution_definition=resolution_source or question_text,
            directional_scoring_policy=scoring_policy,
            official_resolution_source=market.url if market and market.url else None,
            fallback_sources=["Reuters", "AP", "Financial Times"],
            official_domains=official_domains,
            ambiguity_flags=ambiguity_flags,
            clarity_score=clarity_score,
            resolution_risk=resolution_risk,
            suitable_for_auto=(
                template == TemplateKey.OFFICIAL_EVENT
                and clarity_score >= 0.75
                and resolution_risk <= 0.30
            ),
            template_detected=template,
        )

    def _fallback_fact_extraction(
        self,
        source_context: SourceContext,
        question_text: str,
    ) -> list[ExtractedFactDraft]:
        if source_context.possible_facts:
            candidates = source_context.possible_facts
        elif source_context.passages:
            candidates = []
            for passage in source_context.passages[:PASSAGES_FOR_EXTRACTION]:
                candidates.extend(re.split(r"(?<=[.!?])\s+|\n+", passage.text))
        else:
            candidates = re.split(r"(?<=[.!?])\s+|\n+", source_context.source.excerpt)
        facts: list[ExtractedFactDraft] = []
        question_terms = self._signal_terms(self._expand_search_aliases(question_text))
        for sentence in candidates:
            cleaned = " ".join(sentence.split()).strip()
            if len(cleaned) < 20:
                continue
            if self._is_low_signal_sentence(cleaned):
                continue
            if source_context.source.source_kind != SourceKindEnum.MANUAL_INPUT and question_terms:
                sentence_terms = self._signal_terms(self._expand_search_aliases(cleaned))
                if not question_terms.intersection(sentence_terms):
                    continue
            claim_type = ClaimTypeEnum.FACT
            if source_context.source.source_kind == SourceKindEnum.MANUAL_INPUT:
                claim_type = ClaimTypeEnum.RULE_NOTE
            elif source_context.source.source_kind in {
                SourceKindEnum.MANUAL_SOCIAL,
                SourceKindEnum.LIVE_SOCIAL,
            }:
                claim_type = ClaimTypeEnum.SOCIAL_SIGNAL
            elif "will " in cleaned.lower() or "expects" in cleaned.lower():
                claim_type = ClaimTypeEnum.FORECAST
            directness = DirectnessEnum.DIRECT
            if source_context.source.source_kind in {SourceKindEnum.NEWS, SourceKindEnum.PREMIUM_NEWS}:
                directness = DirectnessEnum.INDIRECT
            if (
                claim_type == ClaimTypeEnum.SOCIAL_SIGNAL
                and source_context.source.source_tier == SourceTierEnum.GENERIC_SOCIAL
            ):
                directness = DirectnessEnum.BACKGROUND
            facts.append(
                ExtractedFactDraft(
                    normalized_fact=cleaned.rstrip("."),
                    exact_quote=cleaned[:400],
                    claim_type=claim_type,
                    directness=directness,
                )
            )
            if len(facts) == 5:
                break
        return facts

    def _fallback_fact_verification(
        self,
        source_context: SourceContext,
        fact: ExtractedFactDraft,
    ) -> VerifiedFactDraft:
        excerpt = source_context.source.excerpt.lower()
        normalized = fact.normalized_fact.lower()
        if normalized and normalized[:40] in excerpt:
            return VerifiedFactDraft(verifier_status=VerifierStatusEnum.SUPPORTED)
        if source_context.source.source_kind == SourceKindEnum.MANUAL_SOCIAL:
            return VerifiedFactDraft(
                verifier_status=VerifierStatusEnum.AMBIGUOUS,
                verifier_notes="Manual social input is treated as lower-confidence evidence in v1.",
            )
        if len(excerpt) > 40:
            return VerifiedFactDraft(verifier_status=VerifierStatusEnum.SUPPORTED)
        return VerifiedFactDraft(
            verifier_status=VerifierStatusEnum.REJECTED,
            verifier_notes="Source excerpt was too thin to verify the extracted fact.",
        )

    def _fallback_evidence_role(
        self,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
    ) -> EvidenceRoleDraft:
        text = fact.normalized_fact.lower()

        if fact.claim_type == ClaimTypeEnum.RULE_NOTE or source.source_kind == SourceKindEnum.MANUAL_INPUT:
            return EvidenceRoleDraft(evidence_role=EvidenceRoleEnum.BACKGROUND)

        if source.source_kind in {SourceKindEnum.MANUAL_SOCIAL, SourceKindEnum.LIVE_SOCIAL} and source.source_tier in {
            SourceTierEnum.GENERIC_SOCIAL,
            SourceTierEnum.REPORTER_SOCIAL,
        }:
            return EvidenceRoleDraft(evidence_role=EvidenceRoleEnum.SENTIMENT)

        if rule_parse.claim_family == ClaimFamilyEnum.LEGAL_CASE:
            return EvidenceRoleDraft(
                evidence_role=self._fallback_legal_evidence_role(rule_parse, fact, text)
            )

        if any(keyword in text for keyword in TIMING_KEYWORDS):
            return EvidenceRoleDraft(evidence_role=EvidenceRoleEnum.TIMING)

        if fact.claim_type in {ClaimTypeEnum.OPINION, ClaimTypeEnum.FORECAST}:
            match = self._condition_alignment(rule_parse, fact.normalized_fact)
            if match == StanceEnum.YES:
                return EvidenceRoleDraft(evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT)
            if match == StanceEnum.NO:
                return EvidenceRoleDraft(evidence_role=EvidenceRoleEnum.DIRECT_CONTRADICTION)
            return EvidenceRoleDraft(evidence_role=EvidenceRoleEnum.COMMENTARY)

        match = self._condition_alignment(rule_parse, fact.normalized_fact)
        if match == StanceEnum.YES:
            return EvidenceRoleDraft(evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT)
        if match == StanceEnum.NO:
            return EvidenceRoleDraft(evidence_role=EvidenceRoleEnum.DIRECT_CONTRADICTION)
        if any(keyword in text for keyword in PROCEDURAL_KEYWORDS):
            return EvidenceRoleDraft(evidence_role=EvidenceRoleEnum.PROCEDURAL)
        return EvidenceRoleDraft(evidence_role=EvidenceRoleEnum.BACKGROUND)

    def _fallback_legal_evidence_role(
        self,
        rule_parse: RuleParse,
        fact: FactClaim,
        text: str,
    ) -> EvidenceRoleEnum:
        if self._legal_merits_deferral(text) or self._legal_injunction_scope_only(text):
            return EvidenceRoleEnum.PROCEDURAL

        favors_yes = self._positive_legal_injunction_favors_yes(rule_parse)
        has_decision_signal = self._legal_injunction_outcome(text) is not None or any(
            keyword in text for keyword in LEGAL_DECISION_SIGNALS
        )
        if any(keyword in text for keyword in LEGAL_BACKGROUND_KEYWORDS) and not has_decision_signal:
            return EvidenceRoleEnum.BACKGROUND
        injunction_outcome = self._legal_injunction_outcome(text)
        if injunction_outcome is not None:
            if injunction_outcome == "positive":
                return (
                    EvidenceRoleEnum.DIRECT_SUPPORT
                    if favors_yes
                    else EvidenceRoleEnum.DIRECT_CONTRADICTION
                )
            return (
                EvidenceRoleEnum.DIRECT_CONTRADICTION
                if favors_yes
                else EvidenceRoleEnum.DIRECT_SUPPORT
            )
        if any(keyword in text for keyword in LEGAL_MERITS_YES):
            return (
                EvidenceRoleEnum.DIRECT_SUPPORT
                if favors_yes
                else EvidenceRoleEnum.DIRECT_CONTRADICTION
            )
        if any(keyword in text for keyword in LEGAL_MERITS_NO):
            return (
                EvidenceRoleEnum.DIRECT_CONTRADICTION
                if favors_yes
                else EvidenceRoleEnum.DIRECT_SUPPORT
            )
        if any(keyword in text for keyword in PROCEDURAL_KEYWORDS):
            return EvidenceRoleEnum.PROCEDURAL
        if any(keyword in text for keyword in TIMING_KEYWORDS):
            return EvidenceRoleEnum.TIMING

        match = self._condition_alignment(rule_parse, fact.normalized_fact)
        if match == StanceEnum.YES:
            return EvidenceRoleEnum.DIRECT_SUPPORT
        if match == StanceEnum.NO:
            return EvidenceRoleEnum.DIRECT_CONTRADICTION
        if fact.claim_type in {ClaimTypeEnum.OPINION, ClaimTypeEnum.FORECAST}:
            return EvidenceRoleEnum.COMMENTARY
        return EvidenceRoleEnum.BACKGROUND

    def _deterministic_factor_mapping(
        self,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
    ) -> FactorMappingDraft:
        policy = self._scoring_policy(rule_parse)
        evidence_role = fact.evidence_role

        if fact.verifier_status == VerifierStatusEnum.REJECTED:
            return FactorMappingDraft(
                stance=StanceEnum.NEUTRAL,
                strength=StrengthEnum.WEAK,
                evidence_role=evidence_role,
                used_in_scoring=False,
                exclusion_reason="This fact was rejected during verification.",
                rationale=f"{fact.normalized_fact} was rejected during verification and was not scored.",
            )

        allowed, exclusion_reason = self._role_allowed_in_scoring(
            rule_parse=rule_parse,
            source=source,
            fact=fact,
            policy=policy,
        )
        stance = self._stance_for_fact(rule_parse, fact)
        strength = self._strength_for_fact(rule_parse, source, fact)

        if not allowed or stance == StanceEnum.NEUTRAL:
            exclusion_reason = exclusion_reason or "This fact is contextual rather than directional."
            return FactorMappingDraft(
                stance=StanceEnum.NEUTRAL,
                strength=strength,
                evidence_role=evidence_role,
                used_in_scoring=False,
                exclusion_reason=exclusion_reason,
                rationale=f"{fact.normalized_fact} adds context but was not scored directionally.",
            )

        return FactorMappingDraft(
            stance=stance,
            strength=strength,
            evidence_role=evidence_role,
            used_in_scoring=True,
            exclusion_reason=None,
            rationale=f"{fact.normalized_fact} supports the {stance.value.upper()} case against the parsed proposition.",
        )

    def _fallback_social_intelligence(self, rule_parse: RuleParse) -> SocialIntelDraft:
        summary = (
            "Live X intelligence was unavailable, so the analysis did not rely on a live consensus "
            "read from trusted accounts or broader X sentiment."
        )
        key_themes: list[str] = []
        if rule_parse.template_detected == TemplateKey.MACRO_POLICY:
            key_themes = ["fed path", "policy expectations"]
        elif rule_parse.template_detected == TemplateKey.OFFICIAL_EVENT:
            key_themes = ["official confirmation", "resolution timing"]
        elif rule_parse.template_detected == TemplateKey.LEGAL_CASE:
            key_themes = ["merits", "oral-argument readout", "court posture"]
        elif rule_parse.template_detected == TemplateKey.NARRATIVE_MANUAL:
            key_themes = ["narrative", "consensus", "market attention"]
        return SocialIntelDraft(
            consensus_label=ConsensusLabelEnum.UNCLEAR,
            consensus_strength=ConsensusStrengthEnum.WEAK,
            narrative_phase=NarrativePhaseEnum.FRESH,
            summary=summary,
            key_themes=key_themes,
            trusted_accounts_count=0,
            broad_posts_sampled=0,
            trusted_posts=[],
        )

    @staticmethod
    def _normalize_social_intelligence(
        social_draft: SocialIntelDraft,
        trusted_posts: list[TrustedSocialPostDraft],
    ) -> SocialIntelDraft:
        if trusted_posts:
            social_draft.trusted_accounts_count = len(trusted_posts)
            return social_draft

        if (
            social_draft.consensus_strength != ConsensusStrengthEnum.WEAK
            or "trusted" in social_draft.summary.lower()
        ):
            social_draft.consensus_strength = ConsensusStrengthEnum.WEAK
            social_draft.summary = (
                "Live X discussion was sampled, but no trusted-account posts met the persistence "
                "threshold. Treat this as broad narrative context only."
            )
        social_draft.trusted_accounts_count = 0
        return social_draft

    def _recommendation(
        self,
        *,
        market: Market | None,
        p_low: float | None,
        p_high: float | None,
        confidence_label: ConfidenceLabelEnum,
        priced_in_risk: PricedInRiskLabelEnum,
        facts: list[FactClaim],
        numeric_estimate_available: bool = True,
        numeric_estimate_reason: str | None = None,
        qualitative_label: QualitativeLabelEnum | None = None,
    ) -> RecommendationDraft:
        if (
            not numeric_estimate_available
            or market is None
            or market.yes_ask is None
            or market.no_ask is None
            or p_low is None
            or p_high is None
        ):
            return RecommendationDraft(
                recommendation_label=RecommendationLabelEnum.ANALYSIS_ONLY,
                confidence_label=confidence_label,
                qualitative_label=qualitative_label,
                rationale_json={
                    "reason": numeric_estimate_reason
                    or "No executable market prices were available for edge evaluation.",
                    "qualitative_label": qualitative_label.value if qualitative_label else None,
                },
            )

        friction = 0.02
        edge_yes = round(p_low - market.yes_ask - friction, 4)
        edge_no = round((1 - p_high) - market.no_ask - friction, 4)
        supported_facts = sum(
            1 for fact in facts if fact.verifier_status == VerifierStatusEnum.SUPPORTED
        )

        if supported_facts == 0:
            label = RecommendationLabelEnum.NEEDS_MORE_RESEARCH
        elif priced_in_risk == PricedInRiskLabelEnum.HIGH:
            label = RecommendationLabelEnum.NO_EDGE
        elif edge_yes > 0:
            label = RecommendationLabelEnum.LEAN_YES
        elif edge_no > 0:
            label = RecommendationLabelEnum.LEAN_NO
        elif confidence_label == ConfidenceLabelEnum.LOW:
            label = RecommendationLabelEnum.NEEDS_MORE_RESEARCH
        else:
            label = RecommendationLabelEnum.NO_EDGE

        return RecommendationDraft(
            recommendation_label=label,
            confidence_label=confidence_label,
            qualitative_label=qualitative_label,
            edge_yes=edge_yes,
            edge_no=edge_no,
            rationale_json={
                "friction_buffer": friction,
                "supported_fact_count": supported_facts,
                "priced_in_risk": priced_in_risk.value,
            },
        )

    @staticmethod
    def _market_prior(market: Market | None) -> float | None:
        if market is None:
            return None
        if market.yes_bid is not None and market.yes_ask is not None:
            return round((market.yes_bid + market.yes_ask) / 2, 4)
        if market.yes_ask is not None:
            return round(market.yes_ask, 4)
        return None

    def _factor_weight(self, fact: FactClaim, factor: Factor) -> float:
        return round(
            factor.source_weight
            * STRENGTH_MULTIPLIERS[factor.strength]
            * DIRECTNESS_MULTIPLIERS[fact.directness]
            * VERIFICATION_MULTIPLIERS[fact.verifier_status]
            * factor.freshness_multiplier
            * factor.uniqueness_multiplier
            * factor.template_multiplier,
            4,
        )

    @staticmethod
    def _scoring_policy(rule_parse: RuleParse) -> dict[str, Any]:
        return dict(rule_parse.directional_scoring_policy or {})

    @staticmethod
    def _factor_used_in_scoring(factor: Factor | Any) -> bool:
        return factor_used_in_scoring(factor)

    @staticmethod
    def _source_is_factor_eligible(source: Source) -> bool:
        return source_is_factor_eligible(source)

    def _role_allowed_in_scoring(
        self,
        *,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
        policy: dict[str, Any],
    ) -> tuple[bool, str | None]:
        evidence_role = fact.evidence_role

        if evidence_role in {
            EvidenceRoleEnum.BACKGROUND,
            EvidenceRoleEnum.TIMING,
            EvidenceRoleEnum.SENTIMENT,
        }:
            return False, "Background, timing, and sentiment facts are contextual only."

        if evidence_role == EvidenceRoleEnum.PROCEDURAL:
            return False, "Procedural developments widen uncertainty but do not score direction."

        if evidence_role == EvidenceRoleEnum.COMMENTARY:
            commentary_mode = policy.get("commentary_mode", "none")
            if commentary_mode == "none":
                return False, "Commentary is not directional for this claim family."
            if commentary_mode == "expert_only" and source.source_tier not in {
                SourceTierEnum.EXPERT_ANALYSIS,
                SourceTierEnum.OFFICIAL_PRIMARY,
                SourceTierEnum.OFFICIAL_STATEMENT,
            }:
                return False, "Only expert-analysis or official commentary can score direction here."
            if source.source_kind in {SourceKindEnum.MANUAL_SOCIAL, SourceKindEnum.LIVE_SOCIAL} and source.source_tier not in SOCIAL_FACTOR_TIERS:
                return False, "Lower-trust social commentary is modifier-only."

        if source.source_kind == SourceKindEnum.MANUAL_SOCIAL:
            return False, "Manual social inputs are contextual-only."

        if (
            source.source_kind == SourceKindEnum.LIVE_SOCIAL
            and not self._source_is_factor_eligible(source)
        ):
            return False, "Only official or high-trust social inputs may score direction."

        allowed_roles = set(policy.get("allowed_roles", []))
        if evidence_role.value not in allowed_roles:
            return False, f"{evidence_role.value.replace('_', ' ').title()} facts do not score direction for this claim family."

        return True, None

    def _stance_for_fact(self, rule_parse: RuleParse, fact: FactClaim) -> StanceEnum:
        if fact.evidence_role == EvidenceRoleEnum.DIRECT_SUPPORT:
            return StanceEnum.YES
        if fact.evidence_role == EvidenceRoleEnum.DIRECT_CONTRADICTION:
            return StanceEnum.NO
        if fact.evidence_role == EvidenceRoleEnum.OUTCOME:
            return self._condition_alignment(rule_parse, fact.normalized_fact)
        if fact.evidence_role == EvidenceRoleEnum.COMMENTARY:
            return self._condition_alignment(rule_parse, fact.normalized_fact)
        return StanceEnum.NEUTRAL

    def _strength_for_fact(
        self,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
    ) -> StrengthEnum:
        if fact.verifier_status == VerifierStatusEnum.REJECTED:
            return StrengthEnum.WEAK
        if fact.evidence_role in {
            EvidenceRoleEnum.BACKGROUND,
            EvidenceRoleEnum.PROCEDURAL,
            EvidenceRoleEnum.TIMING,
            EvidenceRoleEnum.SENTIMENT,
        }:
            return StrengthEnum.WEAK

        if fact.verifier_status == VerifierStatusEnum.SUPPORTED and fact.directness == DirectnessEnum.DIRECT:
            strength = StrengthEnum.STRONG
        elif fact.verifier_status in {
            VerifierStatusEnum.SUPPORTED,
            VerifierStatusEnum.AMBIGUOUS,
        } and fact.directness != DirectnessEnum.BACKGROUND:
            strength = StrengthEnum.MEDIUM
        else:
            strength = StrengthEnum.WEAK

        if fact.evidence_role in {EvidenceRoleEnum.COMMENTARY, EvidenceRoleEnum.SENTIMENT}:
            strength = StrengthEnum.WEAK
        if source.source_tier in {SourceTierEnum.EXPERT_ANALYSIS, SourceTierEnum.REPUTABLE_NEWS} and strength == StrengthEnum.STRONG:
            strength = StrengthEnum.MEDIUM
        if rule_parse.claim_family in {ClaimFamilyEnum.MACRO_POLICY, ClaimFamilyEnum.NARRATIVE_MANUAL} and strength == StrengthEnum.STRONG:
            strength = StrengthEnum.MEDIUM
        return strength

    def _numeric_estimate_gate(
        self,
        factors: list[Factor],
        facts: list[FactClaim],
        source_lookup: dict[int, Source],
        evidence: float,
    ) -> tuple[bool, str | None]:
        scored_directional_factors = [
            factor
            for factor in factors
            if self._factor_used_in_scoring(factor)
            and factor.stance in {StanceEnum.YES, StanceEnum.NO}
        ]
        if len(scored_directional_factors) < 2:
            return False, "there are fewer than two scored directional factors"

        contributing_source_ids = {
            fact.source_id
            for fact in facts
            if fact.id in {factor.fact_claim_id for factor in scored_directional_factors}
        }
        if len(contributing_source_ids) < 2:
            return False, "the directional case relies on fewer than two distinct sources"

        contributing_sources = [source_lookup[source_id] for source_id in contributing_source_ids if source_id in source_lookup]
        if not any(
            source.source_tier in NUMERIC_REQUIRED_SOURCE_TIERS
            and source.source_kind not in {SourceKindEnum.MANUAL_SOCIAL, SourceKindEnum.LIVE_SOCIAL}
            for source in contributing_sources
        ):
            return False, "the run lacks a qualifying non-social source for numeric output"

        if abs(evidence) < 0.10:
            return False, "net directional evidence is still below the numeric threshold"

        excluded_or_contextual = sum(1 for factor in factors if not factor.used_in_scoring)
        if excluded_or_contextual > len(scored_directional_factors) * 2:
            return False, "contextual and excluded facts still dominate the evidence mix"

        return True, None

    @staticmethod
    def _qualitative_label(
        factors: list[Factor],
        evidence: float,
    ) -> QualitativeLabelEnum:
        scored_directional_factors = [
            factor
            for factor in factors
            if AnalysisProcessor._factor_used_in_scoring(factor)
            and factor.stance in {StanceEnum.YES, StanceEnum.NO}
        ]
        if len(scored_directional_factors) < 2 or abs(evidence) < 0.05:
            return QualitativeLabelEnum.INSUFFICIENT_BASIS
        yes_count = sum(1 for factor in scored_directional_factors if factor.stance == StanceEnum.YES)
        no_count = sum(1 for factor in scored_directional_factors if factor.stance == StanceEnum.NO)
        if abs(yes_count - no_count) <= 1 and abs(evidence) < 0.14:
            return QualitativeLabelEnum.MIXED
        return QualitativeLabelEnum.LEANS_YES if evidence > 0 else QualitativeLabelEnum.LEANS_NO

    def _condition_alignment(self, rule_parse: RuleParse, text: str) -> StanceEnum:
        fact_terms = self._signal_terms(self._expand_search_aliases(text))
        yes_terms = self._signal_terms(self._expand_search_aliases(rule_parse.yes_condition))
        no_terms = self._signal_terms(self._expand_search_aliases(rule_parse.no_condition))
        yes_score = len(fact_terms.intersection(yes_terms))
        no_score = len(fact_terms.intersection(no_terms))
        macro_yes_score, macro_no_score = self._macro_policy_alignment_scores(rule_parse, text)
        yes_score += macro_yes_score
        no_score += macro_no_score
        if yes_score == no_score == 0:
            lowered = self._expand_search_aliases(text).lower()
            if any(keyword in lowered for keyword in POSITIVE_KEYWORDS):
                yes_score += 1
            if any(keyword in lowered for keyword in NEGATIVE_KEYWORDS):
                no_score += 1
        if yes_score > no_score:
            return StanceEnum.YES
        if no_score > yes_score:
            return StanceEnum.NO
        return StanceEnum.NEUTRAL

    @classmethod
    def _macro_policy_alignment_scores(
        cls,
        rule_parse: RuleParse,
        text: str,
    ) -> tuple[int, int]:
        if rule_parse.claim_family != ClaimFamilyEnum.MACRO_POLICY:
            return 0, 0

        lowered = cls._expand_search_aliases(text).lower()
        action = (rule_parse.action or "").lower()
        easing_yes_score, easing_no_score = cls._macro_easing_scores(lowered)

        if "cut" in action or "ease" in action:
            return easing_yes_score, easing_no_score
        if "hike" in action or "raise" in action:
            return easing_no_score, easing_yes_score
        return 0, 0

    @classmethod
    def _macro_easing_scores(cls, lowered: str) -> tuple[int, int]:
        yes_score = sum(2 for phrase in MACRO_EASING_SUPPORT_PHRASES if phrase in lowered)
        no_score = sum(2 for phrase in MACRO_EASING_CONTRADICTION_PHRASES if phrase in lowered)

        has_inflation_context = any(term in lowered for term in {"inflation", "pce", "cpi", "price index"})
        has_growth_context = any(term in lowered for term in {"gdp", "growth", "economy", "economic activity"})
        has_labor_context = any(
            term in lowered for term in {"jobs", "jobless claims", "labor market", "payroll", "unemployment"}
        )

        if has_inflation_context:
            if any(cue in lowered for cue in MACRO_COOLING_CUES):
                yes_score += 1
            if any(cue in lowered for cue in MACRO_HOT_CUES):
                no_score += 1

        if has_growth_context:
            if any(cue in lowered for cue in {"slow", "slowed", "slowing", "weak", "weaker", "contract", "contraction"}):
                yes_score += 1
            if any(cue in lowered for cue in {"accelerate", "accelerated", "accelerating", "increase", "increased", "strong", "resilient"}):
                no_score += 1

        if has_labor_context:
            if any(cue in lowered for cue in {"soft", "softened", "softening", "weak", "weaker", "rise", "rising", "rose", "higher"}):
                yes_score += 1
            if any(cue in lowered for cue in {"strong", "solid", "resilient", "hot"}):
                no_score += 1

        return yes_score, no_score

    @staticmethod
    def _legal_merits_deferral(text: str) -> bool:
        lowered = text.lower()
        return (
            any(cue in lowered for cue in LEGAL_MERITS_DEFERRAL_CUES)
            or re.search(r"did not[^.]{0,80}weigh in on", lowered) is not None
            or re.search(r"did not[^.]{0,80}(decide|address|rule on) whether", lowered) is not None
        )

    @staticmethod
    def _legal_injunction_scope_only(text: str) -> bool:
        lowered = text.lower()
        if "injunction" not in lowered:
            return False
        if AnalysisProcessor._legal_injunction_outcome(lowered) is not None:
            return False
        return any(cue in lowered for cue in LEGAL_INJUNCTION_SCOPE_CUES)

    @staticmethod
    def _legal_injunction_outcome(text: str) -> str | None:
        lowered = text.lower()
        if "injunction" not in lowered:
            return None
        if any(keyword in lowered for keyword in {"granted", "won", "secured", "obtained"}):
            return "positive"
        if any(keyword in lowered for keyword in {"denied", "refused", "declined", "lost"}):
            return "negative"
        return None

    @staticmethod
    def _positive_legal_injunction_favors_yes(rule_parse: RuleParse) -> bool:
        lowered = rule_parse.yes_condition.lower()
        return AnalysisProcessor._yes_condition_favors_negative_legal_outcome(rule_parse) or any(
            phrase in lowered
            for phrase in {
                "wins meaningful court relief",
                "wins the lawsuit",
                "prevailing on the merits",
                "obtaining the injunction",
            }
        )

    @staticmethod
    def _yes_condition_favors_negative_legal_outcome(rule_parse: RuleParse) -> bool:
        lowered = rule_parse.yes_condition.lower()
        return any(
            keyword in lowered
            for keyword in {"strike down", "block", "invalidate", "rule against", "unconstitutional"}
        )

    def _freshness_multiplier(self, source: Source) -> float:
        reference_time = source.published_at or source.fetched_at
        age_hours = max((datetime.now(UTC) - reference_time).total_seconds() / 3600, 0.0)
        if age_hours <= 6:
            return 1.0
        if age_hours <= 24:
            return 0.85
        if age_hours <= 72:
            return 0.65
        return 0.40

    def _priced_in_risk(
        self,
        market: Market | None,
        source_contexts: list[SourceContext],
        social_intel_summary: SocialIntelSummary | None,
    ) -> PricedInRiskLabelEnum:
        if social_intel_summary is not None:
            if social_intel_summary.narrative_phase == NarrativePhaseEnum.PRICED_IN:
                return PricedInRiskLabelEnum.HIGH
            if social_intel_summary.narrative_phase == NarrativePhaseEnum.CROWDED:
                return PricedInRiskLabelEnum.MEDIUM

        published_times = [
            source_context.source.published_at or source_context.source.fetched_at
            for source_context in source_contexts
            if source_context.source.source_kind != SourceKindEnum.MANUAL_INPUT
        ]
        if not published_times:
            return PricedInRiskLabelEnum.MEDIUM

        freshest = max(published_times)
        age_hours = max((datetime.now(UTC) - freshest).total_seconds() / 3600, 0.0)
        if age_hours <= 6:
            return PricedInRiskLabelEnum.LOW
        if age_hours <= 24:
            return PricedInRiskLabelEnum.MEDIUM
        if market is not None and market.spread is not None and market.spread <= 0.03:
            return PricedInRiskLabelEnum.HIGH
        return PricedInRiskLabelEnum.HIGH

    def _confidence_label(
        self,
        p_low: float,
        p_high: float,
        factors: list[Factor],
    ) -> ConfidenceLabelEnum:
        width = p_high - p_low
        supported_directional = sum(
            1
            for factor in factors
            if factor.used_in_scoring and factor.stance != StanceEnum.NEUTRAL
        )
        if width <= 0.18 and supported_directional >= 2:
            return ConfidenceLabelEnum.HIGH
        if width <= 0.32 and supported_directional >= 1:
            return ConfidenceLabelEnum.MEDIUM
        return ConfidenceLabelEnum.LOW

    @staticmethod
    def _social_uncertainty_adjustment(
        social_intel_summary: SocialIntelSummary | None,
    ) -> float:
        return social_uncertainty_adjustment(social_intel_summary)

    @classmethod
    def _capped_evidence_score(
        cls,
        factors: list[Factor],
        fact_lookup: dict[int, FactClaim],
        source_lookup: dict[int, Source],
    ) -> float:
        return max(min(capped_evidence_score(factors, fact_lookup, source_lookup), 2.5), -2.5)

    @staticmethod
    def _apply_social_confidence_modifier(
        base_confidence: ConfidenceLabelEnum,
        social_intel_summary: SocialIntelSummary | None,
    ) -> ConfidenceLabelEnum:
        if social_intel_summary is None:
            return base_confidence
        if social_intel_summary.consensus_label in {
            ConsensusLabelEnum.MIXED,
            ConsensusLabelEnum.UNCLEAR,
        } or social_intel_summary.narrative_phase in {
            NarrativePhaseEnum.CROWDED,
            NarrativePhaseEnum.PRICED_IN,
        }:
            if base_confidence == ConfidenceLabelEnum.HIGH:
                return ConfidenceLabelEnum.MEDIUM
            if base_confidence == ConfidenceLabelEnum.MEDIUM:
                return ConfidenceLabelEnum.LOW
        return base_confidence

    @staticmethod
    def _has_contradictory_factors(factors: list[Factor]) -> bool:
        return has_contradictory_factors(factors)

    def _fallback_factor_mapping(
        self,
        rule_parse: RuleParse | Any,
        fact: FactClaim,
    ) -> FactorMappingDraft:
        source = Source(
            analysis_run_id=fact.analysis_run_id,
            title="Fallback source",
            source_kind=SourceKindEnum.NEWS,
            source_tier=SourceTierEnum.REPUTABLE_NEWS,
            fetched_at=datetime.now(UTC),
            content_hash="fallback",
            excerpt=fact.exact_quote,
            is_paywalled=False,
            metadata_json={},
            created_at=datetime.now(UTC),
        )
        if not getattr(fact, "evidence_role", None):
            fact.evidence_role = self._fallback_evidence_role(rule_parse, source, fact).evidence_role
        return self._deterministic_factor_mapping(rule_parse, source, fact)

    @staticmethod
    def _should_run_live_x_intelligence(
        request: AnalysisRequest,
        rule_parse: RuleParse,
    ) -> bool:
        if request.mode.value != "manual":
            return False
        payload = request.input_payload or {}
        if payload.get("include_live_x_intelligence") is not None:
            return bool(payload["include_live_x_intelligence"])
        return rule_parse.template_detected in {
            TemplateKey.MACRO_POLICY,
            TemplateKey.LEGAL_CASE,
            TemplateKey.NARRATIVE_MANUAL,
            TemplateKey.GENERIC_MANUAL,
        }

    @staticmethod
    def _social_playbook_context(rule_parse: RuleParse) -> str:
        if rule_parse.template_detected == TemplateKey.OFFICIAL_EVENT:
            return (
                "Prioritize official regulators, company or issuer accounts, official spokespeople, "
                "and specialist beat reporters only when clearly relevant."
            )
        if rule_parse.template_detected == TemplateKey.LEGAL_CASE:
            return (
                "Prioritize specialist legal reporters, litigating parties, court-focused analysis, "
                "and official legal institutions. Treat broad political chatter as low trust."
            )
        if rule_parse.template_detected == TemplateKey.MACRO_POLICY:
            return (
                "Prioritize central bank officials, major macro reporters, economists, and "
                "policy specialists with credible track records."
            )
        return (
            "Use the most conservative trust threshold. Prefer institutional or clearly domain-expert "
            "accounts and avoid overclaiming broad X consensus."
        )

    @staticmethod
    def _social_tools_for_template(rule_parse: RuleParse) -> list[dict[str, Any]]:
        if rule_parse.template_detected == TemplateKey.LEGAL_CASE:
            days = 30
        else:
            days = 21 if rule_parse.template_detected == TemplateKey.OFFICIAL_EVENT else 14
        from_date = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
        to_date = datetime.now(UTC).date().isoformat()
        return [
            {
                "type": "x_search",
                "from_date": from_date,
                "to_date": to_date,
            },
            {
                "type": "web_search",
            },
        ]

    @staticmethod
    def _sigmoid(value: float) -> float:
        return sigmoid(value)

    @staticmethod
    def _logit(probability: float | None) -> float:
        return logit(probability)

    @staticmethod
    def _uniqueness_group(source: Source, fact: ExtractedFactDraft, index: int) -> str:
        if source.canonical_url:
            return source.canonical_url
        event_part = fact.extracted_timestamp.date().isoformat() if fact.extracted_timestamp else "nodate"
        payload = f"{fact.normalized_fact.lower()}|{source.domain}|{event_part}|{index}"
        return sha256(payload.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _hash_text(text: str) -> str:
        return sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _domain_from_url(url: str | None) -> str | None:
        if not url:
            return None
        return urlparse(url).netloc.lower() or None

    @staticmethod
    def _detect_template(text: str) -> TemplateKey:
        lowered = text.lower()
        if any(
            keyword in lowered
            for keyword in {
                "scotus",
                "supreme court",
                "injunction",
                "judge",
                "court",
                "constitutionality",
                "constitutional",
                "strike down",
                "uphold",
                "merits",
                "oral arguments",
                "oral argument",
                "lawsuit",
            }
        ):
            return TemplateKey.LEGAL_CASE
        if any(keyword in lowered for keyword in {"fed", "fomc", "rate cut", "inflation", "jobs report"}):
            return TemplateKey.MACRO_POLICY
        if any(
            keyword in lowered
            for keyword in {
                "approve",
                "approval",
                "announce",
                "filing",
                "file",
                "ruling",
                "official",
                "by ",
            }
        ):
            return TemplateKey.OFFICIAL_EVENT
        if any(
            keyword in lowered
            for keyword in {"sentiment", "narrative", "consensus", "buzz", "vibe"}
        ):
            return TemplateKey.NARRATIVE_MANUAL
        return TemplateKey.GENERIC_MANUAL

    @staticmethod
    def _looks_binary(text: str) -> bool:
        lowered = text.lower()
        return lowered.startswith("will ") or lowered.startswith("is ") or lowered.startswith("does ")

    @staticmethod
    def _official_domains_for_template(template: TemplateKey) -> list[str]:
        if template == TemplateKey.MACRO_POLICY:
            return ["federalreserve.gov", "bls.gov", "bea.gov", "fred.stlouisfed.org"]
        if template == TemplateKey.LEGAL_CASE:
            return ["supremecourt.gov", "uscourts.gov", "justice.gov"]
        if template == TemplateKey.OFFICIAL_EVENT:
            return ["sec.gov", "federalreserve.gov", "whitehouse.gov", "justice.gov"]
        return []

    @staticmethod
    def _expand_search_aliases(text: str | None) -> str:
        if not text:
            return ""
        expanded = text
        for pattern, replacement in SEARCH_ALIAS_REPLACEMENTS.items():
            expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)
        return expanded

    @staticmethod
    def _normalize_legal_party(party: str) -> str:
        normalized = party.strip().rstrip("?")
        normalized = re.sub(r"^\bthe\s+", "", normalized, flags=re.IGNORECASE)
        lowered = normalized.lower()
        if lowered == "dod":
            return "Department of Defense"
        if lowered == "pentagon":
            return "Department of Defense"
        if lowered == "scotus":
            return "Supreme Court"
        return normalized

    @classmethod
    def _normalize_legal_target(cls, target: str) -> str:
        normalized = re.sub(r"\beo\b", "executive order", target, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+", " ", normalized).strip().rstrip("?")
        return normalized

    @classmethod
    def _extract_legal_parties(cls, text: str) -> tuple[str, str] | None:
        match = re.match(
            r"^\s*will\s+(.+?)\s+win\s+(?:its|his|her|their)?\s*lawsuit\s+against\s+(.+?)\s*\??$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        plaintiff = cls._normalize_legal_party(match.group(1))
        defendant = cls._normalize_legal_party(match.group(2))
        if not plaintiff or not defendant:
            return None
        return plaintiff, defendant

    @classmethod
    def _extract_legal_side_with_target(cls, text: str) -> str | None:
        match = re.match(
            r"^\s*will\s+(?:the\s+)?(?:supreme court|scotus|court|judge)\s+side with\s+(.+?)\s*\??$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        target = cls._normalize_legal_target(match.group(1))
        return target or None

    @staticmethod
    def _legal_target_is_challenged_action(target: str) -> bool:
        lowered = target.lower()
        return any(
            phrase in lowered
            for phrase in {
                "executive order",
                "order",
                "rule",
                "policy",
                "statute",
                "law",
                "regulation",
                "ban",
                "program",
            }
        )

    @staticmethod
    def _clean_entity_candidate(candidate: str) -> str | None:
        parts = candidate.split()
        while parts and parts[0].lower() in LEADING_QUESTION_WORDS:
            parts = parts[1:]
        cleaned = " ".join(parts).strip()
        return cleaned or None

    @staticmethod
    def _yes_no_conditions(text: str, claim_family: ClaimFamilyEnum) -> tuple[str, str]:
        lowered = text.lower().strip().rstrip("?")
        if claim_family == ClaimFamilyEnum.LEGAL_CASE:
            parties = AnalysisProcessor._extract_legal_parties(text)
            if parties is not None:
                plaintiff, defendant = parties
                return (
                    f"YES if {plaintiff} wins meaningful court relief against {defendant}, such as prevailing on the merits or obtaining the injunction or order the suit seeks.",
                    f"NO if {plaintiff} loses against {defendant}, the case is dismissed, or the court denies relief and lets {defendant}'s position stand.",
                )
            side_target = AnalysisProcessor._extract_legal_side_with_target(text)
            if side_target is not None:
                if AnalysisProcessor._legal_target_is_challenged_action(side_target):
                    return (
                        f"YES if the court upholds, allows, or lets {side_target} take effect on the merits.",
                        f"NO if the court blocks, strikes down, invalidates, or rules against {side_target} on the merits.",
                    )
                return (
                    f"YES if the court sides with {side_target} on the merits and grants the relief or position that side seeks.",
                    f"NO if the court rules against {side_target} on the merits or denies the relief that side seeks.",
                )
            if "strike down" in lowered:
                return (
                    f"YES if {text.rstrip('?')} is true and the court invalidates or rules against the challenged action.",
                    "NO if the court upholds, allows, or refuses to strike down the challenged action.",
                )
            if "uphold" in lowered:
                return (
                    f"YES if {text.rstrip('?')} is true and the court upholds or allows the challenged action.",
                    "NO if the court blocks, invalidates, or strikes down the challenged action.",
                )
            return (
                f"YES if the court outcome described in '{text.rstrip('?')}' happens on the merits.",
                "NO if the opposite court outcome happens on the merits.",
            )
        if lowered.startswith("will "):
            proposition = text.rstrip("?")
            return (
                f"YES if {proposition[5:]} happens.",
                f"NO if {proposition[5:]} does not happen.",
            )
        if lowered.startswith("is "):
            proposition = text.rstrip("?")
            return (
                f"YES if {proposition[3:]} is true.",
                f"NO if {proposition[3:]} is false.",
            )
        return (
            f"YES if the proposition '{text.rstrip('?')}' is true.",
            f"NO if the opposite of '{text.rstrip('?')}' is true.",
        )

    @staticmethod
    def _default_scoring_policy(claim_family: ClaimFamilyEnum) -> dict[str, Any]:
        if claim_family == ClaimFamilyEnum.OFFICIAL_EVENT:
            return {
                "allowed_roles": [
                    EvidenceRoleEnum.OUTCOME.value,
                    EvidenceRoleEnum.DIRECT_SUPPORT.value,
                    EvidenceRoleEnum.DIRECT_CONTRADICTION.value,
                ],
                "commentary_mode": "none",
                "procedural_mode": "uncertainty_only",
            }
        if claim_family == ClaimFamilyEnum.MACRO_POLICY:
            return {
                "allowed_roles": [
                    EvidenceRoleEnum.OUTCOME.value,
                    EvidenceRoleEnum.DIRECT_SUPPORT.value,
                    EvidenceRoleEnum.DIRECT_CONTRADICTION.value,
                    EvidenceRoleEnum.COMMENTARY.value,
                ],
                "commentary_mode": "expert_only",
                "procedural_mode": "uncertainty_only",
            }
        if claim_family == ClaimFamilyEnum.LEGAL_CASE:
            return {
                "allowed_roles": [
                    EvidenceRoleEnum.OUTCOME.value,
                    EvidenceRoleEnum.DIRECT_SUPPORT.value,
                    EvidenceRoleEnum.DIRECT_CONTRADICTION.value,
                    EvidenceRoleEnum.COMMENTARY.value,
                ],
                "commentary_mode": "expert_only",
                "procedural_mode": "uncertainty_only",
            }
        if claim_family == ClaimFamilyEnum.NARRATIVE_MANUAL:
            return {
                "allowed_roles": [
                    EvidenceRoleEnum.OUTCOME.value,
                    EvidenceRoleEnum.DIRECT_SUPPORT.value,
                    EvidenceRoleEnum.DIRECT_CONTRADICTION.value,
                    EvidenceRoleEnum.COMMENTARY.value,
                ],
                "commentary_mode": "bounded",
                "procedural_mode": "uncertainty_only",
            }
        return {
            "allowed_roles": [
                EvidenceRoleEnum.OUTCOME.value,
                EvidenceRoleEnum.DIRECT_SUPPORT.value,
                EvidenceRoleEnum.DIRECT_CONTRADICTION.value,
            ],
            "commentary_mode": "none",
            "procedural_mode": "uncertainty_only",
        }

    @staticmethod
    def _entity_names(text: str) -> list[str]:
        candidates = re.findall(r"\b[A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})*\b", text)
        unique: list[str] = []
        for candidate in candidates:
            cleaned = AnalysisProcessor._clean_entity_candidate(candidate)
            if cleaned and cleaned not in unique:
                unique.append(cleaned)
        return unique[:5]

    @staticmethod
    def _detect_action(text: str) -> str:
        lowered = text.lower()
        for keyword in [
            "approve",
            "announce",
            "file",
            "rule",
            "cut",
            "win",
            "side with",
            "launch",
            "strike down",
            "uphold",
            "block",
            "invalidate",
        ]:
            if keyword in lowered:
                return keyword
        return "resolve"

    @staticmethod
    def _join_factor_rationales(factors: list[Factor]) -> str:
        rationales = [factor.rationale for factor in factors if factor.rationale]
        if not rationales:
            return "limited evidence so far"
        return " | ".join(rationales)

    @staticmethod
    def _format_probability(probability: float | None) -> str:
        if probability is None:
            return "Pending"
        percentage = probability * 100
        rounded = round(percentage)
        if abs(percentage - rounded) >= 0.05:
            return f"{percentage:.1f}%"
        return f"{rounded}%"

    @staticmethod
    def _normalize_source_text(*parts: str | None) -> str:
        text = "\n\n".join(
            part.strip()
            for part in parts
            if isinstance(part, str) and part.strip()
        )
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:MAX_DOCUMENT_CHARS].strip()

    @staticmethod
    def _signal_terms(text: str) -> set[str]:
        terms: set[str] = set()
        for term in re.findall(r"[a-z0-9]{3,}", text.lower()):
            if term in STOPWORDS:
                continue
            terms.add(term)
            if term.endswith("ies") and len(term) > 5:
                terms.add(term[:-3] + "y")
            elif term.endswith("s") and len(term) > 3 and not term.endswith("ss"):
                terms.add(term[:-1])
        return terms

    @staticmethod
    def _is_low_signal_sentence(text: str) -> bool:
        lowered = text.lower()
        return any(phrase in lowered for phrase in LOW_SIGNAL_PHRASES)


@lru_cache
def _default_analysis_processor() -> AnalysisProcessor:
    return AnalysisProcessor()


def get_analysis_processor() -> AnalysisProcessor:
    return _default_analysis_processor()
