"""
orchestrator/config.py

All environment-variable-backed configuration for the orchestrator and
background worker.  Import individual constants from here — never read
os.environ directly in business logic.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── GitHub App credentials ────────────────────────────────────────────────
GITHUB_APP_ID: str = os.environ["GITHUB_APP_ID"]
GITHUB_PRIVATE_KEY_PATH: str = os.environ["GITHUB_PRIVATE_KEY_PATH"]
WEBHOOK_SECRET: str = os.environ["WEBHOOK_SECRET"]

# ── Persistence ───────────────────────────────────────────────────────────
DATABASE_URL: str = os.environ["DATABASE_URL"]
REDIS_URL: str = os.environ["REDIS_URL"]

# ── LLM (via litellm — vendor-neutral, see BUGHUNTER_CONTEXT.md §2.1) ────
# Set LLM_MODEL to any litellm-supported model string, e.g.:
#   gemini/gemini-2.0-flash  (default — near-free at prototype scale)
#   gpt-4o
#   anthropic/claude-3-5-sonnet-20241022
#   ollama/llama3 (self-hosted)
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")

# Provider-specific API keys are read by litellm automatically from the
# environment using their standard names:
#   GEMINI_API_KEY      -> Google Gemini
#   OPENAI_API_KEY      -> OpenAI
#   ANTHROPIC_API_KEY   -> Anthropic
#   AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY -> AWS Bedrock
# No special handling is needed here — litellm picks them up on its own.

# ── Repair loop ──────────────────────────────────────────────────────────
MAX_REPAIR_ATTEMPTS: int = int(os.getenv("MAX_REPAIR_ATTEMPTS", "5"))
