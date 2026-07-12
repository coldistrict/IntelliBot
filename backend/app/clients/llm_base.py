from __future__ import annotations

import json
from collections.abc import Mapping
from time import perf_counter
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.model_cache import get_cached_response, hash_payload, store_cached_response
from app.models.enums import ExecutionResultModeEnum
from app.services.analysis_execution import enforce_run_budget, record_model_call

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def _openai_strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    def normalize(value: Any) -> Any:
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if not isinstance(value, dict):
            return value

        normalized = {key: normalize(item) for key, item in value.items() if key != "default"}
        if normalized.get("type") == "object" or "properties" in normalized:
            properties = normalized.get("properties")
            additional_properties = normalized.get("additionalProperties")
            if additional_properties is not None and additional_properties is not False:
                raise ValueError("OpenAI strict JSON schemas do not support free-form objects.")
            normalized["additionalProperties"] = False
            if isinstance(properties, dict):
                normalized["required"] = list(properties)
        return normalized

    return normalize(schema)


class StructuredChatClient:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
        enabled: bool = True,
    ) -> None:
        self.provider = provider
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
        temperature: float = 0.1,
    ) -> SchemaT:
        if not self.is_configured:
            raise RuntimeError(f"{self.provider} client is not configured.")

        schema = _openai_strict_json_schema(schema_model.model_json_schema())
        input_payload = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "schema_name": schema_model.__name__,
            "schema": schema,
        }
        input_hash = hash_payload(input_payload)
        cached = get_cached_response(
            session,
            provider=self.provider,
            model=self.model,
            task_name=task_name,
            prompt_version=prompt_version,
            input_hash=input_hash,
        )
        if cached is not None:
            record_model_call(
                session,
                provider=self.provider,
                model=self.model,
                task_name=task_name,
                prompt_version=prompt_version,
                result_mode=ExecutionResultModeEnum.MODEL,
                started_at=perf_counter(),
                cache_hit=True,
            )
            return schema_model.model_validate(cached)

        enforce_run_budget(session, task_name=task_name)

        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_model.__name__,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        started_at = perf_counter()
        try:
            response_payload = self._post_json("/chat/completions", payload)
            content = self._extract_content(response_payload)
            parsed = schema_model.model_validate_json(content)
        except Exception as exc:
            record_model_call(
                session,
                provider=self.provider,
                model=self.model,
                task_name=task_name,
                prompt_version=prompt_version,
                result_mode=ExecutionResultModeEnum.FAILED,
                started_at=started_at,
                error=exc,
            )
            raise
        record_model_call(
            session,
            provider=self.provider,
            model=self.model,
            task_name=task_name,
            prompt_version=prompt_version,
            result_mode=ExecutionResultModeEnum.MODEL,
            started_at=started_at,
            response_payload=response_payload,
        )
        store_cached_response(
            session,
            provider=self.provider,
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
    def _extract_content(payload: Mapping[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("LLM response did not include any choices.")

        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, Mapping):
                    if isinstance(part.get("text"), str):
                        text_parts.append(part["text"])
                    elif part.get("type") == "output_text" and isinstance(part.get("text"), str):
                        text_parts.append(part["text"])
            if text_parts:
                return "".join(text_parts)

        if isinstance(message.get("parsed"), Mapping):
            return json.dumps(message["parsed"])

        raise RuntimeError("Unable to extract structured JSON content from LLM response.")
