"""
ICOS Configuration
All settings live here so nothing is hard-coded elsewhere.
"""

import os

# --- Telegram Bot ---
# Set this as an environment variable before running, e.g.:
#   export TELEGRAM_BOT_TOKEN="8495034853:AAHUaGcM4oxImNjQzWjQKVNOvGkmCWjiLwY"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# The Telegram numeric user ID of the ONLY person allowed to control the bot.
# Leave blank for now — bot.py will print your ID the first time you message it,
# then paste it here (or set as env var OWNER_TELEGRAM_ID) to lock the bot to you.
OWNER_TELEGRAM_ID = os.environ.get("OWNER_TELEGRAM_ID", "")

# --- AI Provider: Google Gemini (free tier, no card required) ---
# Get a free key at: https://aistudio.google.com/apikey
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
AI_MODEL = "gemini-2.0-flash"

# --- Database: Supabase (Postgres) ---
# Get these from your Supabase project: Project Settings -> API
#   SUPABASE_URL looks like: https://xxxxxxxxxxxx.supabase.co
#   SUPABASE_KEY: use the "service_role" secret key (NOT the public "anon" key) —
#   this bot runs as a trusted backend, not a browser, so it needs the service_role
#   key to read/write freely without setting up Row Level Security policies.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# --- Products (from locked blueprint) ---
PRODUCTS = {
    "WPPS": "Workplace Political System",
    "HOS": "Household Operating System",
    "MIZAN": "Mizan",
    "LTOS": "Life/Lifestyle Operating System",
    "DOS": "Decision Operating System",
}

VALID_TIERS = ["Full_OS", "Handbook", "Codex"]

# --- Platforms currently implemented in V1 ---
# (Instagram not yet designed per blueprint — excluded until format is locked)
ACTIVE_PLATFORMS = ["linkedin", "blog", "facebook", "pinterest"]

# --- Reply Assistant (separate, dedicated bot — screenshot-based LinkedIn replies) ---
# This is a SEPARATE bot from the main content bot, on purpose — different Telegram token.
REPLY_BOT_TOKEN = os.environ.get("REPLY_BOT_TOKEN", "")
REPLY_BOT_OWNER_ID = os.environ.get("REPLY_BOT_OWNER_ID", "")
