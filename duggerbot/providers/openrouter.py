"""OpenRouter REST client — async httpx port from PrivyBot.

OpenAI-compatible API at https://openrouter.ai/api/v1/chat/completions.
Completely separate provider — no Google quota dependency.
"""

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def call_openrouter(prompt: str, api_key: str, model: str = "google/gemini-2.0-flash-lite-001") -> str:
    """Call OpenRouter chat completions and return the text response.

    Args:
        prompt: User message text.
        api_key: OPENROUTER_API_KEY from env.
        model: Model ID (default: gemini-2.0-flash-lite via OpenRouter).

    Raises:
        httpx.HTTPStatusError: on non-2xx response
        KeyError/IndexError: on unexpected response shape
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://rfditservices.com",
        "X-Title": "DuggerBot",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
