"""OpenRouter API handler — async httpx port from PrivyBot.

OpenAI-compatible API at https://openrouter.ai/api/v1.
Completely separate provider — no Google quota dependency.
Includes model discovery, validation, and chat completions.
"""

import logging
import os
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Fallback chain from PrivyBot model_registry.yaml — confirmed working
FALLBACK_MODELS = [
    "deepseek/deepseek-chat",           # near-free, good reasoning
    "mistralai/mistral-small",           # free, structured output
    "anthropic/claude-haiku-4-5",        # small tier, fast
]

DEFAULT_MODEL = "deepseek/deepseek-chat"

# In-memory cache for free model list
_model_cache: dict = {"models": [], "fetched_at": None}


async def get_free_models(api_key: str) -> list[str]:
    """Fetch free, tool-capable models from OpenRouter. Cached 1h in memory.

    Returns:
        List of model IDs with free pricing and tool-calling support.
    """
    now = datetime.now(timezone.utc)
    fetched_at = _model_cache["fetched_at"]

    if fetched_at is not None and (now - fetched_at).total_seconds() < 3600:
        return _model_cache["models"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://rfditservices.com",
        "X-Title": "DuggerBot",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{OPENROUTER_BASE_URL}/models",
                headers=headers,
                params={"supported_parameters": "tools"},
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])

            models = []
            for model in data:
                pricing = model.get("pricing", {})
                is_free = (
                    pricing.get("prompt") == "0"
                    and pricing.get("completion") == "0"
                )
                has_tools = "tools" in model.get("supported_parameters", [])
                if is_free and has_tools:
                    models.append(model["id"])

            _model_cache["models"] = models
            _model_cache["fetched_at"] = now
            log.info("OpenRouter: discovered %d free tool-capable models", len(models))
    except Exception as e:
        log.error("OpenRouter get_free_models failed: %s", e)

    return _model_cache["models"]


async def validate_model(api_key: str, model_id: str) -> bool:
    """Check if a model ID is currently available on OpenRouter."""
    models = await get_free_models(api_key)
    return model_id in models


async def call_openrouter(prompt: str, api_key: str, model: str | None = None) -> str:
    """Call OpenRouter chat completions and return the text response.

    Args:
        prompt: User message text.
        api_key: OPENROUTER_API_KEY from env.
        model: Model ID. Defaults to OPENROUTER_MODEL env var or deepseek/deepseek-chat.

    Raises:
        httpx.HTTPStatusError: on non-2xx response
        KeyError/IndexError: on unexpected response shape
    """
    if model is None:
        model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

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
        resp = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
