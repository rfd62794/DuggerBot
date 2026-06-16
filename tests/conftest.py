"""Shared fixtures, mock providers, test config."""

import pytest


@pytest.fixture
def mock_providers_yaml(tmp_path):
    """Provide a temporary providers.yaml for testing."""
    config = tmp_path / "providers.yaml"
    config.write_text("""
providers:
  gemini:
    name: "Gemini Flash"
    tier: "free_first"
    role: "primary_inference"
    base_url: "https://generativelanguage.googleapis.com"
    models: ["gemini-2.0-flash"]
    limits:
      requests_per_day: 1500
      tokens_per_minute: 1000000
      requests_per_minute: 15
    cost_per_1k_tokens: 0.0
    env_key: "GEMINI_API_KEY"

  groq:
    name: "Groq"
    tier: "free"
    role: "speed_tier"
    base_url: "https://api.groq.com/openai/v1"
    models: ["llama-3.1-70b-versatile"]
    limits:
      requests_per_day: 6000
      requests_per_minute: 30
    cost_per_1k_tokens: 0.0
    env_key: "GROQ_API_KEY"
""")
    return config


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables for testing."""
    monkeypatch.setenv("INSTANCE_ROLE", "development")
    monkeypatch.setenv("TOWER_HOST", "100.106.80.49")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "phi3.5:3.8b")
    monkeypatch.setenv("MCP_PORT", "8001")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-token-abc123")
    monkeypatch.setenv("PRESENCE_PORT", "8002")
    monkeypatch.setenv("CLAUDE_DAILY_CAP_USD", "0.25")
