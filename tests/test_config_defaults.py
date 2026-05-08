from videoclaw.config import get_config


def test_default_llm_is_sonnet_4_6(monkeypatch):
    monkeypatch.delenv("VIDEOCLAW_DEFAULT_LLM", raising=False)
    get_config.cache_clear()
    try:
        assert get_config().default_llm == "claude-sonnet-4-6"
    finally:
        get_config.cache_clear()
