"""
Pinterest Generator
Implements the LOCKED Pinterest Master Format v1.0 (blueprint Section 10E).
Selects ONE of 4 structures. Outputs title + description (visual design handled separately/later).
"""

import config
from ai_client import get_client


PROMPT_TEMPLATE = """You are writing a Pinterest Pin (title + description) for INAYA SOLUTIONS,
for the product "{product_name}".

Choose the ONE strongest of these 4 locked structures for this Knowledge Unit:

STRUCTURE A (Problem-Led): Real, searchable problem statement as headline -> why it matters + soft benefit
STRUCTURE B (Insight-Led): Surprising insight/perspective shift as headline -> principle + application
STRUCTURE C (Practical-Outcome): Benefit/outcome statement as headline -> how to achieve it
STRUCTURE D (Observation-Led): Relatable observation as headline -> why this happens + understanding

RULES:
- Headline: 25-35 characters, searchable (real terms people would search), not clickbait
- Description: 150-200 characters, benefit-focused, natural (NOT keyword-stuffed)
- Include 3-5 natural search keywords woven into the description
- Evergreen — must stay relevant for months/years, no time-sensitive language
- NEVER: generic motivational quotes, direct product promotion, keyword stuffing

Avoid repeating this editorial intent if already used for this Knowledge Unit on Pinterest: {avoid_intents}

CANONICAL INSIGHT PACKAGE (source material):
Core Insight: {core_insight}
Real-life Situation: {real_life_situation}
Positive Value: {positive_value}
Alternative Perspective: {alternative_perspective}
Practical Insight: {practical_insight}

Output in exactly this format:
HEADLINE: [headline text]
DESCRIPTION: [description text]
"""


def generate(cip: dict, product_name: str, avoid_intents: list = None) -> str:
    avoid_intents = avoid_intents or []
    prompt = PROMPT_TEMPLATE.format(
        product_name=product_name,
        avoid_intents=", ".join(avoid_intents) if avoid_intents else "none yet",
        core_insight=cip.get("core_insight", ""),
        real_life_situation=cip.get("real_life_situation", ""),
        positive_value=cip.get("positive_value", ""),
        alternative_perspective=cip.get("alternative_perspective", ""),
        practical_insight=cip.get("practical_insight", ""),
    )
    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()
