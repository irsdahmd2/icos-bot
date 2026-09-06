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
