"""Shared fixtures for all router tests."""

from pathlib import Path

import httpx
import pytest

from duggerbot.router.models import Provider
from duggerbot.router.ledger import UsageLedger


PROVIDERS_YAML_CONTENT = """\
providers:
  gemini:
    role: primary
    models:
      - gemini-2.0-flash
    free_tier:
      rpd: 1500
      rpm: 15
      tpm: 1000000
    cost_per_1k_tokens: 0.0
    enabled: true
    health_endpoint: "https://generativelanguage.googleapis.com/v1beta/models"

  groq:
    role: speed
    models:
      - llama-3.1-70b-versatile
    free_tier:
      rpd: 6000
      rpm: 30
    cost_per_1k_tokens: 0.0
    enabled: true
    health_endpoint: "https://api.groq.com/openai/v1/models"

  ollama:
    role: local
    models:
      - phi3.5:3.8b
    cost_per_1k_tokens: 0.0
    enabled: true
    health_endpoint: "http://localhost:11434/api/tags"
    keep_alive: -1

  openrouter:
    role: access
    models:
      - meta-llama/llama-3.1-70b-instruct
    cost_per_1k_tokens: 0.001
    enabled: true
    health_endpoint: "https://openrouter.ai/api/v1/models"

  claude:
    role: reserved
    models:
      - claude-sonnet-4-6
    daily_cap_usd: 0.25
    cost_per_1k_input_tokens: 0.003
    cost_per_1k_output_tokens: 0.015
    enabled: true
    health_endpoint: "https://api.anthropic.com/v1/models"
"""

ROUTING_YAML_CONTENT = """\
routing:
  default_chain:
    - gemini
    - groq
    - ollama
    - openrouter
    - claude

  task_overrides:
    research:
      - gemini
      - openrouter
      - claude
    fast_lookup:
      - groq
      - gemini
      - openrouter
    local_inference:
      - ollama
      - groq
"""


@pytest.fixture
def providers_yaml(tmp_path) -> Path:
    """Write a minimal providers.yaml to tmp_path and return the path."""
    config = tmp_path / "providers.yaml"
    config.write_text(PROVIDERS_YAML_CONTENT)
    return config


@pytest.fixture
def routing_yaml(tmp_path) -> Path:
    """Write a minimal routing.yaml to tmp_path and return the path."""
    config = tmp_path / "routing.yaml"
    config.write_text(ROUTING_YAML_CONTENT)
    return config


@pytest.fixture
def mock_http_client():
    """Return an httpx.AsyncClient backed by httpx.MockTransport."""
    def _make_client(handler):
        transport = httpx.MockTransport(handler)
        return httpx.AsyncClient(transport=transport)
    return _make_client


@pytest.fixture
async def ledger(tmp_path) -> UsageLedger:
    """Initialized UsageLedger backed by a tmp SQLite file."""
    db_path = tmp_path / "test_usage.db"
    l = UsageLedger(db_path)
    await l.initialize()
    return l
