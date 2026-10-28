# WhatsApp Broadcast limits

Generated from `huf/ai/whatsapp/broadcast/policy.py` (`python -m huf.ai.whatsapp.broadcast.policy`); a
test fails when this file drifts from the registry. Do not edit the table by hand.

Effective value = per-broadcast override, then **WhatsApp Broadcast Settings**, then the default.
A blank setting uses the default. For the two recipient caps, `0` means no limit.

| Key | Limit | Type | Default | Range | Unit | Note |
| --- | --- | --- | --- | --- | --- | --- |
| `template_approved_only` | Templates must be approved | Set by Meta | on | - | - | Meta only delivers APPROVED templates to start a conversation. |
| `messaging_tier_24h` | Unique contacts per 24 hours | Set by Meta | - | - | contacts | Set by your WhatsApp messaging tier (250, 1K, 10K, 100K, unlimited). Read live from Meta when a broadcast is chosen. |
| `quality_rating` | Number quality rating | Set by Meta | - | - | - | Set by Meta from user feedback; a low rating can reduce your tier. |
| `marketing_stop_131050` | Contacts who stopped marketing | Set by Meta | on | - | - | Meta rejects marketing messages to contacts who chose to stop them (error 131050); they are skipped. |
| `opt_out_stop` | STOP replies | Set by Meta | on | - | - | Contacts who reply STOP are never messaged again until they opt back in. |
| `bsuid_refused` | Username-only contacts | Set by Meta | on | - | - | A business-scoped user ID cannot be used as a recipient; send to the phone number. (Not verified against Meta's documentation.) |
| `us_plus_one_marketing` | US (+1) marketing | Set by Meta | on | - | - | Meta does not deliver marketing templates to US +1 numbers. (Not verified against Meta's documentation.) |
| `per_user_marketing_limit_131049` | Per-contact marketing cap | Set by Meta | on | - | - | Meta limits how many marketing messages one person receives (error 131049); that contact is skipped. |
| `header_text_max` | Header text length | Set by Meta | 60 | - | characters | Template header text is limited to 60 characters. |
| `copy_code_max` | Copy-code length | Set by Meta | 15 | - | characters | A copy-code button value is up to 15 letters or digits. (Not verified against Meta's documentation.) |
| `max_phone_digits` | Phone number length | Set by Meta | 15 | - | digits | E.164 allows at most 15 digits. |
| `max_recipients_default` | Recipients per broadcast (default) | Huf setting | 1000 | 1 to 1e+07 | recipients | Used when a broadcast does not set its own cap. 0 = no limit. |
| `max_recipients_ceiling` | Recipients per broadcast (highest allowed) | Huf setting | 10000 | 1 to 1e+07 | recipients | No broadcast may ask for more than this. 0 = no limit. |
| `max_rows_per_broadcast` | Stored rows per broadcast | Huf setting | 50000 | 1 to 1e+07 | rows | Includes skipped contacts. |
| `max_rows_per_request` | Recipients per request | Huf setting | 10000 | 1 to 1e+06 | rows | How many recipients one add call accepts. |
| `max_csv_mb` | CSV size | Huf setting | 2 | 1 to 100 | MB | Largest CSV text accepted in one request. |
| `min_phone_digits` | Shortest phone number | Huf setting | 8 | 5 to 15 | digits | Numbers with fewer digits are rejected as invalid. |
| `returned_list_limit` | Skipped rows echoed back | Internal | 200 | - | rows | How many skipped/invalid entries an add call lists; totals are always exact. |
| `location_text_max` | Location name/address length | Internal | 1000 | - | characters | Huf's own cap; Meta does not state a length. (Not verified against Meta's documentation.) |
| `url_suffix_max` | Link suffix length | Internal | 2000 | - | characters | Huf's own cap; Meta's documented URL maximum is 2000. (Not verified against Meta's documentation.) |
| `default_mps` | Default sending speed | Huf setting | 20 | 1 to 1000 | messages/s | Used when a broadcast sets no speed. |
| `max_mps_cap` | Speed cap | Huf setting | 80 | 1 to 1000 | messages/s | Meta's default throughput is 80/s. When Meta reports a rate it is used unless you set a lower cap here. |
| `ramp_first_batch` | First batch size | Huf setting | 20 | 1 to 1000 | messages | Sending starts small, then doubles each chunk. |
| `max_batch` | Largest batch | Huf setting | 200 | 1 to 5000 | messages | Upper bound for one chunk. |
| `max_attempts` | Attempts per recipient | Huf setting | 5 | 1 to 20 | attempts | After this many tries a recipient is marked failed. |
| `auth_defer_seconds` | Wait after an access-token error | Huf setting | 300 | 10 to 86400 | seconds | The recipient is retried after this delay. |
| `gateway_down_defer_seconds` | Wait when the gateway is down | Huf setting | 300 | 10 to 86400 | seconds | The recipient is retried after this delay. |
| `held_throttle_enabled` | Slow down when Meta holds messages | Safety | on | - | - | Cuts speed to a quarter while many messages are held for quality assessment. |
| `held_ratio_limit` | Held-message ratio that slows sending | Safety | 0.3 | 0.01 to 1 | ratio | Share of recent sends held by Meta before sending slows. |
| `held_window` | Held-message window | Safety | 50 | 10 to 500 | messages | How many recent sends are examined. |
| `min_held_sample` | Minimum sample before slowing | Safety | 10 | 1 to 100 | messages | Avoids slowing on one held message out of two. |
| `one_active_per_gateway` | One running broadcast per gateway | Safety | on | - | - | On: only one broadcast sends from a gateway at a time. Off: broadcasts run side by side and share the gateway's sending speed and its 24-hour contact budget. |
| `concurrent_broadcast_max` | Most broadcasts running at once | Safety | - | 2 to 50 | broadcasts | Only used when one running broadcast per gateway is off. Blank or 0 = no limit. |
| `require_typed_count` | Type the recipient count to start | Safety | on | - | - | The start step asks for the queued count (callers using API keys skip the typing). |
| `require_consent_attestation` | Require consent confirmation | Safety | on | - | - | Meta requires opt-in for business-initiated messages; this box is Huf's record of it. |
| `tick_timeout` | Worker job timeout | Internal | 1800 | - | seconds | - |
| `tick_budget_seconds` | Work per tick | Internal | 240 | - | seconds | A tick works this long, then re-enqueues itself. |
| `lock_ttl` | Tick lock lifetime | Internal | 600 | - | seconds | - |
| `heartbeat_seconds` | Lock refresh interval | Internal | 30 | - | seconds | - |
| `heartbeat_every_sends` | Lock refresh every N sends | Internal | 20 | - | messages | - |
| `perm_recheck_every_sends` | Permission re-check every N sends | Internal | 50 | - | messages | - |
| `stale_sending_minutes` | Stuck 'sending' timeout | Internal | 10 | - | minutes | A row stuck sending this long becomes 'unknown' and is never resent. |
| `limits_cache_ttl_seconds` | Meta tier/quality cache | Internal | 600 | - | seconds | - |
| `prepare_retries` | Retries on database deadlock | Internal | 3 | - | attempts | - |
| `rate_create_broadcast` | Create broadcast | Safety | 60 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_add_recipients` | Add recipients | Safety | 60 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_remove_recipient` | Remove recipient | Safety | 120 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_delete_broadcast` | Delete broadcast | Safety | 30 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_attest_consent` | Confirm consent | Safety | 60 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_start_broadcast` | Start broadcast | Safety | 30 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_pause_broadcast` | Pause broadcast | Safety | 60 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_resume_broadcast` | Resume broadcast | Safety | 60 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_cancel_broadcast` | Cancel broadcast | Safety | 60 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_pause_all` | Pause all broadcasts | Safety | 30 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_limits_read` | Read limits | Safety | 120 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_limits_write` | Change limits | Safety | 30 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_audience_read` | Audience reads | Safety | 240 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_audience_write` | Audience changes | Safety | 60 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `rate_audience_import` | Audience import | Safety | 20 | 1 to 1000 | requests/min | Requests allowed per minute for this action, per caller address. |
| `audience_max_members` | Contacts per audience | Huf setting | 200000 | 1 to 1e+07 | contacts | An audience stops accepting new contacts at this size. |
| `audience_inline_import_rows` | Import size run immediately | Huf setting | 10000 | 1 to 1e+06 | rows | Larger imports run in the background. |
| `audience_max_import_rows` | Contacts per import | Huf setting | 200000 | 1 to 1e+07 | rows | Most contacts one import may hold. |
| `audience_max_csv_mb` | Audience CSV size | Huf setting | 20 | 1 to 200 | MB | Largest CSV text accepted for an audience import. |
| `audience_max_tags_per_member` | Tags per contact | Huf setting | 20 | 1 to 100 | tags | Most tags one contact can carry. |
| `audience_max_tag_length` | Tag length | Huf setting | 50 | 1 to 200 | characters | Longest tag accepted. |
| `audience_max_name_length` | Contact name length | Huf setting | 140 | 1 to 140 | characters | Longer names are rejected on import. The stored name field holds 140 characters. |
| `audience_max_remove_per_request` | Contacts removed per request | Huf setting | 10000 | 1 to 1e+06 | contacts | Most contacts one remove call accepts. |
| `audience_page_size_max` | Audience page size | Huf setting | 200 | 10 to 1000 | rows | Largest page of members or audiences returned at once. |
| `audience_max_selection_items` | Audiences per broadcast | Huf setting | 25 | 1 to 100 | audiences | Most audiences one broadcast selection may combine. |
| `audience_import_chunk` | Import commit size | Internal | 1000 | - | rows | Rows written per database commit during an import. |
| `audience_suppression_chunk` | Suppression lookup size | Internal | 500 | - | contacts | Contacts checked against opt-outs per query. |
| `audience_import_job_ttl` | Import progress kept | Internal | 86400 | - | seconds | How long a finished import's progress stays readable. |
| `over_budget_hold_hours` | Over-budget hold | Internal | 24 | - | hours | Rows beyond the 24h budget wait until the oldest counted send leaves this window (or this long from now). |
| `defer_chunk` | Deferral update size | Internal | 1000 | - | rows | Rows updated per query when holding rows back. |
| `progress_throttle_seconds` | Progress update spacing | Internal | 2 | - | seconds | Live progress is sent at most this often per broadcast or import. |
| `api_rate_window_seconds` | API rate window | Internal | 60 | - | seconds | The window the per-minute request limits are counted over. |
| `consent_source_max` | Consent note length on a broadcast | Internal | 200 | - | characters | Audience-based consent notes are cut to this length. |
| `member_consent_source_max` | Imported consent note length | Internal | 255 | - | characters | Per-contact consent text is cut to this length on import. |
| `audience_delete_chunk` | Contact removal chunk | Internal | 1000 | - | contacts | Contacts deleted per query when removing members. |
