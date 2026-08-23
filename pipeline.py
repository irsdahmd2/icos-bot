"""
ICOS Pipeline Orchestrator
Wires together: Extraction -> CIP -> Platform Generation -> Audit -> Bundle ready for Telegram.
This is the "conductor" — bot.py calls into this, this calls into extraction/generators/audits.
"""

import config
import database as db
import extraction
import generator_linkedin as linkedin
import generator_blog as blog
import generator_facebook as facebook
import generator_pinterest as pinterest

GENERATORS = {
    "linkedin": linkedin,
    "blog": blog,
    "facebook": facebook,
    "pinterest": pinterest,
}


def process_new_product(product_id, product_name, tier, source_filename, product_text):
    """
    STEP 1: Product uploaded -> extract Knowledge Units -> build CIP for each.
    Returns the list of new ku_ids created.
    """
    db.add_product(product_id, product_name, tier, source_filename)

    raw_units = extraction.extract_knowledge_units(product_text)
    ku_ids = []

    for unit in raw_units:
        ku_id = db.add_knowledge_unit(
            product_id=product_id,
            category=unit.get("category", ""),
            core_insight=unit.get("core_insight", ""),
            raw_source_text=unit.get("source_excerpt", "")
        )
        cip_dimensions = extraction.build_cip(
            core_insight=unit.get("core_insight", ""),
            category=unit.get("category", ""),
            source_excerpt=unit.get("source_excerpt", "")
        )
        db.save_cip(ku_id, cip_dimensions)
        ku_ids.append(ku_id)

    return ku_ids


def generate_daily_bundle(product_id, product_name):
    """
    STEP 2: Pick next unused Knowledge Unit for this product, generate content
    for every active platform, run audits, save results.
    Returns a summary dict ready to format for Telegram.
    """
    ku = db.get_unused_knowledge_unit(product_id)
    if not ku:
        return None

    cip = _get_latest_cip_for_ku(ku["ku_id"])
    if not cip:
        return None

    results = []
    for platform in config.ACTIVE_PLATFORMS:
        generator = GENERATORS[platform]

        avoid_intents = db.get_used_intents(ku["ku_id"], platform)
        content_text = generator.generate(cip, product_name, avoid_intents=avoid_intents)

        content_id = db.save_generated_content(
            ku_id=ku["ku_id"], cip_id=cip["cip_id"], product_id=product_id,
            platform=platform, editorial_intent="", content_text=content_text
        )

        audit_result = audits_run(content_text, product_name)
        audit_status = "PASS" if audit_result["overall_pass"] else "FAIL"
        db.update_audit_result(content_id, audit_status, audit_result)

        results.append({
            "content_id": content_id,
            "platform": platform,
            "content_text": content_text,
            "audit_status": audit_status,
            "audit_result": audit_result,
        })

    return {
        "ku_id": ku["ku_id"],
        "ku_core_insight": ku["core_insight"],
        "product_id": product_id,
        "product_name": product_name,
        "platform_results": results,
    }


def approve_content(content_id):
    db.update_approval(content_id, "approved")
    content = db.get_content(content_id)
    db.log_ecosystem_use(content["ku_id"], content["platform"], content.get("editorial_intent") or "general")


def reject_content(content_id):
    db.update_approval(content_id, "rejected")


def _get_latest_cip_for_ku(ku_id):
    return db.get_latest_cip_for_ku(ku_id)


# Local import alias to avoid circular import at module load time
from audits import run_audit as audits_run
