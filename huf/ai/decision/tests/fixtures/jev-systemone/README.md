# Jev System One Live Shape Fixtures

These fixtures capture sanitized response shapes from the OpenCode Zen System One endpoint for the PR3 Decision Runtime adapter work.

The requests use only synthetic support examples. They include no headers, bearer tokens, environment values, or real user state.

## Captured Success Cases

- `noul_success.json`: HUF `judge` mapped to Jev `noul`.
- `choice_success.json`: HUF `select` mapped to Jev `choice`.
- `score_success.json`: HUF `score` mapped to Jev `score`.
- `mixed_success.json`: One batched request containing `noul`, `choice`, and `score`.

## Score Mapping Note

Jev `score` responses return:

- a numeric `score`, which may be fractional;
- a `legend` object keyed by stringified numeric indexes such as `"0"`, `"1"`, and `"2"`;
- `probabilities` keyed by the same stringified numeric indexes.

The PR3 adapter should map those numeric legend indexes back to the ordered HUF score options from the request. It should not expose raw legend indexes as caller-facing HUF option ids.

## Error Fixtures Still Needed

The PR3 adapter should add sanitized fixtures for:

- `malformed_response.json`
- `rate_limited.json`
- `auth_failure.json`

Those are not captured here because this prep pass only saved successful synthetic live shapes.
