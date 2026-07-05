import os
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
GITHUB_TEST_TOKEN = os.getenv("GITHUB_TEST_TOKEN", "")