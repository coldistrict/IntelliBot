from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def deadline_uncertainty_adjustment(
    deadline: datetime | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Return the documented horizon adjustment used by scoring and audit output."""
    if deadline is None:
        return None
    reference = now or datetime.now(UTC)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    days = max((deadline - reference).total_seconds() / 86400, 0.0)
    if days <= 7:
        amount, band = 0.06, "event_window"
    elif days <= 45:
        amount, band = 0.03, "near_term"
    elif days <= 180:
        amount, band = 0.01, "medium_term"
    else:
        amount, band = 0.0, "long_horizon"
    return {
        "key": "deadline_horizon",
        "label": "Deadline horizon",
        "amount": amount,
        "band": band,
        "days_remaining": round(days, 2),
        "note": "Short event windows widen the range because timing and final-resolution risk concentrate near the deadline.",
    }
