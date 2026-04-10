# Deliverables Review Layout — Design Spec

**Date:** 2026-04-10
**Branch:** `feat/cli-refactor`
**Author:** tech lead (VideoClaw)
**Status:** proposed — awaiting user review before writing-plans

---

## 1. 背景与问题陈述

VideoClaw 的人工审计 (human review) 目录 `docs/deliverables/<drama_slug>/<episode_slug>/` 目前存在三类可见冗余，导致制作团队打开目录时无法一眼识别「这一集的资产」：

### 冗余 #1 — 历史遗留的 review 目录没被清理

`checkpoint.py` 的 docstring (lines 17–28) 仍然描述老路径 `{projects_dir}/dramas/{series_id}/review/`，而运行时代码已经改用 `docs/deliverables/`。结果同一集存在两份 review 副本：

- `docs/deliverables/satan_in_a_suit/ep01_satan_in_a_suit_epis/`（当前活跃）
- `projects/dramas/e6aabcc14b8c46e1/review/satan_in_a_suit__ep01_satan_in_a_suit_epis/`（历史遗留，symlink 还指向已废弃的 project_id `b0584fdb619b4090`）

### 冗余 #2 — 测试污染生产目录

`docs/deliverables/` 下出现三个以测试 fixture 剧名命名的目录：

```
docs/deliverables/cumulative_test/ep01_pilot/
docs/deliverables/storyboard_test_drama/ep01_pilot/
docs/deliverables/summary_test/ep01_pilot/
```

根因在 `src/videoclaw/cli/drama/_setup.py:330`：

```python
sb_path = generate_storyboard_md(series, ep)   # 未传 base_dir
```

`generate_storyboard_md` 的 `base_dir=None` 会 fallback 到 `get_config().deliverables_dir`，即真实的 `./docs/deliverables/`。任何绕过 `CheckpointController`、直接跑剧本 import 流程的调用（包括测试通过 typer runner 间接调用），都会把测试 fixture 的 slug 写到生产目录。

### 冗余 #3 — 两套并行的 deliverables writer

- `checkpoint.py::_update_review_dir` 写 `docs/deliverables/<slug>/ep<NN>_<ep>/...`（按集组织、symlink）
- `_export.py::drama_export` 写 `docs/deliverables/<slug>/00_metadata/ 01_script/ ... 10_audit/`（按 pipeline stage 编号、物理拷贝）

两者共享同一个 `<slug>` 根目录，子目录命名完全不兼容。先后运行就会在同一个剧名下同时出现 `ep01_satan_in_a_suit_epis/` 和 `00_metadata/ 01_script/...`，造成目录结构视觉噪音。

### 冗余 #4（结构层）— 子目录不匹配制作团队心智模型

当前 `_ALL_SUBDIRS = ("characters", "prompts", "videos", "audio", "audit", "composed")`。其中：

- `prompts/` 每场景一个 `.txt` 文件，内容（description / dialogue / camera / shot_scale / prompt）**100% 已经在 `storyboard.md` 里**，是碎片化的重复
- `composed/` 命名不够直观（制作团队的原生词汇是「成片」）
- 缺少 **景别图 / 场景参考图**（制作流程里的核心中间资产之一，CLAUDE.md 明确列为「角色三视图、场景参考图、物品资产」三件套之一）
- 字幕没有独立落点（当前策略是 Seedance 直接烧录到视频，无单独字幕文件）

第一次 checkpoint 调用时所有 6 个子目录全部被预创建，导致尚未进入的阶段遗留空文件夹（当前 `satan_in_a_suit/ep01_.../` 的 `characters/ audit/ composed/ prompts/ audio/` 五个目录全部为空，只有 `videos/` 有内容）。

---

## 2. 目标

**任务目标：人工能够看见所有人工审计的资产，在一个可读性的文件系统里。**

具体拆解：

1. **唯一性** — 每一集有且仅有一个 review 根目录，路径 `docs/deliverables/<drama_slug>/<episode_slug>/`
2. **完整性** — 8 类审计资产（分镜脚本、角色、景别图、音频、视频片段、AI 审计、字幕、成片）全部可在同一个目录里找到
3. **零冗余** — 删除 `prompts/`（和 storyboard.md 重复），字幕并入 storyboard.md，没有空子目录，没有测试污染，没有历史遗留副本
4. **语义可读** — 文件名基于场景描述 slug（`s01_title_card_one_month_earlier_ivy_in.mp4`），路径无 UUID，symlink 的 source of truth 在 `_REVIEW.txt` 显式列出

---

## 3. 非目标

- **不动** `projects/<uuid>/` 目录：保留作为媒体资产的真实存储 (source of truth)
- **不动** `projects/dramas/<series_id>/characters/`、`<ep>_video/`、`<ep>_audit/` 的路径：这些是 drama 管理层的落盘点，review 目录只是 symlink 回指
- **不做** 物理拷贝作为默认行为：磁盘成本不可接受（单集 5 shots × ~6MB ≈ 30MB，单剧多集多轮迭代会翻数倍）
- **不重写** 视频生成、TTS、audit 的写盘逻辑：只改 review 聚合层

---

## 4. 目标文件布局

```
docs/deliverables/<drama_slug>/<episode_slug>/
├── _REVIEW.txt           # 状态摘要 + === Sources === 段落
├── storyboard.md         # 分镜脚本 + 每场景 prompt + ## 台词逐字稿 段落
├── characters/           # 角色 turnaround  (symlink → projects/dramas/<series_id>/characters/)
├── scenes/               # 景别图 / 场景参考图  (symlink → ConsistencyManifest.scene_references)
├── audio/                # 对话 + 旁白  (symlink → projects/<project_id>/audio/)
├── videos/               # 分镜视频  (symlink → projects/<project_id>/shots/)
├── audit/                # Vision QA 报告  (symlink → projects/dramas/<series_id>/ep<NN>_audit/)
└── final/                # 成片  (symlink → projects/dramas/<series_id>/ep<NN>_video/)
```

**6 个子目录 + 2 个单文件**。

### 4.1 子目录到 8 类审计资产的映射

| # | 审计资产（用户语言） | review 位置 | 数据来源 |
|---|---|---|---|
| 1 | 分镜脚本 | `storyboard.md` | `generate_storyboard_md()` 基于 `series.episodes[i].scenes` |
| 2 | 角色 | `characters/<char>_turnaround.<ext>` + `<char>_url.txt` | `char.reference_image` / `char.reference_image_url` |
| 3 | 景别图 | `scenes/<location_slug>.<ext>` | `series.consistency_manifest.scene_references[loc_name]` |
| 4 | 音频 | `audio/<scene_slug>_{dialogue\|narration}.<ext>` | `scene.dialogue_audio_path` / `scene.narration_audio_path` |
| 5 | 视频片段 | `videos/<scene_slug>.mp4` | `scene.video_asset_path` 或 `projects/<project_id>/shots/` 扫描 |
| 6 | AI 审计 | `audit/*.json`, `audit/*.jsonl` | `projects/dramas/<series_id>/ep<NN>_audit/` |
| 7 | 字幕 | **并入 `storyboard.md` 的 `## 台词逐字稿` 段落** | `scene.dialogue` / `scene.narration` |
| 8 | 成片 | `final/*final*.mp4`, `final/*composed*.mp4` | `projects/dramas/<series_id>/ep<NN>_video/` |

字幕单独说明：根据记忆 `feedback_subtitle_strategy.md`，Seedance 直接把字幕烧进视频，不做外部 FFmpeg overlay。因此 review 目录不建 `subtitles/` 独立子目录，字幕的原文台词作为 `storyboard.md` 内的一个新段落存在，供制作团队复核。

### 4.2 `_REVIEW.txt` 新格式

```
Series:      Satan in a Suit (e6aabcc14b8c46e1)
Episode:     1
Last stage:  after_generation
Cost:        $4.3500
Updated:     2026-04-10T04:53:23.339895+00:00
Checkpoint:  62b95adf860d
Remaining:   audit-regen

=== Assets ===
  characters/      3 files  (turnaround sheets + reference URLs)
  scenes/          4 files  (location reference images)
  audio/           0 files  (dialogue + narration audio)
  videos/          7 files  (generated video clips)
  audit/           0 files  (vision QA reports)
  final/           0 files  (composed episode)

=== Sources ===
  characters/  → projects/dramas/e6aabcc14b8c46e1/characters/
  scenes/      → projects/dramas/e6aabcc14b8c46e1/scene_refs/
  audio/       → projects/efc4120179754946/audio/
  videos/      → projects/efc4120179754946/shots/
  audit/       → (empty)
  final/       → (empty)

=== Scenes ===
  s01_title_card_one_month_earlier_ivy_in  [completed]  Title card 'One Month Earlier'. Ivy in server unif
  ...
```

`=== Sources ===` 段落取每个子目录里第一个 symlink 的 `.readlink().parent`，让审计人员在不 `ls -la` 的情况下就能看到 source of truth 的 UUID project 路径。

---

## 5. 实施手术清单

### 5.1 手术 1 — 修复测试泄露 root cause

**文件：** `src/videoclaw/cli/drama/_setup.py`, `src/videoclaw/drama/checkpoint.py`

- `_setup.py:330` 改为：
  ```python
  from videoclaw.config import get_config
  base_dir = get_config().deliverables_dir
  sb_path = generate_storyboard_md(series, ep, base_dir=base_dir)
  ```
- `checkpoint.py::review_dir_for_episode` 和 `generate_storyboard_md` 的 `base_dir` 参数改为 **必传** (`base_dir: Path`，去掉 `None` 默认)
- grep 所有调用点并更新；mypy strict 通过即扫净

**验收：** `grep -rn "review_dir_for_episode\|generate_storyboard_md" src/` 所有调用点都显式传 `base_dir`。

### 5.2 手术 2 — 精简子目录 + 懒创建 + 重命名

**文件：** `src/videoclaw/drama/checkpoint.py`

- `_ALL_SUBDIRS` 改为 `("characters", "scenes", "audio", "videos", "audit", "final")`
- `_STAGE_SUBDIRS` 改为：
  ```python
  _STAGE_SUBDIRS = {
      "after_design":     ["characters", "scenes"],
      "after_refresh":    ["characters", "scenes"],
      "after_storyboard": [],                          # storyboard.md 由 _update_storyboard 无条件重写（见下）
      "after_video_tts":  ["videos", "audio"],
      "after_generation": ["videos", "audio", "final"],
      "after_compose":    ["final"],
      "after_audit":      ["audit"],
  }
  ```
  注意：`storyboard.md` 位于 review 根目录而非任何子目录，`_update_storyboard()` 在 `_update_review_dir` 末尾**无条件**被调用，因此 `after_storyboard` 阶段即使 `active_subdirs=[]` 也不会丢失 storyboard 更新。
- 删除 `_update_prompts()` 方法
- `_update_composed()` 重命名为 `_update_final()`，内部的 `composed_dir` 参数名同步改
- `_update_review_dir` 去掉第 743–744 行的 `for subdir in self._ALL_SUBDIRS: mkdir` 循环；改为每个 `_update_<name>` 方法内部**第一次写 symlink 前**调用 `dir.mkdir(parents=True, exist_ok=True)`
- `_collect_all_assets` 和 `_write_review_summary` 遍历时跳过不存在的子目录（不强制 mkdir）

**验收：** `tests/test_checkpoint.py::test_lazy_subdir_creation`（新增）验证 `after_design` 阶段只创建 `characters/` 和 `scenes/`，其他 4 个子目录不存在。

### 5.3 手术 3 — 新增 `scenes/` 子目录和 `_update_scenes()`

**文件：** `src/videoclaw/drama/checkpoint.py`

- 新增 `_update_scenes(self, scenes_dir: Path)` 方法：
  ```python
  def _update_scenes(self, scenes_dir: Path) -> None:
      refs = getattr(self.series.consistency_manifest, "scene_references", {}) or {}
      if not refs:
          return
      scenes_dir.mkdir(parents=True, exist_ok=True)
      for loc_name, ref_path in refs.items():
          src = Path(ref_path)
          if not src.exists():
              continue
          slug = _slugify(loc_name, max_len=40)
          dst = scenes_dir / f"{slug}{src.suffix}"
          _safe_symlink(src, dst)
  ```
- 在 `_update_review_dir` 的 `active_subdirs` 判断里加 `if "scenes" in active_subdirs: self._update_scenes(review_dir / "scenes")`

**验收：** `tests/test_checkpoint.py::test_scenes_subdir_populated`（新增）fixture 里设置 `series.consistency_manifest.scene_references = {"Pool deck": "/tmp/pool.png", ...}`，跑 `after_design` 后验证 `scenes/pool_deck.png` 是 symlink。

### 5.4 手术 4 — storyboard.md 追加「台词逐字稿」段落

**文件：** `src/videoclaw/drama/checkpoint.py`

- 在 `generate_storyboard_md()` 的最后（`_write_scene_details` 之后）调用新函数 `_write_dialogue_transcript(lines, scenes)`
- `_write_dialogue_transcript` 输出格式：
  ```markdown
  ## 台词逐字稿

  > 用于字幕复核。Seedance 已将字幕烧录到视频，此处为原文备份。

  ### s01 · Title card 'One Month Earlier'. Ivy in server uniform
  **旁白**: One month earlier...

  ### s02 · Guests whisper about Ivy's foolishness
  **台词** (Colton): "You think you can marry me?"

  ### s03 · ...
  ...
  ```
- 空对话 / 空旁白的场景直接跳过（不输出空段落）

**验收：** `tests/test_checkpoint.py::test_storyboard_includes_transcript`（新增）跑 `generate_storyboard_md` 后验证 `storyboard.md` 包含 `## 台词逐字稿` 且每个有 dialogue 的场景都出现在段落里。

### 5.5 手术 5 — `_REVIEW.txt` 增加 `=== Sources ===` 段落

**文件：** `src/videoclaw/drama/checkpoint.py`

- `_write_review_summary` 在 `=== Assets ===` 之后插入 `=== Sources ===`
- 对每个 `_ALL_SUBDIRS`，找到子目录下第一个 symlink，读取 `.readlink().parent`
- 相对路径显示（相对于 repo 根），无 symlink 或空目录显示 `(empty)`

**验收：** `tests/test_checkpoint.py::test_review_txt_sources_section`（新增）跑完一个 checkpoint 后验证 `_REVIEW.txt` 包含 `=== Sources ===` 且至少一个子目录列出了正确的 `projects/...` 前缀。

### 5.6 手术 6 — 统一 `_export.py` 布局

**文件：** `src/videoclaw/cli/drama/_export.py`

- 删除当前的 `00_metadata/ 01_script/ ... 10_audit/` 硬编码布局（lines 170–500+）
- 重写 `drama_export` 命令：
  ```python
  def drama_export(..., copy_mode: bool = False):
      # 1. 加载 series 和 episode
      # 2. 创建一个临时的 CheckpointController（breakpoints=[], interactive=False）
      # 3. 调用 ctrl._update_review_dir(CheckpointStage.AFTER_AUDIT) 生成完整 review 目录
      # 4. 如果 --copy，walk review_dir 把所有 symlink 替换成物理拷贝（for client delivery）
      # 5. 打印 review_dir 路径
  ```
- 实现方式二选一（由 writing-plans 阶段决定）：
  - **选项 A**：把 `_update_review_dir` / `_update_*` 提升为 `CheckpointController` 的 public 方法，export 命令构造一个临时 controller 并调用
  - **选项 B**：把 updater 抽成 `checkpoint.py` 顶层的纯函数 `build_review_dir(series, episode, base_dir, projects_dir) -> Path`，同时被 controller 和 export 调用
  - 推荐选项 B（更易测试、避免在 export 路径里造 dummy manager 依赖）

**验收：** `claw drama export <series_id> -e 1` 产出的目录结构和 `checkpoint.py` 写的完全一致（`diff -r` 应该只差 symlink vs real file，如果用了 `--copy`）。

### 5.7 手术 7 — 一次性清理脚本

**文件：** `scripts/cleanup_legacy_review.py`（新建）

- 删除 `projects/dramas/*/review/`（所有剧的老 review 目录）
- 删除 `docs/deliverables/cumulative_test/`、`docs/deliverables/storyboard_test_drama/`、`docs/deliverables/summary_test/`
- 删除现存 `docs/deliverables/*/ep*/{prompts,composed}/` 两个老子目录（如果存在）
- 打印 dry-run 预览，`--apply` 才真正执行
- **不动** `projects/<uuid>/`

**运行（一次）：**
```bash
python scripts/cleanup_legacy_review.py --apply
```

**验收：** 手动运行后 `ls docs/deliverables/` 只剩真实剧目；`ls projects/dramas/*/` 无 `review` 子目录；`git status` 不受影响（测试数据本来就在 .gitignore 里）。

### 5.8 手术 8 — 测试加固

**文件：** `tests/test_checkpoint.py`、`tests/test_setup.py`

1. **`test_lazy_subdir_creation`**（新增）：after_design 只创建 `characters/` 和 `scenes/`
2. **`test_scenes_subdir_populated`**（新增）：验证 `_update_scenes` 从 `consistency_manifest.scene_references` 拉取
3. **`test_storyboard_includes_transcript`**（新增）：验证 `## 台词逐字稿` 段落
4. **`test_review_txt_sources_section`**（新增）：验证 `_REVIEW.txt` 的 `=== Sources ===` 段落
5. **`test_base_dir_is_required`**（新增）：调用 `review_dir_for_episode(series, ep)`（不传 `base_dir`）应该 mypy 报错 + 运行时 `TypeError`
6. **`test_drama_import_respects_deliverables_dir`**（`tests/test_setup.py` 新增或扩展）：通过 typer runner 跑 `claw drama import`，monkey-patch `get_config().deliverables_dir` 到 tmp_path，断言 `docs/deliverables/` 真实目录没有新增文件
7. **移除 prompts/ 相关断言**（`tests/test_checkpoint.py:529` 行 `for subdir in ("characters", "prompts", ...)`）

**验收：** `pytest tests/test_checkpoint.py tests/test_setup.py -v` 全绿，`mypy src/videoclaw/` 全绿。

---

## 6. 迁移策略

- 代码落地后**不自动删除**老的 `prompts/`、`composed/` 子目录——避免误删用户手动放置的东西
- 手术 7 的一次性清理脚本由用户手动运行，默认 dry-run
- 新 checkpoint 运行时会创建新布局（`scenes/`、`final/`），老布局的残留被忽略
- 无向后兼容代码路径（无 feature flag）

---

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `base_dir` 必传是 breaking change | mypy strict + CI 全量检查，所有调用点一次性更新 |
| 删除 `prompts/` 影响外部依赖 | 已 grep 确认只有 checkpoint.py 自己写，无外部读者 |
| `scenes/` 依赖 `consistency_manifest.scene_references` 可能为空 | `_update_scenes()` 内部对空 manifest graceful return，不 mkdir 空目录 |
| `_export.py` 重写可能破坏现有调用方 | `claw drama export` 的输出目录对比原布局有 breaking change；需要在 HANDOFF.md 注明 |
| 清理脚本误删 | 默认 dry-run，`--apply` 才执行；不动 `projects/<uuid>/` |

---

## 8. 验收标准 (Definition of Done)

1. ✅ `ls docs/deliverables/satan_in_a_suit/ep01_satan_in_a_suit_epis/` 只看到 6 个子目录 + 2 个文件，全部非空
2. ✅ `ls docs/deliverables/` 不含任何 `*_test` 前缀的目录
3. ✅ `ls projects/dramas/*/review/` 报错（目录不存在）
4. ✅ `cat _REVIEW.txt` 显示 `=== Sources ===` 段落，每个子目录列出正确的 projects/ 前缀
5. ✅ `cat storyboard.md` 包含 `## 台词逐字稿` 段落
6. ✅ `pytest tests/` 全绿（≥489 + 新增测试）
7. ✅ `mypy src/videoclaw/` 全绿
8. ✅ `claw drama export <series_id> -e 1` 输出目录结构与 checkpoint 写的完全一致
9. ✅ 跑一次完整 pipeline（`claw drama run 97e8424712d24fb2 -e 1`）后，审计人员打开 `docs/deliverables/satan_in_a_suit/ep01_satan_in_a_suit_epis/` 能一眼看到 8 类审计资产全部就位

---

## 9. 超出范围

以下项目明确**不在**本 spec 范围内，留给未来迭代：

- `projects/<uuid>/` 的 UUID 目录清理（14 个遗留目录）
- 视频生成路径从 `projects/<project_id>/shots/` 迁移到 review 目录（需要动 executor.py）
- `scenes/` 子目录的来源补充：当前 `ConsistencyManifest.scene_references` 是 `scene_designer.py` 写入，但如果 manifest 里没有场景参考图（还没到 design 阶段），`scenes/` 会是空的，需要额外生成流程——不在本 spec 范围
- `claw drama package` 或 tar/zip 打包交付
