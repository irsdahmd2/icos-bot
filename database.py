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
    global _client
    if _client is None:
        if not config.SUPABASE_URL or not config.SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL / SUPABASE_KEY not set. Create a free project at "
                "https://supabase.com, then set these as environment variables."
            )
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _client


def init_db():
    """Checks the connection actually works, so a missing key or un-run
    schema fails loudly here instead of silently later mid-pipeline."""
    try:
        get_client().table("products").select("product_id").limit(1).execute()
    except Exception as e:
        raise RuntimeError(
            "Could not reach the 'products' table in Supabase. Make sure you've "
            "run schema.sql AND schema_update_2026-09-05.sql in the Supabase SQL "
            "Editor, and that SUPABASE_URL / SUPABASE_KEY are correct. "
            "Original error: " + str(e)
        )


def new_id(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def now():
    return datetime.now(timezone.utc).isoformat()


def today():
    return date.today().isoformat()


# ---------- Products (freeform naming) ----------

def _slugify_code(product_name: str) -> str:
    """Turns a freeform product name into a short readable code, e.g.
    'Household Operating System' -> 'HOS'. Falls back to first letters
    of the raw string if there are no clean words."""
    words = re.findall(r"[A-Za-z0-9]+", product_name)
    if not words:
        return "PROD"
    code = "".join(w[0] for w in words).upper()
    return code[:8] if code else "PROD"


def find_product_by_name(product_name: str):
    """Case-insensitive lookup so re-uploading the same product under a
    different tier reuses the same product_id instead of creating a duplicate."""
    res = get_client().table("products").select("*").execute()
    for row in res.data:
        if row["product_name"].strip().lower() == product_name.strip().lower():
            return row
    return None


def add_or_get_product(product_name: str, tier: str, source_filename: str):
    """Freeform product entry point. If this product name already exists
    (from an earlier tier upload), reuse its product_id. Otherwise generate
    a short unique code from the name and create a new row."""
    existing = find_product_by_name(product_name)
    if existing:
        return existing["product_id"]

    base_code = _slugify_code(product_name)
    code = base_code
    suffix = 1
    # Guard against code collisions between differently-named products
    # that happen to share initials.
    existing_codes = {r["product_id"] for r in get_client().table("products").select("product_id").execute().data}
    while code in existing_codes:
        suffix += 1
        code = f"{base_code}{suffix}"

    get_client().table("products").insert({
        "product_id": code,
        "product_name": product_name,
        "tier": tier,
        "source_filename": source_filename,
        "uploaded_at": now(),
    }).execute()
    return code


def get_all_products():
    res = get_client().table("products").select("*").order("uploaded_at").execute()
    return res.data


# ---------- Knowledge Units ----------

def add_knowledge_unit(product_id, tier, category, core_insight, raw_source_text):
    ku_id = new_id("ku_")
    get_client().table("knowledge_units").insert({
        "ku_id": ku_id,
        "product_id": product_id,
        "tier": tier,
        "category": category,
        "core_insight": core_insight,
        "raw_source_text": raw_source_text,
        "status": "unused",
        "extracted_at": now(),
    }).execute()
    return ku_id


def get_knowledge_unit(ku_id):
    res = get_client().table("knowledge_units").select("*").eq("ku_id", ku_id).execute()
    return res.data[0] if res.data else None


def get_unused_knowledge_units(product_id, limit=1, exclude_ids=None):
    """Get up to `limit` unused KUs for this product, oldest first,
    optionally excluding specific ku_ids (used when combining)."""
    exclude_ids = exclude_ids or []
    query = (
        get_client()
        .table("knowledge_units")
        .select("*")
        .eq("product_id", product_id)
        .eq("status", "unused")
        .order("extracted_at", desc=False)
        .limit(limit + len(exclude_ids))
    )
    res = query.execute()
    rows = [r for r in res.data if r["ku_id"] not in exclude_ids]
    return rows[:limit]


def mark_kus_used(ku_ids: list):
    for ku_id in ku_ids:
        get_client().table("knowledge_units").update({"status": "used"}).eq("ku_id", ku_id).execute()


# ---------- CIP ----------

def save_cip(ku_id, dimensions: dict):
    cip_id = new_id("cip_")
    get_client().table("cip").insert({
        "cip_id": cip_id,
        "ku_id": ku_id,
        "core_insight": dimensions.get("core_insight", ""),
        "real_life_situation": dimensions.get("real_life_situation", ""),
        "hidden_issue": dimensions.get("hidden_issue", ""),
        "psychological_dimension": dimensions.get("psychological_dimension", ""),
        "behavioral_dimension": dimensions.get("behavioral_dimension", ""),
        "positive_value": dimensions.get("positive_value", ""),
        "negative_value": dimensions.get("negative_value", ""),
        "common_behaviour": dimensions.get("common_behaviour", ""),
        "alternative_perspective": dimensions.get("alternative_perspective", ""),
        "practical_insight": dimensions.get("practical_insight", ""),
        "reflection": dimensions.get("reflection", ""),
        "curiosity_bridge": dimensions.get("curiosity_bridge", ""),
        "created_at": now(),
    }).execute()
    return cip_id


def get_latest_cip_for_ku(ku_id):
    res = (
        get_client()
        .table("cip")
        .select("*")
        .eq("ku_id", ku_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


# ---------- Ecosystem Memory (anti-repetition) ----------

def get_used_intents(ku_id, platform):
    res = (
        get_client()
        .table("ecosystem_history")
        .select("editorial_intent")
        .eq("ku_id", ku_id)
        .eq("platform", platform)
        .execute()
    )
    return [r["editorial_intent"] for r in res.data]


def log_ecosystem_use(ku_id, platform, editorial_intent):
    get_client().table("ecosystem_history").insert({
        "id": new_id("eco_"),
        "ku_id": ku_id,
        "platform": platform,
        "editorial_intent": editorial_intent,
        "used_at": now(),
    }).execute()


# ---------- Post ID convention: ProductId/Tier/### ----------

def next_post_code(product_id, tier):
    res = (
        get_client().table("post_sequence").select("*")
        .eq("product_id", product_id).eq("tier", tier).execute()
    )
    if res.data:
        n = res.data[0]["last_number"] + 1
        get_client().table("post_sequence").update({"last_number": n}).eq(
            "product_id", product_id).eq("tier", tier).execute()
    else:
        n = 1
        get_client().table("post_sequence").insert({
            "product_id": product_id, "tier": tier, "last_number": n
        }).execute()
    return f"{product_id}/{tier}/{n:03d}"


# ---------- Generated Content ----------

def save_generated_content(ku_id, cip_id, product_id, tier, platform,
                            editorial_intent, content_text, post_code, version=1):
    content_id = new_id("content_")
    get_client().table("generated_content").insert({
        "content_id": content_id,
        "ku_id": ku_id,
        "cip_id": cip_id,
        "product_id": product_id,
        "tier": tier,
        "platform": platform,
        "editorial_intent": editorial_intent,
        "content_text": content_text,
        "post_code": post_code,
        "version": version,
        "status": "generated",
        "generated_at": now(),
    }).execute()
    return content_id


def save_new_version(old_content_id, new_content_text, new_editorial_intent):
    """REFINE creates a new version of the SAME post_code, not a new post
    (locked rule, 2026-09-05). Marks the old row superseded and inserts a
    new row carrying the same post_code/ku/product/platform, version+1."""
    old = get_content(old_content_id)
    if not old:
        return None
    get_client().table("generated_content").update({"superseded": True}).eq(
        "content_id", old_content_id).execute()

    content_id = new_id("content_")
    get_client().table("generated_content").insert({
        "content_id": content_id,
        "ku_id": old["ku_id"],
        "cip_id": old["cip_id"],
        "product_id": old["product_id"],
        "tier": old.get("tier"),
        "platform": old["platform"],
        "editorial_intent": new_editorial_intent,
        "content_text": new_content_text,
        "post_code": old["post_code"],
        "version": (old.get("version") or 1) + 1,
        "status": "generated",
        "generated_at": now(),
    }).execute()
    return content_id


def update_audit_result(content_id, audit_status, audit_results: dict):
    get_client().table("generated_content").update({
        "status": "audited",
        "audit_status": audit_status,
        "audit_results": audit_results,
    }).eq("content_id", content_id).execute()


def update_content_status(content_id, status):
    """status in: telegram_delivered, ready_to_publish, manually_published,
    confirmed_published, rejected"""
    payload = {"status": status}
    if status == "confirmed_published":
        payload["publication_status"] = "published"
        payload["published_at"] = now()
    get_client().table("generated_content").update(payload).eq("content_id", content_id).execute()


def get_content(content_id):
    res = get_client().table("generated_content").select("*").eq("content_id", content_id).execute()
    return res.data[0] if res.data else None


# ---------- Master Scheduler: daily active product + platform tracking ----------

def _last_active_product_id():
    res = (
        get_client().table("daily_state").select("active_product_id")
        .order("state_date", desc=True).limit(1).execute()
    )
    return res.data[0]["active_product_id"] if res.data else None


def get_or_create_todays_active_product():
    """The Master Scheduler's ONLY job: pick one active product for today,
    via simple round-robin, and remember it. Returns the daily_state row,
    or None if no products exist yet."""
    t = today()
    existing = get_client().table("daily_state").select("*").eq("state_date", t).execute()
    if existing.data:
        return existing.data[0]

    products = get_all_products()
    if not products:
        return None

    last_id = _last_active_product_id()
    ids = [p["product_id"] for p in products]
    if last_id in ids:
        idx = ids.index(last_id)
        next_product_id = ids[(idx + 1) % len(ids)]
    else:
        next_product_id = ids[0]

    row = {
        "id": new_id("day_"),
        "state_date": t,
        "active_product_id": next_product_id,
        "platforms_completed": [],
        "created_at": now(),
    }
    get_client().table("daily_state").insert(row).execute()
    return row


def mark_platform_completed_today(platform):
    t = today()
    res = get_client().table("daily_state").select("*").eq("state_date", t).execute()
    if not res.data:
        return
    state = res.data[0]
    completed = state.get("platforms_completed") or []
    if platform not in completed:
        completed.append(platform)
        get_client().table("daily_state").update(
            {"platforms_completed": completed}
        ).eq("id", state["id"]).execute()


def get_remaining_platforms_today(all_platforms):
    t = today()
    res = get_client().table("daily_state").select("platforms_completed").eq("state_date", t).execute()
    completed = res.data[0]["platforms_completed"] if res.data else []
    return [p for p in all_platforms if p not in completed]


# ---------- Status (used by /status command) ----------

def get_status_counts():
    client = get_client()
    products = client.table("products").select("product_id", count="exact").execute()
    kus = client.table("knowledge_units").select("ku_id", count="exact").execute()
    published = (
        client.table("generated_content")
        .select("content_id", count="exact")
        .eq("status", "confirmed_published")
        .execute()
    )
    return products.count or 0, kus.count or 0, published.count or 0


def get_per_product_dashboard():
    """Serial# | Product | KU counts per tier | posts generated | audit-passed |
    confirmed published. Returns a list of dicts, one per product."""
    products = get_all_products()
    rows = []
    for p in products:
        kus = get_client().table("knowledge_units").select("tier", count="exact").eq(
            "product_id", p["product_id"]).execute().data
        counts = {"Full_OS": 0, "Handbook": 0, "Codex": 0}
        for ku in kus:
            t = ku.get("tier")
            if t in counts:
                counts[t] += 1

        content_rows = get_client().table("generated_content").select(
            "audit_status", "status"
        ).eq("product_id", p["product_id"]).execute().data
        posts_generated = len(content_rows)
        audit_passed = len([c for c in content_rows if c.get("audit_status") == "PASS"])
        confirmed_published = len([c for c in content_rows if c.get("status") == "confirmed_published"])

        rows.append({
            "product_id": p["product_id"],
            "product_name": p["product_name"],
            **counts,
            "posts_generated": posts_generated,
            "audit_passed": audit_passed,
            "confirmed_published": confirmed_published,
        })
    return rows


# ---------- Simple key-value settings (used for the pinned live dashboard) ----------

def get_setting(key: str):
    res = get_client().table("bot_settings").select("value").eq("key", key).execute()
    return res.data[0]["value"] if res.data else None


def set_setting(key: str, value: str):
    existing = get_client().table("bot_settings").select("key").eq("key", key).execute()
    if existing.data:
        get_client().table("bot_settings").update({"value": value}).eq("key", key).execute()
    else:
        get_client().table("bot_settings").insert({"key": key, "value": value}).execute()
