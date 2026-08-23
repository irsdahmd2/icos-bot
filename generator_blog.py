"""
Blog Generator
Implements the LOCKED Blog 10-Stage Architecture (blueprint Section 10, referenced throughout).
Hook -> Real-Life Recognition -> Hidden Problem -> Why -> Consequence -> Different Perspective
-> Practical Insight -> Reflection -> Product Curiosity Bridge -> Soft CTA
"""

import config
from ai_client import get_client


PROMPT_TEMPLATE = """You are writing a Blog article for INAYA SOLUTIONS, for the product "{product_name}".

Follow the LOCKED Blog 10-Stage Architecture exactly. This is the underlying editorial
architecture — do NOT create 10 visible headings. It must read as one intelligently
constructed article, not a checklist.

01 Hook — specific tension, observation, contradiction, or question. No generic openings.
02 Real-Life Recognition — show behavior/situations readers genuinely recognize
03 Hidden Problem — move beneath the visible problem to what's actually happening
04 Why It Happens — relevant psychological/behavioral/decision dimensions, only where genuinely useful
05 Consequence — realistic consequences or what-if/what-if-not outcomes
06 Different Perspective — a meaningful perspective shift
07 Practical Insight — useful standalone value WITHOUT revealing the complete proprietary system
08 Reflection — return to the original situation with new understanding
09 Product Curiosity Bridge — move from "understanding the problem" to "managing it systematically"
10 Soft CTA — mention ONLY {product_name}, product link at the bottom, feels earned not pushy

VOICE: Human, intelligent, specific, deep, relatable, useful, calm, observational, trustworthy.
NEVER: generic SEO filler, AI clichés, corporate thought-leadership, keyword stuffing,
advertisement disguised as an article.

LENGTH: 800-1200 words.

Avoid repeating this editorial intent if already used for this Knowledge Unit on Blog: {avoid_intents}

CANONICAL INSIGHT PACKAGE (source material — use what's relevant, don't force every field):
Core Insight: {core_insight}
Real-life Situation: {real_life_situation}
Hidden Issue: {hidden_issue}
Psychological Dimension: {psychological_dimension}
Behavioral Dimension: {behavioral_dimension}
Positive Value: {positive_value}
Negative Value: {negative_value}
Common Behaviour: {common_behaviour}
Alternative Perspective: {alternative_perspective}
Practical Insight: {practical_insight}
Reflection: {reflection}
Curiosity Bridge: {curiosity_bridge}

Write the full blog article now, including a headline at the top. Output ONLY the article, nothing else.
"""


def generate(cip: dict, product_name: str, avoid_intents: list = None) -> str:
    avoid_intents = avoid_intents or []
    prompt = PROMPT_TEMPLATE.format(
        product_name=product_name,
        avoid_intents=", ".join(avoid_intents) if avoid_intents else "none yet",
        core_insight=cip.get("core_insight", ""),
        real_life_situation=cip.get("real_life_situation", ""),
        hidden_issue=cip.get("hidden_issue", ""),
        psychological_dimension=cip.get("psychological_dimension", ""),
        behavioral_dimension=cip.get("behavioral_dimension", ""),
        positive_value=cip.get("positive_value", ""),
        negative_value=cip.get("negative_value", ""),
        common_behaviour=cip.get("common_behaviour", ""),
        alternative_perspective=cip.get("alternative_perspective", ""),
        practical_insight=cip.get("practical_insight", ""),
        reflection=cip.get("reflection", ""),
        curiosity_bridge=cip.get("curiosity_bridge", ""),
    )
    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()
