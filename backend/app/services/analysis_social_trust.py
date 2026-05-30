from __future__ import annotations

from typing import Any, Protocol

from app.models.enums import SourceTierEnum

TRUSTED_SOCIAL_TIERS = {SourceTierEnum.OFFICIAL_SOCIAL, SourceTierEnum.HIGH_TRUST_SOCIAL}
OFFICIAL_SOCIAL_MIN_CONFIDENCE = 0.65
HIGH_TRUST_SOCIAL_MIN_CONFIDENCE = 0.82

TRUSTED_CATEGORY_TERMS = {
    "academic",
    "agency",
    "analyst",
    "court",
    "data provider",
    "domain expert",
    "economist",
    "election analyst",
    "expert",
    "government",
    "institution",
    "institutional",
    "journalist",
    "judge",
    "legal expert",
    "lawmaker",
    "newsroom",
    "official",
    "pollster",
    "regulator",
    "reporter",
    "researcher",
    "subject-matter expert",
}

PARTISAN_OR_LOW_TRUST_TERMS = {
    "activist",
    "advocacy",
    "anonymous",
    "commentator",
    "conservative media personality",
    "conservative voice",
    "entertainer",
    "fan account",
    "influencer",
    "left-leaning",
    "liberal media personality",
    "meme",
    "media personality",
    "opinion",
    "partisan",
    "podcast",
    "political personality",
    "political voice",
    "pundit",
    "right-leaning",
    "rumor",
    "speculator",
    "trader",
}


class SocialPostLike(Protocol):
    trust_tier: SourceTierEnum
    trust_confidence: float
    account_category: str
    trust_reason: str


def _normalized_text(value: object) -> str:
    return str(value or "").strip().lower()


def _metadata_float(metadata: dict[str, Any], key: str) -> float | None:
    value = metadata.get(key)
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def _has_any_term(value: str, terms: set[str]) -> bool:
    return any(term in value for term in terms)


def social_metadata_is_trusted(
    *,
    source_tier: SourceTierEnum,
    metadata: dict[str, Any],
) -> bool:
    if source_tier not in TRUSTED_SOCIAL_TIERS:
        return False

    confidence = _metadata_float(metadata, "trust_confidence")
    account_category = _normalized_text(metadata.get("account_category"))
    trust_reason = _normalized_text(metadata.get("trust_reason"))
    combined_trust_text = f"{account_category} {trust_reason}"

    if _has_any_term(combined_trust_text, PARTISAN_OR_LOW_TRUST_TERMS):
        return False

    if source_tier == SourceTierEnum.OFFICIAL_SOCIAL:
        return confidence is None or confidence >= OFFICIAL_SOCIAL_MIN_CONFIDENCE

    return (
        confidence is not None
        and confidence >= HIGH_TRUST_SOCIAL_MIN_CONFIDENCE
        and _has_any_term(account_category, TRUSTED_CATEGORY_TERMS)
    )


def social_post_is_trusted(post: SocialPostLike) -> bool:
    return social_metadata_is_trusted(
        source_tier=post.trust_tier,
        metadata={
            "account_category": post.account_category,
            "trust_confidence": post.trust_confidence,
            "trust_reason": post.trust_reason,
        },
    )
