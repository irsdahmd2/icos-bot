"""
ICOS Audit Engine
Runs the locked mandatory checks before any content reaches Telegram for approval.
V1 implements the checks that can be reliably automated with an LLM judge; the full
12-14 point audits per platform (from the blueprint) are the target for later refinement —
this is the working core that catches the most important failures now.
"""

import json
import config
from ai_client import get_client


AUDIT_PROMPT = """You are auditing content generated for INAYA SOLUTIONS before it can be published.
Be strict. This is a quality gate, not a formality.

CONTENT TO AUDIT:
---
{content}
---

PRODUCT THIS SHOULD BE ABOUT: {product_name}

Check ALL of the following and answer true/false for each:

1. product_isolation: Does the content stay focused on ONLY {product_name}, with no mention of
   any other product or confused product identity?
2. no_proprietary_leak: Does it AVOID revealing a complete protocol, framework, internal matrix,
   or enough detail that someone could reconstruct the full proprietary system? (It's fine and
   expected to reveal the insight/problem/perspective — just not the complete system.)
3. human_quality: Does it read like an intelligent human wrote it — NOT generic AI clichés,
   corporate buzzwords, "In today's fast-paced world" style openers, or robotic phrasing?
4. genuine_value: Does it teach something genuinely useful, not just generic/obvious advice or
   empty motivation?
5. not_generic_ai: Could this be mistaken for generic AI-generated content with the product name
   removed? Answer false if it feels intelligent/specific/original, true if it feels generic.
   (true here is a FAIL condition — flag it as a problem)
6. appropriate_cta: If there's a product mention/CTA, is it soft and earned rather than
   pushy/aggressive ("BUY NOW", "Click here now", etc.)?

Return ONLY valid JSON in this exact format, no other text:
{{
  "product_isolation": true/false,
  "no_proprietary_leak": true/false,
  "human_quality": true/false,
  "genuine_value": true/false,
  "not_generic_ai": true/false,
  "appropriate_cta": true/false,
  "overall_pass": true/false,
  "failure_reasons": ["list any specific reasons for failure, empty list if all passed"]
}}
"""


def run_audit(content_text: str, product_name: str) -> dict:
    """Returns dict with per-check results, overall_pass, and failure_reasons."""
    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": AUDIT_PROMPT.format(
            content=content_text, product_name=product_name
        )}]
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```"))

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fail safe: if the audit itself breaks, don't let content through silently
        result = {
            "product_isolation": False, "no_proprietary_leak": False,
            "human_quality": False, "genuine_value": False,
            "not_generic_ai": False, "appropriate_cta": False,
            "overall_pass": False,
            "failure_reasons": ["Audit engine could not parse a result — treated as fail for safety."]
        }

    # Compute overall_pass ourselves too, don't fully trust the model's own summary field
    checks = ["product_isolation", "no_proprietary_leak", "human_quality",
              "genuine_value", "not_generic_ai", "appropriate_cta"]
    all_pass = all(result.get(k, False) for k in checks)
    result["overall_pass"] = all_pass

    return result
