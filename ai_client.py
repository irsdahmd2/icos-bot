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

from google import genai
from google.genai import types

import config

_client = None


class _ContentBlock:
    """Mimics Anthropic's response.content[0] shape so old code keeps working."""
    def __init__(self, text):
        self.text = text


class _Response:
    """Mimics Anthropic's response shape: response.content[0].text"""
    def __init__(self, text):
        self.content = [_ContentBlock(text)]


class _Messages:
    def __init__(self, client, model_name):
        self._client = client
        self._model_name = model_name

    def create(self, model=None, max_tokens=None, messages=None, **kwargs):
        """Mimics Anthropic's client.messages.create(...) signature and return shape."""
        prompt = messages[0]["content"]
        gen_config = None
        if max_tokens:
            gen_config = types.GenerateContentConfig(max_output_tokens=max_tokens)

        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=gen_config,
        )

        try:
            text = response.text
        except Exception:
            # Gemini sometimes returns no text if it hit a safety filter etc.
            text = ""

        return _Response(text)


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
