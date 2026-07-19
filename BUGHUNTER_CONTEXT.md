# BugHunter — Project Context Document

> This document exists to give any LLM (or human) full context on what BugHunter is, why it exists, how it works end to end, and how every architectural decision was made. Read this fully before making changes, suggestions, or generating code for this project.

---

## 1. What Is BugHunter

BugHunter is an **autonomous, AI-powered bug resolution agent** that integrates directly into a team's existing GitHub workflow. It is not a chatbot, not a code review tool, and not a linter — it is a closed-loop agentic system that takes a reported bug from "issue opened" all the way to "pull request opened," with a human approval gate in the middle.

### The Core Idea

A repo owner installs the BugHunter GitHub App on their repository. When an issue is opened and labeled `bug`, BugHunter:

1. Clones the repository into an isolated sandbox
2. Attempts to **reproduce** the reported bug using the issue description
3. If reproduced, **localizes** the root cause in the codebase
4. Generates a **fix**, applies it, and reruns the reproduction check
5. If the bug still occurs, it **recursively retries** — feeding the new failure back into its own reasoning loop — up to a capped number of attempts
6. Once the bug can no longer be reproduced, it is considered resolved
7. BugHunter opens a **pull request** explaining the root cause and the fix in plain language
8. If the maintainer leaves review comments requesting small changes, BugHunter reads those comments and pushes **follow-up commits** addressing them

### The Category This Belongs To

This is best described as **Autonomous Issue Resolution** — a self-healing workflow that does for bug-fixing what CI/CD did for deployment. Just as CI/CD takes code from a commit to production through an automated pipeline, BugHunter takes a bug report from an issue to a reviewable fix through an automated pipeline, with a human approval gate preserved at the PR stage.

### Product Identity

- **Name**: BugHunter
- **Category framing**: Self-healing issue resolution for GitHub repos
- **Bot identity on GitHub**: `bughunter[bot]`
- **Positioning reference points**: Closest analog in UX/distribution is CodeRabbit (GitHub App, Marketplace listing, PR-native bot identity). Closest analog in core capability is SWE-agent / Devin's repair loop, but BugHunter is GitHub-native and installable as a bot rather than a standalone agent product.

---

## 2. Core Design Principles (Non-Negotiable)

These principles were deliberately chosen early and should not be silently violated by future changes:

### 2.1 Vendor Neutrality (AI Model Layer)

BugHunter must never be locked into a single AI provider. Teams should be able to plug in:
- Commercial APIs (OpenAI, Anthropic Claude, Google Gemini)
- Cloud-native LLM services (AWS Bedrock, Azure OpenAI, Google Vertex AI)
- Self-hosted / open models (Ollama, vLLM, LM Studio, Groq, Together AI, Fireworks)

This is implemented via **`litellm`**, a Python library that normalizes 100+ LLM providers behind a single function call (`completion(model=..., messages=...)`). BugHunter's agent logic must never call a provider SDK directly — it always goes through this abstraction.

### 2.2 Reproduction Before Action

BugHunter must **never** attempt a fix without first proving the bug is real by reproducing it in an isolated sandbox. If the bug cannot be reproduced, BugHunter must say so honestly on the issue rather than guessing or hallucinating a fix. This is the single most important trust-building constraint in the entire system.

### 2.3 Human Approval Gate

BugHunter never merges its own PR. The autonomous loop stops at "PR opened." A human maintainer must review and merge. This is intentional and should never be automated away — it is the core safety mechanism that makes this product trustworthy enough to install on a real repository.

### 2.4 Bounded Recursion

The repair loop (attempt fix → verify → retry if failed) must always have a hard cap (default: 5 attempts). If BugHunter cannot resolve the bug within the cap, it must post a diagnosis comment explaining what it found, rather than looping indefinitely or silently giving up with no explanation.

### 2.5 Open Source, Cloud-First (For Now)

BugHunter is being built as an **open-source project**, licensed under **Apache 2.0** (permissive, patent-protected, corporate-friendly — deliberately not GPL, to maximize enterprise adoption). 

Self-hosting was seriously discussed as a future capability (Docker Compose bundle, Helm chart for Kubernetes, GitHub App manifest-flow setup wizard) but has been **explicitly deprioritized** for the current build phase. The current focus is a **cloud-hosted SaaS product**, modeled closely on how CodeRabbit operates: install the GitHub App, no self-hosting required, zero infrastructure setup for the end user. Self-hosting remains a documented future direction, not a current requirement.

---

## 3. End-to-End Flow (What Actually Happens, Step by Step)

This section describes the full lifecycle of a single bug, from report to fix, in the order events actually occur.

### Step 0: One-Time Setup (Per Repo)

A repo owner installs the BugHunter GitHub App on their repository via GitHub's App installation flow. This grants BugHunter App scoped permissions (Issues, Contents, Pull Requests) on that repo. No manual token handling by the user is ever required — this is a hard product requirement (see Section 6).

### Step 1: Trigger

A user opens a GitHub issue describing a bug. The maintainer (or the reporter) adds the label `bug` to the issue.

The instant that label is applied, **GitHub itself** sends an HTTP POST webhook request to BugHunter's backend (`/webhook` endpoint), containing the issue title, body, repository name, and the GitHub App installation ID. This is push-based — BugHunter never polls GitHub for changes.

### Step 2: Webhook Receipt and Verification

BugHunter's FastAPI backend receives the POST request. It:
1. Reads the **raw request body** (not the parsed JSON — signature verification must happen on raw bytes)
2. Verifies the `X-Hub-Signature-256` header using HMAC-SHA256 against the shared webhook secret, to confirm the request genuinely came from GitHub and was not spoofed or tampered with
3. Parses the event type (`X-GitHub-Event` header) and the JSON payload
4. Checks if this is an `issues` event with `action == "labeled"` and `label.name == "bug"`

If any of these checks fail, the request is rejected (`401`) or silently ignored (non-matching event types).

### Step 3: Persist the Job

If the event matches, BugHunter creates a **Job** record in Postgres immediately, containing: installation ID, repo full name, issue number, issue title, issue body, and an initial status of `received`. This happens before any GitHub API calls are made, ensuring no job is ever lost even if a later step fails.

### Step 4: Immediate Acknowledgment

BugHunter authenticates as its GitHub App installation (see Section 6 for the exact auth mechanism) and posts an immediate comment on the issue: *"🐛 BugHunter picked up this issue and is preparing to reproduce it."* This gives the user instant feedback that something is happening, even though the real work hasn't started yet.

### Step 5: Enqueue for Background Processing

The webhook handler does **not** perform the actual bug-fixing work inline. It enqueues a lightweight job reference (`job_id`) onto a Redis-backed queue and immediately returns `200 OK` to GitHub. This is mandatory — GitHub expects webhook responses within seconds, but actual bug reproduction and fixing can take minutes. The queue is what decouples "fast acknowledgment" from "slow actual work."

### Step 6: Background Worker Picks Up the Job

A separate, always-running background worker process is continuously polling the Redis queue. When it sees the new job, it:
1. Fetches the full job details from Postgres using the `job_id`
2. Updates the job status to `reproducing`
3. Begins the actual agentic pipeline

### Step 7: Clone and Reproduce

The worker clones the target repository into an isolated Docker sandbox. It uses the LLM (via the litellm abstraction) to parse the issue's freeform text into structured reproduction steps (expected behavior, actual behavior, steps to trigger it, any stack traces mentioned). It then attempts to actually execute those steps inside the sandboxed container.

If the bug **cannot** be reproduced, BugHunter updates the issue with an honest comment explaining that it could not confirm the bug, and the job ends here. This is a deliberate design choice — false fixes are worse than no fix.

### Step 8: Localize the Root Cause

If reproduced, the worker combines static code analysis (AST parsing via `tree-sitter`, call graph traversal) with LLM-guided semantic search to narrow down the likely location of the bug to a small number of candidate files (typically 3-5). This step exists specifically to avoid feeding an entire codebase into the LLM's context window, which would be both expensive and unreliable.

### Step 9: Generate and Apply a Fix

The worker asks the LLM to generate a code patch (as a diff) targeting the localized files. It applies this patch inside the sandbox and reruns the reproduction check from Step 7.

### Step 10: The Repair Loop

If the bug still reproduces after the fix, the worker feeds the new failure output plus the previous patch attempt back into the LLM as additional context, and tries again. This loop is bounded — it will attempt at most 5 times (configurable per repo) before giving up and posting a diagnosis comment instead of a broken or incomplete fix.

### Step 11: Open the Pull Request

Once the reproduction check passes cleanly (bug no longer occurs), the worker:
1. Creates a new branch
2. Commits the fix with a clear commit message
3. Opens a pull request via the GitHub API, authenticated as the App installation
4. Writes a structured PR description explaining: what the bug was, the root cause found, what was changed, and how it was verified

### Step 12: Maintainer Feedback Loop

If the maintainer leaves a review comment on the PR (e.g., "can you rename this variable?"), GitHub sends another webhook (`pull_request_review_comment` event) to the same `/webhook` endpoint. The same job-processing machinery activates again: a new lightweight job is enqueued, a worker picks it up, the LLM classifies and interprets the comment, generates a follow-up patch, and pushes a new commit to the same PR branch.

### Step 13: Human Merges

BugHunter never merges its own PR. A human reviews it and merges (or closes it) manually. This is the permanent human approval gate described in Section 2.3.

---

## 4. System Architecture

### 4.1 High-Level Component Diagram (Conceptual)

```
GitHub (issues, PRs, webhooks)
        |
        | webhook POST
        v
FastAPI Web Service  (deployed on Render)
  - Verifies webhook signatures
  - Parses GitHub events
  - Persists Job rows to Postgres
  - Authenticates as GitHub App installation
  - Posts immediate acknowledgment comments
  - Enqueues jobs onto Redis queue
        |
        | enqueue_job(job_id)
        v
Redis Queue (Upstash, hosted)
        |
        | worker polls continuously
        v
ARQ Background Worker  (deployed on AWS EC2, via systemd)
  - Pulls job references from Redis
  - Fetches full job data from Postgres
  - Clones target repo into Docker sandbox
  - Calls LLM (via litellm) for parsing, localization, fix generation
  - Runs reproduction checks inside sandbox
  - Applies patches, retries repair loop
  - Opens PRs and pushes follow-up commits via GitHub API
  - Updates Job status in Postgres at every stage
        |
        v
Postgres (Neon, hosted) — shared source of truth for Job state
```

### 4.2 Why Two Separate Compute Environments (Render + AWS)

This split exists because of a **free-tier constraint**, not a fundamental architectural requirement:

- Render's free tier only supports **Web Services** (services that expose an HTTP endpoint). It does **not** support **Background Workers** on the free tier — that requires a paid plan starting at $7/month.
- Rather than pay for this early, or awkwardly merge the worker into the same process as the web server (which was considered as a stopgap using FastAPI's `startup` event to launch the ARQ worker as an asyncio background task within the same process), the decision was made to run the worker on a small **AWS EC2 instance** (t3.micro / t4g.small), using existing AWS credits.
- The EC2 worker runs the ARQ worker process as a **systemd service** (`bughunter-worker.service`) with `Restart=always`, so it survives reboots, crashes, and SSH disconnects without manual intervention.
- Both the Render web service and the AWS EC2 worker connect to the **same external Redis instance (Upstash)** and the **same external Postgres instance (Neon)**. Neither compute environment has any direct knowledge of the other — they are fully decoupled and only communicate through these two shared, hosted data stores.

This is also considered a reasonable long-term shape, not just a stopgap: the EC2 instance is expected to eventually also host the Go-based sandbox executor (see Section 4.5), since Docker-in-Docker execution requires full VM control that Render's free tier would never allow anyway.

### 4.3 Why FastAPI + Python for the Orchestrator

Python was deliberately chosen over Go for the main orchestrator layer, specifically because of the LLM ecosystem:

- **`litellm`** provides the entire vendor-neutral model abstraction layer essentially for free — 100+ providers behind one function call, with retries, fallbacks, and cost tracking built in. Building this from scratch in Go would be significant, unnecessary engineering effort.
- Almost all of BugHunter's orchestration work is **I/O-bound** (waiting on LLM API calls, GitHub API calls, Docker execution) rather than CPU-bound, so Python's GIL is largely irrelevant here — `asyncio` handles this concurrency pattern well.
- FastAPI provides async-native webhook handling, automatic request validation via Pydantic, and is well-supported on every major hosting platform including Render.

### 4.4 Why a Separate Go Service for Sandbox Execution (Planned)

While the orchestrator is Python, the actual **Docker sandbox execution** (cloning repos, running containers, streaming output, enforcing resource limits and timeouts) is planned to be extracted into a **separate Go microservice** once that phase of the project is reached. This is a deliberate hybrid architecture:

- Go's goroutines are extremely cheap (~2KB each vs. ~1MB for Python threads), making it dramatically better suited for managing many concurrent Docker container lifecycles simultaneously (e.g., 50 issues arriving at once, each needing an isolated sandbox).
- The Go service is intentionally scoped as a **pure execution primitive** with no knowledge of GitHub, LLMs, or business logic — it exposes a minimal internal HTTP API (`POST /execute`, `GET /jobs/{id}`, `GET /healthz`) and nothing else.
- Python's orchestrator communicates with this Go service either via a shared Redis queue (for async jobs) or direct internal HTTP calls (for synchronous status checks).
- This also serves as a well-scoped, self-contained learning project for Go, without betting the entire system's architecture on it.

**Status: not yet implemented.** This is documented here so future work stays aligned with the intended design, but as of this document's writing, sandbox execution has not yet been built.

### 4.5 Layered Code Architecture (Spring Boot-Style Separation)

The Python orchestrator explicitly follows a layered architecture inspired by Spring Boot's Controller → Service → Repository pattern, chosen deliberately for clarity and testability:

```
orchestrator/
├── main.py                    # App assembly only — no business logic
├── config.py                  # Environment variable loading
├── routers/
│   └── webhook_router.py      # "Controller" — HTTP concerns only (parsing, signature verification, delegating to service)
├── services/
│   └── job_service.py         # "Service" — business logic and orchestration (calls repository + GitHub client + queue)
├── repositories/
│   └── job_repository.py      # "Repository" — database access only, no business logic
├── db/
│   ├── session.py             # SQLAlchemy engine/session setup
│   └── models.py              # SQLAlchemy ORM models (Job, etc.)
├── schemas/
│   └── webhook_events.py      # Pydantic DTOs for parsing GitHub webhook payloads
├── vcs/
│   ├── auth.py                # GitHub App JWT + installation token generation
│   ├── client.py               # GitHub API calls (comment, PR, etc.) using installation tokens
│   └── webhook.py              # Signature verification, event-type matching helpers
└── worker/
    ├── tasks.py                # ARQ task functions (the actual background job logic)
    └── settings.py             # ARQ WorkerSettings (registers tasks, Redis connection)
```

**Rule of thumb for extending this codebase**: if a file is about *parsing GitHub's specific data shape*, it belongs in `vcs/` or `schemas/`. If a file is about *what BugHunter does with the data*, it belongs in `services/` and should use normalized internal models, not raw GitHub JSON. This distinction is also the seam where future multi-provider support (GitLab, Jira) would eventually be inserted (see Section 8).

Each layer has exactly one reason to change. For example, adding the Redis queue only required changing one line inside `JobService.handle_bug_issue()` — swapping a direct GitHub API call for an `enqueue_job()` call — without touching the controller, repository, or schema layers at all.

---

## 5. Infrastructure and Hosting Decisions

| Component | Choice | Why |
|---|---|---|
| Web service (webhook receiver) | Render (free tier) | Fast git-based deploys, generous enough free tier for a low-traffic prototype, simple environment variable management |
| Background worker | AWS EC2 (t3.micro / t4g.small), via systemd | Render free tier does not support Background Workers; AWS credits were available; EC2 also sets up the future home for Docker sandbox execution |
| Database | Postgres, hosted on Neon (free tier) | Generous free tier, instant setup, standard SQL the team already has deep expertise in |
| Queue | Redis, hosted on Upstash (free tier) | Serverless Redis, minimal setup, works seamlessly with ARQ |
| Job queue library | ARQ | Async-native (built on `asyncio` + Redis), lighter weight than Celery, fits naturally with FastAPI's async style |
| LLM abstraction | `litellm` | Normalizes 100+ LLM providers behind one function call; is the entire vendor-neutrality strategy for near-zero custom code |
| LLM provider (prototyping) | Gemini 2.0 Flash | Near-free at prototype scale, large context window (useful for code without excessive chunking) |
| GitHub integration | GitHub App (not OAuth, not personal tokens) | Required for proper `bughunter[bot]` identity, scoped permissions, and installation-based auth; this is a hard product requirement, not a preference |

### Explicit environment variables required by the system

```
WEBHOOK_SECRET              # shared secret for verifying GitHub webhook signatures
GITHUB_APP_ID                # numeric GitHub App ID
GITHUB_PRIVATE_KEY_PATH       # path to the App's private key .pem file
DATABASE_URL                  # Postgres connection string (Neon)
REDIS_URL                      # Redis connection string (Upstash)
```

These must be present and identical (where applicable) on **both** the Render web service and the AWS EC2 worker, since both processes need access to the same Postgres and Redis instances, and the worker independently needs GitHub App credentials to post PRs and commits.

---

## 6. GitHub Authentication Model (Critical — Do Not Regress)

This is one of the most important sections of this document. BugHunter must **never** require end users to generate or paste personal access tokens. That would be a critical UX failure for a product modeled on frictionless GitHub App installation (like CodeRabbit).

### 6.1 The Correct Production Auth Flow

1. BugHunter has a registered **GitHub App** with an **App ID** and a **private key** (`.pem` file), generated once during app registration and stored securely as backend configuration — never exposed to end users.
2. When a user installs the GitHub App on their repository, GitHub creates an **installation** and assigns it an **installation ID**.
3. Every webhook payload GitHub sends includes this **installation ID** (`payload["installation"]["id"]`).
4. To make any GitHub API call (commenting, opening a PR, pushing a commit) on behalf of that installation, BugHunter's backend:
   a. Generates a **JSON Web Token (JWT)** signed with the App's private key, asserting the App's identity (using `Auth.AppAuth` from PyGithub)
   b. Exchanges that JWT for a short-lived **installation access token** (valid for ~1 hour) via `GithubIntegration.get_access_token(installation_id)`
   c. Uses that installation access token to authenticate all subsequent GitHub API calls for that job
5. All actions performed with this token appear on GitHub as coming from `bughunter[bot]`, not from any individual's personal account.

### 6.2 What Was Explicitly Rejected

Early in development, a **fine-grained personal access token** (`GITHUB_TEST_TOKEN`) was used as a temporary local development shortcut, to unblock testing the comment-posting logic before the full GitHub App JWT flow was implemented. This was explicitly called out as **not a production pattern** and has since been replaced by the real installation-token flow described in 6.1. Any future contributor suggesting a return to personal-token-based auth for end users should be corrected — this was a deliberate, documented rejection, not an oversight.

### 6.3 Required GitHub App Permissions

Minimum permissions for current functionality:
- **Issues**: Read & Write
- **Metadata**: Read-only

Required for planned future functionality (PR creation, follow-up commits):
- **Contents**: Read & Write
- **Pull Requests**: Read & Write

Subscribed webhook events:
- `issues` (specifically the `labeled` action)
- `issue_comment`
- `pull_request_review_comment` (for the maintainer feedback loop)

---

## 7. Current Implementation Status

As of this document's writing, the following is **confirmed working**:

- ✅ GitHub App registered and installable on repositories
- ✅ FastAPI web service deployed on Render, publicly reachable
- ✅ Webhook signature verification (HMAC-SHA256 against raw request body)
- ✅ Real GitHub App authentication (JWT → installation access token, via PyGithub's `Auth.AppAuth` + `GithubIntegration`)
- ✅ Automatic bot comment posted on bug-labeled issues, correctly attributed to `bughunter[bot]`
- ✅ Postgres persistence of Job records (installation ID, repo name, issue number/title/body, status)
- ✅ Layered architecture (Controller → Service → Repository → DB models, plus Pydantic schemas for webhook payloads)
- ✅ Redis queue (Upstash) and ARQ worker wiring in progress — background worker deployment path decided (AWS EC2 + systemd)

**Not yet implemented** (in intended build order):

1. Reproduction verification (Docker sandbox execution, actually attempting to trigger the reported bug)
2. LLM integration via `litellm` (structured extraction of repro steps from issue text)
3. Go-based sandbox executor microservice (isolated container execution, resource limits, timeout enforcement)
4. Code localization (tree-sitter AST parsing + semantic search to find root cause candidates)
5. Repair loop (patch generation, application, reproduction retry, bounded recursion)
6. Pull request creation and structured PR descriptions
7. Maintainer review comment handling and follow-up commit automation
8. React-based dashboard (repo management, per-repo configuration, job activity feed, detailed job trace view) — deliberately deferred until the core repair loop produces real data worth visualizing
9. Self-hosting support (Docker Compose bundle, Helm chart, GitHub App manifest-flow setup wizard) — deliberately deferred, documented as a future direction only

---

## 8. Future Direction (Documented Intent, Not Current Scope)

These are real product decisions that were discussed and intentionally deferred — they should inform future design choices but must not be built prematurely, as doing so within the current 2-3 week build timeline would divert effort from finishing the core repair loop.

### 8.1 Multi-Provider Support (GitLab, Jira)

BugHunter is currently GitHub-only, by deliberate choice, to move fast within a tight timeline. However, the codebase maintains one specific abstraction seam to make future expansion cheaper: GitHub-specific webhook parsing logic stays isolated in `vcs/` and `schemas/`, while everything downstream of that parsing (queue, worker, LLM calls, database) is intended to eventually operate on a normalized internal event shape (conceptually, something like `NormalizedBugEvent` / `IssueRef`) rather than raw GitHub payload dictionaries. No `VCSProvider` interface, plugin registry, or provider-agnostic auth abstraction should be built until a second provider (e.g., GitLab) is an actual, immediate roadmap item — building this abstraction speculatively, before a second real implementation exists, was explicitly identified as premature and likely to be wrong in its guessed shape.

### 8.2 Self-Hosting

A full self-hosting story was designed in detail (Docker Compose bundle with Postgres/Redis/app services, GitHub App manifest-flow setup wizard for one-click app registration, layered sandbox isolation tiers via gVisor/Firecracker, Helm chart for Kubernetes with autoscaling and network policies) but has been explicitly ruled out for the current phase in favor of shipping a cloud-hosted SaaS product first, matching how CodeRabbit operates. This remains a valid, desirable future direction — likely positioned as an "Enterprise tier" unlock — but should not be built now.

### 8.3 Dashboard (React Frontend)

A React-based dashboard was designed (GitHub OAuth login, per-repo BugHunter settings — trigger label, max repair attempts, LLM provider selection, approval requirements — and a job activity feed with detailed per-job trace views showing reproduction logs, diagnosis, diffs, and retry attempts) but was explicitly deferred until after the core repair loop is working end to end. The reasoning: building the dashboard before real job data exists means building it twice — once against fake data, once against real data — and the current priority is finishing the engine before wrapping a UI around it.

### 8.4 Monetization Model (For Future Reference)

A tiered model was discussed, directly inspired by CodeRabbit's approach:
- **Free**: public repos, limited fixes/month (growth engine — OSS maintainers try it, bring it to their employer)
- **Pro**: private repos, unlimited fixes, priority queue
- **Team**: multiple repos, analytics, notifications
- **Enterprise**: SLA, bring-your-own-model, self-hosting, dedicated support

This is not an engineering concern for the current build phase but is documented here so future pricing/config decisions (e.g., per-repo settings schema) don't accidentally conflict with this intended tier structure.

---

## 9. Key Terminology Glossary

- **Job**: A single unit of work in Postgres representing one bug report being processed, from webhook receipt through to PR creation or diagnosis. Has a `status` field that transitions through defined stages (`received` → `reproducing` → `localizing` → `fixing` → `pr_opened` / `failed`).
- **Installation**: A GitHub App's connection to a specific repository or organization, identified by an `installation_id`. All GitHub API actions BugHunter takes are authenticated as a specific installation.
- **Sandbox**: An isolated Docker container environment where a cloned repository is run, tested, and modified — never executed on bare infrastructure, always isolated.
- **Reproduction**: The act of confirming a reported bug actually occurs by executing the described steps inside a sandbox. This must happen before any fix is attempted.
- **Localization**: The step of narrowing down which files/functions in a codebase are likely responsible for a confirmed bug, using a combination of static analysis and LLM reasoning.
- **Repair loop**: The bounded, recursive cycle of generate-fix → apply → reproduce-check → retry-if-failed, capped at a configurable maximum number of attempts (default 5).
- **Normalized event**: The intended future internal representation of a bug-triggering event, independent of which VCS provider (GitHub, GitLab, etc.) it originated from. Not yet implemented, documented for future direction only (see 8.1).

---

## 10. Instructions for Any LLM Continuing This Project

If you are an LLM being asked to write code, review code, or make architectural suggestions for BugHunter, hold yourself to these constraints:

1. **Do not suggest personal access tokens or manual credential handling for end users.** GitHub App installation auth (Section 6) is the only correct end-user-facing auth model. `GITHUB_TEST_TOKEN` was a temporary local dev shortcut and has been superseded — do not reintroduce it as a suggestion for production behavior.
2. **Do not suggest merging the AWS EC2 worker back into the Render web service** unless explicitly asked to reconsider infrastructure costs — this split was a deliberate decision to stay on free tiers while using available AWS credits, and it also sets up the future home for the Go sandbox executor.
3. **Do not suggest abandoning the Controller → Service → Repository layering** in `orchestrator/` in favor of putting logic directly in route handlers. This separation was deliberately established and should be extended, not bypassed.
4. **Do not build multi-provider (GitLab/Jira) abstractions unless asked.** The current scope is GitHub-only; only the naming/seam described in Section 8.1 should be kept in mind, not built out.
5. **Do not build the React dashboard or self-hosting tooling unless asked.** These are documented future directions, explicitly deferred in favor of finishing the core repair loop first.
6. **Always preserve the human approval gate at the PR stage.** BugHunter must never auto-merge its own pull requests, under any configuration.
7. **Always preserve the reproduction-before-fix constraint.** BugHunter must never attempt a fix without first proving the bug is reproducible in a sandbox, and must never silently guess when reproduction fails — it must communicate this honestly on the issue.
8. **Preserve vendor neutrality in the LLM layer.** Any new AI-related code must go through the `litellm`-based abstraction, never a direct provider SDK call, unless explicitly building a new provider adapter.
9. **Respect the bounded repair loop.** Any repair/retry logic must have an explicit, configurable maximum attempt count — never an unbounded or implicit loop.

---

*This document should be updated as the project evolves. Treat it as living context, not a static spec — but any change to the principles in Section 2 or the constraints in Section 10 should be a deliberate, explicit decision, not an incidental drift.*
