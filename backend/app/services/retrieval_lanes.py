from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.clients.fred_client import FredClient
from app.models.analysis import RuleParse
from app.services.pipeline_models import SearchSourceDraft


@dataclass(frozen=True)
class RetrievalLaneResult:
    lane: str
    sources: list[SearchSourceDraft]


class RetrievalLane(Protocol):
    name: str

    def retrieve(self, rule_parse: RuleParse) -> RetrievalLaneResult: ...


class FredRetrievalLane:
    name = "fred"

    def __init__(self, client: FredClient) -> None:
        self.client = client

    def retrieve(self, rule_parse: RuleParse) -> RetrievalLaneResult:
        return RetrievalLaneResult(
            lane=self.name,
            sources=self.client.observations_for_claim(rule_parse.question_text),
        )
