"""
Facebook Generator
Implements the LOCKED Facebook Master Format v1.0 (blueprint Section 10G).
Selects ONE of 4 structures based on the Knowledge Unit's nature.
"""

import config
from ai_client import get_client


PROMPT_TEMPLATE = """You are writing a Facebook post for INAYA SOLUTIONS, for the product "{product_name}".

Choose the ONE strongest of these 4 locked structures for this Knowledge Unit, then write it:

STRUCTURE A (Recognition-Led): Real situation people recognize -> validation + deeper understanding
  -> reflection -> engagement question inviting shared experience
STRUCTURE B (Observation-Led): Specific human behavior observed -> why + consequence -> perspective
  -> engagement question asking their experience
STRUCTURE C (Problem-Solution-Bridge): Real problem -> why it happens (not fully solved) -> hint at
  deeper approach -> engagement question
STRUCTURE D (Question-Led): Genuine question -> explore + deeper layers -> insight -> invite their answer

RULES:
- Warm, conversational tone — like talking to a friend, not a company
- Short paragraphs (2-3 sentences max)
- Simple, jargon-free language
- 200-500 words
- End with ONE genuine engagement question (NOT "Like if you agree" or "Tag someone" — must invite
  real thoughtful response)
- NEVER: corporate language, hard selling, multiple tips/lists, fake personal stories

Avoid repeating this editorial intent if already used for this Knowledge Unit on Facebook: {avoid_intents}

CANONICAL INSIGHT PACKAGE (source material):
Core Insight: {core_insight}
Real-life Situation: {real_life_situation}
Psychological Dimension: {psychological_dimension}
Behavioral Dimension: {behavioral_dimension}
Common Behaviour: {common_behaviour}
Alternative Perspective: {alternative_perspective}
Practical Insight: {practical_insight}

Write the Facebook post now. Output ONLY the post text, nothing else.
"""


def generate(cip: dict, product_name: str, avoid_intents: list = None) -> str:
    avoid_intents = avoid_intents or []
    prompt = PROMPT_TEMPLATE.format(
        product_name=product_name,
        avoid_intents=", ".join(avoid_intents) if avoid_intents else "none yet",
        core_insight=cip.get("core_insight", ""),
        real_life_situation=cip.get("real_life_situation", ""),
        psychological_dimension=cip.get("psychological_dimension", ""),
        behavioral_dimension=cip.get("behavioral_dimension", ""),
        common_behaviour=cip.get("common_behaviour", ""),
        alternative_perspective=cip.get("alternative_perspective", ""),
        practical_insight=cip.get("practical_insight", ""),
    )
    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()
