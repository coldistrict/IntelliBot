from __future__ import annotations

import re
from dataclasses import dataclass

from app.clients.polymarket_client import ResolvedMarketRecord

STOPWORDS = {
    "a", "an", "and", "at", "be", "by", "for", "from", "in", "is", "it", "of",
    "on", "or", "the", "this", "to", "will", "with", "meeting", "next", "market",
}
JURISDICTIONS = {
    "us_federal_reserve": {"federal reserve", "fomc", "us fed", "u.s. fed"},
    "colombia_central_bank": {"colombia", "banco de la republica", "banco de la república"},
    "european_central_bank": {"european central bank", "ecb", "eurozone"},
    "bank_of_england": {"bank of england", "boe", "united kingdom", "uk central bank"},
}


@dataclass(frozen=True)
class MatchAssessment:
    score: float
    reason_codes: list[str]
    auto_link: bool
    confidence: str


def _normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9+]+", " ", text.lower()).strip()


def _terms(text: str) -> set[str]:
    return {term for term in _normalized(text).split() if len(term) > 2 and term not in STOPWORDS}


def _jurisdictions(text: str) -> set[str]:
    normalized = _normalized(text)
    return {
        key for key, aliases in JURISDICTIONS.items()
        if any(_normalized(alias) in normalized for alias in aliases)
    }


def _thresholds(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"\b(\d{1,4})\s*\+?\s*(?:bps|basis points?)\b", text.lower())}


def _years(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"\b(20\d{2})\b", text)}


def assess_market_match(claim: str, record: ResolvedMarketRecord) -> MatchAssessment:
    candidate_text = " ".join(part or "" for part in (record.title, record.description, record.rules_text))
    claim_terms = _terms(claim)
    candidate_terms = _terms(candidate_text)
    title_terms = _terms(record.title)
    coverage = len(claim_terms & candidate_terms) / max(len(claim_terms), 1)
    title_coverage = len(claim_terms & title_terms) / max(len(claim_terms), 1)
    score_value = (coverage * 0.65) + (title_coverage * 0.35)

    reasons: list[str] = []
    disqualified = False
    claim_jurisdictions = _jurisdictions(claim)
    candidate_jurisdictions = _jurisdictions(candidate_text)
    if claim_jurisdictions and candidate_jurisdictions:
        if claim_jurisdictions.isdisjoint(candidate_jurisdictions):
            reasons.append("jurisdiction_mismatch")
            disqualified = True
        else:
            reasons.append("jurisdiction_match")
            score_value += 0.18
    elif claim_jurisdictions != candidate_jurisdictions:
        reasons.append("jurisdiction_missing")
        score_value -= 0.12

    claim_thresholds = _thresholds(claim)
    candidate_thresholds = _thresholds(candidate_text)
    if candidate_thresholds and not claim_thresholds:
        reasons.append("outcome_threshold_missing")
        disqualified = True
    elif claim_thresholds and candidate_thresholds and claim_thresholds != candidate_thresholds:
        reasons.append("outcome_threshold_mismatch")
        disqualified = True
    elif claim_thresholds and claim_thresholds == candidate_thresholds:
        reasons.append("outcome_threshold_match")
        score_value += 0.08

    claim_years = _years(claim)
    candidate_years = _years(candidate_text)
    if claim_years and candidate_years and claim_years.isdisjoint(candidate_years):
        reasons.append("deadline_year_mismatch")
        disqualified = True
    elif claim_years and claim_years == candidate_years:
        reasons.append("deadline_year_match")
        score_value += 0.05

    score = round(max(0.0, min(1.0, score_value)), 4)
    if disqualified:
        confidence, auto_link = "low", False
    elif score >= 0.78:
        confidence, auto_link = "high", True
    elif score >= 0.50:
        confidence, auto_link = "medium", False
        reasons.append("confirmation_required")
    else:
        confidence, auto_link = "low", False
    if not reasons:
        reasons.append("lexical_similarity_only")
    return MatchAssessment(score=score, reason_codes=reasons, auto_link=auto_link, confidence=confidence)
