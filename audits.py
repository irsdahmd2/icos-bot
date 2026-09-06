"""
ICOS Audit Engine
Two kinds of checks, on purpose:
  1. CODE-LEVEL checks — facts, not opinions (length, product name present,
     no other product mentioned). An AI shouldn't "judge" these — code should.
  2. AI-JUDGED checks — style/quality calls that need reading comprehension.

CHANGED 2026-09-05: was 6 checks, now 10 (still short of the full 13-module
spec — Duplication-vs-past-posts and Cross-Platform-Contamination need a
database lookup layer we haven't wired in yet; flagged, not faked).
Added: code-level length check (750-900 chars), Ordinary Content Test,
Curiosity & CTA (split out from genuine_value), explicit Humanisation Audit.
"""

import json
import config
from ai_client import get_client

MIN_LENGTH = 750
MAX_LENGTH = 900

AUDIT_PROMPT = """You are a strict content auditor for INAYA SOLUTIONS. Judge the LinkedIn post
below against these checks. For EACH check, answer PASS or FAIL with a one-sentence reason.

POST:
---
{content_text}
---

PRODUCT THIS POST MAY REFERENCE: {product_name}

CHECKS:
1. product_isolation — mentions ONLY "{product_name}", never any other product name
2. no_proprietary_leak — does NOT reveal a complete protocol/framework/internal mechanism
3. human_quality — reads like a real professional wrote it, not an AI template
4. genuine_value — contains one real, useful insight (not vague platitudes)
