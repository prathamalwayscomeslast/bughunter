# BugHunter 🐛

**Autonomous, AI-powered bug resolution agent for GitHub repositories.**

BugHunter is a GitHub App that takes a reported bug — from `issue opened` all the way to `pull request opened` — through an automated pipeline, with a human approval gate preserved at the PR stage. It never merges its own PRs.

## How It Works

1. Install the BugHunter GitHub App on your repository
2. Open a GitHub issue and apply the `bug` label
3. BugHunter clones your repo into an isolated Docker sandbox, reproduces the bug, localises the root cause, generates a fix, and opens a pull request
4. You review and merge — or don't. BugHunter never force-merges anything.

## Architecture

```
GitHub Webhooks
      ↓
FastAPI (Render) — webhook receipt, signature verification, job persistence, Redis enqueue
      ↓
Redis Queue (Upstash)
      ↓
ARQ Background Worker (AWS EC2) — LLM calls, Docker sandbox, repair loop, PR creation
      ↓
Postgres (Neon) — source of truth for all Job state
```

See [`BUGHUNTER_CONTEXT.md`](./BUGHUNTER_CONTEXT.md) for the full architecture, every decision rationale, and constraints for future contributors.

## Running Locally

### Prerequisites
- Python 3.11+
- Docker
- A registered GitHub App (App ID + private key `.pem`)
- Postgres instance (local or Neon free tier)
- Redis instance (local or Upstash free tier)

### Setup

```bash
cd orchestrator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file inside `orchestrator/`:

```env
WEBHOOK_SECRET=your_webhook_secret
GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=./bughunter.private-key.pem
DATABASE_URL=postgresql://user:pass@localhost:5432/bughunter
REDIS_URL=redis://localhost:6379
```

### Start the web service

```bash
cd orchestrator
uvicorn main:app --reload
```

### Start the background worker

```bash
cd orchestrator
python -m arq worker.settings.WorkerSettings
```

## Current Status

| Capability | Status |
|---|---|
| Webhook receipt + HMAC verification | ✅ Done |
| GitHub App auth (JWT → installation token) | ✅ Done |
| Job persistence (Postgres) | ✅ Done |
| Acknowledgment comment on issue | ✅ Done |
| Redis queue + ARQ worker wiring | ✅ Done |
| LLM integration (litellm) | 🔜 Next |
| Docker sandbox + reproduction | 🔜 Planned |
| Repair loop | 🔜 Planned |
| PR creation | 🔜 Planned |

## License

Apache 2.0
