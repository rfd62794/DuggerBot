"""Gemini Flash REST client — minimal httpx implementation.

Uses the generativelanguage.googleapis.com REST API directly.
No SDK dependency. Phase 4 builds the full executor and migrates.
"""

import os

import httpx

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.0-flash-lite"


async def call_gemini_flash(prompt: str, api_key: str) -> str:
    """Call Gemini and return the text response.

    Model is configurable via GEMINI_MODEL env var (default: gemini-2.0-flash-lite).

    Raises:
        httpx.HTTPStatusError: on non-2xx response
        KeyError/IndexError: on unexpected response shape
    """
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    url = f"{GEMINI_BASE}/{model}:generateContent"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url,
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
