# Flow guarantees G1-G5 (W2 gate)

Tests: `huf/ai/flow/tests/test_flow_guarantees.py`, one class per guarantee.

```
bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_guarantees
```

All data is synthetic. Sends use a fake transport (`send._enqueue` is patched), so nothing leaves the bench.

| Guarantee | Class | Cases |
|---|---|---|
| G1 ledger only through the guarded ledger path | `TestG1LedgerOnlyThroughGuardedPath` | raw `ledger_write` refused in draft and publish; each ledger kind (grant_points, issue_coupon, adjust_points, redeem_points) refused without an idempotency key and caps by an app policy on `huf_flow_validators`; a complete ledger node passes the policy; a crashing policy fails closed with no PII in the result |
| G2 a blocked send is final | `TestG2BlockedIsFinal` | no retry through `retry.run_with_retry`; still blocked after a send-window resume; a re-delivery under the same step key (also after a republish) replays the block and never sends; republish turns `live_send` off |
| G3 live = live_send AND NOT dry_run | `TestG3LiveMatrix` | the four-row truth table, checked on `gate.is_live` and on real transport calls; step tests are dry; the `live_send` lookup fails closed |
| G4 no PII in traces or logs | `TestG4NoPiiInTraceOrLog` | across a queued and a blocked send, the step output, the persisted run context (step-key record) and the logger calls have no phone or email; a free-text block reason is stored as a reason code; the masker and the error-log writer hide PII |
| G5 fail-closed pre-send guard | `TestG5FailClosedGuard` | a hook that raises or returns junk blocks (`hook_error`); a hook timeout blocks (`hook_timeout`); missing consent blocks (Huf's consent step and a consent block in the send); a broken hook lookup blocks; an allowing chain sends exactly once |

Mutation spot check (run at H-W2-20): making `guard._run_step` return "allow" on a step error, a timeout or an invalid verdict makes `test_hook_error_blocks` and `test_hook_timeout_blocks` fail.

## How Happiol CI runs the same cases

Happiol CI runs the Huf module above on its own bench (Huf pinned per `docs/ai/HUF_PIN.md`), then the
Happiol counterparts, which replace the stand-ins with the real app code:

- G1: `TestG1LedgerOnlyThroughGuardedPath` with Happiol's ledger node policy (P-W3-08) in place of `happiol_like_ledger_policy`, and its registered ledger node types in place of the id marker.
- G2, G3: `TestG2BlockedIsFinal`, `TestG3LiveMatrix` against a Happiol flow.
- G4: `TestG4NoPiiInTraceOrLog` with Happiol's `huf_pii_fields` and send token providers installed.
- G5: `TestG5FailClosedGuard` with Happiol's `huf_pre_send_hooks` (consent) installed.

## Not verified here

- G1: Huf has no ledger node kinds; the real kinds, budget caps, approval threshold, dry-run, audit, reversal and kill switch live in Happiol (P-W3-15..19). Huf only proves the validator seam refuses and fails closed.
- G2: republish is checked as "same step key replays" plus "live_send reset"; a full engine run across an actual republish is not run here.
- G4: the trace is checked through the persisted context and logger calls with engine persistence patched; the Agent Flow Run row itself is not read back.
- G5: Happiol's real consent hook; real WhatsApp outbound policy reads.
- No load, perf or timing runs (DEFER H-W2-21).
