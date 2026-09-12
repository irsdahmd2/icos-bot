"""
ICOS Audit Engine — LinkedIn Audit Engine v2.0 (LOCKED, per Irshad's spec document).

Implements the official 12 audit categories from the locked spec, plus three
code-level structural checks that are deterministic rather than AI-judged
(more reliable, and they're facts, not opinions):

CODE-LEVEL (facts, not judgment calls):
  - source_product_identity  : scans for any OTHER product's name in the text
  - structure_check           : 8-14 short paragraphs (locked 2026-09-13 v2.0 rule)
  - hook_length_check         : opening paragraph <= 210 chars (mobile "See more" cutoff)
  - hashtags_check             : 3-5 relevant hashtags present at the end

AI-JUDGED (the 11 remaining official categories, one combined call):
  2. knowledge_unit_integrity
  3. duplication_repetition       (checked against this product's actual past posts)
  4. editorial_drift
  5. linkedin_native_quality
  6. value
  7. human_writing
  8. product_protection
  9. curiosity_and_cta
  10. cross_platform_contamination (checked against actual other-platform posts, when any exist)
  11. ordinary_content_test
  12. novelty_editorial_angle      (checked against this product's actual past posts/angles)

CHANGED 2026-09-13 (v1.0 -> v2.0), to match generator_linkedin.py's v2.0 rewrite:
- structure_check range changed from 6-9 lines to 8-14 short paragraphs.
- Added hook_length_check: new code-level check enforcing the ~210-character mobile
  truncation point found in 2026 LinkedIn engagement research — the single highest-leverage
  lever found across multiple independent studies, more than total post length.
- linkedin_native_quality and human_writing checks now also judge plain-language use and
  whether the core insight is given a specific name/label (the authority mechanism) rather
  than only described in general terms.

CHANGED 2026-09-08: full rewrite against Irshad's actual locked audit spec.
Replaces the earlier ad-hoc 10-check version. Duplication, cross-platform
contamination, and novelty are now REAL checks against real past content
pulled from the database — not just avoided-angle bookkeeping.
"""

import json
import re
import config
import database as db
from ai_client import get_client

MIN_LINES = 8
MAX_LINES = 14
MIN_HASHTAGS = 3
MAX_HASHTAGS = 5
MAX_HOOK_CHARS = 210

AI_JUDGED_CHECKS = [
    "knowledge_unit_integrity", "duplication_repetition", "editorial_drift",
    "linkedin_native_quality", "value", "human_writing", "product_protection",
    "curiosity_and_cta", "cross_platform_contamination", "ordinary_content_test",
    "novelty_editorial_angle",
]

AUDIT_PROMPT = """You are the LinkedIn Audit Engine for INAYA SOLUTIONS — a strict, mandatory
publishing gate. Judge the POST below against these 11 checks. For EACH, answer PASS or FAIL
with a one-sentence reason. Be strict: this is a locked gate, not a formality.

POST TO AUDIT:
---
{content_text}
---

PRODUCT: {product_name}
SOURCE KNOWLEDGE UNIT'S CORE INSIGHT (the post must stay faithful to this, not distort it):
{core_insight}

{recent_posts_block}

{other_platform_block}

CHECKS:
1. knowledge_unit_integrity — the post's central idea remains faithful to the core insight above;
   no invented facts, statistics, studies, or proprietary claims not implied by it.
2. duplication_repetition — compare against the previous posts listed above (if any). FAIL if the
   situation, insight, or conclusion is substantially the same as a previous post, even with
   different wording. Different wording alone does NOT mean different content.
3. editorial_drift — follows the locked LinkedIn Master Format progression (situation established,
   insight lands at the right point, practical value present, natural CTA). FAIL if it reads like a
   generic article, shortened blog, motivational quote, sales ad, or disconnected tips list.
4. linkedin_native_quality — feels deliberately written for LinkedIn: professional relevance,
   scannability, natural paragraph rhythm, credible opening, no unnecessary jargon. Plain,
   concrete words are preferred over long or corporate/consultant vocabulary — precision should
   come from specificity, not from formal-sounding language.
5. value — would this post still be useful if the reader never clicked the product? Genuine
   insight and practical takeaway required; reject empty motivation or obvious statements dressed
   up as profound. The core insight should be given a short, specific name or label (not just
   described in general terms) — that specificity is what signals real domain expertise.
6. human_writing — no AI clichés, corporate buzzwords, "in today's fast-paced world" style
   openers, robotic transitions, forced storytelling, or over-polished unnatural language. Would
   an intelligent human professional genuinely write and publish this?
7. product_protection — reveals the problem/situation/insight but does NOT reveal a complete
   protocol, framework, proprietary matrix, internal architecture, or internal scoring/decision
   mechanism.
8. curiosity_and_cta — progression is value -> recognition -> insight -> reflection -> curiosity
   -> product; the CTA belongs only to "{product_name}", feels like a natural next step, and does
   not mention any other product.
9. cross_platform_contamination — {contamination_instruction}
10. ordinary_content_test — if the INAYA branding were removed, could this be mistaken for generic
    AI-generated LinkedIn content? PASS means NO (it feels original and specific).
11. novelty_editorial_angle — compared to the previous posts above (if any), does this post bring
    a genuinely different situation, perspective, or implication — not just new wording for the
    same underlying insight?

Return ONLY valid JSON:
{{
  "knowledge_unit_integrity": {{"result": "PASS or FAIL", "reason": "..."}},
  "duplication_repetition": {{"result": "PASS or FAIL", "reason": "..."}},
  "editorial_drift": {{"result": "PASS or FAIL", "reason": "..."}},
  "linkedin_native_quality": {{"result": "PASS or FAIL", "reason": "..."}},
  "value": {{"result": "PASS or FAIL", "reason": "..."}},
  "human_writing": {{"result": "PASS or FAIL", "reason": "..."}},
  "product_protection": {{"result": "PASS or FAIL", "reason": "..."}},
  "curiosity_and_cta": {{"result": "PASS or FAIL", "reason": "..."}},
  "cross_platform_contamination": {{"result": "PASS or FAIL", "reason": "..."}},
  "ordinary_content_test": {{"result": "PASS or FAIL", "reason": "..."}},
  "novelty_editorial_angle": {{"result": "PASS or FAIL", "reason": "..."}}
}}
No other text before or after the JSON.
"""


def _source_product_identity_check(content_text: str, other_product_names: list) -> dict:
    """Code-level, deterministic — not an AI judgment call. Scans for any
    OTHER product's name appearing in the text (case-insensitive)."""
    lowered = content_text.lower()
    for name in other_product_names:
        if name and name.lower() in lowered:
            return {"result": "FAIL", "reason": f"Mentions another product: '{name}'."}
    return {"result": "PASS", "reason": "No other product names detected."}


def _structure_check(content_text: str) -> dict:
    """Locked 2026-09-13 v2.0 rule: 8-14 short paragraphs, not counting the
    trailing hashtag line."""
    lines = [l.strip() for l in content_text.split("\n") if l.strip()]
    body_lines = [l for l in lines if not _is_hashtag_line(l)]
    n = len(body_lines)
    if MIN_LINES <= n <= MAX_LINES:
        return {"result": "PASS", "reason": f"{n} paragraphs, within the {MIN_LINES}-{MAX_LINES} range."}
    return {"result": "FAIL", "reason": f"{n} paragraphs — outside the required {MIN_LINES}-{MAX_LINES} range."}


def _hook_length_check(content_text: str) -> dict:
    """Locked 2026-09-13 v2.0 rule: the opening paragraph must work standalone
    under ~210 characters — LinkedIn's actual mobile 'See more' truncation
    point. Research across multiple 2026 studies found this the single
    highest-leverage lever for engagement, more than total post length."""
    lines = [l.strip() for l in content_text.split("\n") if l.strip()]
    if not lines:
        return {"result": "FAIL", "reason": "Post is empty."}
    hook = lines[0]
    n = len(hook)
    if n <= MAX_HOOK_CHARS:
        return {"result": "PASS", "reason": f"Hook is {n} characters, within the {MAX_HOOK_CHARS}-character mobile cutoff."}
    return {"result": "FAIL", "reason": f"Hook is {n} characters — exceeds the {MAX_HOOK_CHARS}-character mobile 'See more' cutoff."}


def _hashtags_check(content_text: str) -> dict:
    hashtags = re.findall(r"#\w+", content_text)
    n = len(hashtags)
    if MIN_HASHTAGS <= n <= MAX_HASHTAGS:
        return {"result": "PASS", "reason": f"{n} hashtags present."}
    return {"result": "FAIL", "reason": f"{n} hashtags found — need {MIN_HASHTAGS}-{MAX_HASHTAGS}."}


def _is_hashtag_line(line: str) -> bool:
    words = line.split()
    if not words:
        return False
    hashtag_words = [w for w in words if w.startswith("#")]
    return len(hashtag_words) >= max(1, len(words) - 1)  # line is mostly/only hashtags


def run_audit(content_text: str, product_name: str, product_id: str, ku_id: str,
              core_insight: str = "", platform: str = "linkedin") -> tuple:
    """Returns (overall_status, results_dict). overall_status is 'PASS' or 'FAIL'."""
    results = {
        "source_product_identity": _source_product_identity_check(
            content_text, db.get_other_product_names(product_id)
        ),
        "structure_check": _structure_check(content_text),
        "hook_length_check": _hook_length_check(content_text),
        "hashtags_check": _hashtags_check(content_text),
    }

    recent_posts = db.get_recent_passed_content(product_id, platform, limit=5)
    other_platform_posts = db.get_recent_content_other_platforms(product_id, ku_id, platform, limit=3)

    if recent_posts:
        excerpts = "\n---\n".join(p["content_text"][:400] for p in recent_posts)
        recent_posts_block = f"THIS PRODUCT'S PREVIOUS PASSING LINKEDIN POSTS:\n---\n{excerpts}\n---"
    else:
        recent_posts_block = "THIS PRODUCT'S PREVIOUS LINKEDIN POSTS: none yet — this is the first."

    if other_platform_posts:
        op_excerpts = "\n---\n".join(
            f"[{p['platform']}] {p['content_text'][:300]}" for p in other_platform_posts
        )
        other_platform_block = (
            f"SAME KNOWLEDGE UNIT ON OTHER PLATFORMS (LinkedIn must not just copy these):\n---\n"
            f"{op_excerpts}\n---"
        )
        contamination_instruction = (
            "compare against the other-platform posts above — LinkedIn must have its own "
            "structure, pacing, wording, and hook, not simply copy them."
        )
    else:
        other_platform_block = "SAME KNOWLEDGE UNIT ON OTHER PLATFORMS: none generated yet."
        contamination_instruction = (
            "no other-platform content exists yet for this Knowledge Unit, so this check "
            "automatically PASSes — there is nothing to have copied from."
        )

    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=2500,
        messages=[{"role": "user", "content": AUDIT_PROMPT.format(
            content_text=content_text, product_name=product_name, core_insight=core_insight or "N/A",
            recent_posts_block=recent_posts_block, other_platform_block=other_platform_block,
            contamination_instruction=contamination_instruction,
        )}]
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```"))

    try:
        ai_results = json.loads(raw)
        results.update(ai_results)
    except json.JSONDecodeError:
        results["audit_parse_error"] = {"result": "FAIL", "reason": "Could not parse audit response."}

    overall = "PASS" if all(v.get("result") == "PASS" for v in results.values()) else "FAIL"
    return overall, results
