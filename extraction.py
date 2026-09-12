"""
ICOS Knowledge Extraction Engine
PRODUCT -> KNOWLEDGE UNIT -> CANONICAL INSIGHT PACKAGE (CIP)

CHANGED 2026-09-05: extraction now targets a tier-appropriate number of
Knowledge Units (Full OS = deepest/most, Handbook = medium, Codex = fewest) —
using config.TIER_KU_TARGET instead of a fixed 3-8 range for every tier.
"""

import json
import config
from ai_client import get_client


EXTRACTION_PROMPT = """You are extracting proprietary knowledge from a product document for INAYA SOLUTIONS.

STRICT RULES:
- Extract ONLY ideas explicitly present in the text below. Do not add outside knowledge.
- Each Knowledge Unit must be a single, distinct, valuable idea a reader could learn.
- Do not include internal tool names, proprietary process names, or anything that would let
  someone reconstruct the full proprietary system if read publicly later.
- This document is the "{tier}" tier of this product. Identify between {min_ku} and {max_ku}
  distinct Knowledge Units from this text (fewer if the text is genuinely too short/thin to
  support that many without padding).

For each Knowledge Unit, return:
- category: a short label (e.g. "Hidden Pattern", "Common Mistake", "Misconception")
- core_insight: 1-2 sentences, the essential idea
- source_excerpt: the short piece of original text this came from (for traceability)

Return ONLY valid JSON, an array of objects with keys: category, core_insight, source_excerpt.
No other text before or after the JSON.

PRODUCT TEXT:
---
{text}
---
"""

CIP_PROMPT = """You are building a Canonical Insight Package (CIP) from ONE approved Knowledge Unit
(or a combined group of related Knowledge Units), for INAYA SOLUTIONS. The CIP is the complete
intellectual source that EVERY platform (LinkedIn, Blog, Facebook, Instagram, Pinterest, YouTube
Short, YouTube Podcast) will later draw its own selective subset from — so be thorough across
every dimension that genuinely applies, but do NOT invent anything not reasonably implied by the
core insight below.

Different products lean on different dimensions naturally — a decision-making product will surface
strong decision_point and misconception material; a household/operations product will surface
strong operational_problem and hidden_issue material; a workplace-conduct product will surface
strong communication_problem material. Do not force every field to be equally rich. Leave a field
as an empty string "" if it genuinely doesn't apply to this Knowledge Unit — a forced, generic
answer is worse than an honest blank, because a later platform generator may pick that field as
its angle and produce a weak post from thin material.

CORE INSIGHT: {core_insight}
CATEGORY: {category}
SOURCE CONTEXT: {source_excerpt}

Return ONLY valid JSON with these exact keys (all strings):
core_insight, real_life_situation, hidden_issue, overlooked_fact, psychological_dimension,
behavioral_dimension, positive_value, negative_value, common_behaviour, alternative_perspective,
misconception, decision_point, communication_problem, operational_problem, what_if_scenario,
what_if_ignored, practical_insight, reflection, curiosity_bridge

No other text before or after the JSON.
"""


DEDUP_PROMPT = """You are comparing NEWLY extracted candidate Knowledge Units for a product against
Knowledge Units ALREADY STORED for that SAME product from a different tier (e.g. the Codex 6-10 page
version, the Handbook 35-50 page version, or the Full OS 150+ page version). The same product's tiers
share the same core proprietary content at different depths — the same underlying insight very often
reappears reworded, expanded, or condensed across two or three tiers. Your job is to catch that.

A NEW candidate is a DUPLICATE if it expresses the same underlying insight as an EXISTING one, even if
the wording, length, or specific examples differ. A NEW candidate is UNIQUE only if it introduces an
idea not meaningfully covered by anything already stored.

EXISTING INSIGHTS ALREADY STORED FOR THIS PRODUCT:
{existing_list}

NEW CANDIDATE INSIGHTS (numbered from 0):
{new_list}

Return ONLY a valid JSON array of the index numbers (integers) of NEW candidates that are genuinely
UNIQUE and should be kept — e.g. [0, 2, 5]. Exclude any index that duplicates an existing insight OR
duplicates another new candidate you've already decided to keep. If everything is unique, return all
indices. No other text before or after the JSON array.
"""


def extract_knowledge_units(product_text: str, tier: str) -> list:
    """Send product text to the AI, get back a tier-appropriate list of
    distinct Knowledge Units."""
    text = product_text[:15000]
    min_ku, max_ku = config.TIER_KU_TARGET.get(tier, (3, 8))

    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(
            text=text, tier=tier, min_ku=min_ku, max_ku=max_ku
        )}]
    )
    raw = response.content[0].text.strip()
    raw = _strip_code_fences(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def filter_duplicate_kus(new_kus: list, existing_insights: list) -> list:
    """Cross-tier dedup: given newly extracted candidate KUs and every
    core_insight already stored for this product (from any other tier already
    uploaded), return only the candidates that are genuinely new/unique.
    If there are no existing insights yet (first tier ever uploaded for this
    product), everything is unique by definition — skip the AI call entirely."""
    if not existing_insights or not new_kus:
        return new_kus

    existing_list = "\n".join(f"- {insight}" for insight in existing_insights)
    new_list = "\n".join(f"{i}: {ku.get('core_insight', '')}" for i, ku in enumerate(new_kus))

    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": DEDUP_PROMPT.format(
            existing_list=existing_list, new_list=new_list
        )}]
    )
    raw = _strip_code_fences(response.content[0].text.strip())
    try:
        keep_indices = set(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        # If the dedup check itself fails to parse, fail safe by keeping
        # everything rather than silently discarding real content.
        return new_kus

    return [ku for i, ku in enumerate(new_kus) if i in keep_indices]


def build_cip(core_insight: str, category: str, source_excerpt: str) -> dict:
    # NOTE: raised from 1500 -> 3000 when the CIP expanded from 12 to 19 fields
    # (2026-09-12) — same truncation lesson learned the hard way on
    # generator_linkedin.py and audits.py. Do not lower this without checking
    # actual output length first.
    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": CIP_PROMPT.format(
            core_insight=core_insight, category=category, source_excerpt=source_excerpt
        )}]
    )
    raw = response.content[0].text.strip()
    raw = _strip_code_fences(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"core_insight": core_insight}


def _strip_code_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return text.strip()
