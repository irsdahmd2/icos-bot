"""
ICOS Knowledge Extraction Engine
PRODUCT -> KNOWLEDGE UNIT -> CANONICAL INSIGHT PACKAGE (CIP)

CHANGED 2026-09-05: extraction now targets a tier-appropriate number of
Knowledge Units (Full OS = deepest/most, Handbook = medium, Codex = fewest) —
using config.TIER_KU_TARGET instead of a fixed 3-8 range for every tier.

CHANGED 2026-09-20 (Educational Depth Rule + richness standard + protection):
- DEPTH OVER QUANTITY: related small insights are merged into ONE premium KU.
  config.TIER_KU_TARGET is now only a CEILING (the minimum is no longer pushed
  on the model, which encouraged padding). Extraction stops when only
  repetition remains.
- RICHNESS STANDARD: every KU must carry enough real source material for every
  platform (LinkedIn, blog, Instagram, Facebook, YouTube Short) without any new
  facts being invented. The KU's stored source text (raw_source_text) is no
  longer a model-written "short excerpt": the model only POINTS at the passages
  (first/last words) and this code slices the real text out of the product.
  That guarantees the excerpt is verbatim, keeps the model's output small
  (long excerpts across many KUs risked truncating the JSON), and gives the
  blog and other platforms real depth.
- PROPRIETARY PROTECTION: core_insight/category use plain words. Each KU also
  lists its protected_terms (internal names, acronyms, formulas). They are kept
  out of the CIP (build_cip) and enforced by a code check in audits.py.
- A truncated/damaged JSON reply is now salvaged object-by-object instead of
  silently returning zero KUs.
"""

import json
import re
import config
from ai_client import get_client


EXTRACTION_PROMPT = """You are extracting proprietary knowledge from a product document for INAYA SOLUTIONS.
The knowledge will be used to write public posts (one idea per post, on many different days and
platforms) that give readers a real glimpse of the product's depth, so the right readers become
regular readers and, in time, buyers. Posts teach ideas; the product teaches the system, so the
system itself must stay protected.

WHAT ONE KNOWLEDGE UNIT (KU) IS
- ONE teachable idea: something a reader could learn, recognise themselves in ("that is exactly my
  situation"), and act on, all by itself, in one short post.
- A single section, page, card or tool of the product usually holds SEVERAL separate ideas.
  Extract each one as its own KU. NEVER make one KU per section, tool, card or chapter.
  Example: a weekly-reset section that teaches a fixed meal rotation, an evening wind-down routine
  and a hand-off note is THREE KUs, not one.
- Merge ONLY when several small points are truly the same idea seen from different sides (example:
  "managers interrupt", "employees stop speaking", "meetings go silent", "problems stay hidden" are
  ONE idea: why silent meetings produce poor decisions). Never merge just to make the list shorter.
- Work through the WHOLE document from start to end so every section that teaches something is
  covered. Do not stop early. Real teaching content usually gives one to three KUs per page.
- Stop when only repetition remains. Never pad. Return at most {max_ku} KUs.
  (This document is the "{tier}" tier of the product.)
- Skip: contents pages, navigation, disclaimers, blank forms/worksheets/logs and instructions on how
  to fill them in. A worksheet only counts through the ideas it teaches; the explanations and
  completed examples around it are the supporting passages.

LOOK THROUGH EVERY LENS (as you read each section, ask what each lens reveals; every distinct idea
any lens reveals is its own KU): situation, pain (hidden, emotional, operational, financial, time,
mental load), misconception, behaviour and habit, psychology (fear, ego, trust, motivation),
pattern and early-warning sign, signal, decision and trade-off, communication, mistake (who makes
it), warning and long-term consequence, practical response (what to do, what not to do, first step),
reflection, operational gap (system, process, boundary, continuity), principle or mental model.
{domain_hint}PURPOSE FILTER: keep an idea ONLY if a post built on it would (1) solve one genuine problem or
teach something memorable, (2) be worth saving, and (3) hint that a larger structured system exists
behind it WITHOUT giving that system away. Drop ideas that are obvious, generic or filler.

RICHNESS STANDARD
- Each KU must have enough real material in the text to write a short post, a blog article, a
  carousel, a Facebook post and a short video script WITHOUT inventing any new fact.
- Extract ONLY ideas explicitly present in the text below. No outside knowledge.

PROTECTION
- category and core_insight must be written in plain everyday words. NEVER include the product's
  internal names: framework, tool, card, step or score names, acronyms, formulas, step numbers, page
  structure, or sequence. Describe the idea, not the system.
- protected_terms (ONE list for the whole document): every distinctive internal name, label,
  acronym or formula the product uses, exactly as written in the text (e.g. "Lifeboat Floor Test",
  "DSS"). No ordinary words like "risk" or "decision".

FOR EACH KU RETURN
- category: ONE label from: Situation, Pain, Misconception, Behaviour, Pattern, Signal, Decision,
  Communication, Mistake, Warning, Practical Response, Reflection, Operational, Principle
- core_insight: 1-3 plain sentences stating the complete idea.
- passages: 1 to 3 objects {{"start": "...", "end": "..."}} that point at the text supporting THIS
  KU. "start" = the first 6-10 words of the passage, "end" = the last 6-10 words, both copied
  EXACTLY as written in the text below (do not paraphrase or fix spelling).

Return ONLY valid JSON in exactly this shape, protected_terms FIRST:
{{"protected_terms": ["..."], "kus": [{{"category": "...", "core_insight": "...", "passages": [{{"start": "...", "end": "..."}}]}}]}}
No other text before or after the JSON.

PRODUCT TEXT:
---
{text}
---
"""

CIP_PROMPT = """You are building a Canonical Insight Package (CIP) from ONE approved Knowledge Unit
(or a combined group of related Knowledge Units), for INAYA SOLUTIONS. The CIP is the complete
intellectual source that EVERY platform (LinkedIn, Blog, Facebook, Instagram, Pinterest, YouTube
Short, YouTube Podcast) will later draw its own selective subset from — so be thorough across
every dimension that genuinely applies, but do NOT invent anything not reasonably implied by the
core insight below.

Different products lean on different dimensions naturally — a decision-making product will surface
strong decision_point and misconception material; a household/operations product will surface
strong operational_problem and hidden_issue material; a workplace-conduct product will surface
strong communication_problem material. Do not force every field to be equally rich. Leave a field
as an empty string "" if it genuinely doesn't apply to this Knowledge Unit — a forced, generic
answer is worse than an honest blank, because a later platform generator may pick that field as
its angle and produce a weak post from thin material.

PLAIN-WORDS RULE (proprietary protection): write every field in plain everyday language that
describes the IDEA. Never carry over the product's internal tool, card, step, score or framework
names, acronyms, formulas, step numbers, or page structure from the source context.{protected_line}

CORE INSIGHT: {core_insight}
CATEGORY: {category}
SOURCE CONTEXT: {source_excerpt}

Return ONLY valid JSON with these exact keys (all strings):
core_insight, real_life_situation, hidden_issue, overlooked_fact, psychological_dimension,
behavioral_dimension, positive_value, negative_value, common_behaviour, alternative_perspective,
misconception, decision_point, communication_problem, operational_problem, what_if_scenario,
what_if_ignored, practical_insight, reflection, curiosity_bridge

No other text before or after the JSON.
"""


DEDUP_PROMPT = """You are comparing NEWLY extracted candidate Knowledge Units for a product against
Knowledge Units ALREADY STORED for that SAME product from a different tier (e.g. the Codex 6-10 page
version, the Handbook 35-50 page version, or the Full OS 150+ page version). The same product's tiers
share the same core proprietary content at different depths — the same underlying insight very often
reappears reworded, expanded, or condensed across two or three tiers. Your job is to catch that.

A NEW candidate is a DUPLICATE if it expresses the same underlying insight as an EXISTING one, even if
the wording, length, or specific examples differ. A NEW candidate is UNIQUE only if it introduces an
idea not meaningfully covered by anything already stored.

EXISTING INSIGHTS ALREADY STORED FOR THIS PRODUCT:
{existing_list}

NEW CANDIDATE INSIGHTS (numbered from 0):
{new_list}

Return ONLY a valid JSON array of the index numbers (integers) of NEW candidates that are genuinely
UNIQUE and should be kept — e.g. [0, 2, 5]. Exclude any index that duplicates an existing insight OR
duplicates another new candidate you've already decided to keep. If everything is unique, return all
indices. No other text before or after the JSON array.
"""

# Product-specific topics the model should actively look for (only where the
# text genuinely covers them). Matched loosely on the product name.
_DOMAIN_HINTS = [
    (("household", "hos"),
     "mental load, household continuity, decision fatigue, family communication, emergency "
     "preparedness, information management, caregiver coordination, household routines, financial "
     "organisation, maintenance planning, delegation, parenting logistics, health records, service "
     "provider management, documentation, travel readiness, crisis recovery, household resilience, "
     "habit formation, household mistakes, prevention strategies, behavioural observations, "
     "psychological patterns, operational lessons, real-life scenarios"),
    (("decision", "dos"),
     "uncertainty, risk, trade-offs, probability, decision quality, cognitive bias, second-order "
     "consequences, opportunity cost, long-term thinking, reversibility, regret, decision fatigue"),
    (("workplace", "professional", "wpps"),
     "workplace politics, promotion, authority, trust, accountability, office culture, professional "
     "boundaries, leadership, responsibility drift, conflict, recognition, career growth, performance "
     "reviews, delegation, professional reputation, meetings, email, onboarding, resignation and "
     "burnout signals"),
]


def _domain_hint(product_name: str) -> str:
    name = (product_name or "").lower()
    for keys, topics in _DOMAIN_HINTS:
        if any(k in name for k in keys):
            return ("PRODUCT-SPECIFIC TOPICS to look for (only where the text truly covers them): "
                    + topics + ".\n")
    return ""


# Size limits for the stored source text (raw_source_text). Big enough to give
# a blog article real depth, small enough to keep the CIP prompt light.
MAX_PASSAGE_CHARS = 1800
MAX_EXCERPT_CHARS = 4000
FALLBACK_WINDOW_CHARS = 1200


def extract_knowledge_units(product_text: str, tier: str, product_name: str = "") -> list:
    """Send product text to the AI, get back the Knowledge Units (one teachable
    idea each). Each returned dict has: category, core_insight, source_excerpt
    (verbatim text sliced from the product), protected_terms (the product-wide
    list of internal names, attached to every KU)."""
    text = product_text[:config.EXTRACTION_TEXT_LIMIT]
    # Only the CEILING of the tier range is given to the model.
    _min_ku, max_ku = config.TIER_KU_TARGET.get(tier, (3, 40))

    response = get_client().messages.create(
        model=config.AI_MODEL,
        # RAISED 2026-09-20: 16000 -> 32000. One KU per idea (not per section)
        # can mean 100+ KUs, and the model also spends hidden reasoning tokens
        # from this same budget. The reply stays small because passages are
        # only pointers (see _build_excerpt).
        max_tokens=32000,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(
            text=text, tier=tier, max_ku=max_ku, domain_hint=_domain_hint(product_name)
        )}]
    )
    raw = _strip_code_fences(response.content[0].text.strip())
    items, master_terms = _parse_extraction(raw)
    master_terms = _clean_protected_terms(master_terms)

    collapsed = _collapse(text)
    kus, last_pos = [], 0
    for item in items:
        if not isinstance(item, dict):
            continue
        core_insight = str(item.get("core_insight", "")).strip()
        if not core_insight:
            continue
        excerpt = _build_excerpt(collapsed, item, core_insight)
        if excerpt:
            pos = collapsed.find(excerpt[:60])
            last_pos = max(last_pos, pos)
        terms = _clean_protected_terms(list(master_terms) + list(item.get("protected_terms") or []))
        kus.append({
            "category": str(item.get("category", "")).strip(),
            "core_insight": core_insight,
            "source_excerpt": excerpt,
            "protected_terms": terms,
        })

    # Coverage warning (log only): if the last KU's source sits well before the
    # end of the document, the reply may have been cut short or the model stopped early.
    if kus and collapsed and last_pos >= 0 and last_pos < 0.7 * len(collapsed):
        print(f"[extraction] WARNING: KUs only reach {100 * last_pos // len(collapsed)}% of the "
              f"document ({len(kus)} KUs) — extraction may have stopped early.", flush=True)
    return kus


# ---------- source-excerpt slicing (verbatim, deterministic) ----------

_PAGE_MARKER = re.compile(r"Page \d+ of \d+")


def _collapse(text: str) -> str:
    """Collapse all whitespace (PDF extraction can leave tabs/newlines between
    words) and drop 'Page N of M' markers so passages match reliably."""
    text = _PAGE_MARKER.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _find(haystack: str, needle: str, start: int = 0) -> int:
    needle = _collapse(needle)
    if not needle:
        return -1
    m = re.compile(re.escape(needle), re.IGNORECASE).search(haystack, start)
    return m.start() if m else -1


def _slice_passage(collapsed: str, start_phrase: str, end_phrase: str) -> str:
    s = _find(collapsed, start_phrase)
    if s < 0:
        return ""
    e = _find(collapsed, end_phrase, s)
    if e >= 0:
        stop = e + len(_collapse(end_phrase))
    else:
        stop = s + 900  # end phrase not found: keep a sensible chunk after the start
    passage = collapsed[s:stop]
    if len(passage) > MAX_PASSAGE_CHARS:
        cut = passage[:MAX_PASSAGE_CHARS]
        last_stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        passage = cut[:last_stop + 1] if last_stop > MAX_PASSAGE_CHARS // 2 else cut
    return passage.strip()


_STOP = set("that this with from have they them their there what when which will would could should "
            "about into than then also only more most some such your yours been being were does "
            "doing done make made just like over under before after every each other".split())


def _window_fallback(collapsed: str, query: str) -> str:
    """When the model's passage pointers can't be found in the text, take the
    real text window that best overlaps the KU's own words. Still verbatim,
    never model-written."""
    words = {w for w in re.findall(r"[a-z]{4,}", query.lower()) if w not in _STOP}
    if not words or not collapsed:
        return ""
    lowered = collapsed.lower()
    best_score, best_at = 0, -1
    step = FALLBACK_WINDOW_CHARS // 4
    for i in range(0, max(1, len(collapsed) - FALLBACK_WINDOW_CHARS + step), step):
        window = lowered[i:i + FALLBACK_WINDOW_CHARS]
        score = sum(1 for w in words if w in window)
        if score > best_score:
            best_score, best_at = score, i
    if best_at < 0 or best_score < 3:
        return ""
    window = collapsed[best_at:best_at + FALLBACK_WINDOW_CHARS]
    # Start on a clean boundary instead of mid-word.
    if best_at > 0 and collapsed[best_at - 1] != " ":
        cut = window.find(" ")
        window = window[cut + 1:] if cut >= 0 else window
    return window.strip()


def _build_excerpt(collapsed: str, item: dict, core_insight: str) -> str:
    parts = []
    passages = item.get("passages")
    if isinstance(passages, list):
        for p in passages[:4]:
            if isinstance(p, dict):
                got = _slice_passage(collapsed, str(p.get("start", "")), str(p.get("end", "")))
                if got and got not in parts:
                    parts.append(got)
    if not parts:
        # Legacy key / total miss: try a model-supplied excerpt as a pointer,
        # else fall back to the best-matching real window.
        legacy = str(item.get("source_excerpt", "")).strip()
        if legacy and _find(collapsed, legacy[:80]) >= 0:
            parts.append(_slice_passage(collapsed, legacy[:80], legacy[-80:]))
        if not parts:
            fb = _window_fallback(collapsed, core_insight + " " + str(item.get("category", "")))
            if fb:
                parts.append(fb)
    excerpt = " [...] ".join(p for p in parts if p)
    return excerpt[:MAX_EXCERPT_CHARS]


def _clean_protected_terms(raw_terms) -> list:
    """Keep only distinctive proprietary names: multi-word labels, or short
    ALL-CAPS acronyms. Single ordinary words are dropped so the audit's
    deterministic check can't reject good posts for common words."""
    if not isinstance(raw_terms, list):
        return []
    out, seen = [], set()
    for t in raw_terms:
        t = re.sub(r"\s+", " ", str(t)).strip(" .,:;\"'")
        if len(t) < 3 or len(t) > 60:
            continue
        is_acronym = t.isupper() and t.isalpha() and 2 <= len(t) <= 6
        if len(t.split()) < 2 and not is_acronym:
            continue
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t)
    return out


# ---------- JSON handling ----------

def _decode_objects_after(raw: str, i: int) -> list:
    """Decode consecutive {...} objects starting after a '[' at/after index i;
    stops at the first incomplete one (truncated reply)."""
    decoder = json.JSONDecoder()
    items = []
    i = raw.find("[", i)
    if i < 0:
        return items
    i += 1
    while i < len(raw):
        while i < len(raw) and raw[i] in " \n\r\t,":
            i += 1
        if i >= len(raw) or raw[i] != "{":
            break
        try:
            obj, i = decoder.raw_decode(raw, i)
        except json.JSONDecodeError:
            break
        items.append(obj)
    return items


def _parse_extraction(raw: str) -> tuple:
    """Returns (list_of_ku_dicts, master_protected_terms). Accepts the new
    {"protected_terms": [...], "kus": [...]} shape and the older plain-array
    shape. If the reply was cut off or slightly damaged, salvages every
    complete KU instead of returning nothing."""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            kus = data.get("kus")
            terms = data.get("protected_terms")
            return (kus if isinstance(kus, list) else []), (terms if isinstance(terms, list) else [])
        if isinstance(data, list):
            return data, []
        return [], []
    except json.JSONDecodeError:
        pass

    terms = []
    m = re.search(r'"protected_terms"\s*:\s*(\[)', raw)
    if m:
        try:
            parsed, _ = json.JSONDecoder().raw_decode(raw, m.start(1))
            if isinstance(parsed, list):
                terms = parsed
        except json.JSONDecodeError:
            pass
    k = re.search(r'"kus"\s*:', raw)
    if k:
        return _decode_objects_after(raw, k.end()), terms
    return _decode_objects_after(raw, 0), terms


def filter_duplicate_kus(new_kus: list, existing_insights: list) -> list:
    """Cross-tier AND intra-batch dedup: given newly extracted candidate KUs
    and every core_insight already stored for this product (from any other
    tier already uploaded), return only the candidates that are genuinely
    new/unique — including catching duplicates WITHIN this same batch (e.g.
    two sections of the same document expressing the same underlying idea),
    not just duplicates against previously uploaded tiers. This runs even on
    the very first tier ever uploaded for a product, since a single large
    extraction batch can still contain internal near-duplicates."""
    if not new_kus:
        return new_kus
    if len(new_kus) < 2 and not existing_insights:
        return new_kus  # nothing to compare against either way

    existing_list = (
        "\n".join(f"- {insight}" for insight in existing_insights)
        if existing_insights else "None yet — this is the first tier uploaded for this product."
    )
    new_list = "\n".join(f"{i}: {ku.get('core_insight', '')}" for i, ku in enumerate(new_kus))

    try:
        response = get_client().messages.create(
            model=config.AI_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": DEDUP_PROMPT.format(
                existing_list=existing_list, new_list=new_list
            )}]
        )
    except Exception as e:
        # 2026-09-20: a temporary AI outage here used to throw away a
        # successful (and quota-costly) extraction. For the FIRST tier of a
        # product there is nothing stored to duplicate, so keep the fresh KUs.
        # For a later tier (e.g. Codex after Handbook) duplicate protection
        # matters, so surface the error and let the upload be retried.
        if not existing_insights:
            print(f"[extraction] Duplicate check unavailable ({str(e)[:80]}) — "
                  f"keeping all {len(new_kus)} extracted KUs (first tier).", flush=True)
            return new_kus
        raise
    raw = _strip_code_fences(response.content[0].text.strip())
    try:
        keep_indices = set(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        # If the dedup check itself fails to parse, fail safe by keeping
        # everything rather than silently discarding real content.
        return new_kus

    return [ku for i, ku in enumerate(new_kus) if i in keep_indices]


def build_cip(core_insight: str, category: str, source_excerpt: str, protected_terms: list = None) -> dict:
    # NOTE: raised from 1500 -> 3000 when the CIP expanded from 12 to 19 fields
    # (2026-09-12) — same truncation lesson learned the hard way on
    # generator_linkedin.py and audits.py. Do not lower this without checking
    # actual output length first.
    protected_terms = protected_terms or []
    protected_line = (
        " Specifically, never use any of these terms: " + "; ".join(protected_terms) + "."
        if protected_terms else ""
    )
    response = get_client().messages.create(
        model=config.AI_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": CIP_PROMPT.format(
            core_insight=core_insight, category=category, source_excerpt=source_excerpt,
            protected_line=protected_line,
        )}]
    )
    raw = response.content[0].text.strip()
    raw = _strip_code_fences(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"core_insight": core_insight}


def _strip_code_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return text.strip()
