"""
ICOS Database Layer — Supabase (Postgres) edition
Implements: Product -> Knowledge Unit -> CIP -> Platform Content -> Publication
Plus Content Ecosystem Memory, the Master Scheduler's daily-state, and the
Post ID sequence.

IMPORTANT FOR NON-TECHNICAL USE: this is the ONLY file that knows the database
is Supabase. Every other file calls these functions by name and has no idea
what's behind them.

CHANGED 2026-09-05:
- Freeform product naming (no more fixed code list) — add_or_get_product()
- Master Scheduler support — get_or_create_todays_active_product(),
  mark_platform_completed_today(), get_remaining_platforms_today()
- Post ID convention (Product/Tier/###) — next_post_code()
- editorial_intent is now actually saved (was always "" before — the bug
  from the earlier checklist item 3)
- Refine-creates-a-new-version support — save_new_version()
- Full status model instead of just approved/rejected —
  update_content_status()
- KU combining — get_unused_knowledge_units(), mark_kus_used()
"""

import json
import re
import uuid
from datetime import datetime, timezone, date

from supabase import create_client, Client

import config

_client: Client = None


def get_client() -> Client:
