# Microsoft Teams gateway: known issues and gaps (slice 1)

An honest list, checked against the code on `wp/teams-t15` merged with `feat/teams-p0` after the
Opus review fixes. "Product decision pending" means the owner has not decided.

## 1. Design gap D1 (resolved): unlinked people were rejected before they could link

- Resolved. `Gateway.validate` now allows `direct_policy = Open` for Slack and Microsoft Teams only
  (case-insensitive provider match). For every other provider `Open` is still rejected with
  "Public direct-message gateways are not available in this release". Room policies are unchanged.
- With `Open`, an unlinked person is not rejected: they get a private connect prompt, nothing runs, and
  there is no fallback to the Run as user. The identity link is the authorization, so pre-approval
  through the access list is not required for these two providers.
- New Slack and Teams gateways default to `Open` in the UI; setup checks (`direct_policy` in Slack
  verify and Teams diagnostics) and the Event diagnosis recommend it.
- Still true: with `Allow list` or `Pairing`, admission runs before identity, so an unlinked person who
  is not approved gets "Sender is not approved for this gateway" (bench E2E S1a). With `Open` and no
  access entry the person gets the connect prompt (S1c). `Open` is refused for other providers (S1d).
  The commands `help`, `connect`, `status`, `disconnect` are answered before admission either way.

## 2. Wording and diagnostics issues in the product

- Wizard step 7 ("Say hello to the bot") suggests `help`. Commands return before a Gateway Event is
  created, so `last_inbound` does not change. Send an ordinary (non-command) message instead.
- (a) The `linked_users` diagnostic says to send `link` to the bot; the command is `connect`.
- (b) The `outbox` diagnostic says Failed messages "will be retried automatically" and that Dead ones can be
  resent. `retry_due` retries only Pending rows (transient failures); Failed (permanent) and Dead rows are
  never retried and there is no resend action.
- Readiness helpers exist but callers do not pass diagnostics results into them (Slack and Teams): not wired.

## 3. Settings and manifest

- `help_text_override` and `bot_handle` (Teams Gateway Settings) are stored but no code reads them.
- The manifest privacy and terms URLs are `<site>/privacy` and `<site>/terms`, which Huf does not serve;
  icons are generic placeholders; schema 1.19 is pinned offline.

## 4. Security and data gaps

- Revoke or disconnect does not close open Teams Action Sessions (they stay Open until expiry) or cancel
  queued outbox rows. A revoked user cannot decide, because identity no longer resolves.
- There is no retention purge for Teams tables, successful Gateway Events, outbox rows, references,
  action sessions or revoked links. Only Rejected Gateway Events older than 30 days are purged.
- No roster check for guests: a B2B guest of the host tenant carries the host tenant id and may lack
  a userType marker. Missing object ids and tenant-claim mismatches are denied; the `teams.getMember`
  roster follow-up is a TODO in `teams_identity._is_guest`.
- A POST that succeeded but timed out is retried; the Bot Connector has no idempotency key, so duplicate
  messages are possible.
- Link confirmation requires an installed personal chat for that exact tenant and Entra id. Without one,
  `connect` confirmation fails and the pending link is revoked.

## 5. Not tested against a live tenant (assumed from code and docs)

Nothing has run against real Microsoft services. Unverified: guest markers in real payloads, Adaptive
Card rendering on desktop/web/mobile, creating a one-to-one chat with `aadObjectId` as member id
(Microsoft documents `29:` ids or the object id with the tenant), the `msteams` endorsement and `serviceurl`
claim in live tokens, private/shared channels, Markdown rendering, Teams behaviour on re-uploading a
same-version package, the Yes/No link card in a real client, and the manifest schema and portal steps (all Microsoft-portal
instructions in ADMIN_SETUP.md need checking against current Microsoft documentation).

## 6. What the real-bench E2E covered

Harness: `bench/e2e/run_e2e.sh` on the `teams-gw` bench (real MariaDB and Redis, Huf code in-process,
Microsoft network blocked, 0 unexpected network attempts, 0 leftover rows). Last run: 15/15 pass.

1. S1a unlinked message on a default gateway: Rejected "not approved" (shows D1)
2. S1b unlinked message from an approved sender: Rejected with a connect prompt via outbox, no agent run
3. S2 bad signature, wrong audience, missing header: 401, no event, outbox row or reference
4. S3 foreign-tenant message: Rejected `tenant_not_allowed`
5. S3b foreign-tenant `help`: Rejected, no reply
6. S4 `help` and `connect` from an unlinked user: outbox reply, no event, no job
7. S5 installationUpdate add and remove: reference installed 1 then 0, no event
8. S5b foreign-tenant install: Rejected, no reference
9. S6 duplicate activity (message and command): no second event, outbox row or job
10. S7a card action from an unlinked clicker: refusal, session stays Open
11. S7b session consume atomicity, 8 threads on separate DB connections: exactly one winner
12. S7c linked clicker with a missing approval: consume then release, session reopened
13. S8 diagnostics, support bundle and token-error output: a canary secret never appears in output, outbox or events
14. S9 outbox delivery: default sender reaches for the token endpoint (blocked) and the row stays Pending (transient); correctly wired sender with a fake HTTP delivers and Sent leaks no secret
15. NET no unexpected network attempts

## 7. What it did not cover

- The real Agent Execution Approval decide path (an actual click that approves a real approval).
- A linked user's message running an agent end to end (needs an agent run without an LLM; the provider would need stubbing).
- Real HTTP to Huf (calls were in-process) and any real Microsoft traffic.
- A multi-process race (the atomicity test used threads in one process).
- The two-way link confirmation flow (Pending, card, Yes/No) is covered by unit tests, not by this E2E.
