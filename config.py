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
AI_MODEL = "gemini-3.6-flash"

# --- Fallback AI Provider: Groq (free tier, no card required) ---
# Used ONLY when Gemini is temporarily overloaded/unavailable after its own
# retries are exhausted (e.g. the 503 UNAVAILABLE error). Gemini stays the
# PRIMARY provider for quality reasons — this is strictly an emergency
# backup so a temporary Gemini outage doesn't stall generation.
# Optional: if GROQ_API_KEY is left blank, the bot behaves exactly as
# before (no fallback attempted, same as pre-fallback behavior).
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_FALLBACK_MODEL = "llama-3.3-70b-versatile"

# --- Database: Supabase (Postgres) ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# --- Tiers (locked) ---
VALID_TIERS = ["Full_OS", "Handbook", "Codex"]

# Roughly how many Knowledge Units to aim for per tier (locked decision:
# Full OS = deepest/most, Handbook = concept-level/medium, Codex = fastest/least).
# These are guidance ranges given to the AI extractor, not hard caps.
TIER_KU_TARGET = {
    "Full_OS": (8, 15),
    "Handbook": (5, 10),
    "Codex": (3, 6),
}

# --- Platforms — add new ones here as their generator files are built ---
# A platform only shows up as a button in Telegram once its generator module exists.
# LOCKED BUILD ORDER (2026-09-01): LinkedIn only, end-to-end, tested, before
# starting any other platform. Do NOT add blog/facebook/pinterest back here
# until each one's generator_*.py is updated to return (content_text, angle) —
# same fix generator_linkedin.py just got. Adding them before that update
# will crash pipeline.py when that platform is picked.
ACTIVE_PLATFORMS = ["linkedin"]

# Max Knowledge Units that may be combined into a single post when one KU
# alone is too thin (locked decision, 2026-09-05): combine up to this many.
MAX_KU_COMBINE = 5

# Locked rule: failed content NEVER reaches Telegram. If a generated post
# fails audit, the pipeline retries internally (different angle each time)
# up to this many attempts before giving up and telling the user honestly
# that this Knowledge Unit needs attention, instead of showing a failed post.
MAX_AUDIT_RETRIES = 3

# The FULL planned platform list (locked spec), shown for progress context in
# Telegram even though most of these don't have a working generator yet.
# ACTIVE_PLATFORMS above is the REAL list the bot can actually generate for.
ALL_PLANNED_PLATFORMS = [
    "linkedin", "blog", "facebook", "instagram",
    "pinterest", "youtube_short", "youtube_podcast",
]

# --- Reply Assistant (separate, dedicated bot — screenshot-based LinkedIn replies) ---
REPLY_BOT_TOKEN = os.environ.get("REPLY_BOT_TOKEN", "")
REPLY_BOT_OWNER_ID = os.environ.get("REPLY_BOT_OWNER_ID", "")
