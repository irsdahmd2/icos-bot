"""
ICOS Database Layer — Supabase (Postgres) edition
Implements the locked data model:
Product -> Knowledge Unit -> CIP -> Platform Content -> Audit -> Publication
Plus Content Ecosystem Memory (tracks which "angle" a KU has used per platform,
so the same insight isn't recycled the same way twice).

IMPORTANT FOR NON-TECHNICAL USE: this is the ONLY file that knows the database
is Supabase. Every other file (pipeline.py, bot.py) calls these functions by
name, exactly as before — they have no idea what's behind them. If the
database is ever changed again, only this file needs to change.

NOTE: unlike SQLite, Supabase tables cannot be created from this Python file —
Supabase's client talks to the database over its REST API (PostgREST), which
doesn't run table-creation SQL. The tables are created ONCE by pasting
schema.sql into the Supabase dashboard's SQL Editor. See SETUP_INSTRUCTIONS.md.
"""

import json
import uuid
from datetime import datetime, timezone

from supabase import create_client, Client

import config

_client: Client = None


def get_client() -> Client:
    global _client
    if _client is None:
        if not config.SUPABASE_URL or not config.SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL / SUPABASE_KEY not set. Create a free project at "
                "https://supabase.com, then set these as environment variables. "
                "See SETUP_INSTRUCTIONS.md."
            )
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _client


def init_db():
    """
    Tables live in Supabase already (created once via schema.sql in the SQL
    Editor). This just checks the connection actually works, so a missing key
    or un-run schema fails loudly here instead of silently later mid-pipeline.
    """
    try:
        get_client().table("products").select("product_id").limit(1).execute()
    except Exception as e:
        raise RuntimeError(
            "Could not reach the 'products' table in Supabase. Make sure you've "
            "run schema.sql in the Supabase SQL Editor first, and that "
            "SUPABASE_URL / SUPABASE_KEY are correct. Original error: " + str(e)
        )


def new_id(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def now():
    return datetime.now(timezone.utc).isoformat()


# ---------- Products ----------

def add_product(product_id, product_name, tier, source_filename):
    get_client().table("products").insert({
        "product_id": product_id,
        "product_name": product_name,
        "tier": tier,
        "source_filename": source_filename,
        "uploaded_at": now(),
    }).execute()


# ---------- Knowledge Units ----------

def add_knowledge_unit(product_id, category, core_insight, raw_source_text):
    ku_id = new_id("ku_")
    get_client().table("knowledge_units").insert({
        "ku_id": ku_id,
        "product_id": product_id,
        "category": category,
        "core_insight": core_insight,
        "raw_source_text": raw_source_text,
        "extracted_at": now(),
    }).execute()
    return ku_id


def get_knowledge_unit(ku_id):
    res = get_client().table("knowledge_units").select("*").eq("ku_id", ku_id).execute()
    return res.data[0] if res.data else None


def get_unused_knowledge_unit(product_id):
    """Get a KU from this product that hasn't been published on every active platform yet."""
    res = (
        get_client()
        .table("knowledge_units")
        .select("*")
        .eq("product_id", product_id)
        .neq("status", "exhausted")
        .order("extracted_at", desc=False)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


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


def get_cip(cip_id):
    res = get_client().table("cip").select("*").eq("cip_id", cip_id).execute()
    return res.data[0] if res.data else None


def get_latest_cip_for_ku(ku_id):
    """Most recently created CIP for a given Knowledge Unit."""
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


# ---------- Ecosystem Memory ----------

def get_used_intents(ku_id, platform):
    """Which Editorial Intents has this KU already used on this platform?"""
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


# ---------- Generated Content ----------

def save_generated_content(ku_id, cip_id, product_id, platform, editorial_intent, content_text):
    content_id = new_id("content_")
    get_client().table("generated_content").insert({
        "content_id": content_id,
        "ku_id": ku_id,
        "cip_id": cip_id,
        "product_id": product_id,
        "platform": platform,
        "editorial_intent": editorial_intent,
        "content_text": content_text,
        "generated_at": now(),
    }).execute()
    return content_id


def update_audit_result(content_id, audit_status, audit_results: dict):
    get_client().table("generated_content").update({
        "audit_status": audit_status,
        "audit_results": audit_results,  # jsonb column — dict stored directly, no json.dumps needed
    }).eq("content_id", content_id).execute()


def update_approval(content_id, approval_status):
    get_client().table("generated_content").update({
        "approval_status": approval_status,
        "approved_at": now(),
    }).eq("content_id", content_id).execute()


def update_publication(content_id, published_url):
    get_client().table("generated_content").update({
        "publication_status": "published",
        "published_url": published_url,
        "published_at": now(),
    }).eq("content_id", content_id).execute()


def get_content(content_id):
    res = get_client().table("generated_content").select("*").eq("content_id", content_id).execute()
    return res.data[0] if res.data else None


def get_pending_bundle_for_ku(ku_id):
    """All platform content generated for one KU that's awaiting approval."""
    res = (
        get_client()
        .table("generated_content")
        .select("*")
        .eq("ku_id", ku_id)
        .eq("approval_status", "pending")
        .order("platform")
        .execute()
    )
    return res.data


# ---------- Status (used by bot.py's /status command) ----------

def get_status_counts():
    """Returns (product_count, ku_count, published_count) for the /status command."""
    client = get_client()
    products = client.table("products").select("product_id", count="exact").execute()
    kus = client.table("knowledge_units").select("ku_id", count="exact").execute()
    published = (
        client.table("generated_content")
        .select("content_id", count="exact")
        .eq("publication_status", "published")
        .execute()
    )
    return products.count or 0, kus.count or 0, published.count or 0
