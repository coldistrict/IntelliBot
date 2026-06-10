# Polymarket Copilot v1

Shadow-mode research copilot for Polymarket markets.

## What This Repo Includes

- `frontend`: Next.js App Router UI with Manual Analysis, History, Settings, and analysis detail pages
- `backend`: FastAPI backend with DB-backed manual-analysis workflow, provider status, and market endpoints
- `docs`: initial product and source-policy docs
- `docker-compose.yml`: local Postgres for development
- root `.env` flow: one gitignored env file shared by frontend scripts and backend settings

## Prerequisites

- Node.js 22+
- `pnpm` via Corepack
- `uv` with Python 3.12 installed
- Docker Desktop running
- API keys for OpenAI, xAI, and Tavily

## Quick Start

1. Copy `.env.example` to `.env`.
2. Fill in `OPENAI_API_KEY`, `XAI_API_KEY`, and `TAVILY_API_KEY`.
3. Install dependencies:

```bash
pnpm install
cd backend && uv sync
cd ..
```

4. Start Postgres and apply migrations:

```bash
docker compose up -d postgres
pnpm --filter backend db:upgrade
```

5. Start the apps:

```bash
pnpm dev
```

The frontend runs on `http://localhost:3000` and the backend runs on `http://localhost:8000`.

## Current Milestone Status

- Milestone 1 foundation is in place: monorepo scaffold, Docker Postgres, DB schema, Alembic, provider status, and docs.
- Milestone 2 now has a first real end-to-end manual-analysis flow:
  - manual submissions queue and process in the background
  - rule parses, sources, fact claims, factors, runs, recommendations, and snapshots are persisted
  - the frontend polls analysis detail until the run completes
  - Manual Mode can optionally run a live X intelligence lane through xAI, with:
    - a trusted-account timeline that includes trust and relevance justification
    - a broader X consensus summary that feeds confidence and priced-in risk, not a hidden social-only probability
- The calibration loop now closes the shadow-mode promise:
  - market-linked analyses are tracked until the market resolves on Polymarket
  - "Check for resolutions" on the Scoreboard page polls the free Gamma API and records final outcomes
  - resolved runs are scored against reality: Brier vs the market prior, direction hit rate,
    calibration buckets, and a virtual $100-per-lean P&L, sliced by template and confidence
- Auto Mode and deeper provider-backed retrieval still need the next implementation passes.

## Useful Commands

```bash
pnpm dev
pnpm build
pnpm typecheck
pnpm --filter frontend test
pnpm --filter backend db:upgrade
pnpm --filter backend test
pnpm --filter frontend dev
pnpm --filter backend dev
docker compose up -d postgres
docker compose down
```

## Environment Strategy

- Root `.env` is the single source of truth for local development.
- Frontend scripts load it with `dotenv-cli`.
- Backend settings load it with `pydantic-settings`.
- `.env` is gitignored; only `.env.example` should be committed.
- Model/base URL settings are env-configurable so you can swap providers or models without code edits.
