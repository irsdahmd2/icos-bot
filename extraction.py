"""
ICOS Knowledge Extraction Engine
Implements: PRODUCT -> KNOWLEDGE UNIT -> CANONICAL INSIGHT PACKAGE (CIP)
per the locked blueprint (Section 8A, Phase 2-6).

Uses Claude to do the actual extraction/reasoning work.
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
- Identify 3 to 8 distinct Knowledge Units from this text (fewer if the text is short/thin).

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

CIP_PROMPT = """You are building a Canonical Insight Package (CIP) from ONE approved Knowledge Unit,
for INAYA SOLUTIONS. The CIP is the complete intellectual source that all platform content will
later be adapted from — so be thorough, but do NOT invent anything not reasonably implied by the
core insight below. Leave a field as an empty string "" if it genuinely doesn't apply.

CORE INSIGHT: {core_insight}
CATEGORY: {category}
SOURCE CONTEXT: {source_excerpt}

Return ONLY valid JSON with these exact keys (all strings):
core_insight, real_life_situation, hidden_issue, psychological_dimension, behavioral_dimension,
positive_value, negative_value, common_behaviour, alternative_perspective, practical_insight,
reflection, curiosity_bridge

No other text before or after the JSON.
"""


def extract_knowledge_units(product_text: str) -> list:
    """Send product text to Claude, get back a list of distinct Knowledge Units."""
    # Guard against extremely long documents — trim to a safe size for V1
    text = product_text[:15000]

    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(text=text)}]
    )
    raw = response.content[0].text.strip()
    raw = _strip_code_fences(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def build_cip(core_insight: str, category: str, source_excerpt: str) -> dict:
    """Send one Knowledge Unit to Claude, get back the full CIP dimension palette."""
    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=1500,
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
