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

import re
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

import audits


def process_new_product(product_name: str, tier: str, source_filename: str, raw_text: str) -> dict:
    """Upload -> tier confirm -> extraction -> cross-tier dedup. Returns a
    summary dict for the Telegram confirmation message."""
    product_id = db.add_or_get_product(product_name, tier, source_filename)

    ku_dicts = extraction.extract_knowledge_units(raw_text, tier, product_name)
    candidate_count = len(ku_dicts)

    # Cross-tier dedup: if this product already has KUs from a different tier
    # (Codex, Handbook, or Full OS uploaded earlier), check new candidates
    # against everything already stored and keep only genuinely unique ones.
    existing_insights = db.get_all_core_insights_for_product(product_id)
    ku_dicts = extraction.filter_duplicate_kus(ku_dicts, existing_insights)
    duplicates_skipped = candidate_count - len(ku_dicts)

    saved = 0
    for ku in ku_dicts:
        db.add_knowledge_unit(
            product_id=product_id,
            tier=tier,
            category=ku.get("category", ""),
            core_insight=ku.get("core_insight", ""),
            raw_source_text=ku.get("source_excerpt", ""),
            protected_terms=ku.get("protected_terms", []),
        )
        saved += 1

    return {
        "product_id": product_id, "product_name": product_name, "tier": tier,
        "ku_count": saved, "duplicates_skipped": duplicates_skipped,
    }


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


def _get_ku_group_for_generation(product_id: str, platform: str = "linkedin", thin_word_threshold: int = 15) -> list:
    """Pick the next Knowledge Unit for this product.

    CHANGED 2026-09-20: a KU can now yield several posts (config.MAX_POSTS_PER_KU),
    each from a new angle. Order: KUs with the FEWEST passing posts first (so every
    KU gets its first post before any gets a second), then KUs with solid source
    text before thin ones, then oldest first.

    Thin-KU combining (unchanged): combine up to config.MAX_KU_COMBINE unused KUs
    into one post ONLY when a single KU's core insight is genuinely fragment-thin
    (under thin_word_threshold words)."""
    candidates = db.get_unused_knowledge_units(product_id, limit=500)
    if not candidates:
        return []
    counts = db.count_passed_posts_by_ku(product_id, platform)

    def sort_key(k):
        thin = len(k.get("raw_source_text") or "") < 250
        return (counts.get(k["ku_id"], 0), thin, k.get("extracted_at") or "")

    candidates.sort(key=sort_key)
    ku = candidates[0]
    group = [ku]
    if len(ku["core_insight"].split()) < thin_word_threshold and counts.get(ku["ku_id"], 0) == 0:
        more = db.get_unused_knowledge_units(
            product_id, limit=config.MAX_KU_COMBINE - 1, exclude_ids=[ku["ku_id"]]
        )
        group.extend(more)
    return group


def _kus_after_pass(ku_group: list, platform: str):
    """After a passing post: the primary KU is retired only once it has
    reached config.MAX_POSTS_PER_KU distinct passing posts; other KUs that were
    merged into this post are retired immediately (their content is now used)."""
    primary = ku_group[0]
    counts = db.count_passed_posts_by_ku(primary["product_id"], platform)
    if counts.get(primary["ku_id"], 0) >= config.MAX_POSTS_PER_KU:
        db.mark_kus_used([primary["ku_id"]])
    rest = [k["ku_id"] for k in ku_group[1:]]
    if rest:
        db.mark_kus_used(rest)


def _anti_repeat_posts(product_id: str, ku_id: str, platform: str) -> list:
    """This KU's own earlier posts FIRST (so a second post on the same idea is
    forced onto new ground), then the product's most recent posts."""
    own = db.get_passed_posts_for_ku(ku_id, platform, limit=3)
    recent = db.get_recent_passed_content(product_id, platform, limit=5)
    seen = {r["content_text"] for r in own}
    return own + [r for r in recent if r["content_text"] not in seen]


def generate_for_platform(product_id: str, product_name: str, tier: str, platform: str) -> dict:
    """Command-based generation for ONE platform (locked model, 2026-09-05):
    no daily bundle, no scheduler push — this runs only when the user picks
    a platform button after /generate.

    Locked rule: failed content NEVER reaches Telegram. Retries internally,
    trying a different editorial angle each time, up to config.MAX_AUDIT_RETRIES.
    Every attempt (pass or fail) is saved to the database for the audit trail,
    but only a PASSING attempt is ever returned to the caller. If nothing
    passes within the retry limit, the KU is marked exhausted (so future
    /generate calls skip it) and an honest failure summary is returned —
    never the failed post text itself."""
    generator = GENERATORS.get(platform)
    if not generator:
        return {"error": f"No generator built yet for '{platform}'."}

    ku_group = _get_ku_group_for_generation(product_id, platform)
    if not ku_group:
        return {"error": "No unused Knowledge Units left for this product."}

    for ku in ku_group:
        if not db.get_latest_cip_for_ku(ku["ku_id"]):
            dims = extraction.build_cip(
                ku["core_insight"], ku.get("category", ""), ku.get("raw_source_text", ""),
                ku.get("protected_terms") or [],
            )
            db.save_cip(ku["ku_id"], dims)

    merged_cip = _merge_cips(ku_group)
    primary_ku = ku_group[0]
    cip_id = (db.get_latest_cip_for_ku(primary_ku["ku_id"]) or {}).get("cip_id")

    attempts_failed = []
    avoid_terms = []
    for attempt in range(1, config.MAX_AUDIT_RETRIES + 1):
        avoid_intents = db.get_used_intents(primary_ku["ku_id"], platform)
        recent_posts = _anti_repeat_posts(product_id, primary_ku["ku_id"], platform)
        content_text, editorial_intent = generator.generate(
            merged_cip, product_name, avoid_intents, recent_posts, avoid_terms=avoid_terms
        )
        post_code = db.next_post_code(product_id, tier)
        content_id = db.save_generated_content(
            ku_id=primary_ku["ku_id"], cip_id=cip_id, product_id=product_id, tier=tier,
            platform=platform, editorial_intent=editorial_intent, content_text=content_text,
            post_code=post_code,
        )
        audit_status, audit_results = audits.run_audit(
            content_text, product_name, product_id, primary_ku["ku_id"],
            core_insight=merged_cip.get("core_insight", ""), platform=platform,
        )
        db.update_audit_result(content_id, audit_status, audit_results)
        db.log_ecosystem_use(primary_ku["ku_id"], platform, editorial_intent)

        if audit_status == "PASS":
            _kus_after_pass(ku_group, platform)
            return {
                "content_id": content_id, "post_code": post_code, "platform": platform,
                "content_text": content_text, "editorial_intent": editorial_intent,
                "audit_status": audit_status, "audit_results": audit_results,
                "attempts": attempt,
            }

        failed_checks = [k for k, v in audit_results.items() if v.get("result") == "FAIL"]
        attempts_failed.append(failed_checks)
        # 2026-09-22: if a protected internal term slipped in, tell the NEXT
        # attempt exactly which word(s) to avoid, instead of blindly re-rolling
        # and hoping it dodges the same word by chance.
        pt = audit_results.get("protected_terms_check", {})
        if pt.get("result") == "FAIL":
            found = re.findall(r"'([^']+)'", pt.get("reason", ""))
            avoid_terms.extend(t for t in found if t not in avoid_terms)

    all_failed = sorted(set(sum(attempts_failed, [])))
    # 2026-09-22: a KU is only genuinely unusable if it failed for a CONTENT
    # reason (too thin, weak value, etc). If EVERY failure was purely a
    # protected-terms collision, the source material was fine — the wording
    # just needs another try later — so the KU is left as 'unused' rather
    # than permanently discarded. A KU that already has a passing post has
    # simply run out of fresh angles: retire it as 'used'.
    passed_before = db.count_passed_posts_by_ku(primary_ku["product_id"], platform).get(primary_ku["ku_id"], 0) > 0
    only_terms_issue = all_failed == ["protected_terms_check"]
    if passed_before:
        db.mark_kus_used([ku["ku_id"] for ku in ku_group])
        status_note = "This Knowledge Unit has been marked used (it already has a passing post)."
    elif only_terms_issue:
        status_note = ("This Knowledge Unit was left as-is (not discarded) — every attempt only "
                       "tripped the internal-term check, so the material itself is fine; try "
                       "/generate again later.")
    else:
        db.mark_kus_exhausted([ku["ku_id"] for ku in ku_group])
        status_note = "This Knowledge Unit has been marked exhausted — /generate will move to the next one automatically."
    return {
        "error": (
            f"Couldn't produce a passing post after {config.MAX_AUDIT_RETRIES} attempts "
            f"for this Knowledge Unit. Recurring failed checks: {', '.join(all_failed)}. "
            f"{status_note}"
        ),
    }


def refine(content_id: str, product_name: str) -> dict:
    """REFINE button: regenerate, re-audit, return as a NEW VERSION of the
    same post_code (locked rule) — not a new independent post. Same
    never-show-a-failed-post rule as generate_for_platform: retries
    internally up to config.MAX_AUDIT_RETRIES before giving up honestly."""
    old = db.get_content(content_id)
    if not old:
        return {"error": "Original content not found."}

    generator = GENERATORS.get(old["platform"])
    cip = db.get_latest_cip_for_ku(old["ku_id"]) or {}

    attempts_failed = []
    latest_content_id = content_id
    for attempt in range(1, config.MAX_AUDIT_RETRIES + 1):
        avoid_intents = db.get_used_intents(old["ku_id"], old["platform"])
        recent_posts = _anti_repeat_posts(old["product_id"], old["ku_id"], old["platform"])
        content_text, editorial_intent = generator.generate(cip, product_name, avoid_intents, recent_posts, avoid_terms=[])
        new_content_id = db.save_new_version(latest_content_id, content_text, editorial_intent)
        latest_content_id = new_content_id

        audit_status, audit_results = audits.run_audit(
            content_text, product_name, old["product_id"], old["ku_id"],
            core_insight=cip.get("core_insight", ""), platform=old["platform"],
        )
        db.update_audit_result(new_content_id, audit_status, audit_results)
        db.log_ecosystem_use(old["ku_id"], old["platform"], editorial_intent)

        if audit_status == "PASS":
            return {
                "content_id": new_content_id, "post_code": old["post_code"], "platform": old["platform"],
                "content_text": content_text, "editorial_intent": editorial_intent,
                "audit_status": audit_status, "audit_results": audit_results,
                "attempts": attempt,
            }

        failed_checks = [k for k, v in audit_results.items() if v.get("result") == "FAIL"]
        attempts_failed.append(failed_checks)

    return {
        "error": (
            f"Couldn't produce a passing post after {config.MAX_AUDIT_RETRIES} more attempts. "
            f"Recurring failed checks: {', '.join(sorted(set(sum(attempts_failed, []))))}. "
            f"The source material for this Knowledge Unit may genuinely be too thin — "
            f"consider checking the original PDF section it came from."
        ),
    }


def mark_ready_to_publish(content_id: str):
    db.update_content_status(content_id, "ready_to_publish")


def mark_confirmed_published(content_id: str):
    content = db.get_content(content_id)
    db.update_content_status(content_id, "confirmed_published")
    if content:
        db.mark_platform_completed_today(content["platform"])
    return content
