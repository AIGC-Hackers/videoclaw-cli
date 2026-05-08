# Tasks — videoclaw Agent-CLI 修复 + 二次部署验证

> Phase 3 输出。每个 task 对应 `2026-05-06-agent-cli-feature-audit.md`
> 中的差距 G1–G12，含 acceptance / verify 命令 / 触及文件 / 依赖。
>
> 命名：T## 序号；执行顺序 = 依赖序（部分可并行）。
> 完成约定：每个 task 完成 → `make lint` → 单独 commit → `git push`。

## 依赖图（关键路径）

```
T16 (gitignore)        T15 (release.yml dry_run)        T14 (exit codes)
   ⏵ 独立                 ⏵ 独立                          ⏵ 独立 (含 src/ 范围扩展)

T1 (skills scaffold + validator)
   ⏵ T2 (workflow SKILL)
   ⏵ T3 (drama-setup SKILL)         可并行 (T2-T6)
   ⏵ T4 (models SKILL)
   ⏵ T5 (checkpoint SKILL)
   ⏵ T6 (troubleshoot SKILL)
        ⏵ T7 (bundle skills in wheel + PyInstaller)
            ⏵ T8 (claw setup 命令)
                ⏵ T9 (install.sh 链入 claw setup)

T10 (README 三段表)
T11 (per-agent quickstart 4 块)      可并行
T12 (manifest informational + 文档同步)
T13 (RELEASE_NOTES.md)

──────────────────────────────────────
最终：T17 二次部署验证（所有任务完成后跑）
```

---

## Track A — Skills + setup（关键路径）

### T1 — Skills 目录脚手架 + validator

**关联**：G9（部分）

**Acceptance**：
- `skills/` 5 个子目录 + `skills/README.md` 创建
- 每份 SKILL.md 至少含完整 frontmatter（name / description / metadata.{author,license,version,requires}）+ 占位 H1 + ≥1 段说明
- `packaging/skills-validate.py` 检查：每目录有 SKILL.md、frontmatter 解析通过、`name == 目录名`、version 与 pyproject 一致

**Files**（NEW）：
- `skills/README.md`
- `skills/videoclaw-workflow/SKILL.md`
- `skills/videoclaw-drama-setup/SKILL.md`
- `skills/videoclaw-models/SKILL.md`
- `skills/videoclaw-checkpoint/SKILL.md`
- `skills/videoclaw-troubleshoot/SKILL.md`
- `packaging/skills-validate.py`

**Verify**：
```bash
python packaging/skills-validate.py skills/    # exit 0
ls skills/videoclaw-*/SKILL.md | wc -l         # → 5
```

---

### T2 — `videoclaw-workflow` 完整 SKILL.md（always-active 入口）

**关联**：G9

**Acceptance**：
- 阶段化内容覆盖 Phase 0 (Understand) → Phase 7 (Observe / Audit)，对应 drama 全流程：`drama new/import → plan → design-{characters,scenes,cover} → assign-voices → run → audit → export`
- 跨 skill 引用：用 `/videoclaw-drama-setup` `/videoclaw-models` `/videoclaw-checkpoint` `/videoclaw-troubleshoot`
- 命令片段全部取自 CLAUDE.md 当前 commands 表（**与 `claw drama --help` 对齐**）
- 长 reference 内容下沉到 `references/pipeline-internals.md`
- ~10–15 KB

**Files**：
- `skills/videoclaw-workflow/SKILL.md`（覆写 T1 占位）
- `skills/videoclaw-workflow/references/pipeline-internals.md`（NEW）

**Verify**：
```bash
python packaging/skills-validate.py skills/                                      # exit 0
grep -c "/videoclaw-" skills/videoclaw-workflow/SKILL.md                         # ≥4
diff <(grep -oE 'claw [a-z-]+' skills/videoclaw-workflow/SKILL.md | sort -u) \
     <(uv run claw drama --help 2>/dev/null | grep -oE 'claw [a-z-]+' | sort -u) # 命令一致性手动审阅
```

---

### T3 — `videoclaw-drama-setup` 完整 SKILL.md

**关联**：G9

**Acceptance**：
- 三种入口对比表：`drama new --concept`（LLM 写稿）vs `drama import --script`（锁定）vs `drama script`（编辑）
- 每种入口的"什么时候用"判定指引
- 包含 `--lang zh|en` / `--title` / `--episode N` 等关键 flag 说明
- ~5 KB

**Files**：
- `skills/videoclaw-drama-setup/SKILL.md`（覆写 T1 占位）

**Verify**：`python packaging/skills-validate.py skills/` exit 0

---

### T4 — `videoclaw-models` 完整 SKILL.md

**关联**：G9

**Acceptance**：
- 7 个 video adapter 表：seedance / seedance_byteplus / kling / minimax / zhipu / openai / mock
- 选择规则：默认 Seedance 2.0；mock 用于测试；其他在何种场景启用
- 平台约束记忆："Seedance 拒绝 base64 data URIs（必须 HTTPS URL）" / "Privacy Information filter 拒绝写实女性人脸（必须 stylized）"
- ~4 KB

**Files**：`skills/videoclaw-models/SKILL.md`

**Verify**：
```bash
python packaging/skills-validate.py skills/                                  # exit 0
# 确认 7 个 adapter 名都在文件里
for a in seedance seedance_byteplus kling minimax zhipu openai mock; do
    grep -q "$a" skills/videoclaw-models/SKILL.md || echo "MISSING: $a"
done
```

---

### T5 — `videoclaw-checkpoint` 完整 SKILL.md

**关联**：G9

**Acceptance**：
- 5 个 checkpoint 子命令表：`drama checkpoint-{list,show,resume,redo,assets}`（**扁平命名，非嵌套**）
- 触发场景：stage 失败 / 重生单镜 / 重新审计
- `build_review_dir` 语义文件名规则
- ~3 KB

**Files**：`skills/videoclaw-checkpoint/SKILL.md`

**Verify**：
```bash
python packaging/skills-validate.py skills/                                  # exit 0
grep -c "checkpoint-" skills/videoclaw-checkpoint/SKILL.md                   # ≥5
```

---

### T6 — `videoclaw-troubleshoot` 完整 SKILL.md

**关联**：G9 + G1（部分文档）

**Acceptance**：
- `claw doctor` 输出解读
- 退出码表：0 / 1 / 2 / 3 / 4
- 常见错误诊断：Seedance privacy filter 拒人脸 / base64 URI 拒绝 / Evolink rate limit / EdgeTTS 语言降级
- ~4 KB

**Files**：`skills/videoclaw-troubleshoot/SKILL.md`

**Verify**：`python packaging/skills-validate.py skills/` exit 0

---

### T7 — wheel + PyInstaller bundle skills/

**关联**：G3

**Acceptance**：
- wheel 构建后包含 `videoclaw/_skills/videoclaw-{workflow,drama-setup,models,checkpoint,troubleshoot}/SKILL.md`
- PyInstaller 单文件构建后 `claw setup --dry-run` 能找到 skills 内容（验证 spec.datas 正确）
- 不破坏 F6.1（wheel 仍不含 tests/projects/etc）

**Files**：
- `pyproject.toml`（添加 `[tool.hatch.build.targets.wheel.force-include]` 把 `skills/` map 到 `videoclaw/_skills/`）
- `packaging/claw.spec`（datas 增加 `("../skills", "videoclaw/_skills")`）

**Verify**：
```bash
uv build --wheel --out-dir dist/
unzip -l dist/videoclaw-0.1.0-py3-none-any.whl | grep -c '_skills/.*SKILL.md'   # ≥5
unzip -l dist/videoclaw-0.1.0-py3-none-any.whl | grep -E '/(tests|projects|models_cache|docs/deliverables)/' | wc -l   # 0
```

---

### T8 — `claw setup` 命令实现

**关联**：G10

**Acceptance**：F11.1–9 全部通过：
- `cli/setup.py` 新文件，注册 `claw setup`
- 探测 Claude Code / Codex / OpenClaw 三家（Cursor / Gemini CLI 暂不支持，输出 hint）
- per-agent 命名：Claude Code / Codex 用平铺 `videoclaw-<role>/`；OpenClaw 用 `videoclaw-<role>-0.1.0/`
- `--dry-run` / `--agent <name>` / `--uninstall` / 默认全装
- 幂等：同 version 写入 → skip + envelope 报告 noop
- 输出 `videoclaw-setup-skills/v1` envelope
- `--json` / `--verbose` 全局兼容

**Files**（**含 src/ 范围扩展**）：
- `src/videoclaw/cli/setup.py`（NEW，~150 LOC）
- `src/videoclaw/cli/__init__.py`（**+1 行** `import videoclaw.cli.setup`）
- `tests/test_setup_skills.py`（NEW）

**Skills 资源加载策略**：
- 优先 `importlib.resources.files("videoclaw") / "_skills"`（wheel 安装路径）
- 回退到 repo-local `<repo>/skills/`（开发模式 `uv pip install -e .` 走这条）
- PyInstaller 路径走 `sys._MEIPASS / "videoclaw" / "_skills"`

**Verify**：
```bash
# 干跑探测
uv run claw setup --dry-run --json | python -c "import json,sys;d=json.load(sys.stdin);assert d['ok'] and d['agents_detected']"

# 临时 HOME 实装
HOME=$(mktemp -d) uv run claw setup --json
HOME=$prev ls $HOME/.claude/skills/videoclaw-workflow/SKILL.md   # 文件存在

# 幂等
HOME=$tmp uv run claw setup --json | jq '.skills_skipped | length'  # 第二次 = 第一次的 installed 数

# 单测
uv run pytest tests/test_setup_skills.py -v
```

**依赖**：T7（需要 wheel 内 _skills/ 路径就位以测 importlib.resources 路径）；本地开发期间 T2–T6 任一完成即可走 repo-local 回退路径。

---

### T9 — install.sh 末尾建议链入 `claw setup`

**关联**：G4

**Acceptance**：
- 安装成功后 stderr 信息：先建议 `claw setup`（skills），再建议 `packaging/setup.sh`（API keys）
- envelope `next_steps` 也更新顺序
- 退出码 / SHA256 / 拒绝 root 等行为不变

**Files**：`install.sh`

**Verify**：
```bash
INSTALL_DIR=$(mktemp -d) CHANNEL=binary bash install.sh 2>&1 | grep -E "claw setup|setup.sh"
# 输出顺序：claw setup 先，setup.sh 后
INSTALL_DIR=$(mktemp -d) CHANNEL=binary bash install.sh 2>/dev/null | tail -n1 | jq '.next_steps[0]'
# → "claw setup"
```

**依赖**：T8

---

## Track B — 文档与 meta（可与 Track A 并行）

### T10 — README 重排为 google 三段表风格

**关联**：G11

**Acceptance**：F12.1–4 全部：
- README 顶部按顺序：Hero（pitch ≤ 25 字 + Works with 列表 ≥4 agent）/ Get Started（3 步）/ Skills（表）/ Commands（表）/ FAQ
- 现有 Why / Features / Architecture / Models 等内容移到 "Reference" / "Architecture" 区，不删除
- FAQ 至少回答 "Is this an alternative to Claude Code / Codex / Gemini CLI?"（答：No, it's a tool *for* coding agents）

**Files**：`README.md`

**Verify**：
```bash
# 顶部 5 个 H2 顺序
grep -n "^## " README.md | head -5
# 期望前 5 个：Get Started / Skills / Commands / FAQ / Reference (or Architecture)

grep -E "Claude Code|OpenClaw|Codex|Cursor|Gemini" README.md | head -1   # 在 Works with 区出现
```

---

### T11 — per-agent quickstart 4 块（README + AGENTS.md）

**关联**：G5

**Acceptance**：
- README "Get Started" 下含子节 "Works with"，4 个 agent 各 3 行（install / first-call / first-mutation）
- AGENTS.md 同样 4 块，更详细（含 skills 路径）
- Cursor 块标注"manual copy required（Cursor 不走 skills 目录）"

**Files**：`README.md` · `AGENTS.md`

**Verify**：
```bash
for a in "Claude Code" "OpenClaw" "Codex" "Cursor"; do
    grep -q "$a" README.md && grep -q "$a" AGENTS.md || echo "MISSING: $a"
done
```

---

### T12 — manifest 降级为 informational + 文档同步真实状态

**关联**：G2 + G8

**Acceptance**：
- README / AGENTS.md / packaging/DISTRIBUTION-PLAN.md 中提到 `agent-cli.yaml` 处都加 "informational; primary discovery is skills"
- AGENTS.md 删除 "P2 (deferred): release.yml" 条（已 ship 在 commit `86e502c`）
- packaging/DISTRIBUTION-PLAN.md §8 复选框全部对齐当前 HEAD（release.yml ✅、setup.sh ✅、install.sh ✅、agent-cli.yaml ✅）

**Files**：`README.md` · `AGENTS.md` · `packaging/DISTRIBUTION-PLAN.md`

**Verify**：
```bash
grep -c "informational" README.md AGENTS.md packaging/DISTRIBUTION-PLAN.md   # 每个 ≥1
grep -c "P2.*release.yml\|release.yml.*deferred" AGENTS.md                   # = 0
grep -E "^- \[x\] .*release.yml|^- \[x\] .*install.sh|^- \[x\] .*setup.sh" packaging/DISTRIBUTION-PLAN.md   # 全 [x]
```

---

### T13 — RELEASE_NOTES.md

**关联**：G12

**Acceptance**：
- 文件 `RELEASE_NOTES.md` 在 repo 根
- 顶部 0.1.0 段：feat / fix / docs 三类，bullet ≥3
- 格式 `## [0.1.0] - 2026-05-06`（仿 google/agents-cli）

**Files**：`RELEASE_NOTES.md`（NEW）

**Verify**：
```bash
test -f RELEASE_NOTES.md
grep -E "^## \[0\.1\.0\]" RELEASE_NOTES.md | head -1   # 存在
```

---

### T14 — 退出码 2 / 3 / 4

**关联**：G1 · **含 src/ 范围扩展**

**Acceptance**：
- `cli/doctor.py`：缺关键 API key（`VIDEOCLAW_EVOLINK_API_KEY`）时退 3（当前退 1）；其他错误保持 1
- `agent-cli.yaml` / README / AGENTS.md 退出码表保留 0/1/2/3/4 全段
- 退出码 4 (blocked) 暂不在 CLI 用，仅 install.sh 中（已用），文档说明

**Files**（**src/ 范围扩展从 {cli/setup.py} → {cli/setup.py, cli/doctor.py}**）：
- `src/videoclaw/cli/doctor.py`（小改：missing-key 路径 `raise typer.Exit(code=3)`）
- `tests/test_doctor.py`（NEW or 扩展）
- `README.md` · `AGENTS.md` · `packaging/agent-cli.yaml`（文档）

**Verify**：
```bash
unset $(env | grep ^VIDEOCLAW_ | cut -d= -f1) 2>/dev/null
uv run claw doctor; echo "exit: $?"   # 期望 3（之前 1）
uv run pytest tests/test_doctor.py -v
```

**Scope note**：本任务把 src/ 改动从 1 个文件（cli/setup.py）扩到 2 个文件
（+ cli/doctor.py，~5 行）。如不接受，T14 降级为**纯文档**：保留代码现状
（退 1），README 中标注"exit code 3 reserved for next milestone"。

---

### T15 — release.yml 添加 dry_run input

**关联**：G6

**Acceptance**：
- `workflow_dispatch.inputs` 加 `dry_run` (boolean, default false)
- 当 `dry_run=true` 时 skip `gh release create` 与 artifact upload；保留 build / smoke
- 注释清楚

**Files**：`.github/workflows/release.yml`

**Verify**：
```bash
gh workflow run release.yml --ref feat/agent-cli-toolkit \
    -f version=0.1.0 -f dry_run=true
gh run watch                      # 期望全绿
gh release list | grep v0.1.0     # 期望无（dry-run 不创建）
```

---

### T16 — .gitignore 收尾

**关联**：G7

**Acceptance**：
- `.gsd-id` `mcp-shim/uv.lock` 之一：要么进 .gitignore（如属本地 / lockfile 政策不追踪），要么 `git add` 显式追踪
- `git status --porcelain` 干净

**Files**：`.gitignore`（最可能） 或 `mcp-shim/uv.lock`（追踪决定）

**Verify**：`git status --porcelain` 输出空

---

## T17 — 二次部署验证（所有 task 完成后一次性跑完）

**关联**：spec Success Criteria §4

**Acceptance**：以下命令全部成功，**任一失败本轮不通过**：

```bash
# 1. lint + test
make lint
make test

# 2. manifest + skills schema
python packaging/manifest-validate.py packaging/agent-cli.yaml
python packaging/skills-validate.py skills/

# 3. 构建三段（无 docker 时 STAGE_DOCKER=0）
bash packaging/dist-verify.sh                       # 或 STAGE_DOCKER=0 bash ...

# 4. install.sh 模拟（本地构建产物）
INSTALL_DIR=$(mktemp -d) CHANNEL=binary bash install.sh
# → envelope ok=true; $INSTALL_DIR/claw version 输出 0.1.0

# 5. setup wizard 幂等
bash packaging/setup.sh --quiet
bash packaging/setup.sh --quiet                     # 二次结果一致

# 6. claw setup 在临时 HOME
HOME=$(mktemp -d) uv run claw setup --json | jq '.ok'           # true
HOME=$prev_tmp uv run claw setup --json | jq '.skills_skipped | length'  # >0 (幂等)

# 7. 真实主 HOME（用户实际环境）
uv run claw setup --json
ls ~/.claude/skills/videoclaw-workflow/SKILL.md                 # 文件存在
ls ~/.codex/skills/videoclaw-workflow/SKILL.md                  # 文件存在
ls ~/.openclaw-autoclaw/skills/videoclaw-workflow-0.1.0/SKILL.md  # 文件存在（带版本）

# 8. external + mcp
uv run pytest tests-external/ -v
uv run pytest mcp-shim/tests/ -v

# 9. 版本一致性 4 处
grep '^version = "' pyproject.toml
grep '^version:' packaging/agent-cli.yaml
uv run claw version
grep -hE '^  version:' skills/videoclaw-*/SKILL.md | sort -u    # 期望全为同一行

# 10. release.yml dry-run
gh workflow run release.yml --ref feat/agent-cli-toolkit \
    -f version=0.1.0 -f dry_run=true && gh run watch

# 11. git status 干净
git status --porcelain    # 空
```

**Files**：无（只是验证 + 报告）

**Verify**：以上 11 个命令一次性跑完，输出 **二次部署验证报告**
`docs/plans/2026-05-06-agent-cli-verification-report.md`：
- 每条命令实际输出 / exit code
- 失败项 + 修复路径
- 三处版本号对齐确认
- "release-ready" 结论（go / no-go）

---

## 任务统计

- **总数**：17 (T1–T17)
- **关键路径**：T1 → T2 → T7 → T8 → T9 → T17（6 个串行节点）
- **可并行批次**：
  - 批 1 (独立)：T1 / T10 / T11 / T12 / T13 / T15 / T16 (T14 视 src/ 扩展决定)
  - 批 2 (T1 后并行)：T2 / T3 / T4 / T5 / T6
  - 批 3 (T2-T6 全完成后)：T7
  - 批 4：T8
  - 批 5：T9
  - 最终：T17
- **预计执行**：3-4 个 focused session
  - Session 1：T1 + T10 + T11 + T12 + T13 + T15 + T16（或 T14）+ 第一份 SKILL（T2）
  - Session 2：T3 / T4 / T5 / T6（剩下 4 份 SKILL）
  - Session 3：T7 / T8 / T9 + T17 二次部署验证

---

**Phase 3 review checkpoint**：用户对 17 个 task + 依赖图 + T14 src/ 扩展决断
之后，进入 Phase 4 (Implement)。

进入 Phase 4 时按 incremental-implementation + TDD：
- 每个 task 单独完成 → `make lint` → commit + push
- T14 / T8 / T15 等代码任务先写失败测试，再写实现
- 任何 task 出现"需要超出本任务文件清单"的改动 → 立即停下来 escalate
