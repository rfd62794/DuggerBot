"""Tests for duggerbot.router.registry — Phase 1."""

import pytest

from duggerbot.router.registry import ProviderRegistry


def test_load_valid_yaml(providers_yaml):
    """Registry loads providers_yaml fixture without error."""
    registry = ProviderRegistry(providers_yaml)
    registry.load()
    assert len(registry.list_enabled()) == 5


def test_missing_file_raises(tmp_path):
    """FileNotFoundError when config path does not exist."""
    registry = ProviderRegistry(tmp_path / "nonexistent.yaml")
    with pytest.raises(FileNotFoundError):
        registry.load()


def test_get_known_provider(providers_yaml):
    """get("gemini") returns Provider with correct role."""
    registry = ProviderRegistry(providers_yaml)
    registry.load()
    gemini = registry.get("gemini")
    assert gemini is not None
    assert gemini.role == "primary"
    assert gemini.name == "gemini"


def test_get_unknown_provider(providers_yaml):
    """get("unknown") returns None."""
    registry = ProviderRegistry(providers_yaml)
    registry.load()
    assert registry.get("unknown") is None


def test_list_enabled_excludes_disabled(tmp_path):
    """Provider with enabled=false excluded from list."""
    config = tmp_path / "providers.yaml"
    config.write_text("""\
providers:
  active:
    role: primary
    models: [test-model]
    cost_per_1k_tokens: 0.0
    enabled: true
    health_endpoint: "https://example.com"
  disabled:
    role: speed
    models: [test-model-2]
    cost_per_1k_tokens: 0.0
    enabled: false
    health_endpoint: "https://example.com"
""")
    registry = ProviderRegistry(config)
    registry.load()
    enabled = registry.list_enabled()
    assert len(enabled) == 1
    assert enabled[0].name == "active"


def test_routing_order_matches_file(providers_yaml):
    """get_routing_order() returns names in YAML order."""
    registry = ProviderRegistry(providers_yaml)
    registry.load()
    order = registry.get_routing_order()
    assert order == ["gemini", "groq", "ollama", "openrouter", "claude"]
