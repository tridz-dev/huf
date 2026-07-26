# SSH execution in Huf — PR1 scope

This document defines the first-PR contract for Huf's SSH execution support.

## Included in PR1

- Persistent encrypted SSH authentication through the `SSH Connection` DocType
- Agent-side allowlisting through `allow_ssh` + `ssh_connections`
- One-shot remote command execution with no PTY
- Host-key pinning and strict host-key verification
- Approval and audit integration
- Timeout and output limits

## Deferred from PR1

- Interactive PTY terminal sessions
- Terminal input streaming
- Shared shell state across agent turns
- `vim`, REPLs, password prompts, and similar terminal workflows
- First-class durable job objects, log streaming, and cancellation APIs

## Execution contract

- Execution kind: `exec`
- Transport: one SSH connection per command
- PTY: not allocated
- Shell model: equivalent to `ssh user@host '<command>'`
- Connection timeout: bounded
- Execution timeout: bounded
- Idle timeout: bounded
- stdout/stderr capture: bounded and truncated when limits are hit
- Concurrency per SSH connection: bounded
- Background forks: not treated as managed durable jobs

If a command daemonizes, forks into the background, or otherwise outlives the SSH worker's managed
execution window, Huf does not currently provide ownership, status, log retrieval, or cleanup for
that process.

## Durable execution pattern for operators

PR1 does not make `tmux`, systemd, or Docker a required backend dependency, but it does support an
explicit operator pattern for long-running remote work.

Recommended `tmux` pattern:

```bash
tmux new-session -d -s huf-job-<job-id> 'your command'
tmux capture-pane -p -t huf-job-<job-id>
tmux has-session -t huf-job-<job-id>
tmux kill-session -t huf-job-<job-id>
```

Equivalent Docker or systemd patterns are also acceptable when the target host already standardizes
on them.

## Admin UI split in PR1

- SSH credential/host-key management: Frappe Desk `SSH Connection` DocType UI
- Agent-side SSH enablement and allowlisting: Huf React app `Agent` advanced settings

PR1 deliberately does not add a standalone React SSH-connection management page.

## Known limitations in PR1 (deferred)

- Output truncated at a byte limit is recorded as `Completed` with `limits_hit=1` (exit code
  unknown once the channel is closed mid-stream); treat `limits_hit` as the truncation signal.
- Idle timeout is labeled `exit_status="Killed"` while overall timeout is `"Timeout"`.
- On timeout/limit the SSH channel is closed without signaling the remote process; a server-side
  process may keep running (use the durable `tmux`/systemd pattern above for long jobs).
- The per-connection concurrency slot uses a non-atomic Redis get-then-set; two jobs starting in
  the same instant can both pass the check.
- The pending-approval stash holds the raw command in Redis (plaintext, up to 24h) by design for
  the integrity-hash check.
- `_truncate` counts characters while capture limits count bytes (multibyte UTF-8 mismatch), and
  the appended truncation marker pushes stored output slightly past the nominal limit.

## Follow-up roadmap

- PR2: first-class `durable_job` support with status, logs, cancellation, cleanup
- PR3: first-class `pty_session` support with interactive input/output streaming and reconnect
