# Fake CLI Executable

This directory contains `fake_cli.py`, a deterministic, dependency-free fake provider CLI for testing subscription-based provider adapters in HUF.

## Features

- **Deterministic output**: Same inputs + env vars = same responses
- **Zero dependencies**: Uses only Python 3 stdlib (`argparse`, `json`, `pathlib`, `uuid`, `time`)
- **Session state tracking**: Remembers sessions across invocations via a local state file
- **Real CLI behavior simulation**: Matches findings from the spike (plain-text stderr errors, JSON stdout, session stability)
- **Configurable failure modes**: Auth failure, timeout, image unsupport via environment variables

## Executable Mode

The script is standalone and executable:
```bash
./fake_cli.py -p "hello" --output-format json
```

## Flags and Arguments

| Flag | Description | Example |
|------|-------------|---------|
| `-p`, `--print` | Prompt text (non-interactive mode) | `-p "What is 2+2?"` |
| `-r`, `--resume` | Resume an existing session by ID | `--resume f50fa1d9-1f4f-4449-97b4-99aca3c6bbc7` |
| `--session-id` | Explicit session ID for idempotency testing | `--session-id my-fixed-id` |
| `--output-format` | Output format: `json` or `text` | `--output-format json` |
| `--auth-status` | Print auth status and exit | `--auth-status` |
| `--image` | Image file path for vision input | `--image /path/to/photo.png` |
| `--state-dir` | Override default session state directory | `--state-dir /tmp/test_state` |

## Environment Variables

| Variable | Values | Purpose | Example |
|----------|--------|---------|---------|
| `FAKE_CLI_AUTH_STATE` | `ready` (default) or `required` | Simulate auth failure | `FAKE_CLI_AUTH_STATE=required ./fake_cli.py ...` |
| `FAKE_CLI_SLEEP_SECONDS` | Float seconds | Simulate slow response (for timeout testing) | `FAKE_CLI_SLEEP_SECONDS=5` |
| `FAKE_CLI_FIXED_SESSION_ID` | UUID string | Use fixed session ID for deterministic tests | `FAKE_CLI_FIXED_SESSION_ID=static-id` |
| `FAKE_CLI_SUPPORTS_IMAGES` | `0` or `1` (default) | Control image input support | `FAKE_CLI_SUPPORTS_IMAGES=0` |
| `FAKE_CLI_STATE_DIR` | Directory path | Override session state storage location | `FAKE_CLI_STATE_DIR=/tmp/fake_cli` |

## Behavior Reference

### New Session (No Resume)
```bash
./fake_cli.py -p "hello" --output-format json
```
**Exit code**: 0
**Stdout** (JSON object):
```json
{
  "session_id": "f50fa1d9-1f4f-4449-97b4-99aca3c6bbc7",
  "result": "HELLO (session: 99aca3c6)",
  "usage": {
    "input_tokens": 4,
    "output_tokens": 6,
    "cache_creation_input_tokens": 1000,
    "cache_read_input_tokens": 500
  },
  ...
}
```

### Resume Known Session
```bash
./fake_cli.py -p "follow-up" --resume f50fa1d9-1f4f-4449-97b4-99aca3c6bbc7 --output-format json
```
**Exit code**: 0
**Stdout** (JSON object):
- Same structure as new session
- Session ID is **stable** (same as the one provided)
- Result includes prior context: `"[previous: HELLO (session: 99aca3c6)]"`

### Resume Unknown Session
```bash
./fake_cli.py -p "hello" --resume not-a-real-id --output-format json
```
**Exit code**: 1 (non-zero)
**Stderr** (plain text, NOT JSON):
```
Error: --resume requires a valid session ID. Provided value "not-a-real-id" is not a UUID and does not match any session.
```
**Stdout**: (empty)

Key finding from spike: Both Claude and Codex emit plain-text errors on invalid resume even when `--output-format json` is requested. This fake CLI matches that behavior.

### Auth Status
```bash
./fake_cli.py --auth-status
```
**Exit code**: 0 (if ready), 1 (if required)
**Stdout** (JSON):
```json
{
  "loggedIn": true,
  "authMethod": "claude.ai",
  "apiProvider": "firstParty",
  "subscriptionType": "max"
}
```

### Auth Required (Simulated Failure)
```bash
FAKE_CLI_AUTH_STATE=required ./fake_cli.py -p "hello" --output-format json
```
**Exit code**: 1
**Stderr** (plain text):
```
Error: Authentication required. Please run: fake_cli auth login
```

### Image Input (Supported)
```bash
./fake_cli.py -p "describe this image" --image /tmp/photo.png --output-format json
```
**Stdout** includes in result: `"[image received]"`

### Image Input (Unsupported)
```bash
FAKE_CLI_SUPPORTS_IMAGES=0 ./fake_cli.py -p "describe this image" --image /tmp/photo.png --output-format json
```
**Exit code**: 1
**Stdout** (JSON error object):
```json
{
  "is_error": true,
  "type": "error",
  "error": "This provider does not support image input."
}
```

## Session State

Sessions are stored in `~/.fake_cli_state/.fake_cli_sessions.json` (or `FAKE_CLI_STATE_DIR` if set).

Structure:
```json
{
  "f50fa1d9-1f4f-4449-97b4-99aca3c6bbc7": {
    "created": 1695312345.123,
    "last_result": "HELLO (session: 99aca3c6)",
    "turns": 2
  }
}
```

Each session is immutable once created; the `turns` counter increments on every resume. The state file is readable by tests for verification.

## Testing

Run the self-test suite:
```bash
python -m pytest huf/ai/tests/subscription/test_fake_cli.py -v
```

Or run syntax checks:
```bash
python -m py_compile huf/ai/tests/subscription/fixtures/fake_cli.py
python -m py_compile huf/ai/tests/subscription/test_fake_cli.py
```

## Design Notes

- **Determinism**: By default, a new session gets a random UUID (via `uuid.uuid4()`). To enable deterministic tests, pass `--session-id` or set `FAKE_CLI_FIXED_SESSION_ID`. Tests that need reproducibility should use the latter.
- **Session stability**: Across resume calls, the session ID is **stable** (does not change). This matches the real Claude and Codex CLIs and is critical for adapter testing.
- **Error format**: Errors during resume (unknown session) are plain-text to stderr. Errors during image validation (unsupported) are JSON to stderr. Both exit non-zero. This matches the spike findings.
- **State persistence**: The state file survives across process invocations, enabling integration tests that simulate multi-turn conversations. Tests should clean up `FAKE_CLI_STATE_DIR` before/after to avoid cross-contamination.

## For Future Adapter Work

When building a new provider adapter:
1. Use `fake_cli.py` with deterministic `--session-id` or `FAKE_CLI_FIXED_SESSION_ID` for unit tests.
2. Use `--state-dir` to isolate test state from other tests.
3. Test error paths with `FAKE_CLI_AUTH_STATE=required` and unknown `--resume` IDs.
4. Validate image support with `FAKE_CLI_SUPPORTS_IMAGES=0`.
5. Test timeout handling with `FAKE_CLI_SLEEP_SECONDS=10` and a short adapter timeout.

All behavior is specified in the response shapes above and in the spike summary (`../STAGE0_SPIKE_SUMMARY.md`).
