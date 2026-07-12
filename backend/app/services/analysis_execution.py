from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import AnalysisRequest, ExecutionEvent
from app.models.enums import ExecutionResultModeEnum, RunQualityEnum
from app.config.settings import get_settings

_request_id: ContextVar[int | None] = ContextVar("analysis_request_id", default=None)
_run_id: ContextVar[int | None] = ContextVar("analysis_run_id", default=None)

TASK_STAGE = {
    "rule_parse": "rule_parse",
    "social_intelligence": "social_intelligence",
    "fact_extract": "fact_extraction",
    "fact_verify": "fact_verification",
    "evidence_role": "evidence_classification",
    "evidence_adjudication": "factor_mapping",
    "final_brief": "brief_generation",
    "fred": "retrieval",
}


class RunBudgetExceeded(RuntimeError):
    pass


def enforce_run_budget(session: Session, *, task_name: str) -> None:
    request_id = _request_id.get()
    if request_id is None:
        return
    settings = get_settings()
    calls, tokens, cost = session.execute(
        select(
            func.count(ExecutionEvent.id),
            func.coalesce(func.sum(ExecutionEvent.prompt_tokens + ExecutionEvent.completion_tokens), 0),
            func.coalesce(func.sum(ExecutionEvent.estimated_cost_usd), 0.0),
        ).where(
            ExecutionEvent.request_id == request_id,
            ExecutionEvent.event_kind == "model_call",
        )
    ).one()
    request = session.get(AnalysisRequest, request_id)
    elapsed = (
        (datetime.now(UTC) - request.started_at).total_seconds()
        if request is not None and request.started_at is not None
        else 0.0
    )
    reason = None
    if int(calls) >= settings.max_run_calls:
        reason = "call_limit"
    elif int(tokens) >= settings.max_run_tokens:
        reason = "token_limit"
    elif float(cost) >= settings.max_run_cost_usd:
        reason = "cost_limit"
    elif elapsed >= settings.max_run_wall_seconds:
        reason = "wall_time_limit"
    if reason is None:
        return
    record_execution_event(
        session,
        stage_key=TASK_STAGE.get(task_name, task_name),
        event_kind="budget_exceeded",
        result_mode=ExecutionResultModeEnum.FAILED,
        task_name=task_name,
        error_class="RunBudgetExceeded",
        detail={
            "reason": reason,
            "calls": int(calls),
            "tokens": int(tokens),
            "cost_usd": float(cost),
            "elapsed_seconds": round(elapsed, 3),
        },
    )
    session.flush()
    raise RunBudgetExceeded(f"Run budget exceeded: {reason}")


@contextmanager
def execution_context(request_id: int) -> Iterator[None]:
    request_token = _request_id.set(request_id)
    run_token = _run_id.set(None)
    try:
        yield
    finally:
        _run_id.reset(run_token)
        _request_id.reset(request_token)


def bind_analysis_run(session: Session, analysis_run_id: int) -> None:
    request_id = _request_id.get()
    _run_id.set(analysis_run_id)
    if request_id is not None:
        session.execute(
            update(ExecutionEvent)
            .where(
                ExecutionEvent.request_id == request_id,
                ExecutionEvent.analysis_run_id.is_(None),
            )
            .values(analysis_run_id=analysis_run_id)
        )
        session.flush()


def usage_counts(payload: Mapping[str, Any]) -> tuple[int, int]:
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        return 0, 0
    prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    completion = usage.get("completion_tokens", usage.get("output_tokens", 0))
    return int(prompt or 0), int(completion or 0)


def estimate_cost(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    # Conservative configurable-model estimate. The immutable token counts remain
    # authoritative when provider pricing changes.
    input_rate, output_rate = {
        "openai": (0.25, 2.0),
        "xai": (0.20, 0.50),
    }.get(provider, (0.0, 0.0))
    return round((prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000, 8)


def record_execution_event(
    session: Session,
    *,
    stage_key: str,
    event_kind: str,
    result_mode: ExecutionResultModeEnum,
    provider: str | None = None,
    model: str | None = None,
    task_name: str | None = None,
    prompt_version: str | None = None,
    cache_hit: bool = False,
    latency_ms: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
    error_class: str | None = None,
    detail: dict[str, Any] | None = None,
) -> ExecutionEvent | None:
    request_id = _request_id.get()
    if request_id is None:
        return None
    row = ExecutionEvent(
        request_id=request_id,
        analysis_run_id=_run_id.get(),
        stage_key=stage_key,
        event_kind=event_kind,
        provider=provider,
        model=model,
        task_name=task_name,
        prompt_version=prompt_version,
        result_mode=result_mode,
        cache_hit=cache_hit,
        attempt_count=1,
        latency_ms=max(latency_ms, 0),
        prompt_tokens=max(prompt_tokens, 0),
        completion_tokens=max(completion_tokens, 0),
        estimated_cost_usd=max(estimated_cost_usd, 0.0),
        error_class=error_class,
        detail_json=detail or {},
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def record_model_call(
    session: Session,
    *,
    provider: str,
    model: str,
    task_name: str,
    prompt_version: str,
    result_mode: ExecutionResultModeEnum,
    started_at: float,
    cache_hit: bool = False,
    response_payload: Mapping[str, Any] | None = None,
    error: Exception | None = None,
    detail: dict[str, Any] | None = None,
) -> ExecutionEvent | None:
    prompt_tokens, completion_tokens = usage_counts(response_payload or {})
    return record_execution_event(
        session,
        stage_key=TASK_STAGE.get(task_name, task_name),
        event_kind="model_call",
        result_mode=result_mode,
        provider=provider,
        model=model,
        task_name=task_name,
        prompt_version=prompt_version,
        cache_hit=cache_hit,
        latency_ms=max(1, int((perf_counter() - started_at) * 1000)),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=(
            0.0 if cache_hit else estimate_cost(provider, prompt_tokens, completion_tokens)
        ),
        error_class=type(error).__name__ if error else None,
        detail=detail,
    )


def record_fallback(
    session: Session,
    *,
    task_name: str,
    provider: str,
    model: str | None,
    error: Exception | None,
) -> None:
    if isinstance(error, RunBudgetExceeded):
        raise error
    record_execution_event(
        session,
        stage_key=TASK_STAGE.get(task_name, task_name),
        event_kind="fallback",
        result_mode=ExecutionResultModeEnum.DETERMINISTIC_FALLBACK,
        provider=provider,
        model=model,
        task_name=task_name,
        prompt_version=f"{task_name}_v1",
        latency_ms=1,
        error_class=type(error).__name__ if error else "ProviderNotConfigured",
    )


def finalize_stage_ledger(session: Session, request: AnalysisRequest, analysis_run_id: int) -> None:
    existing = set(
        session.scalars(
            select(ExecutionEvent.stage_key).where(
                ExecutionEvent.analysis_run_id == analysis_run_id,
                ExecutionEvent.event_kind == "stage",
            )
        ).all()
    )
    for stage_key, state in (request.progress_json or {}).get("stages", {}).items():
        if stage_key in existing:
            continue
        status = state.get("status")
        mode = (
            ExecutionResultModeEnum.SKIPPED
            if status == "skipped"
            else ExecutionResultModeEnum.FAILED
            if status == "failed"
            else ExecutionResultModeEnum.MODEL
        )
        record_execution_event(
            session,
            stage_key=stage_key,
            event_kind="stage",
            result_mode=mode,
            latency_ms=_stage_latency_ms(state),
            detail={"status": status, "note": state.get("note")},
        )


def _stage_latency_ms(state: Mapping[str, Any]) -> int:
    try:
        start = datetime.fromisoformat(str(state.get("started_at")))
        end = datetime.fromisoformat(str(state.get("completed_at")))
        return max(1, int((end - start).total_seconds() * 1000))
    except (TypeError, ValueError):
        return 1


def derive_quality(events: list[ExecutionEvent], *, has_directional_evidence: bool) -> tuple[RunQualityEnum, list[dict[str, Any]]]:
    if not events:
        return RunQualityEnum.UNKNOWN, [{"code": "missing_execution_ledger"}]
    reasons: list[dict[str, Any]] = []
    fallback_tasks = sorted(
        {event.task_name for event in events if event.result_mode == ExecutionResultModeEnum.DETERMINISTIC_FALLBACK and event.task_name}
    )
    if fallback_tasks:
        reasons.append({"code": "deterministic_fallback", "tasks": fallback_tasks})
    failed = sorted({event.task_name or event.stage_key for event in events if event.result_mode == ExecutionResultModeEnum.FAILED})
    if failed:
        reasons.append({"code": "failed_execution", "tasks": failed})
    if not has_directional_evidence:
        reasons.append({"code": "zero_qualifying_directional_evidence"})
    return (RunQualityEnum.WARNING if reasons else RunQualityEnum.CLEAN), reasons
