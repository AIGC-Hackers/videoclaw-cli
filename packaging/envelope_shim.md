# Envelope shim — design note

`src/videoclaw/cli/_output.py:49-61` emits envelopes shaped
`{ok, version, command, data, error: <string>}`. The agent-CLI contract (S03)
mandates `{schema:"agent-cli/v1", ok, data, error:{code, message, hint}}` plus
exit codes 0/1/2/3/4 (success / runtime / usage / config / external).

We do **not** edit `_output.py`. Per the blueprint's write-scope lock, the
upgrade lands as a boundary wrapper:

```
claw … --json   →   _output.write_json(payload)   →   stdout
                              │
                              └─→ (future) post-process step
                                  • inject schema:"agent-cli/v1"
                                  • migrate error to {code,message,hint}
                                  • normalize exit code via envelope.error.code
```

## Why a wrapper, not an in-place rewrite

Two reasons:

1. **Scope lock.** Editing `_output.py` plus normalizing every `typer.Exit(...)`
   / `sys.exit(...)` call site is a ~200-line patch across the CLI. The
   blueprint forbids `src/videoclaw/**` edits in this milestone.
2. **Reversibility.** A wrapper can be toggled with an env flag
   (`VIDEOCLAW_ENVELOPE=v1`) without touching the existing test suite.

## Implementation surface (deferred)

The wrapper plugs into one of:

- A wrapper script `claw-agent` shipped alongside the wheel, invoking
  `python -m videoclaw.cli "$@"` and rewriting stdout via `jq`-equivalent.
- A Typer middleware registered against the root callback in a follow-up
  milestone where `src/videoclaw/**` edits are unlocked.

This file enumerates the design only; actual wrapper code is M002+.

## Verification (today)

- Current envelope shape: `claw --json version | jq -r 'keys|join(",")'`
  → `command,error,ok,version`
- Target shape: `claw --json version | jq -e '.schema == "agent-cli/v1"'`
  → currently fails; placeholder for the future wrapper smoke.
