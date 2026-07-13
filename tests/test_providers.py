"""Provider factory and discovery tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from providers import create_provider, get_provider_options
from providers.custom import CustomProvider
from providers.openai_compat import OpenAIProvider
from providers.anthropic import AnthropicProvider
from providers.codex import get_codex_cached_models, get_codex_model_reasoning_level, get_codex_model_reasoning_levels


class ProviderFactoryTests(unittest.TestCase):
    def test_create_provider_builds_expected_types(self):
        self.assertEqual(type(create_provider({"provider": "ollama", "base_url": "http://localhost:11434"})).__name__, "OllamaProvider")
        self.assertEqual(
            type(create_provider({"provider": "openai", "base_url": "https://api.openai.com/v1", "api_key": "x"})).__name__,
            "OpenAIProvider",
        )
        self.assertEqual(
            type(create_provider({"provider": "anthropic", "base_url": "https://api.anthropic.com/v1", "api_key": "x"})).__name__,
            "AnthropicProvider",
        )
        self.assertEqual(
            type(create_provider({"provider": "llama_cpp", "base_url": "http://localhost:8080/v1", "api_key": ""})).__name__,
            "OpenAIProvider",
        )
        self.assertIsInstance(
            create_provider({"provider": "custom", "custom_backend": "openai", "api_key": "x"}), CustomProvider
        )
        self.assertIsInstance(create_provider({"provider": "codex", "api_key": "x"}), OpenAIProvider)

    def test_create_provider_custom_api_maps_to_custom_provider(self):
        provider = create_provider(
            {
                "provider": "custom_api",
                "custom_backend": "anthropic",
                "custom_base_url": "https://api.anthropic.com/v1",
                "custom_api_key": "x",
                "model": "claude-3-opus-20240229",
            }
        )
        self.assertIsInstance(provider, CustomProvider)
        self.assertEqual(provider.backend, "anthropic")

    def test_create_provider_custom_api_does_not_reuse_legacy_api_key(self):
        provider = create_provider(
            {
                "provider": "custom_api",
                "custom_base_url": "http://localhost:11434/v1",
                "custom_api_key": "",
                "api_key": "legacy-key",
            }
        )
        self.assertIsInstance(provider, CustomProvider)
        self.assertEqual(provider._provider.api_key, "")

    def test_get_provider_options(self):
        providers = get_provider_options()
        self.assertIn("local", providers)
        self.assertIn("custom_api", providers)
        self.assertNotIn("ollama", providers)
        self.assertNotIn("custom", providers)

    def test_create_provider_uses_codex_default_reasoning_level(self):
        with patch("providers.codex.get_codex_model_reasoning_level", return_value="xhigh"):
            provider = create_provider({"provider": "codex", "model": "gpt-5.6-sol", "api_key": "x"})
            self.assertIsInstance(provider, OpenAIProvider)
            self.assertEqual(provider.reasoning_effort, "xhigh")

    def test_create_provider_passes_variant_and_reasoning_to_openai(self):
        provider = create_provider(
            {
                "provider": "openai",
                "model": "gpt-o",
                "api_key": "x",
                "variant": "high",
                "reasoningEffort": "low",
            }
        )
        self.assertEqual(provider.variant, "high")
        self.assertEqual(provider.reasoning_effort, "low")

    def test_create_provider_passes_variant_and_reasoning_to_llama_cpp(self):
        provider = create_provider(
            {
                "provider": "llama_cpp",
                "base_url": "http://localhost:8080/v1",
                "model": "gpt-o",
                "api_key": "x",
                "variant": "reasoning",
                "reasoning_effort": "high",
            }
        )
        self.assertEqual(provider.variant, "reasoning")
        self.assertEqual(provider.reasoning_effort, "high")

    def test_create_provider_passes_variant_and_reasoning_to_custom_openai_backend(self):
        provider = create_provider(
            {
                "provider": "custom",
                "custom_backend": "openai",
                "model": "gpt-o",
                "api_key": "x",
                "variant": "default",
                "reasoningEffort": "medium",
            }
        )
        self.assertIsInstance(provider, CustomProvider)
        self.assertEqual(provider._provider.variant, "default")
        self.assertEqual(provider._provider.reasoning_effort, "medium")


class OpenAIProviderModelTests(unittest.TestCase):
    def test_list_models_extracts_id_array(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": [{"id": "gpt-5"}, {"id": "gpt-4"}]}
        with patch("providers.openai_compat.requests.get", return_value=resp):
            provider = OpenAIProvider(model="gpt-4", api_key="k", base_url="https://example.test")
            self.assertEqual(provider.list_models(), ["gpt-5", "gpt-4"])

    def test_list_models_extracts_model_field_list(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"models": ["alpha", "beta"]}
        with patch("providers.openai_compat.requests.get", return_value=resp):
            provider = OpenAIProvider(model="gpt-4", api_key="k", base_url="https://example.test")
            self.assertEqual(provider.list_models(), ["alpha", "beta"])

    def test_list_models_tries_v1_prefix_if_plain_models_fails(self):
        base = "http://localhost:8080"
        bad = MagicMock()
        bad.status_code = 404
        bad.raise_for_status.side_effect = RuntimeError("404")
        good = MagicMock()
        good.status_code = 200
        good.raise_for_status.return_value = None
        good.json.return_value = {"data": [{"id": "model-a"}]}

        with patch("providers.openai_compat.requests.get", side_effect=[bad, good]) as get:
            provider = OpenAIProvider(model="m", api_key="k", base_url=base, fallback_to_codex_cache=False)
            models = provider.list_models()

        self.assertEqual(models, ["model-a"])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[0].args[0], f"{base}/models")
        self.assertEqual(get.call_args_list[1].args[0], f"{base}/v1/models")

    def test_chat_payload_includes_variant_and_reasoning_effort(self):
        post_resp = MagicMock()
        post_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        post_resp.raise_for_status.return_value = None
        with patch("providers.openai_compat.requests.post", return_value=post_resp) as post:
            provider = OpenAIProvider(
                model="gpt-codex",
                api_key="k",
                base_url="https://example.test",
                variant="reasoning",
                reasoning_effort="high",
            )
            provider.chat([{"role": "user", "content": "x"}])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["variant"], "reasoning")
        self.assertEqual(payload["reasoningEffort"], "high")

    def test_list_models_falls_back_to_codex_cache(self):
        with patch("providers.openai_compat.requests.get", side_effect=RuntimeError("offline")), \
            patch("providers.openai_compat.get_codex_cached_models", return_value=["codex-1", "codex-2"]):
            provider = OpenAIProvider(model="gpt-4", api_key="", base_url="https://example.test")
            self.assertEqual(provider.list_models(), ["codex-1", "codex-2"])

    def test_list_models_without_fallback_returns_empty_on_failure(self):
        with patch("providers.openai_compat.requests.get", side_effect=RuntimeError("offline")), \
            patch("providers.openai_compat.get_codex_cached_models", return_value=["codex-1", "codex-2"]):
            provider = OpenAIProvider(model="gpt-4", api_key="", base_url="https://example.test", fallback_to_codex_cache=False)
            self.assertEqual(provider.list_models(), [])


class CustomProviderTests(unittest.TestCase):
    def test_anthropic_backend_does_not_support_model_listing(self):
        provider = CustomProvider(
            model="claude-3",
            api_key="x",
            base_url="https://api.anthropic.com/v1",
            backend="anthropic",
        )
        self.assertEqual(provider.list_models(), [])
        self.assertIsInstance(provider._provider, AnthropicProvider)


class CodexCacheTests(unittest.TestCase):
    def test_get_codex_cached_models_filters_supported_only(self):
        payload = {
            "models": [
                {"slug": "gpt-1", "supported_in_api": True},
                {"slug": "gpt-2", "supported_in_api": False},
                {"slug": "gpt-3", "supported_in_api": True},
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "models_cache.json"
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("providers.codex.CODEX_MODELS_CACHE", cache_path):
                models = get_codex_cached_models()
                self.assertEqual(models, ["gpt-1", "gpt-3"])

    def test_get_codex_model_reasoning_level(self):
        payload = {
            "models": [
                {"slug": "gpt-1", "default_reasoning_level": "medium", "supported_in_api": True},
                {"slug": "gpt-2", "default_reasoning_level": "high", "supported_in_api": True},
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "models_cache.json"
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("providers.codex.CODEX_MODELS_CACHE", cache_path):
                self.assertEqual(get_codex_model_reasoning_level("gpt-2"), "high")
                self.assertEqual(get_codex_model_reasoning_level("missing"), "")

    def test_get_codex_model_reasoning_levels(self):
        payload = {
            "models": [
                {
                    "slug": "gpt-5.6-sol",
                    "supported_reasoning_levels": [
                        {"effort": "low"},
                        {"effort": "medium"},
                        {"effort": "high"},
                    ],
                },
                {
                    "slug": "gpt-3",
                    "supported_reasoning_levels": ["none", "xhigh"],
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "models_cache.json"
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("providers.codex.CODEX_MODELS_CACHE", cache_path):
                self.assertEqual(get_codex_model_reasoning_levels("gpt-5.6-sol"), ["low", "medium", "high"])
                self.assertEqual(get_codex_model_reasoning_levels("gpt-3"), ["none", "xhigh"])
                self.assertEqual(get_codex_model_reasoning_levels("missing"), [])


if __name__ == "__main__":
    unittest.main()
