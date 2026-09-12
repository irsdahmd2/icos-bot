"""
LinkedIn Generator — LinkedIn Master Format v1.0 (LOCKED, per Irshad's spec document).

CORE PRINCIPLE (locked):
ONE KNOWLEDGE UNIT -> CIP -> MASTER EDITORIAL CORE -> LINKEDIN-NATIVE
TRANSFORMATION -> LINKEDIN AUDIT -> MASTER PRODUCT AUDIT -> APPROVAL -> PUBLICATION

CHANGED 2026-09-08:
- Rewritten against Irshad's actual locked LinkedIn Master Format v1.0 document
  (13-stage editorial flow + full anti-pattern list + explicit Product
  Protection may/must-not + Information Density + Voice, verbatim from spec).
- Structure changed from a fixed 750-900 character range to a LINE-based
  structure (locked 2026-09-08): 6-9 short, dense lines/paragraphs following
  Hook -> Body -> Curiosity bridge -> Product, ending with relevant hashtags.
- Takes recent_posts (this product's last few PASSING LinkedIn posts) so the
  model actively avoids repeating a situation/insight it already used —
  proactive novelty, not just after-the-fact audit rejection.
"""

import config
from ai_client import get_client

ANGLES = [
    "situation-led", "contradiction-led", "consequence-led", "observation-led",
    "question-led", "behaviour-led", "hidden-mechanism-led", "perspective-led",
]

PROMPT_TEMPLATE = """You are writing a LinkedIn post for INAYA SOLUTIONS, for the product "{product_name}".

This is the LOCKED LinkedIn Master Format v1.0. Follow this exact editorial architecture as the
underlying structure of the post — it must NOT appear as visible numbered headings, it must read
as one natural, flowing piece of writing:

REAL PROFESSIONAL PROBLEM -> SCROLL-STOPPING RECOGNITION -> SITUATION MIRROR -> HIDDEN TENSION ->
WHY IT HAPPENS -> REFRAME -> CORE INSIGHT -> PRACTICAL APPLICATION -> CONSEQUENCE/WHAT-IF ->
MEMORABLE CLOSE -> REFLECTION/CONVERSATION -> PRODUCT CURIOSITY BRIDGE -> SOFT PRODUCT CTA

1. RECOGNITION-FIRST OPENING — start inside a real professional problem. Entry angles: pain
   recognition, contradiction, unexpected observation, professional question, specific situation,
   consequence, behaviour, hidden mechanism, perspective. The opening must make the reader think
   "that happens" / "I've seen this" / "I've done this" / "that's an interesting problem."
   NEVER: "Today I want to discuss...", generic motivation, generic company intro, artificial
   controversy, "In today's fast-paced world...", obvious AI-style hooks.

2. SITUATION MIRROR — a concrete, recognisable workplace situation. Specific behaviour, realistic
   tension, everyday professional circumstances, human reactions, believable consequences. Avoid
   abstract explanation before the reader understands the situation.

3. HIDDEN PROBLEM — reveal what lies beneath the visible problem. Transition explicitly from
   WHAT PEOPLE THINK IS HAPPENING to WHAT MAY ACTUALLY BE HAPPENING.

4. WHY IT HAPPENS — use only relevant CIP dimensions (psychology, human behaviour, decision
   science, communication, organisational behaviour, operational thinking). Never add research
   merely to sound authoritative. Never invent facts, statistics, studies, or proprietary knowledge.

5. REFRAME — an intellectual turning point: "I thought the problem was X" -> "maybe the deeper
   issue is Y." (visible->hidden, behaviour->consequence, symptom->cause, assumption->alternative,
   immediate->long-term, individual->systemic).

6. CORE INSIGHT — ONE strong central insight, not a collection of generic tips. The reader must be
   able to answer "what did I actually learn?" with one clear answer.

7. PRACTICAL VALUE — something the reader can notice/question/test/recognise/apply. Genuine
   standalone value. Stop before revealing the complete proprietary product solution.

8. CONSEQUENCE/WHAT-IF — if ignored, what may gradually happen; if recognised, what could change.
   Never fear-monger, exaggerate, or make unsupported promises.

9. MEMORABLE CLOSE — a clear professional observation that compresses the central insight. Human
   and earned. No manufactured motivational quotes.

10. REFLECTION/CONVERSATION — end with a genuine question connected to the issue, giving the
    reader something meaningful to consider. NEVER "Agree?" / "Thoughts?" / "Comment below!"

11. PRODUCT CURIOSITY BRIDGE — natural progression: PROBLEM -> UNDERSTANDING -> DEEPER STRUCTURED
    SOLUTION EXISTS -> PRODUCT CURIOSITY. Never abruptly switch from insight to advertising. The
    reader should naturally think "if this problem can be understood this deeply, I wonder what
    the complete product contains."

12. SOFT PRODUCT CTA — mention ONLY "{product_name}", relevant to the problem discussed, explain
    why the reader may want to explore it, low-pressure, never dominates the post. Never mention
    any other product.

13. EDITORIAL ANGLE — choose the STRONGEST angle for this specific insight from exactly this list:
    {angles}
    Do not reuse the same opening/narrative pattern repeatedly.

INFORMATION DENSITY (locked): dense in meaning, light in reading effort. Short paragraphs,
whitespace, clear progression, simple language, deliberate emphasis, bullets only when genuinely
useful. Do not optimize merely for shortness — optimize for meaningful reading.

STRUCTURE (locked 2026-09-08, overrides any earlier character-count rule): write the post as
6 to 9 short, dense lines/paragraphs (each line a distinct beat — hook, situation, insight, value,
close/curiosity as appropriate), structured overall as: HOOK -> BODY -> CURIOSITY BRIDGE TOWARD
{product_name} -> then end with 3-5 relevant hashtags on their own final line (e.g.
#Leadership #WorkplaceCulture #{product_name_tag}).

VOICE (locked): Professional, Human, Calm, Practical, Evidence-aware, Intellectually useful,
Minimal, Operational. It should feel like an experienced person explaining an important
professional reality — not a company trying to sell something.

REJECT/NEVER (locked anti-patterns): generic motivational content, AI clichés, corporate
buzzwords, fake personal stories, unsupported statistics, unsupported psychological claims,
generic "5/7/10 tips" posts, artificial controversy, engagement bait, excessive emojis, excessive
formatting gimmicks, repetitive structures, generic advice, a blog shortened into LinkedIn form,
content copied from another platform, excessive promotion, obvious AI language, product mechanism
disclosure.

PRODUCT PROTECTION (locked) — MAY reveal: problem, situation, behaviour, consequence, observation,
perspective, partial practical insight. MUST NOT reveal: complete protocol, complete framework,
proprietary matrix, internal architecture, complete operating procedure, complete implementation
sequence, internal scoring/decision mechanism. Curiosity must never allow reconstruction of the
product.

ORDINARY CONTENT TEST (mandatory self-check before you finish): could this reasonably have been
generated by a generic LinkedIn AI content tool? If yes, rewrite until the answer is no. Target:
useful + human + original + professionally relevant + intelligent + memorable + platform-native.

Avoid repeating these editorial angles if already used for this Knowledge Unit on LinkedIn: {avoid_intents}

{recent_posts_block}

CANONICAL INSIGHT PACKAGE (your source material — use only what's relevant, don't force every field.
Blank fields mean that dimension genuinely doesn't apply to this Knowledge Unit — do not invent
content for a blank field):
Core Insight: {core_insight}
Real-life Situation: {real_life_situation}
Hidden Issue: {hidden_issue}
Overlooked Fact: {overlooked_fact}
Psychological Dimension: {psychological_dimension}
Behavioral Dimension: {behavioral_dimension}
Common Behaviour: {common_behaviour}
Alternative Perspective: {alternative_perspective}
Misconception: {misconception}
Decision Point: {decision_point}
Communication Problem: {communication_problem}
Operational Problem: {operational_problem}
What-If Scenario: {what_if_scenario}
What Happens If Ignored: {what_if_ignored}
Practical Insight: {practical_insight}
Reflection: {reflection}
Curiosity Bridge: {curiosity_bridge}

OUTPUT FORMAT (exactly two parts, nothing else):
Line 1: ANGLE: <one angle from the list above, exactly as written>
Then a blank line, then the finished post only (6-9 lines + hashtags as specified above) — no
preamble, no explanation, no headings, no numbered sections.
"""


def generate(cip: dict, product_name: str, avoid_intents: list = None, recent_posts: list = None) -> tuple:
    """Returns (content_text, editorial_angle)."""
    avoid_intents = avoid_intents or []
    recent_posts = recent_posts or []

    if recent_posts:
        excerpts = "\n---\n".join(p["content_text"][:400] for p in recent_posts[:3])
        recent_posts_block = (
            "PREVIOUSLY PUBLISHED POSTS FOR THIS PRODUCT ON LINKEDIN (do NOT repeat the same "
            "situation, insight, or angle as these — genuinely new ground only):\n---\n"
            f"{excerpts}\n---"
        )
    else:
        recent_posts_block = ""

    prompt = PROMPT_TEMPLATE.format(
        product_name=product_name,
        product_name_tag=product_name.replace(" ", ""),
        angles=", ".join(ANGLES),
        avoid_intents=", ".join(avoid_intents) if avoid_intents else "none yet",
        recent_posts_block=recent_posts_block,
        core_insight=cip.get("core_insight", ""),
        real_life_situation=cip.get("real_life_situation", ""),
        hidden_issue=cip.get("hidden_issue", ""),
        overlooked_fact=cip.get("overlooked_fact", ""),
        psychological_dimension=cip.get("psychological_dimension", ""),
        behavioral_dimension=cip.get("behavioral_dimension", ""),
        common_behaviour=cip.get("common_behaviour", ""),
        alternative_perspective=cip.get("alternative_perspective", ""),
        misconception=cip.get("misconception", ""),
        decision_point=cip.get("decision_point", ""),
        communication_problem=cip.get("communication_problem", ""),
        operational_problem=cip.get("operational_problem", ""),
        what_if_scenario=cip.get("what_if_scenario", ""),
        what_if_ignored=cip.get("what_if_ignored", ""),
        practical_insight=cip.get("practical_insight", ""),
        reflection=cip.get("reflection", ""),
        curiosity_bridge=cip.get("curiosity_bridge", ""),
    )
    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=2500,
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
