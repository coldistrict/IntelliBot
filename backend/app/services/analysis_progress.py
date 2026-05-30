from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import AnalysisRequest

StageConfig = dict[str, Any]

STAGE_DEFINITIONS: list[StageConfig] = [
    {
        "key": "normalize",
        "label": "Normalize Input",
        "description": "Prepare the request and determine what needs to run.",
        "optional": False,
    },
    {
        "key": "market_lookup",
        "label": "Market Lookup",
        "description": "Resolve Polymarket metadata and current market context.",
        "optional": True,
    },
    {
        "key": "rule_parse",
        "label": "Rule Parse",
        "description": "Interpret the question, deadline, template, and resolution logic.",
        "optional": False,
    },
    {
        "key": "retrieval",
        "label": "Retrieval",
        "description": "Gather official, news, and supporting sources.",
        "optional": False,
    },
    {
        "key": "social_intelligence",
        "label": "Social Intelligence",
        "description": "Read live X intelligence for trusted accounts and broader consensus.",
        "optional": True,
    },
    {
        "key": "fact_extraction",
        "label": "Fact Extraction",
        "description": "Extract structured claims from the gathered material.",
        "optional": False,
    },
    {
        "key": "fact_verification",
        "label": "Fact Verification",
        "description": "Check extracted claims against source context before scoring.",
        "optional": False,
    },
    {
        "key": "evidence_classification",
        "label": "Evidence Classification",
        "description": "Classify each verified claim by its role relative to the YES and NO conditions.",
        "optional": False,
    },
    {
        "key": "factor_mapping",
        "label": "Factor Mapping",
        "description": "Translate verified claims into directional factors and weights.",
        "optional": False,
    },
    {
        "key": "probability_estimation",
        "label": "Probability Estimation",
        "description": "Apply evidence, uncertainty, and market context to the probability model.",
        "optional": False,
    },
    {
        "key": "brief_generation",
        "label": "Brief Generation",
        "description": "Assemble the final memo, caveats, and recommendation language.",
        "optional": False,
    },
    {
        "key": "complete",
        "label": "Complete",
        "description": "The analysis has finished and the brief is ready to inspect.",
        "optional": False,
    },
]

STAGE_CONFIG_BY_KEY = {item["key"]: item for item in STAGE_DEFINITIONS}
WORK_STAGE_KEYS = [item["key"] for item in STAGE_DEFINITIONS if item["key"] != "complete"]


def initial_progress_payload(now: datetime | None = None) -> dict[str, Any]:
    timestamp = (now or datetime.now(UTC)).isoformat()
    return {
        "version": 1,
        "last_updated_at": timestamp,
        "stages": {
            item["key"]: {
                "status": "pending",
                "note": None,
                "started_at": None,
                "completed_at": None,
            }
            for item in STAGE_DEFINITIONS
        },
    }


def ensure_progress_payload(request: AnalysisRequest) -> dict[str, Any]:
    payload = dict(request.progress_json or {})
    payload.setdefault("version", 1)
    payload.setdefault("stages", {})
    stages = payload["stages"]

    for item in STAGE_DEFINITIONS:
        stage = stages.setdefault(item["key"], {})
        stage.setdefault("status", "pending")
        stage.setdefault("note", None)
        stage.setdefault("started_at", None)
        stage.setdefault("completed_at", None)

    payload.setdefault("last_updated_at", datetime.now(UTC).isoformat())
    request.progress_json = payload
    return payload


def _set_stage_status(
    request: AnalysisRequest,
    stage_key: str,
    status: str,
    note: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if stage_key not in STAGE_CONFIG_BY_KEY:
        raise KeyError(f"Unknown analysis stage: {stage_key}")

    payload = ensure_progress_payload(request)
    timestamp = (now or datetime.now(UTC)).isoformat()
    stage = payload["stages"][stage_key]

    if status == "running":
        stage["started_at"] = stage["started_at"] or timestamp
    elif status in {"complete", "skipped", "failed"}:
        stage["started_at"] = stage["started_at"] or timestamp
        stage["completed_at"] = timestamp

    stage["status"] = status
    if note is not None:
        stage["note"] = note

    payload["last_updated_at"] = timestamp
    request.progress_json = payload
    if status in {"running", "failed"}:
        request.current_stage = stage_key
    elif stage_key == "complete" and status == "complete":
        request.current_stage = "complete"
    return payload


def mark_stage_running(
    request: AnalysisRequest,
    stage_key: str,
    note: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    return _set_stage_status(request, stage_key, "running", note=note, now=now)


def mark_stage_complete(
    request: AnalysisRequest,
    stage_key: str,
    note: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    return _set_stage_status(request, stage_key, "complete", note=note, now=now)


def mark_stage_skipped(
    request: AnalysisRequest,
    stage_key: str,
    note: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    return _set_stage_status(request, stage_key, "skipped", note=note, now=now)


def mark_stage_failed(
    request: AnalysisRequest,
    stage_key: str,
    note: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    return _set_stage_status(request, stage_key, "failed", note=note, now=now)


def build_progress_snapshot(request: AnalysisRequest) -> dict[str, Any]:
    payload = ensure_progress_payload(request)
    stages = []
    for item in STAGE_DEFINITIONS:
        stage_state = payload["stages"][item["key"]]
        stages.append(
            {
                "key": item["key"],
                "label": item["label"],
                "description": item["description"],
                "optional": item["optional"],
                "status": stage_state["status"],
                "note": stage_state["note"],
                "started_at": stage_state["started_at"],
                "completed_at": stage_state["completed_at"],
            }
        )

    current_stage: str | None
    current_label: str | None
    current_note: str | None

    if request.status.value == "queued":
        current_stage = "queued"
        current_label = "Queued"
        current_note = "Waiting for the worker to start the analysis."
        percent_complete = 0
    else:
        current_stage = request.current_stage
        if current_stage in STAGE_CONFIG_BY_KEY:
            current_label = str(STAGE_CONFIG_BY_KEY[current_stage]["label"])
            note_value = payload["stages"].get(current_stage, {}).get("note")
            current_note = note_value if isinstance(note_value, str) else None
        else:
            current_label = None
            current_note = request.error_message
        completed_count = sum(
            1
            for key in WORK_STAGE_KEYS
            if payload["stages"][key]["status"] in {"complete", "skipped"}
        )
        percent_complete = (
            100
            if request.status.value == "complete"
            else int(round((completed_count / len(WORK_STAGE_KEYS)) * 100))
        )

    completed_count = sum(
        1
        for key in WORK_STAGE_KEYS
        if payload["stages"][key]["status"] in {"complete", "skipped"}
    )
    return {
        "current_stage": current_stage,
        "current_label": current_label,
        "current_note": current_note,
        "completed_count": completed_count,
        "total_count": len(WORK_STAGE_KEYS),
        "percent_complete": percent_complete,
        "stages": stages,
        "last_updated_at": payload.get("last_updated_at"),
    }
