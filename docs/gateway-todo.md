# Gateway TODO / Shame List

The channel gateway foundation and adapters were consolidated into `develop` via PR #473,
but the end-to-end feature is **not ready for users**. This file tracks what is missing,
what was disabled, and what must be restored before Gateways can be shipped.

## What works

- Backend DocTypes exist: `Gateway`, `Gateway Binding`, `Gateway Access Entry`, `Gateway Event`.
- Provider-neutral ingress, admission, idempotency, routing, queueing, and execution service
  (`huf/ai/gateway_service.py`) has unit tests.
- Adapter SDK contracts, runtime bridge, VK/WeCom contracts, Teams outgoing webhook, and
  Discord Interaction ingress are merged.

## What is disabled / shameful

- **UI navigation**: Gateways is hidden from the app sidebar and the `/gateways` route is
  commented out in `frontend/src/App.tsx` and `frontend/src/components/app-sidebar.tsx`.
- **Flow Run trigger**: `Gateway` is removed from `Flow Run.trigger_type` options in
  `huf/huf/doctype/flow_run/flow_run.json`.
- **Frontend create form**: `GatewaysPage.tsx` only creates a minimal draft with
  `direct_policy: 'Disabled'`. The full admission and routing forms are not implemented.
- **Provider adapters**: no live inbound adapters are wired to the runtime (webhooks,
  long-polling bots, etc.). The SDK contracts exist but are not connected end-to-end.

## TODOs before re-enabling

1. Implement live provider adapters for at least one channel (Telegram bot webhook is the
   planned first adapter) and add integration tests.
2. Build the in-app gateway connection form: choose integration, map credentials, test
   connectivity, and enable/disable.
3. Build the admission-policy UI (`direct_policy`, `room_policy`, `room_sender_policy`,
   `mention_required`, `pairing_ttl_minutes`) instead of hard-coding `Disabled`.
4. Build binding/routing UI so a gateway can target an Agent or Flow.
5. Re-enable the sidebar item, `/gateways` route, and `Gateway` Flow Run trigger type.
6. Add end-to-end smoke test that creates a gateway, sends a test event, and verifies the
   resulting Agent/Flow run.

## Files with `#473-followup` TODOs

- `frontend/src/services/gatewayApi.ts`
- `frontend/src/pages/GatewaysPage.tsx`
- `frontend/src/components/app-sidebar.tsx`
- `frontend/src/App.tsx`
- `huf/huf/doctype/flow_run/flow_run.json`
- `huf/ai/gateway_service.py`

## History

- Original PRs: #441 (foundation), #446 (adapter SDK), #449 (runtime bridge), #447 (VK),
  #448 (WeCom), #442 (Teams), #443 (Discord).
- Consolidated PR: #473.
- Quick-fix commit that hid the incomplete UI and fixed the `access_policy` frontend bug:
  see commit message for the follow-up change on `develop`.
