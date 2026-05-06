# videoclaw skills

Markdown skills that turn any coding agent into an expert at producing
TikTok-format AI dramas with **videoclaw**. Mirrors the
[google/agents-cli](https://github.com/google/agents-cli) skills model:
each skill is a directory of `SKILL.md` + `references/`, with frontmatter
that tells the coding agent *when* to load it.

## Skills index

| Skill | When the coding agent loads it |
|---|---|
| [`videoclaw-workflow`](videoclaw-workflow/SKILL.md) | Always-active entrypoint. End-to-end drama lifecycle: `drama new/import → plan → design-* → assign-voices → run → audit → export`. |
| [`videoclaw-drama-setup`](videoclaw-drama-setup/SKILL.md) | Creating new series or importing scripts (`drama new`, `drama import`, `drama script`). |
| [`videoclaw-models`](videoclaw-models/SKILL.md) | Choosing video adapters (Seedance / Kling / MiniMax / etc.) and respecting platform constraints (HTTPS-only refs, stylized faces). |
| [`videoclaw-checkpoint`](videoclaw-checkpoint/SKILL.md) | Stage failures, resuming, regenerating single shots (`checkpoint-list/show/resume/redo/assets`). |
| [`videoclaw-troubleshoot`](videoclaw-troubleshoot/SKILL.md) | `claw doctor` failures, exit-code interpretation, common errors (privacy filter, base64 URI rejection, rate limits). |

## How they get installed

`claw setup` (after installing `videoclaw` via `uvx --from <wheel-url>` or
`uv tool install`) detects which coding agents are present and copies the
five skill directories into each agent's skill location:

| Agent | Skills directory | Naming |
|---|---|---|
| Claude Code | `~/.claude/skills/` | flat (`videoclaw-workflow/`) |
| Codex | `~/.codex/skills/` | flat |
| OpenClaw / autoclaw | `~/.openclaw-autoclaw/skills/` | versioned (`videoclaw-workflow-0.1.0/`) |
| Cursor | (manual copy — Cursor doesn't use a skills directory) | — |
| Gemini CLI | (deferred — extension path TBD) | — |

`claw setup --uninstall` removes them. `claw setup --dry-run` previews
without writing.

## Validating skills

```bash
python packaging/skills-validate.py skills/
```

Checks: every `<dir>/SKILL.md` exists · frontmatter parses · `name` field
matches the directory name · `metadata.version` matches `pyproject.toml`'s
`[project] version`.

## Authoring conventions

- Frontmatter is YAML, with `description` written as a multi-line block
  scalar (`>`) listing trigger phrases ("用 videoclaw …", "make a drama …",
  CLI command names) so coding agents reliably activate the right skill.
- Top-level: `STOP — read this before … ` defensive guidance.
- Phase-numbered structure (Phase 0: Understand → Phase N: …).
- Cross-skill references via `/videoclaw-<role>` notation.
- Long content goes in `references/` to keep `SKILL.md` focused.
- Every command snippet must match the live `claw …` CLI surface; when
  the CLI changes, the relevant skill updates with it.
- Chinese and English are both first-class — drama scripts and prompts
  may be Chinese; CLI commands stay English for unambiguous machine
  parsing.
