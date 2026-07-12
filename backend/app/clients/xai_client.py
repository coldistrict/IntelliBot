from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.services.model_cache import get_cached_response, hash_payload, store_cached_response
from app.models.enums import ExecutionResultModeEnum
from app.services.analysis_execution import enforce_run_budget, record_model_call

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class XAIResponsesClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
        enabled: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.api_key) and bool(self.model)

    def generate_structured(
        self,
        *,
        session: Session,
        task_name: str,
        prompt_version: str,
        system_prompt: str,
        user_prompt: str,
        schema_model: type[SchemaT],
    ) -> SchemaT:
        return self.generate_structured_with_tools(
            session=session,
            task_name=task_name,
            prompt_version=prompt_version,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=schema_model,
            tools=[],
        )

    def generate_structured_with_tools(
        self,
        *,
        session: Session,
        task_name: str,
        prompt_version: str,
        system_prompt: str,
        user_prompt: str,
        schema_model: type[SchemaT],
        tools: list[dict[str, Any]],
    ) -> SchemaT:
        if not self.is_configured:
            raise RuntimeError("xAI client is not configured.")

        input_payload = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "schema_name": schema_model.__name__,
            "schema": schema_model.model_json_schema(),
            "tools": tools,
        }
        input_hash = hash_payload(input_payload)
        cached = get_cached_response(
            session,
            provider="xai",
            model=self.model,
            task_name=task_name,
            prompt_version=prompt_version,
            input_hash=input_hash,
        )
        if cached is not None:
            record_model_call(
                session,
                provider="xai",
                model=self.model,
                task_name=task_name,
                prompt_version=prompt_version,
                result_mode=ExecutionResultModeEnum.MODEL,
                started_at=perf_counter(),
                cache_hit=True,
                detail={"tools_path": bool(tools)},
            )
            return schema_model.model_validate(cached)

        enforce_run_budget(session, task_name=task_name)

        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "tools": tools,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_model.__name__,
                    "schema": schema_model.model_json_schema(),
                    "strict": True,
                }
            },
        }
        started_at = perf_counter()
        try:
            response_payload = self._post_json("/responses", payload)
            content = self._extract_output_text(response_payload)
            parsed = schema_model.model_validate_json(content)
        except Exception as exc:
            record_model_call(
                session,
                provider="xai",
                model=self.model,
                task_name=task_name,
                prompt_version=prompt_version,
                result_mode=ExecutionResultModeEnum.FAILED,
                started_at=started_at,
                error=exc,
                detail={"tools_path": bool(tools)},
            )
            raise
        record_model_call(
            session,
            provider="xai",
            model=self.model,
            task_name=task_name,
            prompt_version=prompt_version,
            result_mode=ExecutionResultModeEnum.MODEL,
            started_at=started_at,
            response_payload=response_payload,
            detail={"tools_path": bool(tools)},
        )
        store_cached_response(
            session,
            provider="xai",
            model=self.model,
            task_name=task_name,
            prompt_version=prompt_version,
            input_hash=input_hash,
            output_json=parsed.model_dump(mode="json"),
        )
        session.commit()
        return parsed

    def _post_json(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.base_url}{path}", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _extract_output_text(payload: Mapping[str, Any]) -> str:
        if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
            return payload["output_text"]

        output = payload.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, Mapping):
                    continue
                if item.get("type") == "message":
                    content = item.get("content")
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, Mapping) and part.get("type") == "output_text":
                                text = part.get("text")
                                if isinstance(text, str) and text.strip():
                                    return text

        raise RuntimeError("Unable to extract structured output from xAI Responses API.")


def get_xai_client(*, enabled: bool = True) -> XAIResponsesClient:
    settings = get_settings()
    api_key = settings.xai_api_key.get_secret_value() if settings.xai_api_key is not None else None
    return XAIResponsesClient(
        base_url=settings.xai_base_url,
        api_key=api_key,
        model=settings.xai_social_model,
        timeout_seconds=settings.llm_timeout_seconds,
        enabled=enabled,
    )
