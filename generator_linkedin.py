"""
LinkedIn Generator — LinkedIn Master Format v1.0 (13-stage editorial architecture).

CHANGED 2026-09-05:
- The AI now self-reports which of the 8 editorial angles it chose, on a
  parseable first line. This fixes the bug where editorial_intent was always
  saved as "" and the anti-repetition rule silently did nothing.
- Added the explicit universal Humanisation Rule as its own instruction.
"""

import config
from ai_client import get_client

ANGLES = [
    "situation-led", "contradiction-led", "consequence-led", "observation-led",
    "question-led", "behaviour-led", "hidden-mechanism-led", "perspective-led",
]

PROMPT_TEMPLATE = """You are writing a LinkedIn post for INAYA SOLUTIONS, for the product "{product_name}".

You must follow the LOCKED LinkedIn Master Format exactly. This is the underlying editorial
architecture (NOT visible as headings — it must read as one natural, flowing piece):

1. Recognition-first opening — start inside a real professional problem. Never "Today I want to discuss..."
2. Situation Mirror — concrete, recognizable workplace situation
3. Hidden Problem — what people think is happening vs what's actually happening
4. Why It Happens — relevant psychology/behavior dimension from the CIP below (only if genuinely useful)
5. Reframe — move reader from "I thought it was X" to "maybe the deeper issue is Y"
6. Core Insight — ONE strong central idea, not a list of tips
7. Practical Value — something the reader can notice/apply, WITHOUT revealing the complete system
8. Consequence/What-If — realistic, not fear-mongering
9. Memorable Close — a clear, earned observation
10. Reflection/Conversation — end with a genuine question, NOT "Thoughts?" or "Agree?"
11. Product Curiosity Bridge — natural progression toward "there's a deeper system for this".
    If no product link is available, create general awareness of Inaya Solutions instead.
12. Soft Product CTA — mention ONLY {product_name}, low-pressure, relevant to the problem discussed
13. Editorial angle — choose the STRONGEST one for this specific insight from this exact list:
    {angles}

HUMANISATION RULE (overrides all other style guidance): this must read as if a real, thoughtful
professional wrote it — natural, empathetic, intelligent rhythm. No robotic phrasing, no clichés,
no filler, no formulaic structure. If it could pass for generic AI content with the product name
removed, it has failed.

VOICE: Professional, human, calm, practical, evidence-aware, minimal, operational.

HARD RULES — NEVER:
- Generic motivational content, AI clichés, corporate buzzwords
- "In today's fast-paced world..." or similar openers
- Generic "5 tips" format
- Reveal complete protocols, frameworks, or proprietary mechanisms — only the insight
- Excessive emojis or engagement bait ("Thoughts? Agree? Comment below!")

LENGTH: 750-900 characters for the post text itself (not counting the ANGLE line below).

Avoid repeating these editorial angles if already used for this Knowledge Unit on LinkedIn: {avoid_intents}

CANONICAL INSIGHT PACKAGE (your source material — use only what's relevant, don't force every field):
Core Insight: {core_insight}
Real-life Situation: {real_life_situation}
Hidden Issue: {hidden_issue}
Psychological Dimension: {psychological_dimension}
Behavioral Dimension: {behavioral_dimension}
Common Behaviour: {common_behaviour}
Alternative Perspective: {alternative_perspective}
Practical Insight: {practical_insight}
Reflection: {reflection}
Curiosity Bridge: {curiosity_bridge}

OUTPUT FORMAT (exactly two parts, nothing else):
Line 1: ANGLE: <one angle from the list above, exactly as written>
Then a blank line, then the finished post text only — no preamble, no explanation, no headings.
"""


def generate(cip: dict, product_name: str, avoid_intents: list = None) -> tuple:
    """Returns (content_text, editorial_angle)."""
    avoid_intents = avoid_intents or []
    prompt = PROMPT_TEMPLATE.format(
        product_name=product_name,
        angles=", ".join(ANGLES),
        avoid_intents=", ".join(avoid_intents) if avoid_intents else "none yet",
        core_insight=cip.get("core_insight", ""),
        real_life_situation=cip.get("real_life_situation", ""),
        hidden_issue=cip.get("hidden_issue", ""),
        psychological_dimension=cip.get("psychological_dimension", ""),
        behavioral_dimension=cip.get("behavioral_dimension", ""),
        common_behaviour=cip.get("common_behaviour", ""),
        alternative_perspective=cip.get("alternative_perspective", ""),
        practical_insight=cip.get("practical_insight", ""),
        reflection=cip.get("reflection", ""),
        curiosity_bridge=cip.get("curiosity_bridge", ""),
    )
    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    return _parse_angle_and_text(raw)


def _parse_angle_and_text(raw: str) -> tuple:
    angle = "unspecified"
    text = raw
    if raw.upper().startswith("ANGLE:"):
        lines = raw.split("\n", 1)
        first_line = lines[0]
        angle_candidate = first_line.split(":", 1)[1].strip().lower()
        for a in ANGLES:
            if a in angle_candidate:
                angle = a
                break
        text = lines[1].strip() if len(lines) > 1 else ""
    return text, angle
