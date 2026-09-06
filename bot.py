"""
ICOS Telegram Bot — the user interface ONLY. No business logic lives here;
everything calls into pipeline.py / database.py.

CHANGED 2026-09-05 (final locked model):
- Upload flow now asks for a FREEFORM product name (no fixed code list)
- /generate takes NO arguments. It shows buttons for whichever platforms
  are NOT yet completed today for the Master Scheduler's active product.
- Every generated post gets 3 buttons: REFINE / READY TO PUBLISH / CONFIRM PUBLISHED
- No auto-publishing anywhere, no time-based schedule anywhere.
"""

import logging
import traceback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

import config
import database as db
import pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("icos")

# In-memory state for the two-step upload flow (PDF -> ask name -> ask tier).
# Keyed by chat_id. This resets if the bot restarts, which is fine — it only
# holds a pending upload, not anything durable.
_pending_uploads = {}


def _owner_only(update: Update) -> bool:
    if not config.OWNER_TELEGRAM_ID:
