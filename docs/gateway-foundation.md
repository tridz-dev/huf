# Gateway Foundation

This document captures the consolidated Channel Gateway foundation from PRs
#441, #446, #449, #447, #448, #442, and #443.

## Scope

The gateway layer provides a provider-neutral ingress path from external chat
channels into Huf Agents and Flows. It adds:

- Gateway administration DocTypes for channel configuration, admission control,
  route bindings, and event evidence.
- A provider-neutral adapter SDK for verified inbound events and outbound text
  replies.
- Runtime bridging for installed SDK adapters.
- Initial provider coverage for VK, WeCom, Microsoft Teams outgoing webhooks,
  and Discord interactions.

## Architecture

Provider adapters own their native verification contracts. Only verified,
normalized events enter `huf.ai.gateway_service.ingest_gateway_event`.

The core flow is:

1. A provider-specific endpoint or SDK adapter receives the native webhook.
2. The adapter validates native authentication before persistence.
3. The adapter normalizes the event into sender, conversation, thread, message,
   room, mention, and provider event metadata.
4. `Gateway Event` persists redacted evidence and an idempotency hash.
5. Gateway admission policy decides whether the sender or room may execute work.
6. Gateway bindings choose the first matching Agent or Flow route by priority.
7. Accepted events are queued for asynchronous Agent or Flow execution.
8. Agent responses can be delivered through the same runtime adapter when the
   provider supports outbound replies.

Key modules:

- `huf.ai.gateway_service`: provider-neutral persistence, idempotency,
  admission, routing, queueing, and execution.
- `huf.ai.gateway_webhook`: runtime bridge for SDK-based adapters and outbound
  replies.
- `huf.ai.gateway_adapters`: SDK contracts, registry, conformance checks, VK,
  and WeCom adapters.
- `huf.ai.tools.teams_webhook`: Microsoft Teams outgoing webhook ingress.
- `huf.ai.gateways.discord`: Discord Interaction ingress.

## Security Boundaries

Gateway ingress is fail-closed:

- No unverified payload is routed to an Agent or Flow.
- Provider credentials are read from linked `Integration Settings` password
  rows and are not stored on `Gateway Event`.
- Raw event evidence is redacted for common secret-bearing keys before
  persistence.
- Gateway execution runs as the configured non-administrator `execution_user`.
- Direct-message pairing creates a pending access request but never executes the
  triggering message.
- Room admission and sender admission are separate. Room access does not grant
  sender access.
- Room messages can require a mention before they route.
- Route preview requires read permission on `Gateway`.

The consolidated `Gateway` DocType keeps the richer admission model from the
foundation stack:

- `direct_policy`: `Disabled`, `Pairing`, `Allow list`, or `Open`.
- `room_policy`: `Disabled`, `Allow list`, or `Open`.
- `room_sender_policy`: `Allow list` or `Open`.
- `mention_required` and `pairing_ttl_minutes`.

## Adapter Contract

Every SDK adapter implements `GatewayAdapter`:

- `verify_inbound(request)`: validate the native webhook authentication.
- `normalize_inbound(request)`: convert a verified payload to
  `NormalizedGatewayEvent`.
- `send_reply(reply)`: deliver a `GatewayReply` and return `OutboundDelivery`.

Adapters also declare:

- `provider_id`
- `credential_schema`
- `capabilities`

Conformance checks enforce that required fields and capability declarations are
present before adapters are registered.

## Provider Coverage

VK and WeCom use the provider-neutral adapter SDK and runtime bridge. The
runtime bridge currently maps these channels to their installed adapter classes.

Microsoft Teams uses a dedicated outgoing-webhook handler because Teams expects
a short synchronous acknowledgement after HMAC validation. Huf verifies the
`Authorization: HMAC ...` header, queues approved events, and returns a fixed
acknowledgement without running a model inline.

Discord uses Interaction ingress. It verifies Ed25519 signatures over the exact
timestamp and raw request body, responds to ping checks, defers command
interactions, and queues approved events through the gateway service.

## Evidence And Tests

The umbrella branch includes focused tests for:

- Gateway service admission, routing, idempotency, redaction, and execution
  queueing.
- Adapter SDK value objects, registry, and conformance.
- Runtime webhook verification and outbound reply delivery.
- VK adapter verification, normalization, and reply behavior.
- WeCom adapter verification, URL challenge, normalization, and reply behavior.
- Microsoft Teams HMAC validation and webhook acknowledgement behavior.
- Discord Ed25519 verification, ping handling, command deferral, and rejection
  paths.

Run these locally with the repository's available backend/static checks before
review. The umbrella PR body should include the exact command results from the
branch.

## Follow-Ups

These are intentionally not blockers for this consolidation PR:

- Add a provider-neutral completion callback for non-SDK endpoints that defer
  immediate responses, especially Discord.
- Extend the runtime bridge mapping as more SDK adapters graduate.
- Add bench migration and browser smoke evidence for the Gateway UI page.
- Add provider setup guides for each production channel after credentials and
  deployment URLs are finalized.
