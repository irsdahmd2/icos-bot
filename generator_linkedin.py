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
