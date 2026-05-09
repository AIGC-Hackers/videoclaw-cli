# Audit — videoclaw Agent-CLI 必要特征 vs 当前 commit

> Phase 2 输出。每条特征对照 spec v2（`2026-05-06-agent-cli-distribution-spec.md`）
> 在当前工作树（branch `feat/agent-cli-toolkit`，HEAD `e1c43c3`）上的真实状态。
> 状态符号：✅ 通过 · ⚠ 部分 · ❌ 缺失 / 不达标。
>
> 编号与 spec F1–F13 一一对应。差距条目汇总在文末"差距清单"，每条引向
> Phase 3 任务。

## 审计方法

- 读源码、跑可重现命令、查 git log。
- 对**已实现**特征只标 ✅ + 一句证据；对**部分 / 缺失**特征详写差距。
- 不做修复（Phase 3/4 才修）。

---

## F1 — 稳定 CLI 入口（P0）

| 子项 | 状态 | 证据 |
|---|---|---|
| F1.1 `claw` entry point | ✅ | `pyproject.toml:51-52` `claw = "videoclaw.cli:app"` |
| F1.2 version / info / doctor 三命令 | ✅ | `cli/__init__.py:29-37` (version) · `cli/info.py` · `cli/doctor.py` |
| F1.3 全局 `--json` / `--verbose` | ✅ | `cli/_app.py:68-92` `main_callback` 注册两个全局选项 |

**总评**：✅

---

## F2 — 机读 JSON envelope（P0）

| 子项 | 状态 | 证据 |
|---|---|---|
| F2.1 `{ok, version, command, data, error}` | ✅ | `cli/_output.py:53-60` `OutputContext.emit()` |
| F2.2 `command` 字段反映命令路径 | ✅ | `cli/_output.py:33` `_command` 由各命令在调用前 set |

**总评**：✅。注意：spec 明确**本轮不**强制升级到 `agent-cli/v1` 嵌套 error。

---

## F3 — 退出码契约（P0）

| 子项 | 状态 | 证据 |
|---|---|---|
| F3.1 五段退出码 0/1/2/3/4 | ⚠ partial | grep 全 cli/ 仅见 `Exit(code=1)`（30+ 处）；**未见 2/3/4** |
| F3.2 三方文档一致 | ⚠ partial | `agent-cli.yaml` 注释了五段；`AGENTS.md` 没列；`README.md` 没列；新 SKILL.md 待写 |

**差距 G1**：CLI 实际只用 0 和 1；2 (usage) / 3 (auth) / 4 (blocked) 在合约中承诺
但代码不发。需要：
- (a) 在关键位置（缺 API key、未登录 → 3；CLI 参数错误 → 由 typer.BadParameter 自然走 2）核查 typer 的默认行为
- (b) 至少 doctor / 配置缺失场景显式返回 3
- 文档侧统一三处（README / AGENTS / SKILL.md）

---

## F4 — 配置面（P0）

| 子项 | 状态 | 证据 |
|---|---|---|
| F4.1 `pydantic-settings` env_prefix | ✅ | `config.py:30-35` |
| F4.2 setup.sh XDG → ~/.config → cwd | ✅ | `packaging/setup.sh:72-92` |
| F4.3 chmod 600 | ✅ | `packaging/setup.sh:181` |
| F4.4 `--quiet` 幂等 | ✅ | `packaging/setup.sh:145-157` 空值保留现值 |

**总评**：✅

---

## F5 — Agent-CLI Manifest（informational）（P1）

| 子项 | 状态 | 证据 |
|---|---|---|
| F5.1 validator 通过 | ✅（待重跑确认）| `packaging/agent-cli.yaml` + `packaging/manifest-validate.py` 都存在 |
| F5.2 文档中标注 informational | ❌ | README / AGENTS.md 把 manifest 当作 primary 之一，**未**降级 |

**差距 G2**：F5.2 文档侧 —— 在 README / AGENTS.md / DISTRIBUTION-PLAN.md 中
明确 manifest 是 informational，**首选发现路径是 skills**。

---

## F6 — 三渠道构建可重现（P0）

| 子项 | 状态 | 证据 |
|---|---|---|
| F6.1 wheel 不泄漏 | ✅ | `unzip -l dist/videoclaw-0.1.0-py3-none-any.whl` 仅含 `videoclaw/**`（116 文件，1.1 MB），无 tests/projects/skills/etc |
| F6.1-NEW wheel **必须含** `skills/` | ❌ | skills/ 目录不存在；wheel 也没法装 |
| F6.2 PyInstaller spec | ✅ | `packaging/claw.spec` 存在，excludes ✓ |
| F6.2-NEW PyInstaller bundle skills/ | ❌ | 同上，待 skills/ 创建后在 spec 中加 datas |
| F6.3 Docker 多阶段 + 非 root | ✅ | `packaging/Dockerfile:36-37` `useradd claw` + `USER claw` |
| F6.4 dist-verify.sh 三段 | ✅ | `packaging/dist-verify.sh` 存在；本地未跑（待 Phase 4 二次验证） |

**差距 G3**：skills/ 目录尚未存在，wheel + PyInstaller 都需要把 skills/
作为 package data 打入。具体打包路径：
- wheel：`pyproject.toml [tool.hatch.build.targets.wheel]` 添加 `force-include = { "skills" = "videoclaw/_skills" }` 或类似规则；setup 命令读 `videoclaw/_skills/`
- PyInstaller：`claw.spec` 的 `datas` 中加 `("../skills", "skills")`

---

## F7 — 公共安装器 install.sh（P0）

| 子项 | 状态 | 证据 |
|---|---|---|
| F7.1 OS / arch 检测 | ✅ | `install.sh:55-67` |
| F7.2 拒绝 root | ✅ | `install.sh:48-53` |
| F7.3 SHA256 校验 | ✅ | `install.sh:139-154` |
| F7.4 通道选择 | ✅ | `install.sh:75-81` |
| F7.5 envelope 输出 | ✅ | `install.sh:37-42` `emit_envelope` |
| F7.6 安装后 smoke | ✅ | `install.sh:178-182` |
| F7.7 **新增**：建议 `claw setup` 跑 skills | ❌ | `install.sh:184-190` 只建议 packaging/setup.sh（API key 向导） |

**差距 G4**：install.sh 末尾的 next-steps 提示需要扩展为两步：
1. `claw setup` (skills 安装到 coding agent)
2. `bash $INSTALL_DIR/../share/videoclaw/setup.sh` (API key 向导)

---

## F8 — Agent-callable 端到端（P1）

| 子项 | 状态 | 证据 |
|---|---|---|
| F8.1 tests-external 9 阶段 | ✅ | `tests-external/test_e2e_first_3_shots.py` T1-T4 + T7 默认跑；T5-T8 由 `E2E_REAL_LLM` / `E2E_REAL_VIDEO` 控制 |
| F8.2 MCP shim 不回归 | ✅ | `mcp-shim/tests/` 存在 |
| F8.3 README + AGENTS 给 4 agent 调用片段 | ⚠ partial | AGENTS.md 提了几家但只展开了 Claude Code MCP 一段；README 几乎没提 |

**差距 G5**：F8.3 文档侧 —— 在 README + AGENTS.md 各加 4 个小节：
**Claude Code / OpenClaw / Codex / Cursor**，每节 3 行（install / first-call / first-mutation）。

---

## F9 — Release-ready（P0）

| 子项 | 状态 | 证据 |
|---|---|---|
| F9.1 workflow_dispatch dry-run | ⚠ partial | `release.yml:20-25` 接受 `version` input 但**没有 `dry_run` input**；只有一个 `if: github.event_name == 'workflow_dispatch'` 用于条件控制（line 209，未读完整逻辑） |
| F9.2 三方文档一致 | ⚠ partial | `AGENTS.md:60` 仍写 "P0/P1 delivered, P2 deferred"，没提 release.yml 已 ship；`packaging/DISTRIBUTION-PLAN.md §8` 已知过时；README 第 32-34 行说"Available once v0.1.0 is tagged"，**正确** |
| F9.3 git status 干净 | ⚠ | 有一个 untracked：`mcp-shim/uv.lock` —— 已知，需要 .gitignore |
| F9.4 版本一致 | ⚠ | pyproject `0.1.0` ≡ `__init__.py 0.1.0` ≡ `agent-cli.yaml 0.1.0` ✓；新 SKILL.md frontmatter `version` 待写 |

**差距 G6**：release.yml 没有 `dry_run` input。两条路：
- (a) 加 `dry_run` input（当 true 时跳过 `gh release create` step）—— 改 workflow YAML
- (b) 改用 `gh workflow run` 不实际推 tag，靠 workflow 里的 if 跳过创建 release —— 已经部分实现，但未完整

**差距 G7**：F9.3 把 `mcp-shim/uv.lock` 加进 `.gitignore`（或确认它应该被追踪）

**差距 G8**：F9.2 文档同步 —— `AGENTS.md` 已过时（说 release.yml 是 P2 deferred，实际已 ship）；`packaging/DISTRIBUTION-PLAN.md §8` checkbox 同步

---

## F10 — Skills 目录（P0 ★）

| 子项 | 状态 | 证据 |
|---|---|---|
| F10.* 所有 | ❌ | `ls /Users/moose/Moose/videoclaw/skills` → No such file or directory |

**差距 G9（最大）**：从零写五个 skill：
- `skills/videoclaw-workflow/SKILL.md`（always-active 入口）
- `skills/videoclaw-drama-setup/SKILL.md`
- `skills/videoclaw-models/SKILL.md`
- `skills/videoclaw-checkpoint/SKILL.md`
- `skills/videoclaw-troubleshoot/SKILL.md`

每份需要：frontmatter（含触发动词 description / metadata.requires）+ 阶段化内容
（参考 google `google-agents-cli-workflow/SKILL.md`，~5–15 KB / 份）+ references/ 子目录。
五份合计预估 30–60 KB。

外加 `skills/README.md` 介绍 skills 总览。

外加 `packaging/skills-validate.py`（schema 校验脚本）。

---

## F11 — `claw setup` 命令（P0 ★）

| 子项 | 状态 | 证据 |
|---|---|---|
| F11.* 全部 | ❌ | `cli/setup.py` 不存在；`cli/__init__.py` 没引用 |

**差距 G10**：新写 `src/videoclaw/cli/setup.py`，在 `cli/__init__.py` 加一行
import 注册。功能完整列表见 spec F11。

**Coding agent skills 目录验证（实测当前主机）**：

| Agent | 路径 | 存在 | 备注 |
|---|---|---|---|
| Claude Code | `~/.claude/skills/` | ✅ | 已有 6 个第三方 skills（agent-reach / readchat 等）—— 平铺 `<name>/` 结构 |
| Codex | `~/.codex/skills/` | ✅ | 已有 9 个 skills（remotion / web-research 等）—— 同样平铺 |
| OpenClaw | `~/.openclaw-autoclaw/skills/` | ✅ | 命名带版本号 `<name>-<version>/`（如 `1password-1.0.1`）—— **格式不同** |
| Cursor | `~/.cursor/skills/` | ❌ | 无此目录；Cursor 用 `~/.cursor/projects/` 或 `.cursorrules` |
| Gemini CLI | `~/.gemini/skills/` | ❌ | 无；有 `~/.gemini/extensions/` 路径未确认 |

**差距 G10.x**：
- (i) OpenClaw 命名约定不同（带版本号），setup 实现需要 per-agent 命名策略
- (ii) Cursor / Gemini CLI 安装路径需要查官方文档。建议本轮：
  - Cursor → 安装到 `~/.cursor/rules/videoclaw.md`（rules 文件而非 skills 目录）或暂不支持，标 P2
  - Gemini CLI → audit 中暂不实现，等 G10 任务时确认

---

## F12 — README 模板化（P0 ★）

| 子项 | 状态 | 证据 |
|---|---|---|
| F12.1 三段表（Get Started / Skills / Commands） | ❌ | 当前 README 是 "Install / Why / Features / ClawFlow / Architecture / Models / Contributing" 形态 |
| F12.2 Works with 列表 ≥4 agent | ❌ | README 当前未列 |
| F12.3 一句话 Pitch ≤25 字 | ⚠ | 现有 "Orchestrate multiple AI models. Automate entire video pipelines." 是 16 字，OK，但未在 google 风格 hero 区出现 |
| F12.4 FAQ "Is this an alternative to coding agents?" | ❌ | 当前无 FAQ |

**差距 G11**：README 重排。这是面向**用户**的文档，不是把现有 README 删掉，
而是在顶部加 google 风格的 Get Started / Skills / Commands 三表，原 Why /
Features / Architecture 等内容下移作"Reference"区。需要权衡 README 长度
（google's README 是 8553 字符，比较紧凑）。

---

## F13 — RELEASE_NOTES.md（P1 ★）

| 子项 | 状态 | 证据 |
|---|---|---|
| F13.* 全部 | ❌ | 文件不存在 |

**差距 G12**：新写 `RELEASE_NOTES.md`。0.1.0 段从 git log 提炼三类 bullet
（feat / fix / docs）。

---

## 差距清单（汇总，按优先级 + 依赖序）

| ID | 关联 | 优先级 | 描述 | 估文件数 |
|---|---|---|---|---|
| **G9**  | F10    | P0 | 写 5 份 SKILL.md + skills/README.md + skills-validate.py（**最大块**） | ~8 |
| **G10** | F11    | P0 | `src/videoclaw/cli/setup.py` + `cli/__init__.py` 注册 + 单元测试 | 3 |
| **G3**  | F6.1/2 | P0 | wheel 与 PyInstaller bundle skills/ 作为 package data | 2 (pyproject.toml + claw.spec) |
| **G11** | F12    | P0 | README 重排为 google 三段表风格 + Works with 列表 + FAQ | 1 |
| **G4**  | F7.7   | P0 | install.sh 末尾建议链增加 `claw setup` | 1 |
| **G5**  | F8.3   | P0 | README + AGENTS.md 各加 4 个 per-agent 调用块 | 2 |
| **G2**  | F5.2   | P1 | manifest 降级 informational 文档同步 | 3 (README/AGENTS/DIST-PLAN) |
| **G8**  | F9.2   | P1 | AGENTS.md / DIST-PLAN.md / README §8 同步真实状态 | 2-3 |
| **G12** | F13    | P1 | 新写 RELEASE_NOTES.md 0.1.0 条目 | 1 |
| **G1**  | F3     | P1 | 退出码 2/3/4 实现校验 + 文档同步 | 1-3 |
| **G6**  | F9.1   | P1 | release.yml 加 dry_run input | 1 |
| **G7**  | F9.3   | P2 | .gitignore 添加 mcp-shim/uv.lock | 1 |

**P0 差距**：6 项 (G3 / G4 / G5 / G9 / G10 / G11)
**P1 差距**：5 项 (G1 / G2 / G6 / G8 / G12)
**P2 差距**：1 项 (G7)
**合计**：12 项 ≤ spec 上限 12 ✓

依赖顺序（关键路径）：
1. **G9**（写 skills）独立，可早开始
2. **G10**（claw setup）依赖 G9 至少有一份 SKILL.md 才能跑安装测试
3. **G3**（bundle skills）依赖 G9 完成
4. **G4**（install.sh 引用 setup）依赖 G10
5. **G11/G5/G8/G2/G12** 文档类，并行
6. **G1**（退出码）独立
7. **G6**（dry_run）独立
8. **G7**（.gitignore）小改

并行机会高 —— 8 个独立任务，2 个串行依赖（G10→G3→G4 链 + G9 是 G10/G3 的前置）。

---

## Open Questions（提到 Phase 3 任务化前需要决断）

1. **Cursor / Gemini CLI 支持范围**：
   - Cursor 没有平铺 skills 目录，是写到 `~/.cursor/rules/videoclaw.md`（项目级 `.cursorrules` 暂不动 home 全局）还是直接标 **P2 deferred**？
   - Gemini CLI 的官方 skill / extension 注入路径需要查 docs 才能定。本轮要支持吗？
   
   **我的建议**：本轮只稳定支持 Claude Code / OpenClaw / Codex 三家（这三家本机已实测有 `skills/`）；Cursor 写一段 README 指引用户手动复制；Gemini CLI 标 P2 deferred 但 SKILL.md 中保留 placeholder。

2. **OpenClaw 版本号命名**：实测 OpenClaw skills 目录里都是 `<name>-<version>` 格式。`claw setup` 装到 OpenClaw 时要不要把目录名变成 `videoclaw-workflow-0.1.0`？
   
   **我的建议**：是。setup 实现里加 per-agent 命名策略（dataclass `AgentTarget(name, skills_dir, naming: Literal["flat","versioned"])`）。

3. **wheel 中 skills/ 的打包路径**：spec 写了 `videoclaw/_skills/`，但有个 trade-off：
   - (a) `videoclaw/_skills/`：用 `from importlib.resources import files; files("videoclaw") / "_skills"` 取 → 干净
   - (b) `share/videoclaw/skills/`（FHS 风格）：installer 可在 wheel-install 后从 `sys.prefix/share/...` 找 → 兼容 PyInstaller 的 `--add-data` 更好
   
   **我的建议**：(a)，python idiomatic + 跨平台；PyInstaller spec 也用 `("../skills", "videoclaw/_skills")` 对齐。

4. **退出码 2/3/4 实现位置**：
   - 2 (usage)：typer.BadParameter 默认 exit 2，本来就有，只需文档化
   - 3 (auth)：缺 API key 时 `claw doctor` 应返回 3 而非 1
   - 4 (blocked)：什么情况算 blocked？建议：`install.sh` 已用（`unsupported os/arch` → 4）；CLI 暂时不强制使用 4
   
   **我的建议**：本轮 G1 限定为 (a) typer 的 2 走自然路径，(b) `cli/doctor.py` 中缺 key 改返 3，(c) 4 暂不在 CLI 中使用，仅保留给 install.sh。

---

**Phase 2 review checkpoint**：用户对差距清单 + Open Questions 1-4 给出决策后，
进入 Phase 3（任务拆分）。
