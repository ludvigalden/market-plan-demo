# Market Plan Desk

A campaign planning tool for a fictional multi-market consumer brand,
"Demo Brand". A planner creates a global campaign, assigns local markets,
sees each market's public holidays and the clashes they cause, and reviews
AI-drafted local adaptations. Nothing changes until the planner accepts a
suggestion, and every decision is written to an audit log.

All brand, campaign and budget data in this repository is fictional. Market
codes are real ISO country codes, because the holiday data is real public
data.

## Architecture

```text
browser ── React SPA (static files served by the API)
                │
             FastAPI ─┬─ SQLAlchemy 2 (async) ── PostgreSQL
                      ├─ httpx ── Nager.Date holidays (cached)
                      └─ AI provider seam ── stub | Foundry
```

- `api/`: FastAPI, Pydantic v2, SQLAlchemy 2 with asyncpg, Alembic.
  Errors share one JSON body (`code`, `message`, `request_id`) and every
  response carries an `X-Request-ID`.
- `api/migrations/`: four Alembic revisions, each with a working
  downgrade. The plan `version` column is added as an expand step:
  nullable with a server default, backfilled, then made `NOT NULL`.
- `contracts/openapi.json`: the API contract, exported from the app with
  stable operation ids.
- `web/`: React and TypeScript on Vite. `src/api/schema.d.ts` is generated
  from the contract by openapi-typescript and used through openapi-fetch,
  so a contract change that breaks the client fails the type check.
- `eval/`: a golden set and a deterministic grader for the AI step.
- `Dockerfile`: one image that builds the SPA and serves it from the API.

## How the AI is constrained

- Deterministic code finds the clashes (a holiday on the launch day, on
  the end day, or inside the plan window). The model is only asked what to
  do about them.
- The model receives the retrieved facts (plan dates, flagged holidays,
  campaign window) and must answer in a JSON schema with a fixed action set:
  `shift_start`, `shift_end`, `note_messaging`, `no_change`. The schema has
  no budget field; budget figures come from the database only.
- A server-side validator drops any suggestion that names a market or a
  flag date that was not in the input, moves a date outside the campaign
  window or onto another holiday, or uses a field outside the schema. The
  response reports how many were dropped and why.
- Suggestions are stored with the model deployment and prompt version.
  Accepting one updates the market plan under optimistic concurrency: the
  request carries the plan version the planner saw, and a stale version
  returns 409.
- `AI_PROVIDER=stub` (the default) answers deterministically from the
  flags, so tests and the eval run without a cloud dependency.
  `AI_PROVIDER=foundry` calls a Microsoft Foundry project through
  `azure-ai-projects` with Entra ID authentication (`DefaultAzureCredential`)
  and structured output.

## Run locally

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node.js 24.

```sh
docker compose up -d --wait            # PostgreSQL on 127.0.0.1:55432
cd api
uv sync
uv run alembic upgrade head
uv run uvicorn plandesk.main:app --port 8000
```

In a second terminal:

```sh
cd web
npm ci
npm run dev                             # http://localhost:5173, proxies /api
```

Or run the single image against the compose database:

```sh
docker build -t market-plan-desk .
docker run --rm --network host \
  -e DATABASE_URL=postgresql+asyncpg://plandesk@127.0.0.1:55432/plandesk \
  market-plan-desk                     # http://localhost:8000
```

To use Microsoft Foundry instead of the stub, sign in with `az login` and
set `AI_PROVIDER=foundry`, `FOUNDRY_PROJECT_ENDPOINT` and
`FOUNDRY_MODEL_DEPLOYMENT` (see `.env.example`).

## Checks

```sh
cd api
uv run ruff check . && uv run ruff format --check .
uv run basedpyright
uv run pytest                          # needs the compose database
uv run python scripts/export_openapi.py
cd ../web
npm run generate && npm run typecheck && npm run lint
npm run format:check && npm test && npx vite build
cd .. && uv run --project api python eval/run.py
git diff --exit-code contracts web/src/api
```

## Licence

All rights reserved. See [LICENSE](LICENSE).
