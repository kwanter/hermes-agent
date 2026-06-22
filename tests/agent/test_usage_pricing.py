from types import SimpleNamespace

from agent.usage_pricing import (
    CanonicalUsage,
    estimate_usage_cost,
    get_pricing_entry,
    normalize_usage,
)


def test_normalize_usage_anthropic_keeps_cache_buckets_separate():
    usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=500,
        cache_read_input_tokens=2000,
        cache_creation_input_tokens=400,
    )

    normalized = normalize_usage(usage, provider="anthropic", api_mode="anthropic_messages")

    assert normalized.input_tokens == 1000
    assert normalized.output_tokens == 500
    assert normalized.cache_read_tokens == 2000
    assert normalized.cache_write_tokens == 400
    assert normalized.prompt_tokens == 3400


def test_normalize_usage_openai_subtracts_cached_prompt_tokens():
    usage = SimpleNamespace(
        prompt_tokens=3000,
        completion_tokens=700,
        prompt_tokens_details=SimpleNamespace(cached_tokens=1800),
    )

    normalized = normalize_usage(usage, provider="openai", api_mode="chat_completions")

    assert normalized.input_tokens == 1200
    assert normalized.cache_read_tokens == 1800
    assert normalized.output_tokens == 700


def test_normalize_usage_openai_reads_top_level_anthropic_cache_fields():
    """Some OpenAI-compatible proxies (OpenRouter, Cline) expose
    Anthropic-style cache token counts at the top level of the usage object when
    routing Claude models, instead of nesting them in prompt_tokens_details.

    Regression guard for the bug fixed in cline/cline#10266 — before this fix,
    the chat-completions branch of normalize_usage() only read
    prompt_tokens_details.cache_write_tokens and completely missed the
    cache_creation_input_tokens case, so cache writes showed as 0 and reflected
    inputTokens were overstated by the cache-write amount.
    """
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=200,
        prompt_tokens_details=SimpleNamespace(cached_tokens=500),
        cache_creation_input_tokens=300,
    )

    normalized = normalize_usage(usage, provider="openrouter", api_mode="chat_completions")

    # Expected: cache read from prompt_tokens_details.cached_tokens (preferred),
    # cache write from top-level cache_creation_input_tokens (fallback).
    assert normalized.cache_read_tokens == 500
    assert normalized.cache_write_tokens == 300
    # input_tokens = prompt_total - cache_read - cache_write = 1000 - 500 - 300 = 200
    assert normalized.input_tokens == 200
    assert normalized.output_tokens == 200


def test_normalize_usage_openai_reads_top_level_cache_read_when_details_missing():
    """Some proxies expose only top-level Anthropic-style fields with no
    prompt_tokens_details object. Regression guard for cline/cline#10266.
    """
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=200,
        cache_read_input_tokens=500,
        cache_creation_input_tokens=300,
    )

    normalized = normalize_usage(usage, provider="openrouter", api_mode="chat_completions")

    assert normalized.cache_read_tokens == 500
    assert normalized.cache_write_tokens == 300
    assert normalized.input_tokens == 200


def test_normalize_usage_openai_prefers_prompt_tokens_details_over_top_level():
    """When both prompt_tokens_details and top-level Anthropic fields are
    present, we prefer the OpenAI-standard nested fields. Top-level Anthropic
    fields are only a fallback when the nested ones are absent/zero.
    """
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=200,
        prompt_tokens_details=SimpleNamespace(cached_tokens=600, cache_write_tokens=150),
        # Intentionally different values — proving we ignore these when details exist.
        cache_read_input_tokens=999,
        cache_creation_input_tokens=999,
    )

    normalized = normalize_usage(usage, provider="openrouter", api_mode="chat_completions")

    assert normalized.cache_read_tokens == 600
    assert normalized.cache_write_tokens == 150


def test_openrouter_models_api_pricing_is_converted_from_per_token_to_per_million(monkeypatch):
    monkeypatch.setattr(
        "agent.usage_pricing.fetch_model_metadata",
        lambda: {
            "anthropic/claude-opus-4.6": {
                "pricing": {
                    "prompt": "0.000005",
                    "completion": "0.000025",
                    "input_cache_read": "0.0000005",
                    "input_cache_write": "0.00000625",
                }
            }
        },
    )

    entry = get_pricing_entry(
        "anthropic/claude-opus-4.6",
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
    )

    assert float(entry.input_cost_per_million) == 5.0
    assert float(entry.output_cost_per_million) == 25.0
    assert float(entry.cache_read_cost_per_million) == 0.5
    assert float(entry.cache_write_cost_per_million) == 6.25


def test_estimate_usage_cost_marks_subscription_routes_included():
    result = estimate_usage_cost(
        "gpt-5.3-codex",
        CanonicalUsage(input_tokens=1000, output_tokens=500),
        provider="openai-codex",
        base_url="https://chatgpt.com/backend-api/codex",
    )

    assert result.status == "included"
    assert float(result.amount_usd) == 0.0


def test_estimate_usage_cost_refuses_cache_pricing_without_official_cache_rate(monkeypatch):
    monkeypatch.setattr(
        "agent.usage_pricing.fetch_model_metadata",
        lambda: {
            "google/gemini-2.5-pro": {
                "pricing": {
                    "prompt": "0.00000125",
                    "completion": "0.00001",
                }
            }
        },
    )

    result = estimate_usage_cost(
        "google/gemini-2.5-pro",
        CanonicalUsage(input_tokens=1000, output_tokens=500, cache_read_tokens=100),
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
    )

    assert result.status == "unknown"


def test_custom_endpoint_models_api_pricing_is_supported(monkeypatch):
    monkeypatch.setattr(
        "agent.usage_pricing.fetch_endpoint_model_metadata",
        lambda base_url, api_key=None: {
            "zai-org/GLM-5-TEE": {
                "pricing": {
                    "prompt": "0.0000005",
                    "completion": "0.000002",
                }
            }
        },
    )

    entry = get_pricing_entry(
        "zai-org/GLM-5-TEE",
        provider="custom",
        base_url="https://llm.chutes.ai/v1",
        api_key="test-key",
    )

    assert float(entry.input_cost_per_million) == 0.5
    assert float(entry.output_cost_per_million) == 2.0


def test_nous_portal_pricing_preserves_vendor_prefixed_model_ids(monkeypatch):
    seen = {}

    def _fake_fetch_endpoint_model_metadata(base_url, api_key=None):
        seen["base_url"] = base_url
        return {
            "openai/gpt-5.5-pro": {
                "pricing": {
                    "prompt": "0.000025",
                    "completion": "0.000125",
                }
            }
        }

    monkeypatch.setattr(
        "agent.usage_pricing.fetch_endpoint_model_metadata",
        _fake_fetch_endpoint_model_metadata,
    )

    entry = get_pricing_entry("openai/gpt-5.5-pro", provider="nous")

    assert seen["base_url"] == "https://inference-api.nousresearch.com/v1"
    assert float(entry.input_cost_per_million) == 25.0
    assert float(entry.output_cost_per_million) == 125.0


def test_deepseek_v4_pro_pricing_entry_exists():
    """Regression test: deepseek-v4-pro must have a pricing entry.

    Before this fix, deepseek-v4-pro sessions showed as unknown cost
    in hermes insights because the _OFFICIAL_DOCS_PRICING table had no
    entry for that model.  See #24218.
    """
    entry = get_pricing_entry(
        "deepseek-v4-pro",
        provider="deepseek",
    )

    assert entry is not None
    assert entry.input_cost_per_million is not None
    assert entry.output_cost_per_million is not None
    assert float(entry.input_cost_per_million) == 1.74
    assert float(entry.output_cost_per_million) == 3.48
    assert float(entry.cache_read_cost_per_million) == 0.0145


def test_deepseek_v4_pro_estimate_usage_cost():
    """Ensure deepseek-v4-pro sessions get a dollar estimate, not unknown."""
    result = estimate_usage_cost(
        "deepseek-v4-pro",
        CanonicalUsage(input_tokens=1000000, output_tokens=500000),
        provider="deepseek",
    )

    assert result.status == "estimated"
    assert result.amount_usd is not None
    # 1M input × $1.74/M + 500K output × $3.48/M = $1.74 + $1.74 = $3.48
    assert float(result.amount_usd) == 3.48


def test_bedrock_claude_rows_all_carry_cache_pricing():
    """Invariant: every Bedrock Claude pricing row must carry cache-read AND
    cache-write rates, otherwise a cached session prices as ``unknown``.

    Bedrock Claude routes through the AnthropicBedrock SDK and injects
    cache_control, so cached tokens are always reported — the pricing layer
    must be able to value them.  See #50295.
    """
    from agent.usage_pricing import _OFFICIAL_DOCS_PRICING

    claude_rows = [
        (prov, model)
        for (prov, model) in _OFFICIAL_DOCS_PRICING
        if prov == "bedrock" and "claude" in model
    ]
    assert claude_rows, "expected at least one bedrock Claude pricing row"
    for key in claude_rows:
        entry = _OFFICIAL_DOCS_PRICING[key]
        assert entry.input_cost_per_million is not None, key
        assert entry.cache_read_cost_per_million is not None, key
        assert entry.cache_write_cost_per_million is not None, key
        # Cache reads are cheaper than fresh input; cache writes cost more.
        assert entry.cache_read_cost_per_million < entry.input_cost_per_million, key
        assert entry.cache_write_cost_per_million > entry.input_cost_per_million, key


def test_bedrock_cross_region_profile_prefix_resolves_to_pricing():
    """Cross-region inference profiles (us./global./eu. prefixes) must resolve
    to the same pricing entry as the bare foundation-model id.  Without prefix
    normalization, ``us.anthropic.claude-*`` sessions price as unknown.
    """
    bedrock_url = "https://bedrock-runtime.us-east-1.amazonaws.com"
    bare = get_pricing_entry(
        "anthropic.claude-sonnet-4-5", provider="bedrock", base_url=bedrock_url
    )
    assert bare is not None
    for prefix in ("us.", "global.", "eu."):
        scoped = get_pricing_entry(
            f"{prefix}anthropic.claude-sonnet-4-5",
            provider="bedrock",
            base_url=bedrock_url,
        )
        assert scoped is not None, prefix
        assert scoped.input_cost_per_million == bare.input_cost_per_million
        assert scoped.cache_read_cost_per_million == bare.cache_read_cost_per_million


def test_bedrock_claude_cached_session_estimates_cost_not_unknown():
    """A Bedrock Claude session with cache hits must produce a dollar estimate,
    not ``unknown`` — the user-visible symptom in #50295.
    """
    bedrock_url = "https://bedrock-runtime.us-east-1.amazonaws.com"
    usage = SimpleNamespace(
        input_tokens=55,
        output_tokens=7113,
        cache_read_input_tokens=1369379,
        cache_creation_input_tokens=42135,
    )
    canonical = normalize_usage(usage, provider="bedrock", api_mode="anthropic_messages")
    assert canonical.cache_read_tokens == 1369379
    assert canonical.cache_write_tokens == 42135

    result = estimate_usage_cost(
        "us.anthropic.claude-opus-4-6",
        canonical,
        provider="bedrock",
        base_url=bedrock_url,
    )
    assert result.status == "estimated"
    assert result.amount_usd is not None


# ── chunk 2: GLM, Kimi, Qwen, DashScope pricing entries ────────────────
# Verified against each vendor's published pricing page on 2026-06-22.
# Regression scope: any session on these providers must produce a dollar
# estimate, not ``unknown``.


def test_z_ai_glm_5_pricing_entry_exists():
    """z-ai/glm-5 must have a pricing entry with cache read support."""
    entry = get_pricing_entry("glm-5", provider="z-ai")
    assert entry is not None
    assert entry.input_cost_per_million is not None
    assert entry.output_cost_per_million is not None
    assert entry.cache_read_cost_per_million is not None
    assert float(entry.input_cost_per_million) == 1.00
    assert float(entry.output_cost_per_million) == 3.20
    assert float(entry.cache_read_cost_per_million) == 0.20


def test_z_ai_glm_provider_aliases_resolve_to_pricing():
    """Provider aliases ``zai``, ``zhipu``, ``glm`` and the ``z.ai`` base
    URL must all resolve to the same official_docs_snapshot entry, otherwise
    user configurations that spell the provider differently will silently
    fall through to ``unknown``.
    """
    for alias in ("zai", "zhipu", "glm"):
        entry = get_pricing_entry("glm-5", provider=alias)
        assert entry is not None, f"alias {alias!r} should resolve"
        assert entry.input_cost_per_million is not None
    entry = get_pricing_entry("glm-5", base_url="https://api.z.ai/v1")
    assert entry is not None
    assert entry.input_cost_per_million is not None


def test_z_ai_glm_4_5_air_cached_session_estimates_cost_not_unknown():
    """Cached sessions on a model with an official cache rate must not
    be priced as ``unknown``. Regression covers the cache-write arm of
    the cost calculator: if cache_read is present but cache_write is None
    (which is the GLM case), the cost block must still produce a number.
    """
    result = estimate_usage_cost(
        "glm-4.5-air",
        CanonicalUsage(input_tokens=1_000_000, output_tokens=500_000, cache_read_tokens=200_000),
        provider="z-ai",
    )
    assert result.status == "estimated"
    assert result.amount_usd is not None
    # 1M * $0.20/M input + 500K * $1.10/M output + 200K * $0.03/M cache
    # = 0.20 + 0.55 + 0.006 = 0.756
    assert float(result.amount_usd) == 0.756


def test_moonshot_kimi_k2_6_pricing_entry_exists():
    """moonshot/kimi-k2.6 must have a pricing entry with cache read support."""
    entry = get_pricing_entry("kimi-k2.6", provider="moonshot")
    assert entry is not None
    assert entry.input_cost_per_million is not None
    assert entry.output_cost_per_million is not None
    assert entry.cache_read_cost_per_million is not None
    assert float(entry.input_cost_per_million) == 0.96
    assert float(entry.output_cost_per_million) == 3.99
    assert float(entry.cache_read_cost_per_million) == 0.16


def test_moonshot_kimi_provider_aliases_resolve_to_pricing():
    """Provider alias ``kimi`` and the kimi.com base URL must resolve to
    the moonshot pricing entry, otherwise user configs that say
    ``provider: kimi`` will silently fall through to ``unknown``.
    """
    entry = get_pricing_entry("kimi-k2.5", provider="kimi")
    assert entry is not None
    assert entry.input_cost_per_million is not None
    entry = get_pricing_entry("kimi-k2.5", base_url="https://api.kimi.com/v1")
    assert entry is not None
    assert entry.input_cost_per_million is not None


def test_moonshot_kimi_k2_5_estimate_usage_cost():
    """kimi-k2.5 sessions should produce a dollar estimate at the
    published rate, not ``unknown``.
    """
    result = estimate_usage_cost(
        "kimi-k2.5",
        CanonicalUsage(input_tokens=1_000_000, output_tokens=500_000),
        provider="moonshot",
    )
    assert result.status == "estimated"
    assert result.amount_usd is not None
    # 1M * $0.59/M + 500K * $3.10/M = 0.59 + 1.55 = 2.14
    assert float(result.amount_usd) == 2.14


def test_qwen_qwen3_max_pricing_entry_exists():
    """qwen/qwen3-max must have a pricing entry at the published USD rate.
    International Model Studio pricing is already in USD, so no FX path.
    """
    entry = get_pricing_entry("qwen3-max", provider="qwen")
    assert entry is not None
    assert entry.input_cost_per_million is not None
    assert entry.output_cost_per_million is not None
    assert float(entry.input_cost_per_million) == 1.20
    assert float(entry.output_cost_per_million) == 6.00


def test_qwen_provider_aliases_resolve_to_pricing():
    """Provider aliases ``alibaba``, ``bailian``, ``model-studio`` and the
    alibabacloud.com base URL must resolve to the qwen pricing entry.
    """
    for alias in ("alibaba", "bailian", "model-studio"):
        entry = get_pricing_entry("qwen3.5-plus", provider=alias)
        assert entry is not None, f"alias {alias!r} should resolve"
        assert entry.input_cost_per_million is not None
    entry = get_pricing_entry("qwen3.5-plus", base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    assert entry is not None
    assert entry.input_cost_per_million is not None


def test_qwen_qwen3_5_flash_estimate_usage_cost():
    """qwen3.5-flash is the cheapest tier. Sanity-check the math at the
    published rate so a future copy-paste typo on the output column
    is caught.
    """
    result = estimate_usage_cost(
        "qwen3.5-flash",
        CanonicalUsage(input_tokens=1_000_000, output_tokens=1_000_000),
        provider="qwen",
    )
    assert result.status == "estimated"
    assert result.amount_usd is not None
    # 1M * $0.10/M + 1M * $0.40/M = 0.50
    assert float(result.amount_usd) == 0.50


def test_dashscope_qwen3_max_pricing_entry_exists():
    """dashscope/qwen3-max must have a pricing entry. The DashScope route
    is separate from the qwen route so the China region can disambiguate
    pricing when it diverges from the international Model Studio rate.
    """
    entry = get_pricing_entry("qwen3-max", provider="dashscope")
    assert entry is not None
    assert entry.input_cost_per_million is not None
    assert entry.output_cost_per_million is not None
    assert float(entry.input_cost_per_million) == 1.20
    assert float(entry.output_cost_per_million) == 6.00


def test_dashscope_provider_base_url_resolves_to_pricing():
    """The DashScope base URL (dashscope.aliyuncs.com) must resolve to
    the dashscope provider, not ``unknown``. Without this branch, a user
    pointing their qwen base_url at the CN endpoint would silently fail
    to estimate cost.
    """
    entry = get_pricing_entry(
        "qwen3.5-flash",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    assert entry is not None
    assert entry.input_cost_per_million is not None


def test_qwen_and_dashscope_pricing_tables_are_disjoint_providers():
    """Invariant: the qwen and dashscope provider names must remain
    distinct keys in the pricing table. If a future refactor collapses
    them into one provider, the route resolution above will start
    returning the wrong pricing for one region.
    """
    from agent.usage_pricing import _OFFICIAL_DOCS_PRICING

    qwen_keys = {k for k in _OFFICIAL_DOCS_PRICING if k[0] == "qwen"}
    dashscope_keys = {k for k in _OFFICIAL_DOCS_PRICING if k[0] == "dashscope"}
    assert qwen_keys, "expected at least one qwen pricing row"
    assert dashscope_keys, "expected at least one dashscope pricing row"
    # Same model name can appear under both providers (intentional),
    # but the provider tuple must be distinct.
    shared_models = {k[1] for k in qwen_keys} & {k[1] for k in dashscope_keys}
    for model in shared_models:
        assert ("qwen", model) in _OFFICIAL_DOCS_PRICING
        assert ("dashscope", model) in _OFFICIAL_DOCS_PRICING
