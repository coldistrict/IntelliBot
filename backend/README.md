# Backend

FastAPI service for Polymarket Copilot v1.

## Commands

```bash
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
uv run alembic -c alembic.ini upgrade head
uv run pytest
```
