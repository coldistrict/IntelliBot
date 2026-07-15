import json
import logging

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import literal, select

import app.clients.llm_base as llm_base
from app.clients.llm_base import StructuredChatClient, _openai_strict_json_schema
from app.services.pipeline_models import RuleParseDraft


class NestedDraft(BaseModel):
    note: str | None = None


class StructuredDraft(BaseModel):
    title: str
    nested: NestedDraft


class FlexibleDraft(BaseModel):
    metadata: dict = Field(default_factory=dict)


def test_openai_strict_json_schema_normalizes_objects_recursively():
    schema = _openai_strict_json_schema(StructuredDraft.model_json_schema())

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["title", "nested"]
    assert schema["$defs"]["NestedDraft"]["additionalProperties"] is False
    assert schema["$defs"]["NestedDraft"]["required"] == ["note"]
    assert "default" not in schema["$defs"]["NestedDraft"]["properties"]["note"]


def test_openai_strict_json_schema_rejects_free_form_objects():
    with pytest.raises(ValueError, match="free-form objects"):
        _openai_strict_json_schema(FlexibleDraft.model_json_schema())


def test_openai_strict_json_schema_normalizes_rule_parse_policy():
    schema = _openai_strict_json_schema(RuleParseDraft.model_json_schema())

    policy_schema = schema["$defs"]["DirectionalScoringPolicyDraft"]
    assert policy_schema["additionalProperties"] is False
    assert policy_schema["required"] == ["allowed_roles", "commentary_mode", "procedural_mode"]
    assert policy_schema["properties"]["commentary_mode"]["enum"] == [
        "none",
        "expert_only",
        "bounded",
    ]
    assert policy_schema["properties"]["procedural_mode"]["const"] == "uncertainty_only"


class SimpleDraft(BaseModel):
    value: str


def _client() -> StructuredChatClient:
    return StructuredChatClient(
        provider="openai",
        base_url="https://example.invalid/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=1.0,
    )


def _chat_payload(draft: SimpleDraft) -> dict:
    return {
        "choices": [{"message": {"content": json.dumps(draft.model_dump(mode="json"))}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def test_generate_structured_keeps_model_result_when_persistence_fails(
    session_factory, monkeypatch, caplog
):
    client = _client()
    monkeypatch.setattr(
        client, "_post_json", lambda path, payload: _chat_payload(SimpleDraft(value="ok"))
    )
    session = session_factory()
    monkeypatch.setattr(
        session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("db down"))
    )

    with caplog.at_level(logging.ERROR):
        parsed = client.generate_structured(
            session=session,
            task_name="rule_parse",
            prompt_version="rule_parse_v1",
            system_prompt="s",
            user_prompt="u",
            schema_model=SimpleDraft,
        )

    assert parsed.value == "ok"
    assert "persisting its ledger/cache rows failed" in caplog.text
    # The rollback must leave the session usable for the rest of the stage.
    assert session.execute(select(literal(1))).scalar() == 1
    session.close()


def test_generate_structured_raises_provider_error_when_ledger_write_fails(
    session_factory, monkeypatch
):
    client = _client()
    monkeypatch.setattr(
        client,
        "_post_json",
        lambda path, payload: (_ for _ in ()).throw(ValueError("provider exploded")),
    )
    monkeypatch.setattr(
        llm_base,
        "record_model_call",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("ledger down")),
    )
    session = session_factory()

    with pytest.raises(ValueError, match="provider exploded"):
        client.generate_structured(
            session=session,
            task_name="rule_parse",
            prompt_version="rule_parse_v1",
            system_prompt="s",
            user_prompt="u",
            schema_model=SimpleDraft,
        )
    session.close()
