"""
AI Client — Compatibility Layer
================================
This is the ONLY file that knows which AI provider (Gemini, Claude, etc.) is
actually being used. Every other file in the system (extraction.py, audits.py,
generators/*.py) calls get_client().messages.create(...) exactly like before —
they have NO idea Gemini is behind it.

WHY THIS MATTERS FOR YOU (non-technical, don't want to change things often):
If you ever switch AI providers again in the future, ONLY this one file needs
to be edited. Nothing else in the system changes.

Currently wired to: Google Gemini (free tier, no card required).

UPDATED: Google replaced the old google-generativeai library with a new one
called google-genai, and switched to a new API key format ("Auth keys",
starting with AQ.) that replaces the older AIza... keys. This file now uses
the current library so newly-created Gemini keys work correctly.
"""

import time

from google import genai
from google.genai import types

import config

_client = None

# Transient errors worth retrying automatically instead of surfacing to the
# user — server overload, rate limits, temporary unavailability. NOT retried:
# genuine errors (bad API key, invalid request) since retrying those just
# wastes time and hides a real problem.
_RETRYABLE_STATUS_CODES = {429, 500, 503, 504}
# CHANGED 2026-09-20: was 2 attempts / 1.5s. A real 503 "high demand" spike
# lasted longer than that and killed a whole Handbook upload right after the
# expensive extraction call had already succeeded. Now 5 attempts with growing
# waits (3s, 6s, 12s, 24s = ~45s) before falling back to Groq.
# CHANGED 2026-09-21: the 5 attempts all hit the SAME overloaded model
# (gemini-3.6-flash) and all failed over ~3.5 minutes. Attempts are now spread
# across a chain of different Gemini models (config.GEMINI_FALLBACK_MODELS).
# Each model has its own capacity pool AND its own free daily quota, so this
# also multiplies the free requests available per day.
_PRIMARY_ATTEMPTS = 3      # waits 3s, 6s between them
_FALLBACK_ATTEMPTS = 2     # per fallback model, wait 3s between them
_BASE_DELAY_SECONDS = 3.0
_MAX_DELAY_SECONDS = 24.0

# Groq's free tier counts the prompt PLUS the requested max_tokens against a
# small per-minute budget, so the fallback is only attempted for prompts that
# can realistically fit, and with a capped output size. Large jobs (e.g. a full
# product extraction) are simply not sent to Groq.
_GROQ_MAX_PROMPT_CHARS = 16000
_GROQ_MAX_OUTPUT_TOKENS = 4000


class _ContentBlock:
    """Mimics Anthropic's response.content[0] shape so old code keeps working."""
    def __init__(self, text):
        self.text = text


class _Response:
    """Mimics Anthropic's response shape: response.content[0].text"""
    def __init__(self, text):
        self.content = [_ContentBlock(text)]


def _call_groq_fallback(prompt: str, max_tokens: int = None) -> str:
    """One-shot emergency fallback to Groq's free API (OpenAI-compatible)
    when Gemini is temporarily down. Only called after Gemini has already
    exhausted its own retries. Requires GROQ_API_KEY — if it's not set,
    this function is never reached (see the caller above).

    CHANGED 2026-09-20: the first real use returned "HTTP Error 403:
    Forbidden". Groq sits behind Cloudflare, which commonly blocks Python's
    default urllib User-Agent, so an explicit User-Agent is now sent, and the
    response body of any HTTP error is logged so the true reason is visible in
    Render's logs instead of a bare status code. Output size is capped (see
    _GROQ_MAX_OUTPUT_TOKENS)."""
    import json
    import urllib.error
    import urllib.request

    body = {
        "model": config.GROQ_FALLBACK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(max_tokens or _GROQ_MAX_OUTPUT_TOKENS, _GROQ_MAX_OUTPUT_TOKENS),
    }

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; ICOS-bot/1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            detail = ""
        raise RuntimeError(f"Groq HTTP {e.code}: {detail}") from e
    return data["choices"][0]["message"]["content"]


def _is_retryable(error: Exception) -> bool:
    text = str(error)
    if any(str(code) in text for code in _RETRYABLE_STATUS_CODES):
        return True
    lowered = text.lower()
    return "unavailable" in lowered or "overloaded" in lowered or "rate limit" in lowered


class _Messages:
    def __init__(self, client, model_name):
        self._client = client
        self._model_name = model_name

    def create(self, model=None, max_tokens=None, messages=None, **kwargs):
        """Mimics Anthropic's client.messages.create(...) signature and return shape.
        Automatically retries a few times, with a short growing delay, if Gemini's
        servers are temporarily overloaded — the caller never needs to know this
        happened; it just gets a normal successful response, or a real error only
        after genuinely exhausting retries."""
        prompt = messages[0]["content"]
        gen_config = None
        if max_tokens:
            gen_config = types.GenerateContentConfig(max_output_tokens=max_tokens)

        models = [self._model_name] + [
            m for m in getattr(config, "GEMINI_FALLBACK_MODELS", []) if m != self._model_name
        ]
        last_error = None
        for idx, model_name in enumerate(models):
            attempts = _PRIMARY_ATTEMPTS if idx == 0 else _FALLBACK_ATTEMPTS
            for attempt in range(1, attempts + 1):
                try:
                    response = self._client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=gen_config,
                    )
                    try:
                        text = response.text
                    except Exception:
                        # Gemini sometimes returns no text if it hit a safety filter etc.
                        text = ""
                    if idx > 0:
                        print(f"[ai_client] {self._model_name} unavailable — answered by "
                              f"fallback model {model_name}.", flush=True)
                    return _Response(text)
                except Exception as e:
                    last_error = e
                    retryable = _is_retryable(e)
                    if not retryable and idx == 0:
                        raise  # a real error (bad key, bad request) on the main model: surface it
                    if retryable and attempt < attempts:
                        delay = min(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), _MAX_DELAY_SECONDS)
                        print(f"[ai_client] {model_name} attempt {attempt}/{attempts} failed "
                              f"({str(e)[:60]}...) — retrying in {delay:.0f}s.", flush=True)
                        time.sleep(delay)
                        continue
                    print(f"[ai_client] {model_name} unavailable ({str(e)[:60]}...) — "
                          f"trying the next model." if idx + 1 < len(models) else
                          f"[ai_client] {model_name} unavailable ({str(e)[:60]}...).", flush=True)
                    break  # next model

        # Gemini failed after exhausting its own retries. If this was a genuine
        # overload/unavailable error (not a bad key or malformed request) and a
        # Groq fallback key is configured, try ONE Groq call before giving up —
        # keeps generation/audit moving during a temporary Gemini outage instead
        # of failing the attempt outright. Gemini remains primary; this never
        # runs unless Gemini has already failed.
        if _is_retryable(last_error) and config.GROQ_API_KEY and len(prompt) > _GROQ_MAX_PROMPT_CHARS:
            print(f"[ai_client] Groq fallback skipped: prompt too large "
                  f"({len(prompt)} chars) for Groq's free-tier limits.", flush=True)
        elif _is_retryable(last_error) and config.GROQ_API_KEY:
            try:
                text = _call_groq_fallback(prompt, max_tokens)
                print("[ai_client] Gemini unavailable after retries — used Groq fallback.", flush=True)
                return _Response(text)
            except Exception as fallback_error:
                print(f"[ai_client] Groq fallback also failed: {fallback_error}", flush=True)

        raise last_error


class GeminiCompatClient:
    """Drop-in replacement for anthropic.Anthropic() — same .messages.create() interface."""
    def __init__(self, api_key, model_name):
        underlying_client = genai.Client(api_key=api_key)
        self.messages = _Messages(underlying_client, model_name)


def get_client():
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey and set it as an environment variable."
            )
        _client = GeminiCompatClient(config.GEMINI_API_KEY, config.AI_MODEL)
    return _client


# ---------------------------------------------------------------------------
# ADDITIVE CAPABILITY — image reading (for the Reply Assistant module).
# This does NOT touch the Messages-mimicking interface above, which the main
# content bot (extraction/audits/generators) relies on. Kept fully separate
# so nothing already working can break.
# ---------------------------------------------------------------------------

def generate_with_image(prompt: str, image_bytes: bytes, mime_type: str = "image/png") -> str:
    """
    Send a prompt + an image (e.g. a LinkedIn screenshot) to Gemini and get text back.
    Used only by the Reply Assistant module — the main content bot never calls this.
    """
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    response = client.models.generate_content(
        model=config.AI_MODEL,
        contents=[prompt, image_part],
    )

    try:
        return response.text.strip()
    except Exception:
        return ""
