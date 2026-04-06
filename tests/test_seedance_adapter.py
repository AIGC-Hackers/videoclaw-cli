"""Tests for SeedanceVideoAdapter — persistent HTTP client and core behaviour."""

import pytest


class TestSeedancePersistentClient:
    """P1#5: adapter must reuse a single AsyncClient across requests."""

    def _make_adapter(self, api_key: str = "test-key") -> "SeedanceVideoAdapter":
        from videoclaw.models.adapters.seedance import SeedanceVideoAdapter
        return SeedanceVideoAdapter(api_key=api_key)

    def test_client_is_none_before_first_use(self):
        """_http_client must start as None (lazy init)."""
        adapter = self._make_adapter()
        assert adapter._http_client is None

    def test_client_created_on_first_call(self):
        """_client() must create and cache an AsyncClient on first invocation."""
        import httpx
        adapter = self._make_adapter()
        client = adapter._client()
        assert isinstance(client, httpx.AsyncClient)
        assert adapter._http_client is client

    def test_client_reused_on_subsequent_calls(self):
        """_client() must return the exact same instance every time."""
        adapter = self._make_adapter()
        c1 = adapter._client()
        c2 = adapter._client()
        assert c1 is c2

    def test_separate_adapters_have_independent_clients(self):
        """Two adapter instances must not share their HTTP client."""
        adapter_a = self._make_adapter()
        adapter_b = self._make_adapter()
        c_a = adapter_a._client()
        c_b = adapter_b._client()
        assert c_a is not c_b


class TestSeedanceAdapterProperties:
    """Basic property smoke tests."""

    def _make_adapter(self) -> "SeedanceVideoAdapter":
        from videoclaw.models.adapters.seedance import SeedanceVideoAdapter
        return SeedanceVideoAdapter(api_key="test-key")

    def test_model_id(self):
        assert self._make_adapter().model_id == "seedance-2.0"

    def test_capabilities_include_video(self):
        from videoclaw.models.protocol import ModelCapability
        caps = self._make_adapter().capabilities
        assert ModelCapability.TEXT_TO_VIDEO in caps

    def test_execution_mode_is_cloud(self):
        from videoclaw.models.protocol import ExecutionMode
        assert self._make_adapter().execution_mode == ExecutionMode.CLOUD
