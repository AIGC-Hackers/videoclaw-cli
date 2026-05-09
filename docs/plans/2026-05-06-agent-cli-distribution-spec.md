# Spec — videoclaw Agent-callable Distributable CLI (M002)

> Phase 1 输出（spec-driven-development）。本文件是 audit / fix / reverify
> 的唯一事实源；所有差距、任务、验证都回引这里的特征编号 (F1–F13)。
>
> **本版本（v2）变更**：参考 [google/agents-cli](https://github.com/google/agents-cli)
> 的 "CLI + Skills + setup" 模板，新增 F10–F13；旧 F8.2 (MCP) 降级 P2 informational；
> 放开 `src/videoclaw/cli/setup.py` 单一新文件的修改许可。

## Objective

让 `claw` CLI 成为可被 **Claude Code / OpenClaw / Codex / Cursor / 任意 coding agent**
**无缝**调用的 release-ready 可分发 CLI。"无缝"的具体形态参考 google/agents-cli：

1. 一条命令安装：`uvx --from <wheel-url> videoclaw setup` —— 自动探测已安装的
   coding agent，把 videoclaw 的 skills 拷贝进每家的 skills 目录。
2. coding agent 启动后立即"知道怎么用"：用户说 "用 videoclaw 把这个剧本生成短剧"，
   agent 加载相应 skill，按 skill 中的阶段化指引调用 `claw drama …`。
3. CLI 独立可用：不依赖 skill 也可被任何 agent 通过 `Bash("claw …")` 直接驱动。

**User story**：任意 coding agent 用户，在 macOS arm64 / Linux x86_64 主机上，从
零开始 ≤ 60 秒拿到可工作的 `claw` + 已安装的 skills；让 coding agent 用一句话
"做一集短剧" 就能自动完成 `drama new → plan → design → run → export`。

**完成形态**：F1–F13 全部 ✅ → 二次部署验证（本地 wheel + binary + skills install
+ 在 Claude Code / Codex 实际加载 skill 调用 `claw` 一次）全绿。**不**触发真实
PyPI 发布或 GitHub Release。

## Tech Stack（沿用 pyproject.toml）

- Python ≥3.12 · Typer · pydantic v2 + pydantic-settings · litellm · httpx
- Build：hatchling (wheel) · PyInstaller 6.x (binary) · Docker multi-stage
- 验证：pytest (asyncio_mode=auto) · ruff · mypy strict
- CI：GitHub Actions (`.github/workflows/release.yml`，已存在)
- **新增**：skills 文件（纯 markdown，无 runtime 依赖）
- 分发渠道（按"无缝接入 agent"重新优先级排序）：
  1. **Skills + CLI 一体路径**（首选）：`uvx --from <gh-release-wheel> videoclaw setup`
  2. `uv tool install videoclaw`（CLI only，agent 自行管理 skills）
  3. `bash install.sh` PyInstaller binary（无 Python 主机）
  4. `docker run videoclaw-cli`（容器化）
  5. wheel 直装

## Commands

```bash
# build
uv build --wheel --out-dir dist/                                # → dist/videoclaw-0.1.0-py3-none-any.whl
uv run pyinstaller packaging/claw.spec --clean --noconfirm      # → dist/claw
docker build -t videoclaw-cli -f packaging/Dockerfile .         # → image

# 一键三段构建 + smoke
bash packaging/dist-verify.sh                                   # wheel + binary + docker
STAGE_DOCKER=0 bash packaging/dist-verify.sh                    # 跳过 docker

# manifest 校验
python packaging/manifest-validate.py packaging/agent-cli.yaml  # exit 0 = pass

# 模拟"从 release 安装" + skills 注入
INSTALL_DIR="$(mktemp -d)" CHANNEL=binary GH_OWNER=AIGC-Hackers \
    GH_REPO=videoclaw-cli VERSION=0.1.0 bash install.sh
"$INSTALL_DIR/claw" setup --dry-run                             # 探测 agent 但不写入
"$INSTALL_DIR/claw" setup                                       # 实际写入 skills 到 ~/.claude/skills/ 等
"$INSTALL_DIR/claw" setup --uninstall                           # 清理（幂等）

# setup wizard
bash packaging/setup.sh --quiet                                 # → videoclaw-setup/v1 envelope ok=true

# skill install via uvx (匹配 google/agents-cli UX)
uvx --from "https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.0/videoclaw-0.1.0-py3-none-any.whl" \
    videoclaw setup
# 或本地构建产物
uvx --from "$(pwd)/dist/videoclaw-0.1.0-py3-none-any.whl" videoclaw setup

# 端到端 agent 调用测试
uv run pytest tests-external/ -v
uv run pytest mcp-shim/tests/ -v                                # 不回归 MCP 路径

# Skills 内容校验（每个 SKILL.md frontmatter 完整 + name 与目录名一致）
python packaging/skills-validate.py skills/                     # 新增脚本

# 单元 / 集成 / lint
make test
make lint

# Release workflow dry-run
gh workflow run release.yml --ref feat/agent-cli-toolkit -f dry_run=true
gh run watch
```

## Project Structure

```
videoclaw/
├── README.md                        # 重排：Pitch / Get Started / Skills 表 / Commands 表 / FAQ（仿 google/agents-cli）
├── RELEASE_NOTES.md                 # ★ 新增：0.1.0 起每个 release 一段
├── AGENTS.md                        # 顶层 agent quickstart（保留）
├── LICENSE                          # 保留 Modified-MIT，不改
├── install.sh                       # 公开一键安装器
├── pyproject.toml                   # CLI 源（保留 src/ in repo，不复制 google "wheel-only" 模型）
├── src/videoclaw/
│   └── cli/
│       └── setup.py                 # ★ 新增：唯一允许的 src/ 改动 — `claw setup` 命令实现
├── skills/                          # ★ 新增：核心交付物
│   ├── README.md                    # 介绍 skills 总览 + 安装方式
│   ├── videoclaw-workflow/          # always-active 入口
│   │   ├── SKILL.md                 # 阶段化：drama new → plan → design → run → audit → export
│   │   └── references/
│   │       └── pipeline-internals.md
│   ├── videoclaw-drama-setup/       # `drama new` / `drama import` / `script` 阶段
│   │   ├── SKILL.md
│   │   └── references/
│   ├── videoclaw-models/            # 视频 adapter 选择 (seedance / kling / minimax / mock)
│   │   └── SKILL.md
│   ├── videoclaw-checkpoint/        # 断点恢复 (`drama checkpoint-list/show/resume/redo`)
│   │   └── SKILL.md
│   └── videoclaw-troubleshoot/      # `claw doctor` + 常见错误 + 退出码解析
│       └── SKILL.md
├── packaging/
│   ├── agent-cli.yaml               # 保留但标注 informational
│   ├── manifest-validate.py
│   ├── skills-validate.py           # ★ 新增：校验 skills/ 内容
│   ├── setup.sh                     # 配置向导（API keys，不动）
│   ├── dist-verify.sh
│   ├── claw.spec
│   ├── Dockerfile
│   ├── _entry.py
│   ├── pyproject.overlay.toml
│   ├── DISTRIBUTION-PLAN.md
│   ├── AUDIT.md                     # 现状审计（保留作历史档案）
│   └── envelope_shim.md
├── mcp-shim/                        # 次要通道，保不回归
├── tests-external/                  # 9 阶段端到端
├── tests/                           # 不动
├── .github/workflows/release.yml    # 已存在
└── docs/plans/
    ├── 2026-05-06-agent-cli-distribution-spec.md      # ← 本 spec (Phase 1)
    ├── 2026-05-06-agent-cli-feature-audit.md          # ← Phase 2 产物
    └── 2026-05-06-agent-cli-tasks.md                  # ← Phase 3 产物
```

**硬约束**（v2 调整）：
- 只允许新增 **一个** src/ 文件：`src/videoclaw/cli/setup.py`（实现 `claw setup`）
- 不允许修改任何已存在的 `src/videoclaw/**` 文件，**例外**：在 `cli/__init__.py`
  添加一行 `from . import setup as _setup` 之类的注册（必要的最小副作用）
- 所有其他变更落在 `packaging/` `mcp-shim/` `skills/` `install.sh` `docs/`
  `.github/` `README.md` `RELEASE_NOTES.md`

## Necessary Features（F1–F13 = 审计基线）

### F1 — 稳定 CLI 入口（P0）
- F1.1 `claw` binary 在 PATH（pyproject `[project.scripts]`）
- F1.2 `claw version` / `claw --json info` / `claw --json doctor` 零参数零环境也能成功
- F1.3 全局 `--json/-j` 与 `--verbose/-v` 在所有命令可用

### F2 — 机读 JSON envelope（P0）
- F2.1 每条 `--json` 输出 `{ok, version, command, data, error}`
- F2.2 envelope 中 `command` 字段反映命令路径

### F3 — 退出码契约（P0）
- F3.1 `0` ok · `1` runtime · `2` usage · `3` auth · `4` blocked
- F3.2 manifest + README + AGENTS.md + 新 skills 中 troubleshoot 一致

### F4 — 配置面（P0）
- F4.1 `pydantic-settings` `env_prefix="VIDEOCLAW_"`
- F4.2 `setup.sh` 配置路径解析顺序：`$XDG_CONFIG_HOME/videoclaw/` → `~/.config/videoclaw/` → repo cwd
- F4.3 配置文件 `chmod 600`
- F4.4 `setup.sh --quiet` 幂等

### F5 — Agent-CLI Manifest（informational）（P1，降级）
- F5.1 `packaging/agent-cli.yaml` 通过 validator
- F5.2 README / docs 中明确 manifest 是 **informational**（skills 是首选发现路径，manifest 给走 manifest-driven 路径的 orchestrator 用）

### F6 — 三渠道构建可重现（P0）
- F6.1 wheel 不泄漏 `tests/` `projects/` `models_cache/` `mcp-shim/` `packaging/` `docs/deliverables/` `skills/`
  - **新增**：wheel **必须**包含 `skills/` 作为 package data，否则 `claw setup` 找不到内容；具体打包路径在 audit 中确定
- F6.2 PyInstaller 单文件构建产出可执行 `dist/claw`，excludes 包含 torch/diffusers/transformers/fastapi/uvicorn
  - **新增**：PyInstaller 也必须 bundle `skills/` 作为 data
- F6.3 Docker 多阶段镜像 `videoclaw-cli`，runtime 非 root
- F6.4 `dist-verify.sh` 三段串行通过

### F7 — 公共安装器 install.sh（P0）
- F7.1 检测 OS / arch
- F7.2 拒绝 root（exit 4）
- F7.3 SHA256SUMS 校验
- F7.4 通道选择：auto / uv / binary
- F7.5 末尾输出 `videoclaw-install/v1` envelope
- F7.6 安装后 smoke `claw version` 通过
- F7.7 **新增**：安装成功后建议下一步 `claw setup`（跑 skills 安装到 coding agent）

### F8 — Agent-callable 端到端（P1）
- F8.1 `tests-external/test_e2e_first_3_shots.py` 9 阶段；T9 真实视频允许在缺 ARK key 时 skip
- F8.2 MCP shim 不回归（次要通道）—— **从 P0 降到 P2 informational**
- F8.3 README + AGENTS.md 给 Claude Code / OpenClaw / Codex / Cursor 各一段调用片段

### F9 — Release-ready（P0）
- F9.1 `release.yml` workflow_dispatch dry-run 通过
- F9.2 README / AGENTS.md / packaging/DISTRIBUTION-PLAN.md / RELEASE_NOTES.md 与 HEAD 一致
- F9.3 `git status` 干净
- F9.4 三处版本号一致：`pyproject.version` ≡ `agent-cli.yaml.version` ≡ `claw version` 输出 ≡ 每个 SKILL.md `metadata.version`

### F10 — Skills 目录（仿 google/agents-cli，P0 ★ 新增）

`skills/` 下五个 skill 目录（命名前缀 `videoclaw-`）：

| Skill | 触发条件（description 字段）| Always-active |
|---|---|---|
| `videoclaw-workflow` | "用 videoclaw 做短剧" / "build a drama with videoclaw" / 进入 videoclaw 工作 | ✅ 入口 |
| `videoclaw-drama-setup` | "新建剧集" / "import 剧本" / "写脚本" / `drama new\|import\|script` | 按需 |
| `videoclaw-models` | "选视频模型" / "调 adapter" / `model list\|info` / `drama run` 之前 | 按需 |
| `videoclaw-checkpoint` | "断点恢复" / "重新生成镜头" / `checkpoint-*` / 任何 stage 失败 | 按需 |
| `videoclaw-troubleshoot` | `claw doctor` 报错 / 任何非零 exit / 配置缺失 | 按需 |

每个 SKILL.md 必须：
- F10.1 frontmatter 含 `name` / `description`（含触发动词）/ `metadata.author/license/version` / `metadata.requires.bins=[claw]` / `metadata.requires.install`
- F10.2 内容阶段化（仿 google：Phase 0 Understand → Phase 1+ 操作）
- F10.3 命令例子用真实 `claw …` 调用（在 audit 中可执行验证）
- F10.4 跨 skill 引用：`/videoclaw-drama-setup` 形式跳转
- F10.5 `references/` 子目录承载长 reference 内容（避免 SKILL.md 太长）
- F10.6 `version` 与 pyproject 一致（F9.4）
- F10.7 中文与英文双向友好（剧本可中文，skill 命令片段保留英文方便机器解析）

`packaging/skills-validate.py` 校验：每个目录有 SKILL.md / frontmatter 解析通过 / `name == 目录名` / version 与 pyproject 一致。

### F11 — `claw setup` 命令（P0 ★ 新增）

新增 `src/videoclaw/cli/setup.py`，在主 Typer app 注册 `claw setup`。能力：

- F11.1 探测已安装 coding agent，目录映射：
  | Agent | Skills 目录 | 配置文件 |
  |---|---|---|
  | Claude Code | `~/.claude/skills/` | `~/.claude/CLAUDE.md` |
  | OpenClaw / autoclaw | `~/.openclaw-autoclaw/skills/` | `~/.openclaw-autoclaw/AGENTS.md` |
  | Codex | `~/.codex/skills/` | `~/.codex/AGENTS.md` |
  | Cursor | `~/.cursor/skills/`（或 `~/.cursor/projects/.../`，audit 确认） | `~/.cursor/.cursorrules` |
  | Gemini CLI | `~/.gemini/extensions/` 或自动发现 | `~/.gemini/GEMINI.md` |
- F11.2 `claw setup` 默认对所有探测到的 agent 执行：把 wheel/binary 自带的
  `skills/videoclaw-*/` 拷贝（或 symlink）到对应 agent 目录
- F11.3 `--dry-run`：列出会写入的目标但不执行
- F11.4 `--agent <name>`：只对指定 agent 安装
- F11.5 `--uninstall`：移除已安装的 videoclaw skills（按目录前缀 `videoclaw-` 识别）
- F11.6 幂等：重复运行不会累积副本，已存在版本相同则 skip + 输出 noop
- F11.7 输出 `videoclaw-setup-skills/v1` envelope：
  ```json
  {
    "schema": "videoclaw-setup-skills/v1",
    "ok": true,
    "agents_detected": ["claude_code", "codex"],
    "skills_installed": [
      {"agent": "claude_code", "path": "/Users/x/.claude/skills/videoclaw-workflow/", "version": "0.1.0", "action": "created"}
    ],
    "skills_skipped": [],
    "next_steps": ["agent restart 后说 '用 videoclaw 做一集短剧' 即可触发"]
  }
  ```
- F11.8 退出码：探测到 0 个 agent → 0（带警告 envelope）；写入失败 → 1
- F11.9 `--json` / `--verbose` 全局标志兼容

### F12 — README 模板化（P0 ★ 新增）

按 google/agents-cli README 三段表式结构重排：

```markdown
# videoclaw — Agent OS for AI Video Generation

> Turn your favorite coding agent into an expert at producing TikTok-format dramas.

**Works seamlessly with:** Claude Code · OpenClaw · Codex · Cursor · Gemini CLI · *and any coding agent.*

## Get Started

1. Install: `uvx --from <wheel-url> videoclaw setup`
2. Open your coding agent
3. Say: "用 videoclaw 把 examples/script.md 做成一集短剧"

## Skills

| Skill | What your coding agent learns |
|---|---|
| videoclaw-workflow | drama 完整生命周期：plan → design → run → audit → export |
| ... |

## Commands

| Command | What it does |
|---|---|
| `claw setup` | Install CLI + skills to coding agents |
| `claw drama new "<synopsis>"` | Create a new drama from synopsis |
| ... |

## FAQ
...
```

- F12.1 三段表（Get Started / Skills / Commands）齐全
- F12.2 Works with 列表覆盖 ≥ 4 个 coding agent
- F12.3 一句话 Pitch ≤ 25 字
- F12.4 FAQ 至少回答："Is this an alternative to coding agents?"（答：No, it's a tool for coding agents）

### F13 — RELEASE_NOTES.md（P1 ★ 新增）

- F13.1 文件存在
- F13.2 0.1.0 段含：feat / fix / docs 三类
- F13.3 schema 与 google/agents-cli 风格一致：`## [version] - YYYY-MM-DD` + bullet 列表

## Code Style

继承现有约定：

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from videoclaw.cli._output import print_json_envelope


def setup(
    agent: str | None = typer.Option(None, "--agent", "-a"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    uninstall: bool = typer.Option(False, "--uninstall"),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Install videoclaw skills into detected coding agents."""
    ...
```

- ruff py312 / line-length 100 / 保留中文
- mypy strict
- shell：POSIX sh `set -eu`，envelope 写 stdout，info/err 写 stderr

**SKILL.md 风格**（参考 google/agents-cli/skills/google-agents-cli-workflow/SKILL.md）：
- frontmatter YAML 严格，description 是多行 block scalar (`>`)
- 文档标题 `# <Role> Guide`
- 立刻一段 STOP/READ-FIRST 防御性指引
- 阶段化（Phase 0 Understand → Phase 1+ 实操）
- 表格映射"用户说 → CLI flag"
- 跨 skill `/skill-name` 引用

## Testing Strategy

- 单元 / 集成（不动）：`make test`
- MCP 不回归：`uv run pytest mcp-shim/tests/ -v`
- External 9 阶段：`uv run pytest tests-external/ -v`
- Manifest schema：`python packaging/manifest-validate.py packaging/agent-cli.yaml`
- **Skills schema**：`python packaging/skills-validate.py skills/`（**新写**）
- 构建三段：`bash packaging/dist-verify.sh`
- Install 模拟：`INSTALL_DIR=$(mktemp -d) CHANNEL=binary bash install.sh`
- Skills install 模拟：在临时 `HOME` 下跑 `claw setup`，断言 `~/.claude/skills/videoclaw-workflow/SKILL.md` 存在且 frontmatter `name` 正确
- Setup 幂等：连跑两次 `claw setup`，第二次输出 envelope `skills_skipped` 列表 = 第一次 `skills_installed`
- 真实 agent 集成（手动）：在主 `~/.claude/skills/` 下安装后，启动 Claude Code 让其响应 "用 videoclaw 做短剧" 触发 skill 的 description

新写测试 TDD：先失败、再修。

## Boundaries

**Always**
- 每次 commit 前 `make lint`
- 修改 packaging/*.sh / install.sh 后 `bash packaging/dist-verify.sh` 至少 wheel + binary 段
- 修改 manifest 后 validator pass
- **修改任何 SKILL.md 后 `python packaging/skills-validate.py skills/` pass**
- 提交后立即 `git push`
- 三方文档（README / AGENTS.md / RELEASE_NOTES.md / DISTRIBUTION-PLAN.md）任一变更同步另几份

**Ask first**
- 修改 `pyproject.toml` 的 dependencies / version / entry_points
- 修改 `.github/workflows/release.yml`
- **任何会产生公开制品的命令**（`gh release create` / `docker push` / `uv publish` / `git tag v0.1.0 && git push --tags`）
- 修改 `src/videoclaw/**` 中 **`cli/setup.py` 之外**的任何文件（包括 `cli/__init__.py` 注册新 setup 命令的最小副作用 —— 这一行需要明确报告）
- 切换 git branch（当前 `feat/agent-cli-toolkit`）
- **PyPI name 申请 / 注册**

**Never**
- 不打 tag 创建 GitHub Release
- 在 install.sh / setup.sh / SKILL.md 中硬编码 API key
- 把 `projects/` `models_cache/` `docs/deliverables/` `tests/` 打进 wheel
- 在 mcp-shim 之外占用 `claw mcp-server` 命令命名
- skip pre-commit / signing hooks（`--no-verify` / `--no-gpg-sign`）
- 在 SKILL.md 写出过时的 `claw` 命令名（如已废弃的 stage-* 旧形态）
- **不在 SKILL.md 里塞业务剧情数据**（剧集信息走 CLI/配置/资产，零硬编码原则同样适用 skills）

## Success Criteria（gated 顺序）

1. **审计完成**（Phase 2 → `2026-05-06-agent-cli-feature-audit.md`）
   F1–F13 每条状态标注（✅ / ⚠ partial / ❌ 缺失），差距列表 ≤ 12 项。

2. **任务拆分完成**（Phase 3 → `2026-05-06-agent-cli-tasks.md`）
   每条差距对应一个任务，每个任务 ≤ 5 文件、有验证命令。

3. **修复全部完成**：tasks 全部 ✅，每个任务 commit + push 到远程。

4. **二次部署验证全绿**：
   - `make lint` ✓
   - `make test` ✓
   - `python packaging/manifest-validate.py packaging/agent-cli.yaml` exit 0 ✓
   - `python packaging/skills-validate.py skills/` exit 0 ✓
   - `bash packaging/dist-verify.sh` 三段全绿 ✓（无 docker 时 STAGE_DOCKER=0 注明）
   - `INSTALL_DIR=$(mktemp -d) CHANNEL=binary bash install.sh` → envelope ok=true ✓
   - `bash packaging/setup.sh --quiet` → envelope ok=true ✓
   - **临时 HOME 下 `claw setup` 写入 ≥ 1 个 agent 的 skills 目录** ✓
   - **`claw setup` 第二次跑输出 skills_skipped 等于第一次 skills_installed** ✓
   - **真实 Claude Code 实例（用户主 HOME）加载 `videoclaw-workflow` skill 成功** ✓
   - `tests-external/` 9 阶段全过（T9 缺 key 允许 skip） ✓
   - `mcp-shim/tests/` 全过 ✓

5. **三方文档一致**：README / AGENTS.md / DISTRIBUTION-PLAN.md / RELEASE_NOTES.md / 5 份 SKILL.md 与 HEAD 状态对齐。

6. **Release-ready**：
   - `git status` 干净
   - 四处版本号一致（pyproject / manifest / `claw version` / 每个 SKILL.md frontmatter）
   - `release.yml` workflow_dispatch dry-run 通过
   - 准备好接入 `git tag v0.1.0 && git push --tags`，**本轮不执行**

## Open Questions

进入 Phase 2 audit 时若发现以下情况立刻回到用户：

- Cursor 的 skills 目录约定不明 —— audit 中确认或暂时跳过 Cursor，标注 P2 deferred
- Gemini CLI 的 skills 装载机制（extensions vs skills）audit 时确认
- T9 真实视频测试是否允许 skip（已在 spec 中默认 yes，audit 中复核）
- 如果 audit 发现修改 `cli/__init__.py` 注册 setup 命令需要超过一行（典型情况：subcommand registry 是 dict-based 而非 import-based），是否升级 src/ 改动权限

---

**Phase 1 review checkpoint**：用户 ✅ 之后，进入 Phase 2 (audit)。
