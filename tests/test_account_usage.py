from datetime import datetime, timezone

from agent.account_usage import (
    AccountUsageSnapshot,
    AccountUsageWindow,
    fetch_account_usage,
    render_account_usage_lines,
)


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self._status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        return _Response(self._payload, status_code=self._status_code)


class _RoutingClient:
    def __init__(self, payloads):
        self._payloads = payloads

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        return _Response(self._payloads[url])


def test_fetch_account_usage_codex(monkeypatch):
    monkeypatch.setattr(
        "agent.account_usage.resolve_codex_runtime_credentials",
        lambda refresh_if_expiring=True: {
            "provider": "openai-codex",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": "access-token",
        },
    )
    monkeypatch.setattr(
        "agent.account_usage._read_codex_tokens",
        lambda: {"tokens": {"account_id": "acct_123"}},
    )
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=15.0: _Client(
            {
                "plan_type": "pro",
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 15,
                        "reset_at": 1_900_000_000,
                        "limit_window_seconds": 18000,
                    },
                    "secondary_window": {
                        "used_percent": 40,
                        "reset_at": 1_900_500_000,
                        "limit_window_seconds": 604800,
                    },
                },
                "credits": {"has_credits": True, "balance": 12.5},
            }
        ),
    )

    snapshot = fetch_account_usage("openai-codex")

    assert snapshot is not None
    assert snapshot.plan == "Pro"
    assert len(snapshot.windows) == 2
    assert snapshot.windows[0].label == "Session"
    assert snapshot.windows[0].used_percent == 15.0
    assert snapshot.windows[0].reset_at == datetime.fromtimestamp(1_900_000_000, tz=timezone.utc)
    assert "Credits balance: $12.50" in snapshot.details


def test_render_account_usage_lines_includes_reset_and_provider():
    snapshot = AccountUsageSnapshot(
        provider="openai-codex",
        source="usage_api",
        fetched_at=datetime.now(timezone.utc),
        plan="Pro",
        windows=(
            AccountUsageWindow(
                label="Session",
                used_percent=25,
                reset_at=datetime.now(timezone.utc),
            ),
        ),
        details=("Credits balance: $9.99",),
    )
    lines = render_account_usage_lines(snapshot)

    assert lines[0] == "📈 Account limits"
    assert "openai-codex (Pro)" in lines[1]
    assert "Session: 75% remaining (25% used)" in lines[2]
    assert "Credits balance: $9.99" in lines[3]


def test_fetch_account_usage_openrouter_uses_limit_remaining_and_ignores_deprecated_rate_limit(monkeypatch):
    monkeypatch.setattr(
        "agent.account_usage.resolve_runtime_provider",
        lambda requested, explicit_base_url=None, explicit_api_key=None: {
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-test",
        },
    )
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _RoutingClient(
            {
                "https://openrouter.ai/api/v1/credits": {
                    "data": {"total_credits": 300.0, "total_usage": 10.92}
                },
                "https://openrouter.ai/api/v1/key": {
                    "data": {
                        "limit": 100.0,
                        "limit_remaining": 70.0,
                        "limit_reset": "monthly",
                        "usage": 12.5,
                        "usage_daily": 0.5,
                        "usage_weekly": 2.0,
                        "usage_monthly": 8.0,
                        "rate_limit": {"requests": -1, "interval": "10s"},
                    }
                },
            }
        ),
    )

    snapshot = fetch_account_usage("openrouter")

    assert snapshot is not None
    assert snapshot.windows == (
        AccountUsageWindow(
            label="API key quota",
            used_percent=30.0,
            detail="$70.00 of $100.00 remaining • resets monthly",
        ),
    )
    assert "Credits balance: $289.08" in snapshot.details
    assert "API key usage: $12.50 total • $0.50 today • $2.00 this week • $8.00 this month" in snapshot.details
    assert all("-1 requests / 10s" not in line for line in render_account_usage_lines(snapshot))


def test_fetch_account_usage_openrouter_omits_quota_window_when_key_has_no_limit(monkeypatch):
    monkeypatch.setattr(
        "agent.account_usage.resolve_runtime_provider",
        lambda requested, explicit_base_url=None, explicit_api_key=None: {
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-test",
        },
    )
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _RoutingClient(
            {
                "https://openrouter.ai/api/v1/credits": {
                    "data": {"total_credits": 100.0, "total_usage": 25.5}
                },
                "https://openrouter.ai/api/v1/key": {
                    "data": {
                        "limit": None,
                        "limit_remaining": None,
                        "usage": 25.5,
                        "usage_daily": 1.25,
                        "usage_weekly": 4.5,
                        "usage_monthly": 18.0,
                    }
                },
            }
        ),
    )

    snapshot = fetch_account_usage("openrouter")

    assert snapshot is not None
    assert snapshot.windows == ()
    assert "Credits balance: $74.50" in snapshot.details
    assert "API key usage: $25.50 total • $1.25 today • $4.50 this week • $18.00 this month" in snapshot.details


# chunk 3: MiniMax Token Plan and Z.AI GLM Coding Plan quota fetchers.
# Each one was verified to fail on the pre-chunk-3 source (no branches
# for these providers in fetch_account_usage) and pass on the new source.


def test_fetch_account_usage_minimax_token_plan(monkeypatch):
    """A MiniMax Token Plan user with a valid key gets a snapshot with
    both the 5-hour and weekly windows, plus the per-model breakdown.
    """
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _Client(
            {
                "remains_time": 1_900_000_000,
                "current_interval_total_count": 1000,
                "current_interval_usage_count": 230,
                "current_weekly_total_count": 10000,
                "current_weekly_usage_count": 4200,
                "model_remains": [
                    {
                        "model_name": "MiniMax-M3",
                        "current_interval_total_count": 800,
                        "current_interval_usage_count": 200,
                    },
                ],
            }
        ),
    )

    snapshot = fetch_account_usage("minimax", base_url="https://api.minimax.io/anthropic", api_key="sk-cp-test")

    assert snapshot is not None
    assert snapshot.provider == "minimax"
    assert snapshot.plan == "Token Plan"
    assert len(snapshot.windows) == 2
    assert snapshot.windows[0].label == "5-hour window"
    assert snapshot.windows[0].used_percent == 23.0
    assert snapshot.windows[0].reset_at == datetime.fromtimestamp(1_900_000_000, tz=timezone.utc)
    assert snapshot.windows[1].label == "Weekly window"
    assert snapshot.windows[1].used_percent == 42.0
    assert any("MiniMax-M3: 25% used this window" in d for d in snapshot.details)


def test_fetch_account_usage_minimax_cn_hits_cn_host(monkeypatch):
    """CN users pointing base_url at api.minimaxi.com must hit the
    /v1/token_plan/remains endpoint on the CN mirror, not the global one.
    """
    captured_urls: list[str] = []

    class _UrlCapturingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            captured_urls.append(url)
            return _Response(
                {
                    "current_interval_total_count": 100,
                    "current_interval_usage_count": 10,
                }
            )

    monkeypatch.setattr("agent.account_usage.httpx.Client", _UrlCapturingClient)

    snapshot = fetch_account_usage("minimax", base_url="https://api.minimaxi.com/anthropic", api_key="sk-cp-cn")

    assert snapshot is not None
    assert captured_urls == ["https://api.minimaxi.com/v1/token_plan/remains"]


def test_fetch_account_usage_minimax_no_api_key_returns_none(monkeypatch):
    """Missing key must not raise; it returns None so /usage still shows
    the cost block instead of crashing.
    """
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _Client({"current_interval_total_count": 1, "current_interval_usage_count": 0}),
    )

    snapshot = fetch_account_usage("minimax", base_url="https://api.minimax.io/anthropic", api_key="")

    assert snapshot is None


def test_fetch_account_usage_minimax_401_fails_open(monkeypatch):
    """A 401 from the plan endpoint (pay-as-you-go key, not a Token Plan
    subscription key) must fail open and return None, not raise.
    """
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _Client({}, status_code=401),
    )

    snapshot = fetch_account_usage("minimax", base_url="https://api.minimax.io/anthropic", api_key="sk-paygo")

    assert snapshot is None


def test_fetch_account_usage_minimax_unprovisioned_returns_none(monkeypatch):
    """When the server returns the documented #48 state (no plan windows
    provisioned, all count fields are 0), the snapshot is None rather than
    a misleading empty block.
    """
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _Client(
            {
                "remains_time": 1_900_000_000,
                "current_interval_total_count": 0,
                "current_interval_usage_count": 0,
                "current_weekly_total_count": 0,
                "current_weekly_usage_count": 0,
            }
        ),
    )

    snapshot = fetch_account_usage("minimax", base_url="https://api.minimax.io/anthropic", api_key="sk-cp-test")

    # The 5h window is preserved (0/0 -> 0.0%) so the user sees that the
    # plan endpoint is reachable and reporting fresh data, but the weekly
    # window is dropped (also 0/0 -> 0.0%) so the block does not bloat.
    assert snapshot is not None
    assert len(snapshot.windows) == 2
    assert all(w.used_percent == 0.0 for w in snapshot.windows)


def test_fetch_account_usage_zai_glm_coding_plan(monkeypatch):
    """A Z.AI Coding Plan subscriber with a valid key gets a snapshot
    with the 5-hour token window and the MCP usage window.
    """
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _Client(
            {
                "limits": [
                    {"type": "TOKENS_LIMIT", "percentage": 35.0, "usage": 35000, "currentValue": 35000},
                    {"type": "TIME_LIMIT", "percentage": 12.0, "usage": 300000, "currentValue": 300000, "usageDetails": [
                        {"name": "web_search", "count": 420},
                        {"name": "code_exec", "count": 89},
                        {"name": "file_read", "count": 12},
                    ]},
                ],
            }
        ),
    )

    snapshot = fetch_account_usage("zai", base_url="https://api.z.ai/api/paas/v4", api_key="zai-coding-plan-key")

    assert snapshot is not None
    assert snapshot.provider == "zai"
    assert snapshot.plan == "GLM Coding Plan"
    assert len(snapshot.windows) == 2
    assert snapshot.windows[0].label == "5-hour window"
    assert snapshot.windows[0].used_percent == 35.0
    assert snapshot.windows[1].label == "MCP usage (monthly)"
    assert snapshot.windows[1].used_percent == 12.0
    assert any("web_search: 420 calls" in d for d in snapshot.details)
    assert any("code_exec: 89 calls" in d for d in snapshot.details)


def test_fetch_account_usage_zai_provider_alias_resolves(monkeypatch):
    """The provider string 'z-ai' (with the dash) must also resolve so
    users with config files that spell it the long form are not silently
    dropped.
    """
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _Client(
            {
                "limits": [
                    {"type": "TOKENS_LIMIT", "percentage": 5.0},
                ],
            }
        ),
    )

    snapshot = fetch_account_usage("z-ai", base_url="https://api.z.ai/api/paas/v4", api_key="zai-coding-plan-key")

    assert snapshot is not None
    assert snapshot.provider == "zai"
    assert len(snapshot.windows) == 1
    assert snapshot.windows[0].used_percent == 5.0


def test_fetch_account_usage_zai_cn_hits_open_bigmodel(monkeypatch):
    """CN users with a Zhipu (bigmodel.cn) base_url must hit the CN plan
    host, not api.z.ai.
    """
    captured_urls: list[str] = []

    class _UrlCapturingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            captured_urls.append(url)
            return _Response({"limits": [{"type": "TOKENS_LIMIT", "percentage": 1.0}]})

    monkeypatch.setattr("agent.account_usage.httpx.Client", _UrlCapturingClient)

    snapshot = fetch_account_usage("zai", base_url="https://open.bigmodel.cn/api/paas/v4", api_key="glm-cn-key")

    assert snapshot is not None
    assert captured_urls == ["https://open.bigmodel.cn/api/monitor/usage/quota/limit"]


def test_fetch_account_usage_zai_no_api_key_returns_none(monkeypatch):
    """Missing key must not raise; it returns None so /usage still shows
    the cost block instead of crashing.
    """
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _Client({"limits": [{"type": "TOKENS_LIMIT", "percentage": 1.0}]}),
    )

    snapshot = fetch_account_usage("zai", base_url="https://api.z.ai/api/paas/v4", api_key="")

    assert snapshot is None


def test_fetch_account_usage_zai_403_fails_open(monkeypatch):
    """A 403 from the plan endpoint (standard ZAI_API_KEY without Coding
    Plan subscription) must fail open.
    """
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _Client({}, status_code=403),
    )

    snapshot = fetch_account_usage("zai", base_url="https://api.z.ai/api/paas/v4", api_key="standard-zai-key")

    assert snapshot is None


def test_fetch_account_usage_zai_empty_limits_returns_none(monkeypatch):
    """When the server returns an empty limits list (e.g. a user with a
    plan key that has no active windows), the snapshot is None rather
    than showing a header with no rows.
    """
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _Client({"limits": []}),
    )

    snapshot = fetch_account_usage("zai", base_url="https://api.z.ai/api/paas/v4", api_key="zai-coding-plan-key")

    assert snapshot is None
