from enum import Enum

from sqlalchemy import Enum as SQLEnum


class ModeEnum(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class InputTypeEnum(str, Enum):
    MARKET_URL = "market_url"
    MARKET_ID = "market_id"
    CUSTOM_CLAIM = "custom_claim"


class RequestStatusEnum(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class RunQualityEnum(str, Enum):
    UNKNOWN = "unknown"
    CLEAN = "clean"
    WARNING = "warning"
    INVALID = "invalid"


class ExecutionResultModeEnum(str, Enum):
    MODEL = "model"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"
    SKIPPED = "skipped"
    FAILED = "failed"


class AttemptReasonEnum(str, Enum):
    ORIGINAL = "original"
    INTENTIONAL_RERUN = "intentional_rerun"
    RETRY = "retry"
    RECOVERY = "recovery"


class JournalEventTypeEnum(str, Enum):
    BEFORE = "before"
    AFTER = "after"


class TemplateKey(str, Enum):
    OFFICIAL_EVENT = "official_event"
    MACRO_POLICY = "macro_policy"
    LEGAL_CASE = "legal_case"
    NARRATIVE_MANUAL = "narrative_manual"
    GENERIC_MANUAL = "generic_manual"


class ClaimFamilyEnum(str, Enum):
    OFFICIAL_EVENT = "official_event"
    MACRO_POLICY = "macro_policy"
    LEGAL_CASE = "legal_case"
    NARRATIVE_MANUAL = "narrative_manual"
    GENERIC_MANUAL = "generic_manual"


class SourceKindEnum(str, Enum):
    OFFICIAL = "official"
    NEWS = "news"
    PREMIUM_NEWS = "premium_news"
    LIVE_SOCIAL = "live_social"
    MANUAL_SOCIAL = "manual_social"
    MANUAL_INPUT = "manual_input"


class SourceTierEnum(str, Enum):
    OFFICIAL_PRIMARY = "official_primary"
    OFFICIAL_STATEMENT = "official_statement"
    EXPERT_ANALYSIS = "expert_analysis"
    PREMIUM_NEWS = "premium_news"
    REPUTABLE_NEWS = "reputable_news"
    OFFICIAL_SOCIAL = "official_social"
    HIGH_TRUST_SOCIAL = "high_trust_social"
    REPORTER_SOCIAL = "reporter_social"
    GENERIC_SOCIAL = "generic_social"


class ClaimTypeEnum(str, Enum):
    FACT = "fact"
    FORECAST = "forecast"
    OPINION = "opinion"
    RULE_NOTE = "rule_note"
    SOCIAL_SIGNAL = "social_signal"


class DirectnessEnum(str, Enum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    BACKGROUND = "background"


class VerifierStatusEnum(str, Enum):
    SUPPORTED = "supported"
    AMBIGUOUS = "ambiguous"
    REJECTED = "rejected"


class EvidenceRoleEnum(str, Enum):
    OUTCOME = "outcome"
    DIRECT_SUPPORT = "direct_support"
    DIRECT_CONTRADICTION = "direct_contradiction"
    PROCEDURAL = "procedural"
    BACKGROUND = "background"
    COMMENTARY = "commentary"
    TIMING = "timing"
    SENTIMENT = "sentiment"


class StanceEnum(str, Enum):
    YES = "yes"
    NO = "no"
    NEUTRAL = "neutral"


class StrengthEnum(str, Enum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"


class RecommendationLabelEnum(str, Enum):
    LEAN_YES = "lean_yes"
    LEAN_NO = "lean_no"
    NO_EDGE = "no_edge"
    NEEDS_MORE_RESEARCH = "needs_more_research"
    ANALYSIS_ONLY = "analysis_only"


class ConfidenceLabelEnum(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class QualitativeLabelEnum(str, Enum):
    LEANS_YES = "leans_yes"
    LEANS_NO = "leans_no"
    MIXED = "mixed"
    INSUFFICIENT_BASIS = "insufficient_basis"


class ReviewDecisionEnum(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    WATCH = "watch"
    RERUN = "rerun"


class SnapshotTypeEnum(str, Enum):
    T0 = "t0"
    ONE_HOUR = "1h"
    TWENTY_FOUR_HOURS = "24h"
    SEVENTY_TWO_HOURS = "72h"
    RESOLVED = "resolved"


class PricedInRiskLabelEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConsensusLabelEnum(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    MIXED = "mixed"
    UNCLEAR = "unclear"


class ConsensusStrengthEnum(str, Enum):
    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"


class NarrativePhaseEnum(str, Enum):
    FRESH = "fresh"
    EMERGING = "emerging"
    CROWDED = "crowded"
    PRICED_IN = "priced_in"


def enum_column(enum_cls: type[Enum], name: str) -> SQLEnum:
    return SQLEnum(
        enum_cls,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
