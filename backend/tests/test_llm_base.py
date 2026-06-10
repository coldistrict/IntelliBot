import pytest
from pydantic import BaseModel, Field

from app.clients.llm_base import _openai_strict_json_schema
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
