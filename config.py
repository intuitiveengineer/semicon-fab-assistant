"""Central configuration.

Loads environment variables from `.env` once, validates them, and exposes
them as plain Python values the rest of the app imports. Keeping this in one
place means no other module re-reads `os.environ`, and a missing/blank secret
fails fast here with a clear message instead of deep inside the SDK later.
"""

import os

from dotenv import load_dotenv

# Read `.env` (if present) into the process environment. Real secrets live in
# `.env` (gitignored); `.env.example` documents which keys are required.
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is not set. Add it to your .env file "
        "(see .env.example for the template)."
    )

# Default chat model for quick calls: cheap and fast. Easy to swap later.
DEFAULT_CHAT_MODEL = "gpt-4o-mini"
