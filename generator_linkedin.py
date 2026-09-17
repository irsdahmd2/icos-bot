"""
LinkedIn Generator — LinkedIn Master Format v2.2 (LOCKED, per Irshad's spec document).

CORE PRINCIPLE (locked):
ONE KNOWLEDGE UNIT -> CIP -> MASTER EDITORIAL CORE -> LINKEDIN-NATIVE
TRANSFORMATION -> LINKEDIN AUDIT -> MASTER PRODUCT AUDIT -> APPROVAL -> PUBLICATION

CHANGED 2026-09-13 (v1.0 -> v2.0), based on 2026 LinkedIn algorithm/engagement research
(AuthoredUp, MagicPost, van der Blom Algorithm Insights — cross-checked across multiple
independent studies):
- Structure changed from "6-9 dense lines" to 8-14 SHORT paragraphs (1-3 sentences each,
  one idea per paragraph). Same total length, restructured for scannability — dense
  multi-clause paragraphs measurably underperform short ones regardless of total length.
- New HOOK CONSTRAINT: the opening must work standalone in under ~210 characters — the
  actual mobile "See more" truncation point. This is the single highest-leverage lever,
  more than total post length.
- New AUTHORITY MECHANISM: name the hidden pattern with a short, specific label (not just
  describe it) — this is what reads as deep domain expertise, not vocabulary complexity.
- New PLAIN LANGUAGE rule: short, concrete words beat long/corporate ones — research shows
  posts using longer average word length measurably underperform.
- New SAVE-PROMPT line before the CTA — saves are now one of the most heavily-weighted
  algorithm signals, more than likes.
- Hashtags are now explicitly topic-derived per post, not a fixed rotating set.
- Takes recent_posts (this product's last few PASSING LinkedIn posts) so the model actively
  avoids repeating a situation/insight it already used — proactive novelty, not just
  after-the-fact audit rejection.

CHANGED 2026-09-16 (v2.0 -> v2.1), per Irshad's direct request: live posts were running as long
as 16 paragraphs — far past what was intended. Structure tightened from "8-14 short paragraphs"
to a hard ceiling of 8-9 short paragraphs, with explicit guidance on which of the 14 editorial
stages to combine into a shared paragraph so the full architecture still fits without thinning
out the insight. All other v2.0 rules (210-char hook, named authority mechanism, plain language,
save-prompt, money line, etc.) are unchanged.

CHANGED 2026-09-16 (v2.1 -> v2.2), per Irshad's reference examples from his own LinkedIn feed:
blended the terse, broken-line, personally-reflective style of those posts with ICOS's need to
still build curiosity toward the product. Architecture simplified from 14 stages to 6 (hook,
situation, hidden reframe + named insight, practical edge, self-reflective tail, one-line soft
product bridge). Dedicated save-prompt stage dropped. Primary structural constraint changed from
paragraph-count (8-9) to total WORD COUNT (80-140 words), since paragraph count alone doesn't
capture the broken-line rhythm the reference posts use. See audits.py for the matching word-count
check.
"""

import config
from ai_client import get_client

ANGLES = [
    "situation-led", "contradiction-led", "consequence-led", "observation-led",
    "question-led", "behaviour-led", "hidden-mechanism-led", "perspective-led",
]

PROMPT_TEMPLATE = """You are writing a LinkedIn post for INAYA SOLUTIONS, for the product "{product_name}".

This is the LOCKED LinkedIn Master Format v2.2. Follow this exact editorial architecture as the
underlying structure of the post — it must NOT appear as visible numbered headings, it must read
as one natural, flowing piece of writing:

HOOK (incomplete loop) -> SITUATION -> HIDDEN REFRAME + NAMED INSIGHT -> PRACTICAL EDGE ->
SELF-REFLECTIVE TAIL -> SOFT PRODUCT BRIDGE (one line only)

CHANGED 2026-09-16 (v2.1 -> v2.2), per Irshad's reference examples from his own LinkedIn feed:
those posts are terse, broken into short rhythmic lines (a single sentence often split across 2-3
lines), end on a personal reflective question aimed at the READER'S own life — not a generic
engagement prompt — and carry ZERO product CTA. ICOS still needs to build curiosity toward
{product_name}, so v2.2 blends the two: keep the terse broken-line rhythm and the personal
reflective tail, but close with exactly ONE soft bridge line that reframes the reader's own
reflection as something a structured tool could help with — never a separate CTA paragraph, never
a hard pitch. The dedicated SAVE PROMPT stage is dropped entirely — it reads as engagement bait
and Irshad's reference posts don't use one.

1. HOOK (HARD CONSTRAINT) — one short, incomplete-loop line. It must NOT explain itself; it plants
   a statement, observation, or fragment that only makes sense once the reader keeps going (e.g.
   "Someone marked it urgent." / "Two questions. Ten seconds."). Aim for well under 60 characters
   — short enough to feel like a fragment, not a sentence. Must still work standalone under the
   210-character mobile "See more" cutoff. NEVER: "Today I want to discuss...", generic motivation,
   generic company intro, artificial controversy, "In today's fast-paced world...", obvious
   AI-style hooks, or a hook that already explains the whole point.

2. SITUATION — a concrete, recognisable professional situation. Specific behaviour, realistic
   tension, everyday circumstances, believable consequences. Write it as 2-4 SHORT broken lines
   (see BROKEN-LINE TECHNIQUE below), not one dense sentence.

3. HIDDEN REFRAME + NAMED INSIGHT — reveal what actually lies beneath the visible situation (what
   people think is happening -> what's actually happening), and land ONE strong central insight
   with a short, specific, memorable name or label (e.g. "this has a name: X"). This is the money
   line — the most quotable, screenshot-worthy sentence in the post. Use only relevant CIP
   dimensions; never invent facts, statistics, studies, or proprietary knowledge.

4. PRACTICAL EDGE — one quick, genuine practical takeaway the reader can notice/question/test, plus
   what happens if it's ignored vs recognised. Stop well before revealing the complete proprietary
   product solution. 1-2 short broken lines, not a full paragraph.

5. SELF-REFLECTIVE TAIL — end with a genuine, personal question that turns the insight back onto
   the READER'S own life or week — not a generic engagement prompt. NEVER "Agree?" / "Thoughts?" /
   "Comment below!" Model this on Irshad's own reference posts: "What would have been different
   this week if you'd asked both questions before agreeing?" / "Whose emergency ran your week this
   time?" — specific, personal, connected to the exact insight just given.

6. SOFT PRODUCT BRIDGE (exactly ONE line, hard ceiling) — after the reflective question, ONE short
   line that reframes the reader's own reflection as something a structured system exists for —
   naming "{product_name}" lightly, curiosity-driven, never a pitch, never explaining what the
   product does. Think: a door left open, not a sign pointing at it. This replaces the old
   multi-paragraph CURIOSITY BRIDGE + SOFT PRODUCT CTA stages entirely — compress both into this
   single closing line.

7. EDITORIAL ANGLE — choose the STRONGEST angle for this specific insight from exactly this list:
   {angles}
   Do not reuse the same opening/narrative pattern repeatedly.

BROKEN-LINE TECHNIQUE (locked, new in v2.2): this is the core stylistic device of the whole format.
Even a single sentence should often be split across 2-3 short lines at natural clause or breath
boundaries, each on its own line, to create whitespace and rhythm — e.g. a sentence like "They
just feel the pull to help, the discomfort of saying no, and they absorb it" becomes three lines:
"They just feel the pull to help," / "the discomfort of saying no," / "and they absorb it." Do
this deliberately within the SITUATION and PRACTICAL EDGE stages especially. This is a rhythm
device, not a rule to force onto every single line — a one-clause line can stand alone too.

PLAIN LANGUAGE (locked): favor short, concrete, everyday words over long or corporate/consultant
words. "Structural vulnerability" -> "a weak point." "Operational continuity" -> "things keep
running." Precision comes from naming the pattern specifically (see step 6), not from vocabulary
complexity. Longer average word length measurably reduces engagement.

INFORMATION DENSITY (locked): dense in meaning, light in reading effort. Do not optimize merely
for shortness — optimize for meaningful reading.

ELITE CRAFT (locked, applies on top of everything above): write like a world-class LinkedIn
copywriter, not just a compliant format-follower.
- MONEY LINE: include exactly one sentence designed to be the most quotable, screenshot-worthy
  line in the post — almost always the named core insight (step 6), stated as a clean, standalone
  truth someone would want to repeat or save on its own.
- RHYTHM: vary sentence length deliberately. Do not let every paragraph run the same length or
  cadence. A short, blunt line followed by a slightly longer explanatory one reads as confident,
  practiced writing; uniform-length sentences throughout read as generated and flat.
- CONCRETE OVER ABSTRACT: wherever the CIP's real_life_situation is available, use it — specific,
  situational, almost visual detail beats abstract description every time. Prefer "the phone rings
  at 6am and no one else knows the pediatrician's name" over "critical information is often
  centralized in one person."
- NO HEDGING: state the insight directly and confidently. Avoid weak qualifiers ("might," "could
  potentially," "in some cases," "sort of") that dilute authority — say the true thing plainly.
  This is about confident phrasing of the real insight, never about fabricating certainty the
  source material doesn't support.

STRUCTURE (locked 2026-09-16, v2.2 — overrides the previous 8-9 paragraph rule): the primary
constraint is now TOTAL WORD COUNT, not paragraph count — write the post at 80-140 words total
(not counting hashtags). This is a hard band: under 80 reads thin, over 140 reads heavy. Within
that word budget, use the BROKEN-LINE TECHNIQUE above so the post reads as roughly 6-9 short
blocks separated by blank lines, most blocks 1-4 short lines each:
  Block 1 — HOOK: one incomplete-loop line, under ~60 characters ideally.
  Block 2 — SITUATION: 2-4 broken lines.
  Block 3 — HIDDEN REFRAME + NAMED INSIGHT: 1-3 lines — the money line.
  Block 4 — PRACTICAL EDGE: 1-2 broken lines.
  Block 5 — SELF-REFLECTIVE TAIL: 1-2 lines, ending in the personal question.
  Block 6 — SOFT PRODUCT BRIDGE: exactly 1 line.
Despite being lean, the post must still carry real value, not feel thin — this is compression of
language via rhythm and whitespace, not compression of substance: keep the concrete detail, the
named insight, and the real practical value; cut only redundancy and throat-clearing.
Then end with 3-5 hashtags on their own final line, chosen specifically for THIS post's actual
topic and insight (not a fixed recycled set) — always include one INAYA/product-related tag among
them (e.g. #{product_name_tag}), the rest should vary post to post based on what this specific
post is actually about.

VOICE (locked): Professional, Human, Calm, Practical, Evidence-aware, Intellectually useful,
Minimal, Operational. It should feel like an experienced person explaining an important
professional reality — not a company trying to sell something.

REJECT/NEVER (locked anti-patterns): generic motivational content, AI clichés, corporate
buzzwords, fake personal stories, unsupported statistics, unsupported psychological claims,
generic "5/7/10 tips" posts, artificial controversy, engagement bait, excessive emojis, excessive
formatting gimmicks, repetitive structures, generic advice, a blog shortened into LinkedIn form,
content copied from another platform, excessive promotion, obvious AI language, product mechanism
disclosure, a soft bridge line that reads as a pitch rather than a natural closing thought.

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
Then a blank line, then the finished post only (80-140 words, broken-line rhythm, + hashtags as
specified above) — no preamble, no explanation, no headings, no numbered sections.
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
        # RAISED 2026-09-13: real HOS posts were being cut off mid-sentence even
        # at under 500 visible characters — far too short to need 2500 tokens
        # of visible text. AI_MODEL is a reasoning-capable model with no
        # thinking_config set, so it likely spends an unpredictable chunk of
        # the budget on hidden internal reasoning before writing any visible
        # text. Raised with real headroom rather than guessing a small bump.
        max_tokens=8000,
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
