from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ModelResponseCache


def hash_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def get_cached_response(
    session: Session,
    *,
    provider: str,
    model: str,
    task_name: str,
    prompt_version: str,
    input_hash: str,
) -> dict[str, Any] | None:
    cache_row = session.scalar(
        select(ModelResponseCache).where(
            ModelResponseCache.provider == provider,
            ModelResponseCache.model == model,
            ModelResponseCache.task_name == task_name,
            ModelResponseCache.prompt_version == prompt_version,
            ModelResponseCache.input_hash == input_hash,
        )
    )
    if cache_row is None:
        return None
    return cache_row.output_json


def store_cached_response(
    session: Session,
    *,
    provider: str,
    model: str,
    task_name: str,
    prompt_version: str,
    input_hash: str,
    output_json: dict[str, Any],
) -> None:
    existing = get_cached_response(
        session,
        provider=provider,
        model=model,
        task_name=task_name,
        prompt_version=prompt_version,
        input_hash=input_hash,
    )
    if existing is not None:
        return

    session.add(
        ModelResponseCache(
            provider=provider,
            model=model,
            task_name=task_name,
            prompt_version=prompt_version,
            input_hash=input_hash,
            output_json=output_json,
        )
    )
    session.flush()
