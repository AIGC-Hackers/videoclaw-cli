from videoclaw.config import get_config


def test_default_llm_is_sonnet_4_6(monkeypatch):
    monkeypatch.delenv("VIDEOCLAW_DEFAULT_LLM", raising=False)
    get_config.cache_clear()
    try:
        assert get_config().default_llm == "claude-sonnet-4-6"
    finally:
        get_config.cache_clear()


def test_config_loads_xdg_videoclaw_env_file(tmp_path, monkeypatch):
    xdg_home = tmp_path / "xdg"
    config_dir = xdg_home / "videoclaw"
    config_dir.mkdir(parents=True)
    projects_dir = tmp_path / "configured-projects"
    (config_dir / ".env").write_text(
        "\n".join(
            [
                "VIDEOCLAW_DEFAULT_LLM=claude-sonnet-4-6",
                "VIDEOCLAW_DEFAULT_VIDEO_MODEL=mock",
                f"VIDEOCLAW_PROJECTS_DIR={projects_dir}",
                "VIDEOCLAW_EVOLINK_API_KEY=ev-test",
            ]
        ),
        encoding="utf-8",
    )
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))
    monkeypatch.delenv("VIDEOCLAW_DEFAULT_VIDEO_MODEL", raising=False)
    monkeypatch.delenv("VIDEOCLAW_PROJECTS_DIR", raising=False)
    monkeypatch.delenv("VIDEOCLAW_EVOLINK_API_KEY", raising=False)
    get_config.cache_clear()
    try:
        cfg = get_config()
        assert cfg.default_video_model == "mock"
        assert cfg.projects_dir == projects_dir
        assert cfg.evolink_api_key == "ev-test"
    finally:
        get_config.cache_clear()
