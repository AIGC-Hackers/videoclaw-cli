# Agent Instructions — agent-cli-toolkit milestone

**Scope lock (non-negotiable):**

1. Write only under `agent-cli-toolkit/**`. Do **not** modify `src/videoclaw/**`, `tests/**`, or any other videoclaw source.
2. You may READ from `docs/references/kimi-cli-teardown/**` (already committed kimi-cli analysis) and `~/Moose/kimi-cli/**` (source-of-truth reference; read-only).
3. Do **not** clone or modify `~/Moose/kimi-cli/` during execution. Treat it as a read-only reference.
4. All deliverables live in `agent-cli-toolkit/docs/`, `agent-cli-toolkit/templates/`, `agent-cli-toolkit/examples/`, and `agent-cli-toolkit/README.md`.

**Deliverable quality bar:**

- **Prescriptive, not descriptive.** Every doc must answer "what do I do, in what order?" — not "what does kimi-cli do?".
- **Reusability first.** Templates and playbooks must work for ANY CLI, not just videoclaw or kimi-cli. Use kimi-cli as the evidence base and videoclaw as the worked example.
- **Cite sources.** Claims about kimi-cli structure must cite `~/Moose/kimi-cli/path/to/file:LINE`.
- **Working code over prose.** Templates must be runnable (`pyproject.toml` must `uv build`; `__main__.py` must `python -m` start). Prefer a 20-line working example over a 200-line explanation.

**Language:**

- All user-facing docs in **English**, except the final executive summary which should have a Chinese mirror.
- Variable/code comments minimal — clean identifiers beat comments.

**End-of-milestone verification (S06):**

- Run the 7-step migration playbook against `examples/hello-agent-cli/`. Produce `examples/hello-agent-cli/VERIFIED.md` that shows each step's expected-vs-actual output.
- Wheel must build. Example CLI must start in three modes: interactive TUI (not required), one-shot (`hello-agent hello "world"`), and MCP server mode (`hello-agent mcp-server` → responds to `tools/list`).

**Out of scope (don't do):**

- Building videoclaw's actual packaging (that's a future milestone). S09 only produces a **plan**, not execution.
- Adding videoclaw-specific agent features.
- Integrating with any cloud service.
