# WhatsApp Business Calling: design and spike (T10)

Status: design + spike, plus an EXPERIMENTAL greeting-only implementation behind `Gateway.calling_enabled` (default OFF), see section 14. Researched 2026-10-21.
Legend: **[V]** verified against Meta's official docs fetched today; **[U]** unverified (not on a fetched page, or from prior research only); **[L]** verified locally by running code.
Sources fetched: `developers.facebook.com/docs/whatsapp/cloud-api/calling` (+ `/user-initiated-calls`, `/business-initiated-calls`, `/call-settings`), `/docs/whatsapp/pricing`. The pricing page for calls, call-permissions page, SIP page body, limits page and test-number notes were NOT retrievable in this pass.

## 1. Purpose and scope

Automation, not a softphone:
1. Phase 1: a user calls the business number; Huf answers, plays one pre-recorded audio file (greeting/announcement), hangs up.
2. Phase 2: business-initiated call after the user grants call permission (e.g. appointment reminder read-out).
Out of scope: live conversation/ASR/TTS agent loop, DTMF menus (DTMF arrives as RTP events, no webhook [V per research]), call recording, voicemail, SIP trunking.

## 2. Meta prerequisites checklist

| # | Item | Status |
|---|------|--------|
| 1 | Number is on Cloud API (not WhatsApp Business app) | V |
| 2 | App has `whatsapp_business_messaging` permission; app subscribed to Messaging webhook for the number | V |
| 3 | Subscribe app to the `calls` webhook field (not needed for SIP-only) | V |
| 4 | Business daily messaging limit >= 2,000 unique recipients; test numbers and sandbox exempt | V (test-number exemption stated on calling overview) |
| 5 | Enable calling: `POST /<PHONE_ID>/settings {"calling":{"status":"ENABLED"}}` -> `{"success":true}`; off by default | V |
| 6 | Verify: `GET /<PHONE_ID>/settings` returns `calling.{status,call_icon_visibility,callback_permission_status,call_hours,sip,audio,voicemail}`; needs `whatsapp_business_management` | V |
| 7 | Client-side visibility of settings changes can lag up to 7 days (server applies immediately) | V |
| 8 | `call_icon_visibility`: DEFAULT shows button; DISABLE_ALL hides it and blocks unsolicited calls. `restrict_to_user_countries` exists (Dec 2025) | V |
| 9 | `callback_permission_status: ENABLED` prompts the user for call permission after they call (path to business-initiated permission) | V |
| 10 | Audio codecs: Opus always on; PCMA/PCMU optional via `audio.additional_codecs` (need transcoding) | V |
| 11 | User-initiated calling: everywhere Cloud API is available | V |
| 12 | Business-initiated: NOT available when the business number is in US, Canada, Egypt, Vietnam, Nigeria | V |
| 13 | Call permission required for business-initiated; error `138006` when missing | V |
| 14 | Permission request via free-form message in open service window, or template, or `callback_permission_status`, or permanent grant in business profile | V |
| 15 | Permission limits (production, per business+user): 1 request/day, 2/week; 2 consecutive unanswered -> reconsider notice, 4 -> auto-revoke. Sandbox (Tech Partners): 25/day, 100/week, 5/10 | V |
| 16 | 10,000 new business-initiated calls per number per 24 h; per-user 100 calls/day (changelog 2025-12-19, relation to the 1/day permission limit unclear) | V (10k), V (changelog) |
| 17 | Restrictions for low pickup rate (Sep 2025) and user feedback (Jan 2026) | V (exists), U (thresholds) |
| 18 | Can calling be enabled on the Meta-provided test number, and in which countries | U. Overview says test numbers are exempt from the 2,000 floor; the settings page says nothing about test numbers. First live step must confirm. |
| 19 | Calling pricing (per minute, by country, user- vs business-initiated, free tiers, increments) | U. Pricing page only says calling "has different pricing". Fetch `.../calling/pricing`. |
| 20 | Graph API version to pin | U (spike defaults v21.0; set to current) |

## 3. Call lifecycle

### 3.1 User-initiated (Phase 1)

Webhook `calls` / `event:connect` [V]: `calls[0] = {id, from, to, direction:"USER_INITIATED", timestamp, session:{sdp_type:"offer", sdp}, deeplink_payload?, cta_payload?}`; `contacts[0]` carries `wa_id`, `user_id`(BSUID), profile.

```
WhatsApp user   Meta            gwh (gunicorn)         Redis            huf-media (aiortc)        Frappe (whitelisted API)
   | call -------->|                |                    |                    |                          |
   |               |--POST connect->| verify X-Hub-Sig   |                    |                          |
   |               |  (SDP offer)   | admission(policy)  |                    |                          |
   |               |                | STOP/blocked?----> POST /calls reject (via sidecar-less direct call) ; Event(call,rejected)
   |               |                | Gateway Event(call,received)            |                          |
   |               |<--200 fast-----| RPUSH huf:media:calls {call_id,gateway,offer,audio_ref,deadline}
   |               |                |                    |--BLPOP------------>|                          |
   |               |                |                    |                    |--get_call_credentials--->|
   |               |                |                    |                    | setRemoteDescription(offer)
   |               |                |                    |                    | add audio track (gated: silence)
   |               |                |                    |                    | createAnswer, wait ICE gather
   |               |<------------------------ POST /calls pre_accept (SDP answer) ---|
   |<==== ICE + DTLS-SRTP (UDP, peer-to-peer media path to sidecar) ====>|
   |               |                |                    |                    | wait pc connected (timeout)
   |               |<------------------------ POST /calls accept (SAME SDP) ---------|
   |               |---200 OK------------------------------------------------------>|
   |<===== audio starts ONLY now (gate opens) ==========================|
   |               |<------------------------ POST /calls terminate (at EOF/max dur)|
   |               |--POST terminate webhook (status, start/end, duration, errors)-->| gwh updates Event
   |               |                |                    |<--PUBLISH huf:media:status----| record_call_result
```
Notes: pre_accept/accept bodies are `{messaging_product:"whatsapp", call_id, action, session:{sdp_type:"answer", sdp}}`; reject/terminate have no `session` [V]. `accept` SDP must equal the `pre_accept` SDP or it fails [V]. Answer deadline after connect webhook is about 30-60 s, then user sees Not Answered and a terminate webhook arrives [V]. Wait for 200 on accept before sending media, else first words are clipped [V]. Call `terminate` even if RTCP BYE was seen (affects pricing accuracy); not needed if the user hung up [V]. Terminate webhook: `status` COMPLETED|FAILED, `start_time/end_time/duration` only if answered, `errors` only on failure, echoes `biz_opaque_callback_data` if given on accept (<=512 chars) [V]. DTMF: clock rate 8000, PT 126 only [V].
Whether `pre_accept` is strictly required: Meta calls it recommended (research) [V-prior]; we always do it so ICE/DTLS completes before accept.

### 3.2 Business-initiated (Phase 2, later)
```
Huf -> send call-permission request (free-form in open window, or template)     [V]
User grants (or callback_permission_status / permanent grant)                    [V]
sidecar: RTCPeerConnection, createOffer (audio sendonly/sendrecv, Opus), wait ICE gather
sidecar -> POST /<PHONE_ID>/calls {messaging_product, to|recipient(BSUID), action:"connect",
                                    session:{sdp_type:"offer", sdp}, biz_opaque_callback_data?}  -> call id   [V]
Meta -> webhook calls event:connect direction:BUSINESS_INITIATED, session = SDP ANSWER             [V]
gwh -> Redis PUBLISH huf:media:answer:<call_id> -> sidecar setRemoteDescription(answer)
Meta -> status webhooks RINGING | ACCEPTED | REJECTED                                              [V]
on ACCEPTED (media connected): open gate, play, terminate action; terminate webhook closes Event.  [V]
```
Gates: not for US/CA/EG/VN/NG numbers; 138006 if no permission; 1 permission request/day/user.

## 4. Process model (Opus 5.5 recommendation, adopted)

A call is a long-lived stateful media session (ICE, DTLS, SRTP, a 20 ms audio clock, an ffmpeg subprocess) with a 30-60 s answer deadline. It must NOT run in gunicorn (request-bound, worker timeouts, no UDP lifecycle) nor in an RQ worker (blocks a slot, job timeouts, killed on restart, no sticky state). Use a dedicated **`huf-media` asyncio sidecar** (aiortc), same pattern as Frappe's socketio node process.

- Jobs in: Redis list `huf:media:calls` (RPUSH by gwh, BLPOP by sidecar). Job = `{call_id, gateway, direction, sdp_offer, audio_ref, max_seconds, deadline_ts}`. Drop jobs whose `deadline_ts` already passed (answer window gone) and write a `missed` Event.
- Status out: Redis pub/sub `huf:media:status` (`{call_id, stage, t}`), plus the durable result via whitelisted `huf.ai.whatsapp_calls.record_call_result` which writes the Gateway Event. Pub/sub alone is lossy; the Event is the record.
- Credentials: the sidecar never stores the WhatsApp token; it calls `get_call_credentials` (service API key) for a short-lived value (design from GAP_ANALYSIS section 3).
- Deployment: one more unit next to gunicorn/RQ: systemd (`huf-media.service`), supervisor program, or a compose service with `network_mode: host` (or a published UDP range). Restart policy always; on crash all live calls die, so `terminate` them best-effort on SIGTERM.
- Network: public IP reachable on a UDP port range (set aiortc/ICE port range; ~2 ports per call plus margin, e.g. 40000-40199 -> ~100 calls), outbound UDP to Meta media relays, STUN/TURN. aiortc defaults to Google STUN; a host with a public IP can run with no TURN **[U against Meta's relays]**; behind NAT or restrictive firewalls add coturn (TURN over 443/TCP+TLS as fallback). Today's Huf bench/prod topology exposes none of this **[from GAP_ANALYSIS]**.
- Capacity: aiortc is Python/GIL bound; Opus encode plus ffmpeg decode per call. One process per CPU core, scale by running N sidecars on the same list. CPU per call is a spike measurement (not yet measured). Go/Pion or a media server is the escape hatch above tens of concurrent calls.
- Audio prep: pre-transcode the greeting once to 48 kHz Opus/ogg at upload; avoids per-call ffmpeg cost spikes.

## 5. Data model additions (pre-release: no migrations/back-compat needed)

Gateway (WhatsApp type): `calling_enabled` (Check), `call_audio_file` (Attach, private File, <=~60 s, ogg/opus preferred), `call_greeting_text` (Small Text, accessible text alternative/for later TTS), `call_max_seconds` (Int, default 60), `call_max_concurrent` (Int, default 2).
Gateway Event: kind/type `call` with `call_id`, `direction`, `call_status` (received, rejected, answered, completed, failed, missed), `duration` (s), `terminate_reason` (user_hangup | eof | max_duration | ice_failed | answer_timeout | rejected_policy | error), `timings` (JSON: webhook->pre_accept->accept->first_rtp->terminate), reuse `wa_id`/BSUID contact link. `call_id` unique index for idempotency (Meta retries webhooks).

## 6. Security and compliance
- Verify `X-Hub-Signature-256` on the `calls` webhook with the same HMAC path as messages; reject unsigned. Do it before queueing (a forged connect would otherwise make the sidecar open media).
- Admission = same policy as messages (allow-list/pairing, STOP/opt-out, blocked) -> `reject` action, Event `rejected_policy`. Unknown callers: default reject unless gateway policy is open.
- Abuse: max concurrent calls per gateway and global, per-caller rate limit (e.g. 3 calls/hour), `call_max_seconds` hard cap enforced in the sidecar (terminate), job deadline check, bounded Redis list length.
- Idempotency on `call_id` (Meta may redeliver `connect`; never answer twice).
- Recording consent: Phase 1 plays audio only and records nothing. Any future recording/ASR needs an in-call consent announcement and legal review per jurisdiction **[U, legal]**. Do not store inbound audio by default.
- PII: caller number/BSUID in Event is personal data; mask in logs (last 4), do not log SDP bodies at INFO (contain IPs/ICE candidates/fingerprints). SDP IPs reveal the sidecar host publicly by design.
- Token handling: no token in the sidecar config or logs (see Credentials).

## 7. Observability
Per-call timings (webhook, answer_built, pre_accept_ok, dtls_connected, accept_ok, first_rtp_out, terminate_sent, terminate_webhook); counters by outcome and terminate_reason; gauge of live calls; ICE/DTLS failure count; p95 webhook->accept; sidecar CPU and RSS per call; Graph error codes (138006 etc.) logged with call_id. Surface as Gateway Event rows and sidecar structured logs; a health key `huf:media:heartbeat` (TTL 10 s) so gwh can reject early with "calling unavailable" instead of queueing into a dead sidecar.

## 8. Failure modes
| Failure | Handling |
|---|---|
| ICE/DTLS never connects (UDP blocked, wrong public IP) | connect timeout (spike 20 s) -> `terminate`, Event `ice_failed`; surfaced as top diagnostic |
| Answer deadline (30-60 s [V]) exceeded (slow queue, sidecar down) | deadline_ts in job; miss -> Event `answer_timeout`; heartbeat check prevents queueing |
| Audio clipped | gate opens only after accept 200 [V rule]; verified gate in selftest [L] |
| Silence after accept (late start) | start immediately on accept 200; measure accept->first_rtp_out |
| accept SDP != pre_accept SDP | build answer once, reuse string [L] |
| ICE gathering slow | measured 5.3 s locally with default STUN and many interfaces [L]; restrict interfaces/use a fixed host candidate to cut it; it eats the answer budget |
| Sidecar crash mid-call | supervisor restart; user sees call drop; Event left `answered` -> reaper marks `failed`; terminate webhook may still arrive |
| Duplicate/out-of-order webhooks | idempotent on call_id and status ordering |
| Graph 4xx on actions | log code; for connect-window errors just clean up; never retry accept blindly |
| Meta restricts number (low pickup, feedback) [V exists] | alert on rising rejected/FAILED ratio |

## 9. Cost
Calling has separate per-minute pricing [V that it is separate; U on rates/increments/free tiers]. A user call also opens the 24 h customer service window like a message [V on pricing page]. Terminate promptly: billing accuracy depends on the terminate action [V]. Cost of Phase 1 is dominated by minutes x rate; cap with `call_max_seconds`. Infra: one small VM with public IP/UDP range; TURN adds bandwidth cost only if needed.

## 10. Testing strategy
1. Unit: signature check, admission, job schema, Event mapping, idempotency (no network).
2. Local loopback: two aiortc peers, fake Graph recording action order (done in spike `--selftest`: order pre_accept, accept, terminate; zero media frames before accept) [L].
3. Fake Graph server + recorded webhook fixtures incl. terminate/FAILED/errors, replay duplicates.
4. Live: enabled test number (confirm item 18), host with public UDP, real phone: listen for clipping, measure timings, CPU, then business-initiated with a real permission grant (non-restricted country).
5. Soak: N simulated peers (aiortc callers) against the sidecar for CPU/port limits.

## 11. Rollout and effort
| Phase | Scope | Effort |
|---|---|---|
| 0 | This design + spike (done locally) | done |
| 1 | Live spike on test number (needs host, owner go-ahead) | 1-2 days |
| 2 | `huf-media` sidecar, Gateway fields, webhook routing, Events, admission, unit tests | ~1-1.5 weeks |
| 3 | Hardening: concurrency, TURN, metrics, reaper, UI toggle/upload | ~1 week |
| 4 | Business-initiated + permission-request flow | ~1 week, blocked on Meta/country |
Total to usable Phase 1: about 2-3 weeks; spike alone 2-3 days (matches GAP_ANALYSIS).

## 12. Spike: `wa_call_spike.py` (kept in the workspace track, not in this repo)
Standalone; aiohttp webhook server (GET challenge, POST HMAC check), connect -> RTCPeerConnection + remote offer + gated MediaPlayer track -> pre_accept -> wait connected -> accept (same SDP) -> open gate -> play N s -> terminate; terminate webhook handler; timing log; injectable post; `--dry-run`; `--selftest`.
aiortc facts used [L]: `MediaPlayer(file)` decodes through ffmpeg/PyAV; `setLocalDescription` returns after ICE gathering so `localDescription.sdp` is final; Opus is encoded by aiortc. The gate does not read the file before accept, so nothing is consumed early.
Selftest result (Python 3.14.7, aiortc 1.15.0, aiohttp 3.14.5, macOS): PASS. Action order pre_accept, accept, terminate; 0 frames received before accept; 147 frames received (about 3 s tone); webhook->answer_built 5.3 s (ICE gathering), accept->first outbound frame 25 ms.
NOT verified: any Meta interaction, Meta's SDP acceptance of aiortc's answer (codec/ICE/DTLS role/`a=setup`, ICE-lite expectations) [U], real-phone audio quality, CPU per call.

### Live-spike exit criteria
1. Audio heard on the phone, first words not clipped.
2. webhook -> accept under 10 s (ICE gather time reduced from 5 s if needed).
3. terminate webhook arrives with `COMPLETED` and a sane `duration`.
4. 10 consecutive calls without leaked sockets/processes; CPU per call recorded.
5. Failure paths exercised: blocked UDP -> `ice_failed` terminate; unanswered -> terminate webhook.
Fail -> record findings, decide between fixing SDP/ICE or the SIP+Asterisk alternative.

## 13. Open questions for the owner
1. Which number/country for the live spike; OK to enable calling on the test number (item 18) or use a real number >= 2,000 limit?
2. Host with public IP and a UDP range (and who opens the firewall)? Is TURN acceptable?
3. Is Phase 1 (inbound greeting) enough value, or is a conversational (ASR/TTS) call the real goal? That changes the media stack.
4. Business-initiated blocked for US/CA/EG/VN/NG numbers: which numbers will Huf customers actually use?
5. Recording/consent stance (none in v1?).
6. Budget approval for per-minute call charges (rates unverified).
7. Admission for unknown callers: reject by default or follow gateway open policy?

## 14. Owner decisions and what is implemented (2026-10-21)

Decisions: scope = GREETING plus optional pre-recorded reply/closing clips (no live conversation); number is US (+1 555-075-1406), so business-initiated calls are NOT available (item 12) and only user-initiated calls apply; policy = NO RECORDING (call audio is never stored, only metadata is logged), unknown callers are rejected, the greeting audio must announce an automated assistant; Calling was enabled on the test number by the owner. Default route stays webhook + WebRTC.

Implemented (all mocked-tested, nothing invoked live, default OFF):
- `gateway_adapters/whatsapp_calls.py`: `calls` webhook normalisation (`WhatsAppCall`; connect, terminate, call-typed `statuses`), payload builders (call actions, calling settings, `call_permission_request`), `CallsGraph` Graph wrapper with injectable HTTP, strict `call_admission`, Gateway Event recording (`raw_payload.kind == "call"`, metadata only, SDP never stored), `handle_call` routing.
- `whatsapp.py`: `parse_payload` returns `WhatsAppParsed.calls`; `gateway_webhook._handle_calls` routes them. Calls never start an agent run (no config switch exists yet).
- `whatsapp/management.py`: `get_calling_settings`, `set_calling_settings`, `call_action`, `send_call_permission_request` (admin only; permission request obeys opt-out and the 24 h window).
- `whatsapp_call_flow.py`: state machine `run_call` (received, answering, pre_accepted, connected, accepted, playing, terminating, completed|failed|rejected), `answer_inbound_call_job`, `AiortcMediaSession` (lazy import; `get_media_backend()` reports `not_installed`, the job then rejects the call and marks the event Failed).
- Gateway fields: `calling_enabled` (Check, default 0), `call_greeting_audio`, `call_reply_audio`, `call_closing_audio`, `call_max_seconds`.
- Offline simulator `huf/testing/wa_call_sim.py` (+ tests in `huf/ai/tests/test_whatsapp_calls.py`).

Behaviour: calling off -> a metadata Event (Rejected, "Calling is not enabled") and NO Graph call. Calling on, caller not in an approved Sender access entry (or blocked/opted out; `Open` and `Pairing` policies do NOT admit a caller, no pairing request is created) -> `reject` action sent and recorded on the Event (success or error), status Rejected. Approved caller -> Event Received, `answer_inbound_call_job` enqueued (idempotent on `call_id`); flow: pre_accept, wait media, accept with the SAME SDP, open the audio gate, play clips, terminate. `terminate`/status webhooks update the same Event (COMPLETED -> Succeeded, FAILED -> Failed).

No-recording invariant: caller audio goes only to `CallAudioSink`; `InMemoryAudioSink` keeps name/bytes/sha256 and nothing else (`retain=True` exists only for simulator assertions); `AiortcMediaSession` drains and discards inbound RTP; Events and `CallTrace` hold no SDP and no audio. A test asserts no file I/O during a call.

Stubbed / not verified: `AiortcMediaSession` (ported from the spike, never run against Meta; aiortc is not a declared dependency); the RQ job runs the media in a worker, the design target remains the `huf-media` sidecar; `call_permission_request` JSON is from recall (docs page 404 today) [U]; the settings greeting is the voicemail announcement (`voicemail.audio.default.announcement_media_id`, upload via `/media` with `use_case=call_voicemail_announcement`, Opus, < 60 s) [V] but no upload wrapper exists; Gateway audio fields are not yet synced into Meta settings; no UI.

### 14.1 Audio interfaces and the realtime hook
`CallAudioSource.next_clip(heard) -> AudioClip | None` (bot side; `wants_caller_audio` makes the flow `listen` after each clip), `CallAudioSink.write(clip)` (caller side, must not persist), `MediaSession` (transport: `create_answer`, `wait_connected`, `open_gate`, `play`, `listen`, `close`). Now: `FilePlayback` (2-3 files in order) and `InMemoryAudioSink`. A realtime provider (e.g. Gemini Live) later implements a duplex source/sink pair over the same `MediaSession` (stream frames instead of clips); the flow, admission, events and terminate logic stay unchanged. The clip-based `next_clip` is turn-based, so a true streaming bridge will need a frame-level `MediaSession.stream(source, sink)` addition.

### 14.2 Simulating a call without Meta
`python huf/testing/wa_call_sim.py [--unknown]` (bench python; no site, DB, network or aiortc needed) feeds a signed simulated `calls` connect webhook through the real adapter parser and `run_call` with `FakeMediaSession`: greeting -> caller file(s) heard (memory only) -> bot reply -> closing -> terminate, then a simulated terminate webhook; it prints a metadata-only report (states, actions, played, heard hashes). `--unknown` shows the reject path. An aiortc loopback variant is not implemented.

## 15. SIP vs WebRTC (aiortc) signalling [V: developers.facebook.com/docs/whatsapp/cloud-api/calling/sip, fetched 2026-10-21]

SIP facts: enable with `settings.calling.sip = {status: ENABLED, servers: [{hostname, port (default 5061, TLS only), request_uri_user_params?}], webhook_delivery?}`; one effective SIP server per number; while SIP is enabled the number does NOT work with the Graph calling endpoints (pre_accept/accept/reject/terminate, connect) and the `calls` webhooks are off unless `webhook_delivery` is ENABLED (then only `call_created`/`terminate`, no SDP). Auth: SIP digest; Meta generates a password per number+app, read with `GET /<PHONE_ID>/settings?include_sip_credentials=true` (needs `whatsapp_business_management` Advanced access); username is the normalised business number; rotate by disable, clear servers, re-enable. TLS mandatory (Meta cert covers `wa.meta.vc`; yours must match the configured hostname; optional mTLS when your server requests a client cert). Media: SRTP with DTLS key exchange by default or SDES (key in SDP, skips ICE/STUN/DTLS, faster setup); the business side must send the first SRTP packet; Opus 48 kHz is the example codec, `telephone-event/8000` for DTMF; whether media flows straight to your SIP server is not stated explicitly (confirm with Meta); allowlist Meta's IP ranges for signalling and media. User-initiated flow: Meta INVITEs your server (answer with a digest challenge, then 200 OK with SDP). Meta adds custom headers (`x-wa-meta-wacid`, phone-number-id, user id, `x-wa-meta-call-duration` on BYE, cta/deeplink payloads). App mode must be Live.

| | Webhook + WebRTC (aiortc), current route | SIP |
|---|---|---|
| Signalling | Graph `/calls` actions + `calls` webhook, SDP in JSON | SIP INVITE/200/BYE over TLS to our server |
| Settings change | none | switches the number to SIP-only; Graph calling actions stop working (reversible by disabling) |
| Our component | aiortc app (Python), tied to Huf webhook/Event code | any SIP server: Asterisk, FreeSWITCH, Pipecat/Pion/LiveKit SIP |
| Caller admission | in Huf (reject action) | in the SIP layer (needs an HTTP lookup into Huf by `x-wa-meta-*` headers or caller id; digest-challenge is not admission) |
| Playing files | MediaPlayer + gated track, self-written | native (Asterisk `Playback`, FreeSWITCH `playback`), battle tested |
| Media setup | ICE + DTLS-SRTP, aiortc compatibility with Meta unproven | DTLS or SDES; SDES is simpler, no ICE |
| Infra | public UDP range, STUN/TURN maybe | public TLS 5061 + cert + SRTP/UDP range; a real SIP/media server to operate |
| Observability | Huf Events natively | SIP logs + optional `webhook_delivery` for `call_created`/`terminate` |
| Realtime (Gemini Live) | aiortc track to PCM bridge in Python; fine for a few calls | SIP server or Pipecat/LiveKit bridges audio to the model; scales better |

Recommendation. Greeting-only with audio-file playback: stay on webhook + WebRTC for the first live test (no settings change beyond Calling, reuses Huf admission/Events, already coded and simulated). If aiortc fails against Meta's SDP/ICE (spike exit criteria in section 12) or capacity matters, switch to SIP with Asterisk or FreeSWITCH playing the files: it is the lowest-risk playback path, with SDES for simple media. Realtime (Gemini Live) later: prefer SIP into a media framework (Pipecat or LiveKit SIP, or FreeSWITCH with a streaming module) over growing aiortc, because codec/jitter/scale work is already solved there; keep the `CallAudioSource`/`CallAudioSink` interfaces as the Huf-side contract either way. Do not enable SIP on the test number until the WebRTC route has been tried: enabling it disables the Graph call endpoints this implementation uses.

## 16. Media path from a NAT'd Mac: Meta docs findings and ICE strategy (2026-10-21)

Legend as above. Sources fetched today: https://developers.facebook.com/docs/whatsapp/cloud-api/calling/user-initiated-calls and https://developers.facebook.com/docs/whatsapp/cloud-api/calling/reference.

| Topic | Finding |
|---|---|
| Connect webhook | `calls[]` with `id`, `from`, `to`, `event: "connect"`, `timestamp`, `session {sdp_type: "offer", sdp}`; optional `deeplink_payload`, `cta_payload`, `from_user_id` [V] |
| SDP rules | "compliant with RFC 8866". Answer is sent in `pre_accept` and again in `accept`; accept errors if the answer differs from the pre_accept one [V]. Docs table says `sdp_type` "offer" but all samples use "answer" (doc inconsistency; Huf sends "answer") [V] |
| Timing | Answer window "about 30 to 60 seconds" after connect; otherwise "Not Answered" + terminate webhook [V]. `pre_accept` recommended to connect media early and avoid clipped audio; start sending media only after its 200 OK; with pre_accept, media flows right after accept [V]. Other timeouts (ICE, DTLS, media) not stated [U] |
| ICE-lite | Sample user-initiated OFFER contains `a=ice-lite` [V as sample only]; docs do not say it is required or promise it always holds [U]. Samples also show `ice-options:trickle`, `ice-ufrag/pwd` |
| Candidates | Samples show only `typ host` candidates [V as sample]. Nothing on srflx/relay/tcp/IPv6 support [U]. STUN/TURN: not stated anywhere [U] |
| DTLS role | Not mandated. Sample offers `a=setup:actpass`, sample answers `a=setup:active`, `sha-256` fingerprints [V as sample]. aiortc answers `active` to `actpass` (same as sample) |
| Codecs | No codec mandated. Sample offers Opus 48000/2 (pt 111, `minptime=10;useinbandfec=1`), G722, PCMU, PCMA, telephone-event (8000), sometimes red [V as sample]. aiortc answers with Opus. Docs: user-initiated offer uses 8000 clock rate for DTMF (RFC 4733) |

Consequence: if Meta's offer is ice-lite with public host candidates, the full-ICE side (aiortc on the Mac) does the checks outbound. An outbound-only NAT is enough, no inbound port forward, and even a symmetric-like NAT is fine because replies come from the exact address we probed. This is the primary plan and is UNPROVEN until a live call shows the offer's candidates.

### Strategy (in this order)
1. Default: direct UDP, STUN only (`IceConfig` defaults: Google + Cloudflare STUN; aiortc uses the first). No config needed.
2. Fallback: TURN over TCP/TLS 443 with `relay_only` (below). Needed only if the offer has no usable public UDP candidate or outbound UDP to Meta's media IPs is blocked.
3. Last resort: SIP (section 15) or a host with a public IP.

### Config keys (site_config.json or env; env wins; the credential is never a DocType field and is never logged)
| Site config key | Env var | Meaning |
|---|---|---|
| `huf_wa_call_stun_urls` | `HUF_WA_CALL_STUN_URLS` | comma list `stun:host:port` (default Google + Cloudflare) |
| `huf_wa_call_turn_urls` | `HUF_WA_CALL_TURN_URLS` | e.g. `turns:turn.example.com:443?transport=tcp` or `turn:host:443?transport=tcp` (aiortc supports tcp transport only for turns) |
| `huf_wa_call_turn_username` / `_credential` | `HUF_WA_CALL_TURN_USERNAME` / `_CREDENTIAL` | TURN auth |
| `huf_wa_call_relay_only` | `HUF_WA_CALL_RELAY_ONLY` | `1` = force relay candidates only (like `iceTransportPolicy: relay`). Needs TURN. aiortc has no such option; Huf sets aioice's RELAY policy on the gatherers and fails closed if it cannot |

aiortc limits: one STUN and one TURN server are used (first of each).

### Measured today [L] (this Mac, home NAT, `wa_call_ice_probe.py` (kept in the workspace track, not in this repo))
- Outbound UDP and replies work. Public STUN returned srflx `103.94.138.221`.
- Mapping is address/port dependent: Google saw port 50715, Cloudflare 50716 for the same local socket (symmetric-like). Fine vs an ice-lite public peer, bad for hole-punching to a full-ICE peer.
- Public Open Relay (`openrelay.metered.ca`) is dead: DNS now resolves to 192.0.2.1 (TEST-NET), TCP 80/443/3478 time out. You need your own TURN (coturn, or a metered/Twilio/Cloudflare account) if the fallback is required.
- Loopback proof `wa_call_loopback_test.py` (kept in the workspace track, not in this repo) [L]: Huf's real `AiortcMediaSession` + `run_call` answered an aiortc "Meta" peer; action order pre_accept, accept, terminate; Opus greeting decoded on the peer (97 frames, 95 non-silent), silent before accept.

## 17. Ops: running a live call test (needs the owner)

Prereqs: Calling enabled on the test number (already done by the owner, do not change from here), webhook `calls` field subscribed, ngrok HTTP tunnel to the bench webhook, aiortc + ffmpeg in the bench Python (`pip install aiortc`; `brew`/apt ffmpeg), Gateway: `calling_enabled=1`, an allowed caller, greeting audio uploaded (private File, Opus/ogg/wav ok).
1. Probe the network first: `python wa_call_ice_probe.py` (add `--turn-test --turn-url host:443` with `TURN_USER`/`TURN_PASS` env to test your own TURN). Expect "outbound UDP: OK".
2. Optional env/site config for TURN (above); leave unset for the first attempt.
3. Start the bench with the ngrok override already used for WhatsApp webhooks; confirm the `connect` webhook arrives (Gateway Event "Received").
4. From the admitted phone, call the business number. Watch: Event goes Answering, pre_accepted, connected, accepted, completed; you hear the greeting; the call hangs up.
5. Do not log SDP. To see candidates, inspect only the offer's `a=candidate` and `a=ice-lite` lines locally (they reveal Meta IPs, not secrets).

If ICE fails (Event `ice_failed`, terminate after 20 s):
- Check the offer: no `a=candidate ... typ host/srflx` public UDP lines or no `a=ice-lite` means plan 1 is wrong; go to TURN relay-only.
- Re-run the probe; NO_UDP means outbound UDP is blocked (hotspot, firewall): use `turns:...:443?transport=tcp` + `relay_only=1`.
- ICE completes but no DTLS: compare `a=setup`/fingerprint in the answer; Meta may require `a=setup:active` in the answer (aiortc does this) and the SAME SDP in accept.
- No audio after accept: confirm the gate opened only after accept 200, ffmpeg can decode the clip, and the clip is not empty.
- Accept error about SDP mismatch: pre_accept and accept must send the identical answer (the flow does).
- Slow answer (>10 s): ICE gathering with many interfaces (measured 5 s); reduce STUN servers/interfaces.
- Last resort: SIP, section 15.
