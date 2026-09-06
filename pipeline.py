"""
ICOS Pipeline — the conductor. Wires extraction -> generation -> audit -> storage.
No Telegram code here, no Supabase code here — only calls into database.py,
extraction.py, and the generator_*.py files.

CHANGED 2026-09-05:
- process_new_product() uses freeform naming (no product code list)
- generate_for_platform() replaces generate_daily_bundle() — generates ONE
  platform on demand (command-based model, not a daily bundle of all platforms)
- KU combining: if the next unused KU is thin, combines up to
  config.MAX_KU_COMBINE related unused KUs into one merged CIP
- refine() implements the REFINE button: new version of the same post, re-audited
"""

import config
import database as db
import extraction

GENERATORS = {}
try:
    import generator_linkedin
    GENERATORS["linkedin"] = generator_linkedin
except ImportError:
    pass
try:
    import generator_blog
    GENERATORS["blog"] = generator_blog
except ImportError:
    pass
try:
    import generator_facebook
    GENERATORS["facebook"] = generator_facebook
except ImportError:
    pass
try:
    import generator_pinterest
