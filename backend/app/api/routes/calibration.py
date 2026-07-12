from dataclasses import asdict

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.clients.polymarket_client import PolymarketClient
from app.db.session import get_db_session
from app.schemas.calibration import CalibrationScoreboardResponse, OutcomeRefreshResponse
from app.services.calibration import build_scoreboard
from app.services.outcome_tracker import refresh_market_outcomes

router = APIRouter(prefix="/calibration")


def get_polymarket_client() -> PolymarketClient:
    return PolymarketClient(enabled=True)


@router.get("/scoreboard", response_model=CalibrationScoreboardResponse)
def calibration_scoreboard(
    session: Session = Depends(get_db_session),
) -> CalibrationScoreboardResponse:
    return build_scoreboard(session)


@router.post("/refresh", response_model=OutcomeRefreshResponse)
def refresh_outcomes(
    session: Session = Depends(get_db_session),
    client: PolymarketClient = Depends(get_polymarket_client),
) -> OutcomeRefreshResponse:
    summary = refresh_market_outcomes(session, client=client)
    return OutcomeRefreshResponse(**asdict(summary))
