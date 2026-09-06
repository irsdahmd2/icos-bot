"""
ICOS Configuration
All settings live here so nothing is hard-coded elsewhere.

CHANGED 2026-09-05:
- Removed the fixed PRODUCTS dict. Products are now FREEFORM — you type the
  real product name when you upload, no code list to maintain.
- Removed the example token that was written directly in this file's comments.
  NEVER paste a real key/token into this file as text, even as an "example" —
  only ever set secrets as environment variables in Termux. If a real token
  was ever pasted here before, rotate it via @BotFather now.
"""

import os

# --- Telegram Bot ---
# Set this as an environment variable in Termux before running:
#   export TELEGRAM_BOT_TOKEN="your-real-token-here"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# The Telegram numeric user ID of the ONLY person allowed to control the bot.
# Leave blank the first time — bot.py will print your ID when you message it,
# then set it as an environment variable OWNER_TELEGRAM_ID.
OWNER_TELEGRAM_ID = os.environ.get("OWNER_TELEGRAM_ID", "")

# --- AI Provider: Google Gemini (free tier, no card required) ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
AI_MODEL = "gemini-2.0-flash"

# --- Database: Supabase (Postgres) ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# --- Tiers (locked) ---
VALID_TIERS = ["Full_OS", "Handbook", "Codex"]
