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
    GENERATORS["pinterest"] = generator_pinterest
except ImportError:
    pass

import audits


def process_new_product(product_name: str, tier: str, source_filename: str, raw_text: str) -> dict:
    """Upload -> tier confirm -> extraction. Returns a summary dict for the
    Telegram confirmation message."""
    product_id = db.add_or_get_product(product_name, tier, source_filename)

    ku_dicts = extraction.extract_knowledge_units(raw_text, tier)
    saved = 0
    for ku in ku_dicts:
        db.add_knowledge_unit(
            product_id=product_id,
            tier=tier,
            category=ku.get("category", ""),
            core_insight=ku.get("core_insight", ""),
            raw_source_text=ku.get("source_excerpt", ""),
        )
        saved += 1

    return {"product_id": product_id, "product_name": product_name, "tier": tier, "ku_count": saved}


def _merge_cips(ku_group: list) -> dict:
    """Combine up to MAX_KU_COMBINE KUs' CIPs into one merged CIP dict when
    a single KU is too thin to carry a full post on its own."""
    if len(ku_group) == 1:
        cip = db.get_latest_cip_for_ku(ku_group[0]["ku_id"])
        return cip or {"core_insight": ku_group[0]["core_insight"]}

    merged = {}
    fields = ["core_insight", "real_life_situation", "hidden_issue", "psychological_dimension",
              "behavioral_dimension", "positive_value", "negative_value", "common_behaviour",
              "alternative_perspective", "practical_insight", "reflection", "curiosity_bridge"]
    for field in fields:
        parts = []
        for ku in ku_group:
            cip = db.get_latest_cip_for_ku(ku["ku_id"]) or {}
            val = cip.get(field, "")
            if val:
                parts.append(val)
        merged[field] = " | ".join(parts)
    return merged


def _get_ku_group_for_generation(product_id: str, thin_word_threshold: int = 35) -> list:
    """Locked rule (2026-09-05): combine up to config.MAX_KU_COMBINE unused
    KUs into one post when a single KU's core insight is too thin on its own."""
    first = db.get_unused_knowledge_units(product_id, limit=1)
    if not first:
        return []
    ku = first[0]
    group = [ku]
    if len(ku["core_insight"].split()) < thin_word_threshold:
        more = db.get_unused_knowledge_units(
            product_id, limit=config.MAX_KU_COMBINE - 1, exclude_ids=[ku["ku_id"]]
        )
        group.extend(more)
    return group


def generate_for_platform(product_id: str, product_name: str, tier: str, platform: str) -> dict:
    """Command-based generation for ONE platform (locked model, 2026-09-05):
    no daily bundle, no scheduler push — this runs only when the user picks
    a platform button after /generate."""
    generator = GENERATORS.get(platform)
    if not generator:
        return {"error": f"No generator built yet for '{platform}'."}

    ku_group = _get_ku_group_for_generation(product_id)
    if not ku_group:
        return {"error": "No unused Knowledge Units left for this product."}

    # Ensure every KU in the group has a CIP (build any missing ones)
    for ku in ku_group:
        if not db.get_latest_cip_for_ku(ku["ku_id"]):
            dims = extraction.build_cip(ku["core_insight"], ku.get("category", ""), ku.get("raw_source_text", ""))
            db.save_cip(ku["ku_id"], dims)

    merged_cip = _merge_cips(ku_group)
    primary_ku = ku_group[0]

    avoid_intents = db.get_used_intents(primary_ku["ku_id"], platform)
    content_text, editorial_intent = generator.generate(merged_cip, product_name, avoid_intents)

    post_code = db.next_post_code(product_id, tier)
    cip_id = (db.get_latest_cip_for_ku(primary_ku["ku_id"]) or {}).get("cip_id")
    content_id = db.save_generated_content(
        ku_id=primary_ku["ku_id"], cip_id=cip_id, product_id=product_id, tier=tier,
        platform=platform, editorial_intent=editorial_intent, content_text=content_text,
        post_code=post_code,
    )

    audit_status, audit_results = audits.run_audit(content_text, product_name)
    db.update_audit_result(content_id, audit_status, audit_results)

    db.mark_kus_used([ku["ku_id"] for ku in ku_group])
    db.log_ecosystem_use(primary_ku["ku_id"], platform, editorial_intent)

    return {
        "content_id": content_id,
        "post_code": post_code,
        "platform": platform,
        "content_text": content_text,
        "editorial_intent": editorial_intent,
        "audit_status": audit_status,
        "audit_results": audit_results,
        "kus_used": len(ku_group),
    }


def refine(content_id: str, product_name: str) -> dict:
    """REFINE button: regenerate, re-audit, return as a NEW VERSION of the
    same post_code (locked rule) — not a new independent post."""
    old = db.get_content(content_id)
    if not old:
        return {"error": "Original content not found."}

    generator = GENERATORS.get(old["platform"])
    ku = db.get_knowledge_unit(old["ku_id"])
    cip = db.get_latest_cip_for_ku(old["ku_id"]) or {}
    avoid_intents = db.get_used_intents(old["ku_id"], old["platform"])

    content_text, editorial_intent = generator.generate(cip, product_name, avoid_intents)
    new_content_id = db.save_new_version(content_id, content_text, editorial_intent)

    audit_status, audit_results = audits.run_audit(content_text, product_name)
    db.update_audit_result(new_content_id, audit_status, audit_results)
    db.log_ecosystem_use(old["ku_id"], old["platform"], editorial_intent)

    return {
        "content_id": new_content_id,
        "post_code": old["post_code"],
        "platform": old["platform"],
        "content_text": content_text,
        "editorial_intent": editorial_intent,
        "audit_status": audit_status,
        "audit_results": audit_results,
    }


def mark_ready_to_publish(content_id: str):
    db.update_content_status(content_id, "ready_to_publish")


def mark_confirmed_published(content_id: str):
    content = db.get_content(content_id)
    db.update_content_status(content_id, "confirmed_published")
    if content:
        db.mark_platform_completed_today(content["platform"])
    return content
