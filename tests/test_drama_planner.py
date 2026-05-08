"""Tests for drama planner (planner.py)."""

import json
from unittest.mock import AsyncMock

import pytest

from videoclaw.drama.models import (
    Character,
    DramaSeries,
    Episode,
    EpisodeStatus,
    ShotScale,
    ShotType,
)
from videoclaw.drama.planner import DramaPlanner

# ---------------------------------------------------------------------------
# Mock LLM → DramaScene parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_series_retries_when_llm_first_returns_non_json():
    """plan_series should recover when an LLM first ignores the JSON-only prompt."""
    valid_plan = json.dumps({
        "title": "工具人恋爱",
        "genre": "romance",
        "synopsis": "两个各怀目的的人在假相亲中动了真心。",
        "characters": [
            {
                "name": "陆北辰",
                "description": "航天工程师，理性克制。",
                "visual_prompt": "Chinese man in his early thirties, neat black hair, crisp shirt",
                "voice_style": "calm",
            },
            {
                "name": "苏念念",
                "description": "带货主播，嘴贫心软。",
                "visual_prompt": (
                    "Chinese woman in her late twenties, shoulder-length hair, modern outfit"
                ),
                "voice_style": "playful",
            },
        ],
        "episodes": [
            {
                "number": 1,
                "title": "相亲协议",
                "synopsis": "两人在相亲局互相摊牌，决定暂时合作。",
                "opening_hook": "苏念念当场吐槽陆北辰像在开项目会。",
                "duration_seconds": 60,
            }
        ],
    }, ensure_ascii=False)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(side_effect=[
        "I'll generate the drama package.\n\n## Characters\n- 陆北辰\n- 苏念念",
        valid_plan,
    ])

    planner = DramaPlanner(llm=mock_llm)
    series = DramaSeries(
        title="测试",
        synopsis="假相亲变真心",
        genre="romance",
        total_episodes=1,
        target_episode_duration=60,
        language="zh",
    )

    result = await planner.plan_series(series)

    assert len(result.characters) == 2
    assert len(result.episodes) == 1
    assert result.episodes[0].status == EpisodeStatus.PENDING
    assert mock_llm.chat.await_count == 2
    retry_messages = mock_llm.chat.await_args_list[1].kwargs["messages"]
    assert "Return ONLY valid JSON" in retry_messages[0]["content"]
    assert "Previous response was not valid JSON" in retry_messages[1]["content"]


@pytest.mark.asyncio
async def test_plan_series_retries_when_llm_returns_wrong_schema():
    """plan_series should reject JSON that lacks required plan arrays."""
    valid_plan = json.dumps({
        "title": "工具人恋爱",
        "genre": "romance",
        "synopsis": "两个工具人动了真心。",
        "characters": [
            {
                "name": "陆北辰",
                "description": "理性工程师。",
                "visual_prompt": "Chinese man in his early thirties, neat hair",
                "voice_style": "calm",
            },
            {
                "name": "苏念念",
                "description": "嘴贫主播。",
                "visual_prompt": "Chinese woman in her late twenties, modern outfit",
                "voice_style": "playful",
            },
        ],
        "episodes": [
            {
                "number": 1,
                "title": "协议开始",
                "synopsis": "两人达成假相亲协议。",
                "opening_hook": "苏念念吐槽陆北辰。",
                "duration_seconds": 60,
            }
        ],
    }, ensure_ascii=False)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(side_effect=[
        json.dumps({"title": "只有标题"}, ensure_ascii=False),
        valid_plan,
    ])

    planner = DramaPlanner(llm=mock_llm)
    series = DramaSeries(
        title="测试",
        synopsis="假相亲变真心",
        genre="romance",
        total_episodes=1,
        target_episode_duration=60,
        language="zh",
    )

    result = await planner.plan_series(series)

    assert len(result.characters) == 2
    assert len(result.episodes) == 1
    assert mock_llm.chat.await_count == 2
    retry_messages = mock_llm.chat.await_args_list[1].kwargs["messages"]
    assert "required JSON fields were missing or empty" in retry_messages[1]["content"]


@pytest.mark.asyncio
async def test_plan_series_requests_large_low_temperature_json_completion():
    """plan_series should avoid default short, creative LLM completions."""
    valid_plan = json.dumps({
        "title": "工具人恋爱",
        "genre": "romance",
        "synopsis": "两个工具人动了真心。",
        "characters": [
            {
                "name": "陆北辰",
                "description": "理性工程师。",
                "visual_prompt": "Chinese man in his early thirties, neat hair",
                "voice_style": "calm",
            },
            {
                "name": "苏念念",
                "description": "嘴贫主播。",
                "visual_prompt": "Chinese woman in her late twenties, modern outfit",
                "voice_style": "playful",
            },
        ],
        "episodes": [
            {
                "number": 1,
                "title": "协议开始",
                "synopsis": "两人达成假相亲协议。",
                "opening_hook": "苏念念吐槽陆北辰。",
                "duration_seconds": 60,
            }
        ],
    }, ensure_ascii=False)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=valid_plan)

    planner = DramaPlanner(llm=mock_llm)
    series = DramaSeries(
        title="测试",
        synopsis="假相亲变真心",
        total_episodes=1,
        target_episode_duration=60,
        language="zh",
    )

    await planner.plan_series(series)

    assert mock_llm.chat.await_args.kwargs["max_tokens"] == 8192
    assert mock_llm.chat.await_args.kwargs["temperature"] == 0.2


@pytest.mark.asyncio
async def test_script_episode_parses_mock_llm_response():
    """script_episode should parse mock LLM JSON into DramaScene objects."""
    mock_llm_response = json.dumps({
        "episode_title": "命运来电",
        "scenes": [
            {
                "scene_id": "ep01_s01",
                "description": "深夜办公室，林晓接到神秘电话",
                "visual_prompt": (
                    "Modern office at night, young Chinese woman in business suit, short "
                    "black hair, looking shocked at phone, dramatic lighting from desk lamp"
                ),
                "camera_movement": "dolly_in",
                "duration_seconds": 5.0,
                "dialogue": "喂？你是谁？",
                "narration": "",
                "speaking_character": "林晓",
                "shot_scale": "medium_close",
                "shot_type": "action",
                "emotion": "suspense",
                "characters_present": ["林晓"],
                "transition": "fade_in",
            },
            {
                "scene_id": "ep01_s02",
                "description": "林晓震惊地看着手机屏幕",
                "visual_prompt": (
                    "Close-up of young Chinese woman's face, short black hair, eyes wide "
                    "with shock, phone screen illuminating her face, dark office background"
                ),
                "camera_movement": "static",
                "duration_seconds": 3.0,
                "dialogue": "",
                "narration": "那一刻，她的世界彻底改变了",
                "speaking_character": "",
                "shot_scale": "close_up",
                "shot_type": "reaction",
                "emotion": "shock",
                "characters_present": ["林晓"],
                "transition": "cut",
            },
        ],
        "voice_over": {"text": "那一刻，她的世界彻底改变了", "tone": "dramatic", "language": "zh"},
        "music": {"style": "orchestral", "mood": "mysterious", "tempo": 90},
        "cliffhanger": "电话那头的声音，竟然是她自己",
    }, ensure_ascii=False)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=mock_llm_response)

    planner = DramaPlanner(llm=mock_llm)
    series = DramaSeries(title="测试剧", characters=[Character(name="林晓")])
    episode = Episode(number=1, title="命运来电", synopsis="深夜接到神秘电话", duration_seconds=8.0)

    script_data = await planner.script_episode(series, episode)

    assert len(episode.scenes) == 2
    assert episode.scenes[0].scene_id == "ep01_s01"
    assert episode.scenes[0].speaking_character == "林晓"
    assert episode.scenes[0].shot_scale == ShotScale.MEDIUM_CLOSE
    assert episode.scenes[0].shot_type == ShotType.ACTION
    assert episode.scenes[0].emotion == "suspense"
    assert episode.scenes[0].characters_present == ["林晓"]
    assert episode.scenes[0].transition == "fade_in"

    assert episode.scenes[1].shot_scale == ShotScale.CLOSE_UP
    assert episode.scenes[1].shot_type == ShotType.REACTION
    assert episode.scenes[1].narration == "那一刻，她的世界彻底改变了"

    assert episode.script is not None
    assert "命运来电" in episode.script
    assert script_data["cliffhanger"] == "电话那头的声音，竟然是她自己"


@pytest.mark.asyncio
async def test_script_episode_retries_when_llm_first_returns_non_json():
    """script_episode should recover when an LLM first returns markdown."""
    valid_script = json.dumps({
        "episode_title": "相亲协议",
        "scenes": [
            {
                "scene_id": "ep01_s01",
                "description": "茶餐厅里两人互相试探",
                "visual_prompt": (
                    "Shanghai tea restaurant, Chinese man and woman talking, warm lighting"
                ),
                "camera_movement": "static",
                "duration_seconds": 8.0,
                "dialogue": "你是来相亲，还是来开会？",
                "narration": "",
                "speaking_character": "苏念念",
                "shot_scale": "medium_close",
                "shot_type": "action",
                "emotion": "warm",
                "characters_present": ["陆北辰", "苏念念"],
                "transition": "cut",
            }
        ],
        "voice_over": {"text": "", "tone": "warm", "language": "zh"},
        "music": {"style": "acoustic", "mood": "romantic", "tempo": 80},
        "cliffhanger": "陆北辰第一次不知道怎么回答。",
    }, ensure_ascii=False)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(side_effect=[
        "# 相亲协议\n\n这是一个 Markdown 分镜脚本。",
        valid_script,
    ])

    planner = DramaPlanner(llm=mock_llm)
    series = DramaSeries(
        title="工具人恋爱",
        characters=[Character(name="陆北辰"), Character(name="苏念念")],
        language="zh",
    )
    episode = Episode(number=1, title="相亲协议", synopsis="两人互相试探", duration_seconds=8.0)

    script_data = await planner.script_episode(series, episode)

    assert len(episode.scenes) == 1
    assert script_data["cliffhanger"] == "陆北辰第一次不知道怎么回答。"
    assert mock_llm.chat.await_count == 2
    retry_messages = mock_llm.chat.await_args_list[1].kwargs["messages"]
    assert "Return ONLY valid JSON" in retry_messages[0]["content"]
    assert "Previous response was not valid JSON" in retry_messages[1]["content"]


@pytest.mark.asyncio
async def test_script_episode_retries_when_llm_returns_wrong_schema():
    """script_episode should reject JSON that lacks scenes."""
    valid_script = json.dumps({
        "episode_title": "相亲协议",
        "scenes": [
            {
                "scene_id": "ep01_s01",
                "description": "茶餐厅里两人互相试探",
                "visual_prompt": (
                    "Shanghai tea restaurant, Chinese man and woman talking, warm lighting"
                ),
                "camera_movement": "static",
                "duration_seconds": 8.0,
                "dialogue": "你是来相亲，还是来开会？",
                "narration": "",
                "speaking_character": "苏念念",
                "shot_scale": "medium_close",
                "shot_type": "action",
                "emotion": "warm",
                "characters_present": ["陆北辰", "苏念念"],
                "transition": "cut",
            }
        ],
        "voice_over": {"text": "", "tone": "warm", "language": "zh"},
        "music": {"style": "acoustic", "mood": "romantic", "tempo": 80},
        "cliffhanger": "陆北辰第一次不知道怎么回答。",
    }, ensure_ascii=False)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(side_effect=[
        json.dumps({"episode_title": "相亲协议"}, ensure_ascii=False),
        valid_script,
    ])

    planner = DramaPlanner(llm=mock_llm)
    series = DramaSeries(
        title="工具人恋爱",
        characters=[Character(name="陆北辰"), Character(name="苏念念")],
        language="zh",
    )
    episode = Episode(number=1, title="相亲协议", synopsis="两人互相试探", duration_seconds=8.0)

    script_data = await planner.script_episode(series, episode)

    assert len(episode.scenes) == 1
    assert script_data["cliffhanger"] == "陆北辰第一次不知道怎么回答。"
    assert mock_llm.chat.await_count == 2
    retry_messages = mock_llm.chat.await_args_list[1].kwargs["messages"]
    assert "required JSON fields were missing or empty" in retry_messages[1]["content"]


@pytest.mark.asyncio
async def test_script_episode_requests_large_low_temperature_json_completion():
    """script_episode should request enough output for a full scene list."""
    valid_script = json.dumps({
        "episode_title": "相亲协议",
        "scenes": [
            {
                "scene_id": "ep01_s01",
                "description": "茶餐厅里两人互相试探",
                "visual_prompt": (
                    "Shanghai tea restaurant, Chinese man and woman talking, warm lighting"
                ),
                "camera_movement": "static",
                "duration_seconds": 8.0,
                "dialogue": "你是来相亲，还是来开会？",
                "narration": "",
                "speaking_character": "苏念念",
                "shot_scale": "medium_close",
                "shot_type": "action",
                "emotion": "warm",
                "characters_present": ["陆北辰", "苏念念"],
                "transition": "cut",
            }
        ],
        "voice_over": {"text": "", "tone": "warm", "language": "zh"},
        "music": {"style": "acoustic", "mood": "romantic", "tempo": 80},
        "cliffhanger": "陆北辰第一次不知道怎么回答。",
    }, ensure_ascii=False)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=valid_script)

    planner = DramaPlanner(llm=mock_llm)
    series = DramaSeries(
        title="工具人恋爱",
        characters=[Character(name="陆北辰"), Character(name="苏念念")],
        language="zh",
    )
    episode = Episode(number=1, title="相亲协议", synopsis="两人互相试探", duration_seconds=8.0)

    await planner.script_episode(series, episode)

    assert mock_llm.chat.await_args.kwargs["max_tokens"] == 8192
    assert mock_llm.chat.await_args.kwargs["temperature"] == 0.2


# ---------------------------------------------------------------------------
# Duration validation / adjustment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_script_episode_adjusts_duration_proportionally():
    """When scene durations deviate >5s from target, planner should scale them.

    Seedance 2.0 constrains individual scenes to 4-15s, so test values are
    chosen so that both scaled durations remain within that range.
    """
    # 8+12=20s, target=14s → scale ~0.7 → 5.6+8.4 (both within 4-15s)
    mock_llm_response = json.dumps({
        "episode_title": "时长测试",
        "scenes": [
            {
                "scene_id": "ep01_s01",
                "description": "场景1",
                "visual_prompt": "scene one",
                "camera_movement": "static",
                "duration_seconds": 8.0,
                "dialogue": "",
                "narration": "",
                "speaking_character": "",
                "shot_scale": "medium",
                "shot_type": "action",
                "emotion": "tense",
                "characters_present": [],
                "transition": "cut",
            },
            {
                "scene_id": "ep01_s02",
                "description": "场景2",
                "visual_prompt": "scene two",
                "camera_movement": "static",
                "duration_seconds": 12.0,
                "dialogue": "",
                "narration": "",
                "speaking_character": "",
                "shot_scale": "wide",
                "shot_type": "establishing",
                "emotion": "warm",
                "characters_present": [],
                "transition": "cut",
            },
        ],
        "voice_over": {"text": "", "tone": "warm", "language": "zh"},
        "music": {"style": "acoustic", "mood": "romantic", "tempo": 80},
        "cliffhanger": "测试悬念",
    }, ensure_ascii=False)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=mock_llm_response)

    planner = DramaPlanner(llm=mock_llm)
    series = DramaSeries(title="测试剧")
    episode = Episode(number=1, title="时长测试", synopsis="测试", duration_seconds=14.0)

    await planner.script_episode(series, episode)

    # Original: 8+12=20s, target=14s → scale by 0.7 → 5.6+8.4
    total = sum(s.duration_seconds for s in episode.scenes)
    assert abs(total - 14.0) <= 2.0, f"Expected ~14s, got {total}s"
    # Ratio should be preserved: scene1 should be less than scene2
    assert episode.scenes[0].duration_seconds < episode.scenes[1].duration_seconds


@pytest.mark.asyncio
async def test_script_episode_no_adjustment_within_tolerance():
    """When scene durations are within ±5s of target, no adjustment should occur.

    Individual scenes are still clamped to Seedance 2.0's 4-15s range.
    """
    # Two scenes: 7+8=15s, target=18s → within 5s tolerance, no scaling
    # Both durations already within 4-15s range → no clamping either
    mock_llm_response = json.dumps({
        "episode_title": "精准时长",
        "scenes": [
            {
                "scene_id": "ep01_s01",
                "description": "场景1",
                "visual_prompt": "scene one",
                "camera_movement": "static",
                "duration_seconds": 7.0,
                "dialogue": "",
                "narration": "",
                "speaking_character": "",
                "shot_scale": "medium",
                "shot_type": "action",
                "emotion": "tense",
                "characters_present": [],
                "transition": "cut",
            },
            {
                "scene_id": "ep01_s02",
                "description": "场景2",
                "visual_prompt": "scene two",
                "camera_movement": "static",
                "duration_seconds": 8.0,
                "dialogue": "",
                "narration": "",
                "speaking_character": "",
                "shot_scale": "wide",
                "shot_type": "establishing",
                "emotion": "warm",
                "characters_present": [],
                "transition": "cut",
            },
        ],
        "voice_over": {"text": "", "tone": "warm", "language": "zh"},
        "music": {"style": "acoustic", "mood": "romantic", "tempo": 80},
        "cliffhanger": "测试",
    }, ensure_ascii=False)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=mock_llm_response)

    planner = DramaPlanner(llm=mock_llm)
    series = DramaSeries(title="测试剧")
    episode = Episode(number=1, title="精准", synopsis="测试", duration_seconds=18.0)

    await planner.script_episode(series, episode)

    # 15s is within 5s of 18s target — no scaling; durations within 4-15s — no clamping
    assert episode.scenes[0].duration_seconds == 7.0
    assert episode.scenes[1].duration_seconds == 8.0


@pytest.mark.asyncio
async def test_parse_json_strips_markdown_fences():
    """_parse_json should handle markdown code fences around JSON."""
    planner = DramaPlanner()

    fenced = '```json\n{"key": "value"}\n```'
    result = planner._parse_json(fenced)
    assert result == {"key": "value"}

    bare = '{"key": "value"}'
    result = planner._parse_json(bare)
    assert result == {"key": "value"}

    with pytest.raises(ValueError, match="invalid JSON"):
        planner._parse_json("not json at all")


# ---------------------------------------------------------------------------
# Task 5: inner_monologue in EPISODE_SCRIPT_PROMPT
# ---------------------------------------------------------------------------


def test_episode_script_has_inner_monologue():
    from videoclaw.drama.planner import EPISODE_SCRIPT_PROMPT
    assert "inner_monologue" in EPISODE_SCRIPT_PROMPT
    assert "dialogue_line_type" in EPISODE_SCRIPT_PROMPT
    assert "内心独白" in EPISODE_SCRIPT_PROMPT


def test_planner_prompts_match_seedance_five_to_fifteen_second_range():
    from videoclaw.drama.planner import EPISODE_SCRIPT_PROMPT, IMPORT_DECOMPOSE_PROMPT

    assert "5～15 秒" in EPISODE_SCRIPT_PROMPT
    assert "5-15s" in IMPORT_DECOMPOSE_PROMPT
