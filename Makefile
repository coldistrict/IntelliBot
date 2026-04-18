SHELL := /bin/zsh

.PHONY: install backend-sync dev build typecheck db-up db-down

install:
	pnpm install

backend-sync:
	cd backend && uv sync

dev:
	pnpm dev

build:
	pnpm build

typecheck:
	pnpm typecheck

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

