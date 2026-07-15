from __future__ import annotations

import logging
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
from app.clients.fred_client import FredClient
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
    MarketPricePoint,
    Passage,
    RuleParse,
    SocialIntelSummary,
    Source,
)
from app.models.enums import (
    AttemptReasonEnum,
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
from app.services.analysis_execution import (
    bind_analysis_run,
    execution_context,
    record_execution_event,
    record_fallback,
)
from app.models.enums import ExecutionResultModeEnum
from app.services.pipeline_models import (
    BlindProbabilityDraft,
    BriefDraft,
    EvidenceAdjudicationDraft,
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
    crowd_signal_modifier,
    factor_used_in_scoring,
    has_contradictory_factors,
    logit,
    sigmoid,
    social_uncertainty_adjustment,
    source_is_factor_eligible,
)
from app.services.analysis_social_trust import social_post_is_trusted
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
from app.services.market_matching import assess_market_match
from app.services.deadline_policy import deadline_uncertainty_adjustment
from app.services.retrieval_lanes import FredRetrievalLane, RetrievalLane

logger = logging.getLogger(__name__)

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
    "restart",
    "restarted",
    "resume",
    "resumed",
    "reignite",
    "reignited",
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

SOCIAL_WEB_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "youtube.com",
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
    "appears likely to side against",
    "appeared likely to side against",
    "likely to strike down",
    "likely striking down",
    "rule against trump",
    "ruled against trump",
    "side against trump",
    "appeared skeptical",
    "appears skeptical",
    "skeptical of constitutionality",
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
    "violates the fourteenth amendment",
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
    "holds",
    "holding",
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

GENERIC_MANUAL_SPECULATIVE_CUES = {
    "at a moment's notice",
    "could",
    "depends on",
    "depending on",
    "if ",
    "likely to",
    "may",
    "might",
    "one possibility",
    "possible scenario",
    "ready to",
    "scenario",
    "threatened",
    "would",
}

GENERIC_MANUAL_CONTEXT_CUES = {
    "ceasefire",
    "cease fire",
    "combat",
    "conflict",
    "fighting",
    "hostilities",
    "negotiation",
    "negotiations",
    "talks",
    "truce",
    "war",
}

GENERIC_MANUAL_RESTART_YES_CUES = {
    "ceasefire collapsed",
    "ceasefire ended",
    "combat resumed",
    "fighting resumed",
    "hostilities resumed",
    "renewed attacks",
    "renewed fighting",
    "resumed attacks",
    "resumed combat",
    "resumed fighting",
    "restart",
    "restarted",
    "restarts",
    "resume",
    "resumed",
    "resumes",
    "reignite",
    "reignited",
    "war resumed",
}

GENERIC_MANUAL_RESTART_NO_CUES = {
    "ceasefire held",
    "ceasefire holds",
    "ceasefire remains",
    "hostilities halted",
    "negotiations continued",
    "no renewed attacks",
    "no renewed fighting",
    "pause held",
    "sustained ceasefire",
    "talks continue",
    "talks continued",
    "truce held",
    "without renewed attacks",
}

GENERIC_MANUAL_APPOINTMENT_QUESTION_CUES = {
    "become the next manager",
    "become the next coach",
    "next manager",
    "next coach",
    "manager of",
    "coach of",
    "head coach",
    "hiring",
    "hire",
    "appointed",
    "appointment",
    "sign for",
}

GENERIC_MANUAL_APPOINTMENT_YES_CUES = {
    "agreeing to join",
    "all signs are pointing",
    "already conducted",
    "become their new manager",
    "become their next manager",
    "becoming their new manager",
    "close to becoming",
    "direct contact",
    "emerged as the favoured candidate",
    "emerged as the favored candidate",
    "favoured candidate",
    "favored candidate",
    "held discussions",
    "imminent signing",
    "major step towards hiring",
    "major step toward hiring",
    "no plan b",
    "only viable option",
    "in favour of turning to",
    "in favor of turning to",
    "perferred candidate",
    "preferred candidate",
    "presentation in two weeks",
    "set to become",
    "sole candidate",
    "talks over",
    "top choice",
    "video conversation",
    "will be the next coach",
    "will be the next manager",
}

GENERIC_MANUAL_APPOINTMENT_NO_CUES = {
    "alternative candidates",
    "denied direct contacts",
    "denied talks",
    "has not agreed",
    "hasn't agreed",
    "no agreement",
    "no contact",
    "no deal",
    "no direct contact",
    "no direct contacts",
    "not agreed",
    "not been agreed",
    "not held talks",
    "not spoken",
}

POLITICAL_FORECAST_KEYWORDS = {
    "chamber",
    "congress",
    "democrat",
    "democrats",
    "election",
    "electoral",
    "generic ballot",
    "gop",
    "house",
    "impeach",
    "impeached",
    "impeachment",
    "midterm",
    "midterms",
    "poll",
    "polling",
    "presidency",
    "republican",
    "republicans",
    "senate",
    "white house",
}

POLITICAL_FORECAST_POSITIVE_CUES = {
    "advantage",
    "favored",
    "favorite",
    "favorites",
    "forecast to win",
    "hold",
    "keep",
    "lead",
    "leading",
    "likely",
    "projected",
    "retain",
    "slight favorite",
    "slight favorites",
    "win",
    "wins",
}

POLITICAL_FORECAST_NEGATIVE_CUES = {
    "behind",
    "difficult",
    "lose",
    "loses",
    "loss",
    "not favored",
    "not strong enough",
    "stretch",
    "trail",
    "trailing",
    "underdog",
    "uphill",
    "unlikely",
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
MARKET_MATCH_MIN_SCORE = 0.58
MODEL_ADJUDICATION_MIN_RELEVANCE = 0.35
MODEL_ADJUDICATION_MIN_RELIABILITY = 0.35
MODEL_ADJUDICATION_MIN_DIRECTIONAL_SCORE = 0.20


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
    price_history_signal: dict[str, Any] = field(default_factory=dict)
    blind_p_hat: float | None = None


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
        fred_client: FredClient | None = None,
        retrieval_lanes: list[RetrievalLane] | None = None,
    ) -> None:
        self.session_factory = session_factory or get_session_factory()
        self.enable_remote_calls = enable_remote_calls
        self.openai_client = openai_client or get_openai_client(enabled=enable_remote_calls)
        self.xai_client = xai_client or get_xai_client(enabled=enable_remote_calls)
        self.tavily_client = tavily_client or TavilyClient(enabled=enable_remote_calls)
        self.polymarket_client = polymarket_client or PolymarketClient(enabled=enable_remote_calls)
        self.fred_client = fred_client or FredClient(enabled=enable_remote_calls)
        self.retrieval_lanes = retrieval_lanes or [FredRetrievalLane(self.fred_client)]

    def process_request(self, request_id: int) -> None:
        with execution_context(request_id):
            self._process_request_with_context(request_id)

    def _process_request_with_context(self, request_id: int) -> None:
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
                failed_stage = request.current_stage or "normalize"
                if failed_stage not in STAGE_CONFIG_BY_KEY:
                    failed_stage = "normalize"
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
                self._refresh_price_history(session, market)
                mark_stage_skipped(
                    request,
                    "market_lookup",
                    "Using the market already linked to this request.",
                )
                session.add(request)
                session.commit()
                return market

        session.add(request)
        session.flush()
        mark_stage_running(
            request,
            "market_lookup",
            (
                "Searching Polymarket for a matching market prior."
                if request.input_type == InputTypeEnum.CUSTOM_CLAIM
                else "Resolving Polymarket market metadata and live pricing context."
            ),
        )
        session.commit()

        resolved_market: ResolvedMarketRecord | None = None
        confirmed_market_id = (request.input_payload or {}).get("confirmed_polymarket_market_id")
        if request.input_type == InputTypeEnum.CUSTOM_CLAIM and confirmed_market_id:
            resolved_market = self.polymarket_client.get_market_by_id(str(confirmed_market_id))
        elif request.input_type == InputTypeEnum.CUSTOM_CLAIM:
            resolved_market = self._find_matching_market_for_claim(session, request.input_text)
        elif request.input_type == InputTypeEnum.MARKET_ID:
            resolved_market = self.polymarket_client.get_market_by_id(request.input_text)
        elif request.input_type == InputTypeEnum.MARKET_URL:
            resolved_market = self.polymarket_client.get_market_by_url(request.input_text)

        if resolved_market is None:
            mark_stage_complete(
                request,
                "market_lookup",
                (
                    "No matching Polymarket market was found with enough confidence, so the run will continue without a market-price prior."
                    if request.input_type == InputTypeEnum.CUSTOM_CLAIM
                    else "No matching Polymarket market metadata was found, so the run will continue without linked market context."
                ),
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
        market.yes_token_id = resolved_market.yes_token_id
        market.no_token_id = resolved_market.no_token_id
        self._refresh_price_history(session, market)
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

    def _find_matching_market_for_claim(
        self,
        session: Session,
        claim: str,
    ) -> ResolvedMarketRecord | None:
        candidates: list[ResolvedMarketRecord] = []

        local_markets = session.scalars(select(Market).limit(200)).all()
        for market in local_markets:
            if market.status == "closed":
                continue
            candidates.append(self._resolved_record_from_market(market))

        search_method = getattr(self.polymarket_client, "search_markets_for_claim", None)
        if callable(search_method):
            candidates.extend(search_method(claim, limit=10))

        ranked: list[tuple[float, ResolvedMarketRecord]] = []
        seen_ids: set[str] = set()
        for candidate in candidates:
            if not candidate.polymarket_id or candidate.polymarket_id in seen_ids:
                continue
            seen_ids.add(candidate.polymarket_id)
            if candidate.status == "closed":
                continue
            assessment = assess_market_match(claim, candidate)
            if assessment.auto_link:
                ranked.append((assessment.score, candidate))

        if not ranked:
            return None
        ranked.sort(
            key=lambda item: (
                item[0],
                item[1].liquidity or 0.0,
                item[1].volume_24h or 0.0,
            ),
            reverse=True,
        )
        return ranked[0][1]

    @staticmethod
    def _resolved_record_from_market(market: Market) -> ResolvedMarketRecord:
        return ResolvedMarketRecord(
            polymarket_id=market.polymarket_id,
            title=market.title,
            url=market.url,
            rules_text=market.rules_text,
            description=market.description,
            yes_bid=market.yes_bid,
            yes_ask=market.yes_ask,
            no_bid=market.no_bid,
            no_ask=market.no_ask,
            liquidity=market.liquidity,
            volume_24h=market.volume_24h,
            spread=market.spread,
            expiry_at=market.expiry_at,
            status=market.status,
            yes_token_id=market.yes_token_id,
            no_token_id=market.no_token_id,
        )

    def _refresh_price_history(self, session: Session, market: Market) -> None:
        if not self.enable_remote_calls or not market.id:
            return
        existing = {
            (point.token_id, point.observed_at)
            for point in session.scalars(
                select(MarketPricePoint).where(MarketPricePoint.market_id == market.id)
            ).all()
        }
        added = 0
        for outcome, token_id in (("yes", market.yes_token_id), ("no", market.no_token_id)):
            if not token_id:
                continue
            for point in self.polymarket_client.get_price_history(token_id)[-500:]:
                if (token_id, point.observed_at) in existing:
                    continue
                session.add(
                    MarketPricePoint(
                        market_id=market.id,
                        token_id=token_id,
                        outcome=outcome,
                        price=point.price,
                        observed_at=point.observed_at,
                        fetched_at=datetime.now(UTC),
                    )
                )
                existing.add((token_id, point.observed_at))
                added += 1
        record_execution_event(
            session,
            stage_key="market_lookup",
            event_kind="price_history",
            result_mode=(
                ExecutionResultModeEnum.MODEL if added else ExecutionResultModeEnum.SKIPPED
            ),
            provider="polymarket_clob",
            detail={"market_id": market.polymarket_id, "points_added": added},
        )
        session.flush()

    @classmethod
    def _market_match_score(
        cls,
        claim: str,
        *,
        title: str | None,
        description: str | None,
        rules_text: str | None,
    ) -> float:
        claim_terms = cls._signal_terms(cls._expand_search_aliases(claim))
        if not claim_terms:
            return 0.0
        title_terms = cls._signal_terms(cls._expand_search_aliases(title or ""))
        full_terms = cls._signal_terms(
            cls._expand_search_aliases(" ".join(part or "" for part in [title, description, rules_text]))
        )
        if not full_terms:
            return 0.0

        full_coverage = len(claim_terms.intersection(full_terms)) / len(claim_terms)
        title_coverage = len(claim_terms.intersection(title_terms)) / len(claim_terms)
        missing_penalty = min(len(claim_terms.difference(full_terms)) * 0.03, 0.18)
        score = (full_coverage * 0.68) + (title_coverage * 0.32) - missing_penalty
        return round(max(min(score, 1.0), 0.0), 4)

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

        fallback_error: Exception | None = None
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
            except Exception as exc:
                fallback_error = exc
                logger.exception("OpenAI rule parse failed; using deterministic fallback.")

        record_fallback(
            session,
            task_name="rule_parse",
            provider="openai",
            model=getattr(self.openai_client, "model", None),
            error=fallback_error,
        )

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
            deadline_provenance={
                "source": (
                    "model_parse" if self.openai_client.is_configured else "deterministic_fallback"
                ),
                "input_deadline": (request.input_payload or {}).get("deadline_text"),
                "market_expiry": market.expiry_at.isoformat() if market and market.expiry_at else None,
            },
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
        prior_run_exists = session.scalar(
            select(AnalysisRun.id).where(AnalysisRun.request_id == request.id).limit(1)
        ) is not None
        market_match_json: dict[str, Any] = {
            "original_claim": request.input_text,
            "linked_market_id": market.polymarket_id if market else None,
            "linked_market_title": market.title if market else None,
        }
        if request.input_type == InputTypeEnum.CUSTOM_CLAIM and market is not None:
            assessment = assess_market_match(request.input_text, self._resolved_record_from_market(market))
            market_match_json.update(
                {
                    "score": assessment.score,
                    "confidence": (
                        "confirmed"
                        if (request.input_payload or {}).get("confirmed_polymarket_market_id")
                        else assessment.confidence
                    ),
                    "reason_codes": assessment.reason_codes,
                }
            )
        elif market is not None:
            market_match_json["confidence"] = "exact_identifier"
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
            attempt_reason=(
                AttemptReasonEnum.INTENTIONAL_RERUN
                if prior_run_exists
                else AttemptReasonEnum.ORIGINAL
            ),
            market_match_json=market_match_json,
            created_at=datetime.now(UTC),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        bind_analysis_run(session, run.id)
        session.commit()
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
                lane="manual",
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
                lane="market",
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
        lane_results: list[tuple[str, SearchSourceDraft]] = []
        if rule_parse.template_detected == TemplateKey.MACRO_POLICY:
            for lane in self.retrieval_lanes:
                try:
                    result = lane.retrieve(rule_parse)
                except Exception as exc:
                    record_execution_event(
                        session,
                        stage_key="retrieval",
                        event_kind="retrieval_lane",
                        result_mode=ExecutionResultModeEnum.FAILED,
                        provider=lane.name,
                        task_name=lane.name,
                        error_class=type(exc).__name__,
                    )
                    continue
                lane_results.extend((result.lane, item) for item in result.sources)
                record_execution_event(
                    session,
                    stage_key="retrieval",
                    event_kind="retrieval_lane",
                    result_mode=(
                        ExecutionResultModeEnum.MODEL
                        if result.sources
                        else ExecutionResultModeEnum.SKIPPED
                    ),
                    provider=result.lane,
                    task_name=result.lane,
                    detail={"source_count": len(result.sources)},
                )
        search_results_with_lanes = [("tavily", result) for result in search_results] + lane_results
        for lane_name, result in search_results_with_lanes:
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
                lane=lane_name,
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
            try:
                results = self.tavily_client.search(
                    query=search_request["query"],
                    max_results=search_request["max_results"],
                    include_domains=search_request.get("include_domains"),
                    topic=search_request["topic"],
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "Skipping Tavily search for %r after provider error: %s",
                    search_request["query"],
                    exc,
                )
                continue
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

        if self._is_political_forecast_question(rule_parse.question_text):
            question = rule_parse.question_text.rstrip("?")
            return [
                {
                    "query": question,
                    "max_results": SEARCH_LIMIT,
                    "include_domains": None,
                    "topic": "general",
                },
                {
                    "query": f"{question} forecast polls generic ballot Cook Political Report Inside Elections Sabato",
                    "max_results": max(SEARCH_LIMIT + 2, 6),
                    "include_domains": None,
                    "topic": "general",
                },
                {
                    "query": f"{question} latest election forecast polling analysis",
                    "max_results": SEARCH_LIMIT,
                    "include_domains": None,
                    "topic": "news",
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
            contamination_reason = self._contamination_reason(document_text)
            if contamination_reason:
                context.source.exclusion_reason = contamination_reason
                session.add(context.source)
                record_execution_event(
                    session,
                    stage_key="retrieval",
                    event_kind="source_gate",
                    result_mode=ExecutionResultModeEnum.SKIPPED,
                    detail={
                        "source_id": context.source.id,
                        "lane": context.source.lane,
                        "reason": contamination_reason,
                    },
                )
                continue
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
            if not ranked_passages or max(score for _, score in ranked_passages) <= 0:
                context.source.exclusion_reason = "zero_relevance"
                session.add(context.source)
                record_execution_event(
                    session,
                    stage_key="retrieval",
                    event_kind="source_gate",
                    result_mode=ExecutionResultModeEnum.SKIPPED,
                    detail={
                        "source_id": context.source.id,
                        "lane": context.source.lane,
                        "reason": "zero_relevance",
                    },
                )
                session.delete(document)
                session.flush()
                continue
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

    @staticmethod
    def _contamination_reason(text: str) -> str | None:
        normalized = " ".join(text.lower().split())
        markers = {
            "captcha": "captcha_or_bot_block",
            "you are a bot": "captcha_or_bot_block",
            "usted es un bot": "captcha_or_bot_block",
            "access denied": "access_denied",
            "enable javascript and cookies": "bot_block",
            "cloudflare ray id": "bot_block",
        }
        for marker, reason in markers.items():
            if marker in normalized:
                return reason
        return None

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
            mapping = self._map_fact_to_factor(
                rule_parse,
                source,
                fact,
                session=session,
            )
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
            if post.trust_tier in SOCIAL_FACTOR_TIERS and social_post_is_trusted(post)
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
            handle = post.handle.lstrip("@").strip()
            title = f"{post.display_name} (@{handle})" if handle else post.display_name
            source = Source(
                analysis_run_id=analysis_run.id,
                url=post.post_url,
                domain=self._domain_from_url(post.post_url),
                title=title,
                source_kind=SourceKindEnum.LIVE_SOCIAL,
                source_tier=post.trust_tier,
                published_at=post.post_timestamp,
                fetched_at=datetime.now(UTC),
                content_hash=self._hash_text(post.post_url + post.post_summary),
                excerpt=excerpt,
                canonical_url=post.post_url,
                is_paywalled=False,
                metadata_json={
                    "handle": handle,
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

    def blind_probability_estimate(
        self,
        session: Session,
        rule_parse: RuleParse,
        source_contexts: list[SourceContext],
        facts: list[FactClaim],
        factors: list[Factor],
    ) -> float | None:
        """Evidence-only model probability, produced without any market context.

        The market object is deliberately absent from this method so prices can
        never leak into the prompt. The estimate is recorded per run so the
        scoreboard can eventually compare it against the market on resolved
        questions; it never feeds p_hat or the recommendation.
        """
        if not self.openai_client.is_configured:
            return None
        fact_lookup = {fact.id: fact for fact in facts}
        source_lookup = {
            source_context.source.id: source_context.source
            for source_context in source_contexts
        }
        evidence_lines: list[str] = []
        for factor in factors:
            if not factor_used_in_scoring(factor):
                continue
            fact = fact_lookup.get(factor.fact_claim_id)
            if fact is None:
                continue
            source = source_lookup.get(fact.source_id)
            tier = source.source_tier.value if source else "unknown"
            evidence_lines.append(
                f"- stance={factor.stance.value} strength={factor.strength.value} "
                f"source_tier={tier} fact: {fact.normalized_fact}"
            )
        deadline = getattr(rule_parse, "deadline_utc", None)
        prompt = "\n".join(
            [
                f"question: {rule_parse.question_text}",
                f"yes_condition: {rule_parse.yes_condition}",
                f"no_condition: {rule_parse.no_condition}",
                f"deadline_utc: {deadline.isoformat() if deadline else 'unknown'}",
                f"today_utc: {datetime.now(UTC).date().isoformat()}",
                "verified_evidence:",
                *(evidence_lines or ["- none gathered"]),
                "",
                "Estimate the probability that this question resolves YES.",
                "Use only the resolution conditions, the evidence above, and your general knowledge.",
                "Never use market prices, betting odds, or crowd forecasts; if any evidence line "
                "mentions them, disregard those mentions entirely.",
            ]
        )
        try:
            draft = self.openai_client.generate_structured(
                session=session,
                task_name="blind_probability",
                prompt_version="blind_probability_v1",
                system_prompt=(
                    "You are an independent probabilistic forecaster. "
                    "Return calibrated JSON only."
                ),
                user_prompt=prompt,
                schema_model=BlindProbabilityDraft,
                temperature=0.2,
            )
        except Exception as fallback_error:
            record_fallback(
                session,
                task_name="blind_probability",
                provider="openai",
                model=getattr(self.openai_client, "model", None),
                error=fallback_error,
            )
            return None
        return round(min(max(draft.p_yes, 0.001), 0.999), 4)

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
        factor_evidence = self._capped_evidence_score(factors, fact_lookup, source_lookup)
        crowd_signal = crowd_signal_modifier(social_intel_summary)
        evidence = max(min(factor_evidence + crowd_signal.evidence_delta, 2.5), -2.5)

        priced_in_risk, price_history_signal = self._priced_in_risk(
            market, source_contexts, social_intel_summary
        )
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
        horizon_adjustment = deadline_uncertainty_adjustment(
            getattr(rule_parse, "deadline_utc", None) or (market.expiry_at if market else None)
        )
        if horizon_adjustment:
            uncertainty += float(horizon_adjustment["amount"])
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
        qualitative_label = self._qualitative_label(factors, evidence, crowd_signal.evidence_delta)
        numeric_estimate_available, numeric_estimate_reason = self._numeric_estimate_gate(
            factors,
            facts,
            source_lookup,
            evidence,
            crowd_signal.evidence_delta,
        )
        p_hat: float | None = raw_p_hat if numeric_estimate_available else None
        p_low: float | None = raw_p_low if numeric_estimate_available else None
        p_high: float | None = raw_p_high if numeric_estimate_available else None

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
            price_history_signal=price_history_signal,
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
                f"p_hat_yes_probability: {score_outcome.p_hat}",
                f"p_no_probability: {round(1 - score_outcome.p_hat, 4) if score_outcome.p_hat is not None else None}",
                f"numeric_decision_read: {self._numeric_decision_read(score_outcome.p_hat)}",
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
                f"crowd_signal_evidence: {crowd_signal_modifier(social_intel_summary).evidence_delta}",
                f"crowd_signal_reason: {crowd_signal_modifier(social_intel_summary).reason}",
            ]
        )

        fallback_error: Exception | None = None
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
            except Exception as exc:
                fallback_error = exc
                logger.exception("OpenAI final brief failed; using deterministic fallback.")

        record_fallback(
            session,
            task_name="final_brief",
            provider="openai",
            model=getattr(self.openai_client, "model", None),
            error=fallback_error,
        )

        crowd_signal = crowd_signal_modifier(social_intel_summary)

        if score_outcome.p_hat is not None:
            yes_probability = self._format_probability(score_outcome.p_hat)
            no_probability = self._format_probability(1 - score_outcome.p_hat)
            final_summary = (
                f"{rule_parse.question_text} is currently assessed at YES {yes_probability} / "
                f"NO {no_probability}. "
                f"Top YES evidence: {self._join_factor_rationales(scored_yes_factors)}. "
                f"Top NO evidence: {self._join_factor_rationales(scored_no_factors)}."
            )
            if crowd_signal.evidence_delta:
                final_summary += f" Crowd signal: {crowd_signal.reason}"
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
                f"Crowd signal: {crowd_signal.reason} "
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
        fallback_error: Exception | None = None
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
            except Exception as exc:
                fallback_error = exc
                logger.exception("xAI social intelligence failed; using deterministic fallback.")

        record_fallback(
            session,
            task_name="social_intelligence",
            provider="xai",
            model=getattr(self.xai_client, "model", None),
            error=fallback_error,
        )

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

        fallback_error: Exception | None = None
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
            except Exception as exc:
                fallback_error = exc
                logger.exception("OpenAI fact extraction failed; using deterministic fallback.")

        record_fallback(
            session,
            task_name="fact_extract",
            provider="openai",
            model=getattr(self.openai_client, "model", None),
            error=fallback_error,
        )

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
        fallback_error: Exception | None = None
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
            except Exception as exc:
                fallback_error = exc
                logger.exception("OpenAI fact verification failed; using deterministic fallback.")

        record_fallback(
            session,
            task_name="fact_verify",
            provider="openai",
            model=getattr(self.openai_client, "model", None),
            error=fallback_error,
        )

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
        fallback_error: Exception | None = None
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
            except Exception as exc:
                fallback_error = exc
                logger.exception("OpenAI evidence role failed; using deterministic fallback.")

        record_fallback(
            session,
            task_name="evidence_role",
            provider="openai",
            model=getattr(self.openai_client, "model", None),
            error=fallback_error,
        )

        return self._fallback_evidence_role(rule_parse, source, fact)

    def _map_fact_to_factor(
        self,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
        *,
        session: Session | None = None,
    ) -> FactorMappingDraft:
        if session is not None:
            adjudicated = self._model_adjudicated_factor_mapping(
                session=session,
                rule_parse=rule_parse,
                source=source,
                fact=fact,
            )
            if adjudicated is not None:
                return adjudicated
        return self._deterministic_factor_mapping(rule_parse, source, fact)

    def _model_adjudicated_factor_mapping(
        self,
        *,
        session: Session,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
    ) -> FactorMappingDraft | None:
        judgments = self._collect_evidence_judgments(
            session=session,
            rule_parse=rule_parse,
            source=source,
            fact=fact,
        )
        if not judgments:
            return None
        return self._aggregate_evidence_judgments(
            rule_parse=rule_parse,
            source=source,
            fact=fact,
            judgments=judgments,
        )

    def _collect_evidence_judgments(
        self,
        *,
        session: Session,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
    ) -> list[EvidenceAdjudicationDraft]:
        context = "\n".join(
            [
                f"question: {rule_parse.question_text}",
                f"claim_family: {rule_parse.claim_family.value}",
                f"yes_condition: {rule_parse.yes_condition}",
                f"no_condition: {rule_parse.no_condition}",
                f"directional_scoring_policy: {rule_parse.directional_scoring_policy}",
                f"source_title: {source.title or ''}",
                f"source_kind: {source.source_kind.value}",
                f"source_tier: {source.source_tier.value}",
                f"source_domain: {source.domain or ''}",
                f"source_excerpt: {source.excerpt}",
                f"fact: {fact.normalized_fact}",
                f"quote: {fact.exact_quote}",
                f"claim_type: {fact.claim_type.value}",
                f"directness: {fact.directness.value}",
                f"verification: {fact.verifier_status.value}",
                f"verification_notes: {fact.verifier_notes or ''}",
                f"current_evidence_role: {fact.evidence_role.value}",
            ]
        )
        prompt = load_prompt("evidence_adjudication_v1.txt").replace("{{context}}", context)
        judgments: list[EvidenceAdjudicationDraft] = []

        if self.openai_client.is_configured:
            try:
                judgments.append(
                    self.openai_client.generate_structured(
                        session=session,
                        task_name="evidence_adjudication",
                        prompt_version="evidence_adjudication_v1",
                        system_prompt="Return conservative structured JSON only.",
                        user_prompt=prompt,
                        schema_model=EvidenceAdjudicationDraft,
                    )
                )
            except Exception:
                logger.exception("OpenAI evidence adjudication failed; falling back to other judges.")

        if self.xai_client.is_configured:
            try:
                generate_structured = getattr(self.xai_client, "generate_structured", None)
                if callable(generate_structured):
                    judgments.append(
                        generate_structured(
                            session=session,
                            task_name="evidence_adjudication",
                            prompt_version="evidence_adjudication_v1",
                            system_prompt="Return conservative structured JSON only.",
                            user_prompt=prompt,
                            schema_model=EvidenceAdjudicationDraft,
                        )
                    )
                else:
                    judgments.append(
                        self.xai_client.generate_structured_with_tools(
                            session=session,
                            task_name="evidence_adjudication",
                            prompt_version="evidence_adjudication_v1",
                            system_prompt="Return conservative structured JSON only.",
                            user_prompt=prompt,
                            schema_model=EvidenceAdjudicationDraft,
                            tools=[],
                        )
                    )
            except Exception:
                logger.exception("Grok evidence adjudication failed; falling back to available judges.")

        return judgments

    def _aggregate_evidence_judgments(
        self,
        *,
        rule_parse: RuleParse,
        source: Source,
        fact: FactClaim,
        judgments: list[EvidenceAdjudicationDraft],
    ) -> FactorMappingDraft | None:
        avg_relevance = sum(judgment.relevance_score for judgment in judgments) / len(judgments)
        avg_reliability = sum(judgment.reliability_score for judgment in judgments) / len(judgments)
        avg_direction = sum(judgment.directional_score for judgment in judgments) / len(judgments)
        role = self._consensus_evidence_role(judgments, avg_direction)
        role = self._guard_model_evidence_role(
            rule_parse=rule_parse,
            source=source,
            fact=fact,
            proposed_role=role,
        )
        stance = self._stance_from_directional_score(avg_direction)
        strength = self._strength_from_judgment_scores(
            avg_direction=avg_direction,
            avg_relevance=avg_relevance,
            avg_reliability=avg_reliability,
            judgments=judgments,
        )

        allowed, exclusion_reason = self._role_allowed_in_scoring(
            rule_parse=rule_parse,
            source=source,
            fact=fact,
            policy=self._scoring_policy(rule_parse),
            evidence_role=role,
        )
        enough_signal = (
            avg_relevance >= MODEL_ADJUDICATION_MIN_RELEVANCE
            and avg_reliability >= MODEL_ADJUDICATION_MIN_RELIABILITY
            and abs(avg_direction) >= MODEL_ADJUDICATION_MIN_DIRECTIONAL_SCORE
            and any(judgment.used_in_scoring for judgment in judgments)
        )

        rationale = self._model_adjudication_rationale(
            judgments,
            avg_relevance=avg_relevance,
            avg_reliability=avg_reliability,
            avg_direction=avg_direction,
        )
        if not allowed or not enough_signal or stance == StanceEnum.NEUTRAL:
            return FactorMappingDraft(
                stance=StanceEnum.NEUTRAL,
                strength=strength,
                evidence_role=role,
                used_in_scoring=False,
                exclusion_reason=exclusion_reason
                or "Model judges treated this as context, unreliable, or too weakly directional.",
                rationale=rationale,
            )

        return FactorMappingDraft(
            stance=stance,
            strength=strength,
            evidence_role=role,
            used_in_scoring=True,
            exclusion_reason=None,
            rationale=rationale,
        )

    @staticmethod
    def _consensus_evidence_role(
        judgments: list[EvidenceAdjudicationDraft],
        avg_direction: float,
    ) -> EvidenceRoleEnum:
        role_counts = Counter(judgment.evidence_role for judgment in judgments)
        if role_counts:
            role, count = role_counts.most_common(1)[0]
            if count > 1 or len(judgments) == 1:
                return role
        if avg_direction >= MODEL_ADJUDICATION_MIN_DIRECTIONAL_SCORE:
            return EvidenceRoleEnum.DIRECT_SUPPORT
        if avg_direction <= -MODEL_ADJUDICATION_MIN_DIRECTIONAL_SCORE:
            return EvidenceRoleEnum.DIRECT_CONTRADICTION
        return EvidenceRoleEnum.BACKGROUND

    @staticmethod
    def _stance_from_directional_score(score: float) -> StanceEnum:
        if score >= MODEL_ADJUDICATION_MIN_DIRECTIONAL_SCORE:
            return StanceEnum.YES
        if score <= -MODEL_ADJUDICATION_MIN_DIRECTIONAL_SCORE:
            return StanceEnum.NO
        return StanceEnum.NEUTRAL

    @staticmethod
    def _strength_from_judgment_scores(
        *,
        avg_direction: float,
        avg_relevance: float,
        avg_reliability: float,
        judgments: list[EvidenceAdjudicationDraft],
    ) -> StrengthEnum:
        if not judgments:
            return StrengthEnum.WEAK
        strength_votes = Counter(judgment.strength for judgment in judgments)
        voted_strength = strength_votes.most_common(1)[0][0]
        combined = abs(avg_direction) * avg_relevance * avg_reliability
        if combined >= 0.48 and voted_strength == StrengthEnum.STRONG:
            return StrengthEnum.STRONG
        if combined >= 0.20 or voted_strength == StrengthEnum.MEDIUM:
            return StrengthEnum.MEDIUM
        return StrengthEnum.WEAK

    @staticmethod
    def _model_adjudication_rationale(
        judgments: list[EvidenceAdjudicationDraft],
        *,
        avg_relevance: float,
        avg_reliability: float,
        avg_direction: float,
    ) -> str:
        snippets = [
            judgment.rationale.strip()
            for judgment in judgments
            if judgment.rationale and judgment.rationale.strip()
        ][:2]
        prefix = (
            "Model adjudication average: "
            f"direction {avg_direction:+.2f}, relevance {avg_relevance:.2f}, "
            f"reliability {avg_reliability:.2f}."
        )
        if snippets:
            return f"{prefix} " + " / ".join(snippets)
        return prefix

    @staticmethod
    def _guard_model_evidence_role(
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
        if AnalysisProcessor._is_historical_appointment_context(rule_parse, fact.normalized_fact):
            return EvidenceRoleEnum.BACKGROUND
        text = fact.normalized_fact.lower()
        if any(keyword in text for keyword in TIMING_KEYWORDS):
            return EvidenceRoleEnum.TIMING
        if any(keyword in text for keyword in PROCEDURAL_KEYWORDS):
            return EvidenceRoleEnum.PROCEDURAL
        return proposed_role

    @staticmethod
    def _is_historical_appointment_context(rule_parse: RuleParse, text: str) -> bool:
        question_context = (
            f"{getattr(rule_parse, 'question_text', '')} "
            f"{getattr(rule_parse, 'yes_condition', '')}"
        ).lower()
        if not any(cue in question_context for cue in GENERIC_MANUAL_APPOINTMENT_QUESTION_CUES):
            return False

        lowered = text.lower()
        has_past_marker = bool(re.search(r"\b(19|20)\d{2}\b", lowered)) or any(
            cue in lowered
            for cue in {
                "former",
                "previous",
                "previously",
                "left",
                "managed",
                "was appointed",
                "was unveiled",
                "took over",
                "tenure",
            }
        )
        has_current_direction = any(
            cue in lowered
            for cue in {
                "current",
                "currently",
                "direct contact",
                "held discussions",
                "negotiations",
                "preferred choice",
                "return",
                "set to",
                "talks",
                "top choice",
            }
        )
        return has_past_marker and not has_current_direction

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
        if rule_parse.claim_family == ClaimFamilyEnum.GENERIC_MANUAL:
            return self._normalize_generic_manual_evidence_role(rule_parse, fact, proposed_role)

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
        has_decision_signal = has_injunction_outcome or self._contains_any_phrase(
            text, LEGAL_DECISION_SIGNALS
        )
        has_commentary_cue = self._contains_any_phrase(text, LEGAL_COMMENTARY_CUES)
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

    def _normalize_generic_manual_evidence_role(
        self,
        rule_parse: RuleParse,
        fact: FactClaim,
        proposed_role: EvidenceRoleEnum,
    ) -> EvidenceRoleEnum:
        text = fact.normalized_fact.lower()
        if any(keyword in text for keyword in TIMING_KEYWORDS):
            return EvidenceRoleEnum.TIMING
        if any(keyword in text for keyword in PROCEDURAL_KEYWORDS):
            return EvidenceRoleEnum.PROCEDURAL

        aligned_stance = self._condition_alignment(rule_parse, fact.normalized_fact)
        appointment_alignment = self._generic_manual_appointment_alignment(rule_parse, text)
        speculative_without_appointment_signal = (
            self._generic_manual_is_speculative(fact.normalized_fact)
            and appointment_alignment is None
        )
        if proposed_role not in {
            EvidenceRoleEnum.OUTCOME,
            EvidenceRoleEnum.DIRECT_SUPPORT,
            EvidenceRoleEnum.DIRECT_CONTRADICTION,
        }:
            if (
                proposed_role == EvidenceRoleEnum.BACKGROUND
                and aligned_stance != StanceEnum.NEUTRAL
                and not speculative_without_appointment_signal
            ):
                return (
                    EvidenceRoleEnum.DIRECT_SUPPORT
                    if aligned_stance == StanceEnum.YES
                    else EvidenceRoleEnum.DIRECT_CONTRADICTION
                )
            return proposed_role

        if aligned_stance == StanceEnum.NEUTRAL:
            return (
                EvidenceRoleEnum.COMMENTARY
                if fact.claim_type in {ClaimTypeEnum.OPINION, ClaimTypeEnum.FORECAST}
                else EvidenceRoleEnum.BACKGROUND
            )

        if speculative_without_appointment_signal:
            return (
                EvidenceRoleEnum.COMMENTARY
                if fact.claim_type in {ClaimTypeEnum.OPINION, ClaimTypeEnum.FORECAST}
                else EvidenceRoleEnum.BACKGROUND
            )

        if proposed_role == EvidenceRoleEnum.DIRECT_SUPPORT and aligned_stance != StanceEnum.YES:
            return EvidenceRoleEnum.BACKGROUND
        if proposed_role == EvidenceRoleEnum.DIRECT_CONTRADICTION and aligned_stance != StanceEnum.NO:
            return EvidenceRoleEnum.BACKGROUND

        return proposed_role

    @staticmethod
    def _generic_manual_is_speculative(text: str) -> bool:
        lowered = text.lower()
        return any(cue in lowered for cue in GENERIC_MANUAL_SPECULATIVE_CUES)

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
            elif (
                "will " in cleaned.lower()
                or "expects" in cleaned.lower()
                or (
                    self._is_political_forecast_question(question_text)
                    and any(
                        cue in cleaned.lower()
                        for cue in {
                            "advantage",
                            "favored",
                            "favorite",
                            "favorites",
                            "forecast",
                            "forecasters",
                            "generic ballot",
                            "poll",
                            "polling",
                            "projected",
                            "rating",
                        }
                    )
                )
            ):
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
        has_decision_signal = self._legal_injunction_outcome(text) is not None or self._contains_any_phrase(
            text, LEGAL_DECISION_SIGNALS
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
        legal_alignment = self._legal_merits_alignment(rule_parse, text)
        if legal_alignment == StanceEnum.YES:
            return EvidenceRoleEnum.DIRECT_SUPPORT
        if legal_alignment == StanceEnum.NO:
            return EvidenceRoleEnum.DIRECT_CONTRADICTION
        if any(keyword in text for keyword in PROCEDURAL_KEYWORDS):
            return EvidenceRoleEnum.PROCEDURAL
        if any(keyword in text for keyword in TIMING_KEYWORDS):
            return EvidenceRoleEnum.TIMING

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
            rationale=f"{fact.normalized_fact} supports the {stance.value.upper()} case.",
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
        social_draft.summary = AnalysisProcessor._strip_model_markup(social_draft.summary)
        social_draft.key_themes = [
            AnalysisProcessor._strip_model_markup(theme)
            for theme in social_draft.key_themes
            if AnalysisProcessor._strip_model_markup(theme)
        ]
        for post in trusted_posts:
            post.post_summary = AnalysisProcessor._strip_model_markup(post.post_summary)
            post.possible_facts = [
                AnalysisProcessor._strip_model_markup(fact)
                for fact in post.possible_facts
                if AnalysisProcessor._strip_model_markup(fact)
            ]

        if trusted_posts:
            social_draft.trusted_accounts_count = len(trusted_posts)
            return social_draft

        if "trusted" in social_draft.summary.lower():
            social_draft.summary = (
                "Live X discussion was sampled, but no trusted-account posts met the persistence "
                "threshold. Treat this as broad crowd flow, not trusted evidence."
            )
        social_draft.trusted_accounts_count = 0
        return social_draft

    @staticmethod
    def _strip_model_markup(text: str) -> str:
        cleaned = re.sub(
            r"<grok:render\b[^>]*>.*?</grok:render>",
            " ",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(
            r"<argument\b[^>]*>.*?</argument>",
            " ",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

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
        evidence_role: EvidenceRoleEnum | None = None,
    ) -> tuple[bool, str | None]:
        evidence_role = evidence_role or fact.evidence_role
        domain = (source.domain or "").removeprefix("www.").lower()
        if domain in SOCIAL_WEB_DOMAINS and source.source_kind not in {
            SourceKindEnum.MANUAL_SOCIAL,
            SourceKindEnum.LIVE_SOCIAL,
        }:
            return False, "Social-platform pages scraped as web results are contextual only."

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
        crowd_signal_evidence: float = 0.0,
    ) -> tuple[bool, str | None]:
        scored_directional_factors = [
            factor
            for factor in factors
            if self._factor_used_in_scoring(factor)
            and factor.stance in {StanceEnum.YES, StanceEnum.NO}
        ]
        has_crowd_signal = abs(crowd_signal_evidence) >= 0.025
        if not scored_directional_factors and not has_crowd_signal:
            return False, "no directional source or crowd signal was strong enough to estimate"

        if abs(evidence) < 0.02:
            return False, "net directional evidence is effectively balanced"

        contributing_source_ids = {
            fact.source_id
            for fact in facts
            if fact.id in {factor.fact_claim_id for factor in scored_directional_factors}
        }
        caution_reasons: list[str] = []
        if len(scored_directional_factors) < 2:
            if has_crowd_signal:
                caution_reasons.append(
                    "estimate leans on broad X crowd flow because fewer than two scored source factors were available"
                )
            else:
                caution_reasons.append(
                    "estimate is based on a single scored directional factor"
                )

        if len(contributing_source_ids) < 2 and not has_crowd_signal:
            caution_reasons.append("directional case relies on fewer than two distinct sources")

        contributing_sources = [source_lookup[source_id] for source_id in contributing_source_ids if source_id in source_lookup]
        if not any(
            source.source_tier in NUMERIC_REQUIRED_SOURCE_TIERS
            and source.source_kind not in {SourceKindEnum.MANUAL_SOCIAL, SourceKindEnum.LIVE_SOCIAL}
            for source in contributing_sources
        ) and not has_crowd_signal:
            caution_reasons.append("no qualifying non-social directional source was available")

        if abs(evidence) < 0.10:
            caution_reasons.append("net directional evidence is light")

        excluded_or_contextual = sum(1 for factor in factors if not factor.used_in_scoring)
        if excluded_or_contextual > len(scored_directional_factors) * 2:
            caution_reasons.append("contextual facts still dominate the evidence mix")

        if caution_reasons:
            return True, "Decision estimate shown with low confidence: " + "; ".join(caution_reasons)
        return True, None

    @staticmethod
    def _qualitative_label(
        factors: list[Factor],
        evidence: float,
        crowd_signal_evidence: float = 0.0,
    ) -> QualitativeLabelEnum:
        scored_directional_factors = [
            factor
            for factor in factors
            if AnalysisProcessor._factor_used_in_scoring(factor)
            and factor.stance in {StanceEnum.YES, StanceEnum.NO}
        ]
        if abs(evidence) < 0.025:
            if scored_directional_factors:
                return QualitativeLabelEnum.MIXED
            return QualitativeLabelEnum.INSUFFICIENT_BASIS

        if len(scored_directional_factors) < 2:
            return QualitativeLabelEnum.LEANS_YES if evidence > 0 else QualitativeLabelEnum.LEANS_NO

        yes_count = sum(1 for factor in scored_directional_factors if factor.stance == StanceEnum.YES)
        no_count = sum(1 for factor in scored_directional_factors if factor.stance == StanceEnum.NO)
        if abs(yes_count - no_count) <= 1 and abs(evidence) < 0.14:
            return QualitativeLabelEnum.MIXED
        return QualitativeLabelEnum.LEANS_YES if evidence > 0 else QualitativeLabelEnum.LEANS_NO

    @staticmethod
    def _numeric_decision_read(p_hat: float | None) -> str:
        if p_hat is None:
            return "no numeric YES probability"
        if p_hat > 0.5:
            return "YES is more likely"
        if p_hat < 0.5:
            return "NO is more likely"
        return "coin flip"

    def _condition_alignment(self, rule_parse: RuleParse, text: str) -> StanceEnum:
        fact_terms = self._signal_terms(self._expand_search_aliases(text))
        yes_terms = self._signal_terms(self._expand_search_aliases(rule_parse.yes_condition))
        no_terms = self._signal_terms(self._expand_search_aliases(rule_parse.no_condition))
        political_alignment = self._political_forecast_alignment(rule_parse, text)
        if political_alignment is not None:
            return political_alignment
        if rule_parse.claim_family == ClaimFamilyEnum.LEGAL_CASE:
            return self._legal_merits_alignment(rule_parse, text) or StanceEnum.NEUTRAL
        if rule_parse.claim_family == ClaimFamilyEnum.GENERIC_MANUAL:
            generic_alignment = self._generic_manual_alignment(
                rule_parse=rule_parse,
                fact_terms=fact_terms,
                yes_terms=yes_terms,
                no_terms=no_terms,
                text=text,
            )
            if generic_alignment is not None:
                return generic_alignment
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

    def _political_forecast_alignment(
        self,
        rule_parse: RuleParse,
        text: str,
    ) -> StanceEnum | None:
        question_text = getattr(rule_parse, "question_text", "") or ""
        yes_condition = getattr(rule_parse, "yes_condition", "") or ""
        question_context = f"{question_text} {yes_condition}"
        if not self._is_political_forecast_question(question_context):
            return None

        lowered = self._expand_search_aliases(text).lower()
        question_lowered = self._expand_search_aliases(question_context).lower()

        yes_actor: str | None = None
        no_actor: str | None = None
        if "republican" in question_lowered or "gop" in question_lowered:
            yes_actor = "republican"
            no_actor = "democrat"
        elif "democrat" in question_lowered:
            yes_actor = "democrat"
            no_actor = "republican"

        if yes_actor is None:
            if "impeach" in question_lowered or "impeachment" in question_lowered:
                has_impeachment_anchor = "impeach" in lowered or "impeachment" in lowered
                if has_impeachment_anchor and any(cue in lowered for cue in POLITICAL_FORECAST_NEGATIVE_CUES):
                    return StanceEnum.NO
                if has_impeachment_anchor and any(cue in lowered for cue in POLITICAL_FORECAST_POSITIVE_CUES):
                    return StanceEnum.YES
            return None

        yes_actor_terms = self._political_actor_terms(yes_actor)
        no_actor_terms = self._political_actor_terms(no_actor) if no_actor else []
        yes_positive = self._actor_forecast_cue_match(
            lowered,
            actor_terms=yes_actor_terms,
            cues=POLITICAL_FORECAST_POSITIVE_CUES,
        )
        yes_negative = self._actor_forecast_cue_match(
            lowered,
            actor_terms=yes_actor_terms,
            cues=POLITICAL_FORECAST_NEGATIVE_CUES,
        )
        no_positive = self._actor_forecast_cue_match(
            lowered,
            actor_terms=no_actor_terms,
            cues=POLITICAL_FORECAST_POSITIVE_CUES,
        )
        no_negative = self._actor_forecast_cue_match(
            lowered,
            actor_terms=no_actor_terms,
            cues=POLITICAL_FORECAST_NEGATIVE_CUES,
        )

        if yes_positive and not no_positive and not yes_negative:
            return StanceEnum.YES
        if yes_negative and not no_negative:
            return StanceEnum.NO
        if no_positive and not yes_positive and not no_negative:
            return StanceEnum.NO
        if no_negative and not yes_negative:
            return StanceEnum.YES
        return None

    @staticmethod
    def _political_actor_terms(actor: str) -> list[str]:
        if actor == "republican":
            return ["republican", "republicans", "gop"]
        if actor == "democrat":
            return ["democrat", "democrats", "democratic"]
        return [actor]

    @staticmethod
    def _actor_forecast_cue_match(
        text: str,
        *,
        actor_terms: list[str],
        cues: set[str],
    ) -> bool:
        if not actor_terms:
            return False
        for actor in actor_terms:
            escaped_actor = re.escape(actor)
            for cue in cues:
                escaped_cue = re.escape(cue)
                if re.search(rf"\b{escaped_actor}\b[^.!?;,]{{0,90}}\b{escaped_cue}\b", text):
                    return True
                if re.search(rf"\b{escaped_cue}\b[^.!?;,]{{0,45}}\b{escaped_actor}\b", text):
                    return True
        return False

    def _generic_manual_alignment(
        self,
        *,
        rule_parse: RuleParse,
        fact_terms: set[str],
        yes_terms: set[str],
        no_terms: set[str],
        text: str,
    ) -> StanceEnum | None:
        lowered = self._expand_search_aliases(text).lower()
        has_context_anchor = any(cue in lowered for cue in GENERIC_MANUAL_CONTEXT_CUES)
        has_entity_anchor = any(
            self._expand_search_aliases(entity).lower() in lowered
            for entity in rule_parse.entity_names
        )
        if not has_context_anchor and not has_entity_anchor:
            return StanceEnum.NEUTRAL

        yes_score = 0
        no_score = 0
        action = (rule_parse.action or "").lower()
        if action in {"restart", "resume", "reignite"}:
            yes_score += sum(1 for cue in GENERIC_MANUAL_RESTART_YES_CUES if cue in lowered)
            no_score += sum(1 for cue in GENERIC_MANUAL_RESTART_NO_CUES if cue in lowered)
        else:
            appointment_alignment = self._generic_manual_appointment_alignment(rule_parse, lowered)
            if appointment_alignment is not None:
                return appointment_alignment
            shared_terms = yes_terms.intersection(no_terms)
            yes_unique_terms = {
                term
                for term in yes_terms.difference(shared_terms)
                if term not in {"happen", "happens", "true", "not", "false"}
            }
            no_unique_terms = {
                term
                for term in no_terms.difference(shared_terms)
                if term not in {"happen", "happens", "true", "not", "false"}
            }
            yes_score += len(fact_terms.intersection(yes_unique_terms))
            no_score += len(fact_terms.intersection(no_unique_terms))
            if action and action != "resolve" and action in lowered:
                yes_score += 1
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
    def _generic_manual_appointment_alignment(
        cls,
        rule_parse: RuleParse,
        lowered_text: str,
    ) -> StanceEnum | None:
        question_context = (
            f"{getattr(rule_parse, 'question_text', '')} "
            f"{getattr(rule_parse, 'yes_condition', '')}"
        ).lower()
        if not any(cue in question_context for cue in GENERIC_MANUAL_APPOINTMENT_QUESTION_CUES):
            return None

        entity_anchors = [
            cls._expand_search_aliases(entity).lower()
            for entity in getattr(rule_parse, "entity_names", [])
            if entity
        ]
        if entity_anchors and not any(anchor in lowered_text for anchor in entity_anchors):
            return StanceEnum.NEUTRAL

        yes_score = sum(1 for cue in GENERIC_MANUAL_APPOINTMENT_YES_CUES if cue in lowered_text)
        no_score = sum(1 for cue in GENERIC_MANUAL_APPOINTMENT_NO_CUES if cue in lowered_text)
        if yes_score > no_score:
            return StanceEnum.YES
        if no_score > yes_score:
            return StanceEnum.NO
        return None

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

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        pattern = r"(?<![a-z0-9])" + r"\s+".join(
            re.escape(part) for part in phrase.lower().split()
        ) + r"(?![a-z0-9])"
        return re.search(pattern, text.lower()) is not None

    @classmethod
    def _contains_any_phrase(cls, text: str, phrases: set[str]) -> bool:
        return any(cls._contains_phrase(text, phrase) for phrase in phrases)

    @classmethod
    def _legal_merits_alignment(cls, rule_parse: RuleParse, text: str) -> StanceEnum | None:
        yes_favors_blocking_or_striking = cls._yes_condition_favors_negative_legal_outcome(rule_parse)
        negative_for_challenged_action = cls._contains_any_phrase(text, LEGAL_MERITS_YES)
        positive_for_challenged_action = cls._contains_any_phrase(text, LEGAL_MERITS_NO)

        if negative_for_challenged_action:
            return StanceEnum.YES if yes_favors_blocking_or_striking else StanceEnum.NO
        if positive_for_challenged_action:
            return StanceEnum.NO if yes_favors_blocking_or_striking else StanceEnum.YES
        return None

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
    ) -> tuple[PricedInRiskLabelEnum, dict[str, Any]]:
        if social_intel_summary is not None:
            if social_intel_summary.narrative_phase == NarrativePhaseEnum.PRICED_IN:
                return PricedInRiskLabelEnum.HIGH, {"basis": "social_narrative", "attributed": True}
            if social_intel_summary.narrative_phase == NarrativePhaseEnum.CROWDED:
                return PricedInRiskLabelEnum.MEDIUM, {"basis": "social_narrative", "attributed": True}

        history_signal = self._price_history_signal(market, source_contexts)
        if history_signal:
            return PricedInRiskLabelEnum(history_signal["risk"]), history_signal

        published_times = [
            source_context.source.published_at or source_context.source.fetched_at
            for source_context in source_contexts
            if source_context.source.source_kind != SourceKindEnum.MANUAL_INPUT
        ]
        if not published_times:
            return PricedInRiskLabelEnum.MEDIUM, {"basis": "missing_evidence_time", "attributed": False}

        freshest = max(published_times)
        age_hours = max((datetime.now(UTC) - freshest).total_seconds() / 3600, 0.0)
        if age_hours <= 6:
            return PricedInRiskLabelEnum.LOW, {"basis": "source_age_fallback", "attributed": False}
        if age_hours <= 24:
            return PricedInRiskLabelEnum.MEDIUM, {"basis": "source_age_fallback", "attributed": False}
        if market is not None and market.spread is not None and market.spread <= 0.03:
            return PricedInRiskLabelEnum.HIGH, {"basis": "source_age_fallback", "attributed": False}
        return PricedInRiskLabelEnum.HIGH, {"basis": "source_age_fallback", "attributed": False}

    @staticmethod
    def _price_history_signal(
        market: Market | None,
        source_contexts: list[SourceContext],
    ) -> dict[str, Any] | None:
        if market is None:
            return None
        points = sorted(
            (point for point in market.price_points if point.outcome == "yes"),
            key=lambda point: point.observed_at,
        )
        evidence_times = [
            context.source.published_at or context.source.fetched_at
            for context in source_contexts
            if context.source.source_kind != SourceKindEnum.MANUAL_INPUT
        ]
        if len(points) < 2 or not evidence_times:
            return None
        evidence_time = max(evidence_times)
        before = [point for point in points if point.observed_at <= evidence_time]
        after = [point for point in points if point.observed_at > evidence_time]
        if not before or not after:
            return None
        movement = round(after[-1].price - before[-1].price, 4)
        magnitude = abs(movement)
        risk = "high" if magnitude >= 0.05 else "medium" if magnitude >= 0.02 else "low"
        return {
            "basis": "clob_price_history",
            "risk": risk,
            "attributed": magnitude >= 0.02,
            "evidence_published_at": evidence_time.isoformat(),
            "price_before": before[-1].price,
            "price_after": after[-1].price,
            "movement": movement,
            "reason": (
                "The market moved after the newest retained evidence was published."
                if magnitude >= 0.02
                else "No material move followed the newest retained evidence."
            ),
        }

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
        if AnalysisProcessor._is_political_forecast_question(rule_parse.question_text):
            return (
                "Prioritize pollsters, election forecasters, political data journalists, campaign beat "
                "reporters, and credible district or chamber-control analysts. Treat broad partisan "
                "cheering as crowd flow only, but do capture whether many smaller accounts are converging early."
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
        if AnalysisProcessor._is_political_forecast_question(text):
            return TemplateKey.NARRATIVE_MANUAL
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
    def _is_political_forecast_question(text: str | None) -> bool:
        if not text:
            return False
        lowered = text.lower()
        return any(keyword in lowered for keyword in POLITICAL_FORECAST_KEYWORDS)

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
            "restart",
            "resume",
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
