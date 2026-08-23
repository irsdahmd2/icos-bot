"""
LinkedIn Generator
Implements LINKEDIN MASTER FORMAT v1.0 (blueprint Section 10A) exactly as locked.
13-stage editorial architecture, NOT visible as 13 headings — must read as natural editorial writing.
"""

import config
from ai_client import get_client


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
11. Product Curiosity Bridge — natural progression toward "there's a deeper system for this"
12. Soft Product CTA — mention ONLY {product_name}, low-pressure, relevant to the problem discussed
13. Editorial angle — choose the strongest of: situation-led, contradiction-led, consequence-led,
    observation-led, question-led, behaviour-led, hidden-mechanism-led, or perspective-led

VOICE: Professional, human, calm, practical, evidence-aware, minimal, operational.

HARD RULES — NEVER:
- Generic motivational content, AI clichés, corporate buzzwords
- "In today's fast-paced world..." or similar openers
- Generic "5 tips" format
- Reveal complete protocols, frameworks, or proprietary mechanisms — only the insight
- Excessive emojis or engagement bait ("Thoughts? Agree? Comment below!")

LENGTH: 750-900 characters.

Avoid repeating this editorial intent if already used for this Knowledge Unit on LinkedIn: {avoid_intents}

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

Write the LinkedIn post now. Output ONLY the post text, nothing else — no preamble, no explanation.
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
    return response.content[0].text.strip()
