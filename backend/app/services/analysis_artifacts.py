from __future__ import annotations

from typing import Any


def _artifact_status(
    progress: dict[str, Any],
    stage_key: str,
    *,
    label: str,
    available: bool,
) -> dict[str, Any]:
    stage_lookup = {stage["key"]: stage for stage in progress["stages"]}
    stage = stage_lookup.get(stage_key, {})
    return {
        "key": stage_key,
        "label": label,
        "status": stage.get("status", "pending"),
        "note": stage.get("note"),
        "available": available,
    }


def build_artifact_statuses(
    *,
    progress: dict[str, Any],
    has_rule_parse: bool,
    has_sources: bool,
    has_social_sources: bool,
    has_factors: bool,
    has_analysis_run: bool,
    has_final_summary: bool,
) -> list[dict[str, Any]]:
    return [
        _artifact_status(
            progress,
            "rule_parse",
            label="Rules interpreted",
            available=has_rule_parse,
        ),
        _artifact_status(
            progress,
            "retrieval",
            label="Sources grounded",
            available=has_sources,
        ),
        _artifact_status(
            progress,
            "social_intelligence",
            label="Social intelligence",
            available=has_social_sources,
        ),
        _artifact_status(
            progress,
            "factor_mapping",
            label="Factors scored",
            available=has_factors,
        ),
        _artifact_status(
            progress,
            "brief_generation",
            label="Brief written",
            available=has_final_summary,
        ),
        {
            "key": "audit",
            "label": "Audit ready",
            "status": "complete" if has_analysis_run and has_factors else "pending",
            "note": (
                "Structured scoring, uncertainty, recommendation, and grounding details are ready."
                if has_analysis_run and has_factors
                else "The audit inspector unlocks once scored factors are ready."
            ),
            "available": has_analysis_run and has_factors,
        },
    ]
