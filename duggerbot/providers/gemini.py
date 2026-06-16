"""Gemini Flash REST client — minimal httpx implementation.

Uses the generativelanguage.googleapis.com REST API directly.
No SDK dependency. Phase 4 builds the full executor and migrates.
"""

import httpx

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-2.0-flash:generateContent"
)


async def call_gemini_flash(prompt: str, api_key: str) -> str:
    """Call Gemini 2.0 Flash and return the text response.

    Raises:
        httpx.HTTPStatusError: on non-2xx response
        KeyError/IndexError: on unexpected response shape
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            GEMINI_URL,
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
