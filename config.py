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
# NEW 2026-09-21: tried in this order when AI_MODEL is overloaded (503) or its
# free daily quota is used up (429). All are current stable Gemini models per
# Google's model list; each has its own capacity and its own free quota.
GEMINI_FALLBACK_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]

# --- Fallback AI Provider: Groq (free tier, no card required) ---
# Used ONLY when Gemini is temporarily overloaded/unavailable after its own
# retries are exhausted (e.g. the 503 UNAVAILABLE error). Gemini stays the
# PRIMARY provider for quality reasons — this is strictly an emergency
# backup so a temporary Gemini outage doesn't stall generation.
# Optional: if GROQ_API_KEY is left blank, the bot behaves exactly as
# before (no fallback attempted, same as pre-fallback behavior).
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_FALLBACK_MODEL = "openai/gpt-oss-120b"

# --- Database: Supabase (Postgres) ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# --- Tiers (locked) ---
VALID_TIERS = ["Full_OS", "Handbook", "Codex"]

# Roughly how many Knowledge Units to aim for per tier (locked decision:
# Full OS = deepest/most, Handbook = concept-level/medium, Codex = fastest/least).
# These are guidance ranges given to the AI extractor, not hard caps.
TIER_KU_TARGET = {
    # RAISED 2026-09-13: the old ranges (Full_OS 8-15, Handbook 5-10, Codex 3-6)
    # were an artificial ceiling that had nothing to do with how much genuine
    # content each tier actually contains. A real 51-page Handbook was found
    # to contain 20+ distinct content sections (Emergency Anchor Card,
    # Household Identification, Lifeboat Protocol, Knowledge Loss Audit,
    # Disaster Recovery Timeline, Weekly Reset SOP, Daily Household
    # Dashboard, Child Profile Tracker, and more) — far more than 10 KUs
    # worth of extractable insight. New ranges are set to genuinely scale
    # with each tier's real page count (Codex 6-10pp, Handbook 35-50pp,
    # Full OS 150+pp), not an arbitrary round number.
    # CHANGED 2026-09-20: only the SECOND number is used now (a ceiling, not a
    # target). One KU = one teachable idea, and a single section of a product
    # usually holds several, so the old ceilings (Handbook 50 / Codex 8) were
    # capping supply far below what the documents contain. Extraction still
    # stops when only repetition remains.
    "Full_OS": (40, 250),
    "Handbook": (20, 120),
    "Codex": (3, 40),
}

# RAISED 2026-09-13: extraction was silently truncating product text to the
# first 15,000 characters before ever showing it to the AI — a 66,000
# character Handbook only ever had its first ~23% actually read. Raised to
# cover a full Handbook or Codex; a true 150+ page Full OS may still exceed
# this and need chunked extraction later, but this is a large improvement
# over the previous silent 15,000-character cutoff.
EXTRACTION_TEXT_LIMIT = 100000

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
MAX_KU_COMBINE = 2  # LOWERED 2026-09-13: was 5 — silently collapsing up to 5
# potential standalone posts into a single post. Irshad's explicit priority is
# maximum publishable post volume; combining is now reserved for genuinely
# thin KUs paired with exactly one other, never a 5-way merge.

# Locked rule: failed content NEVER reaches Telegram. If a generated post
# fails audit, the pipeline retries internally (different angle each time)
# up to this many attempts before giving up and telling the user honestly
# that this Knowledge Unit needs attention, instead of showing a failed post.
# NEW 2026-09-20: how many distinct LinkedIn posts ONE Knowledge Unit may
# produce over time, each from a genuinely different angle (situation, mistake,
# warning, ...). Every KU gets its first post before any KU gets a second, so
# the daily product rotation stays fresh. A KU is retired ('used') once it has
# this many passing posts, or earlier if it cannot yield a new angle.
MAX_POSTS_PER_KU = 3

MAX_AUDIT_RETRIES = 3

# The FULL planned platform list (locked spec), shown for progress context in
# Telegram even though most of these don't have a working generator yet.
# ACTIVE_PLATFORMS above is the REAL list the bot can actually generate for.
ALL_PLANNED_PLATFORMS = [
    "linkedin", "blog", "facebook", "instagram",
    "youtube_short", "youtube_podcast",
]

# --- Reply Assistant (separate, dedicated bot — screenshot-based LinkedIn replies) ---
REPLY_BOT_TOKEN = os.environ.get("REPLY_BOT_TOKEN", "")
REPLY_BOT_OWNER_ID = os.environ.get("REPLY_BOT_OWNER_ID", "")
