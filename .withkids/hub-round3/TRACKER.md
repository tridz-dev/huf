# withkids tracker — Hub round 3 (UX polish + tool-call bug fixes + ask_user)

Repo: /Users/safwan/Code/Docker/frappe_docker/development/16/apps/huf
Site: huf.localhost:8000 · Branch: feat/design-simplified-hub-homepage-interface

## Diagnosed root causes (parent)

- BUG-1: sdk_tools.py on_invoke_tool injected run-context agent_name/conversation_id/agent_run_id, CLOBBERING explicit LLM args (verified in tabAgent Tool Call). Fixed via `_merge_run_context` setdefault semantics.
- BUG-2: confirm sent as string "false" is truthy → preview executed. Fixed via `_as_bool` coercion in all 9 two-phase tools.

## Tasks

| id | task | kid | status | result |
|----|------|-----|--------|--------|
| R3-T1 | Backend fixes + tools | coder | done | sdk_tools _merge_run_context; _as_bool in 9 tools; create_huf_table returns already_exists+schema; NEW list_provider_options (configured flags, suggested, no key material); NEW ask_user.py tool; registry + seeding updated; 65/65 tests OK |
| R3-T2 | Hub chat UI | coder | done | NEW HubAskUser.tsx (yes_no/single/multi/input/textarea, icon allowlist, locks after answer); splitAskUserBlocks parser; onSendText wired ('Regarding "q": answer'); composer no longer jumps on focus, subtle downward slide on first send; greeting "What can I do for you."; rail default visible confirmed; tsc + build clean |
| R3-T3 | History icon fix | coder | done | Root cause: IconRailButton didn't forward ref → Radix PopoverTrigger asChild never wired. forwardRef fix in IconRail.tsx; tsc clean |
| R3-T4 | Parent integration | parent | done | hub-orchestrator.json rewritten (GATHER→PLAN(mermaid)→single ask_user confirm→EXECUTE confirm=true→REPORT+navigate; provider rules via list_provider_options; ask_user rules); live agent doc updated; migrate synced+attached list_provider_options & ask_user to Hub Orchestrator; draft_agent string-confirm verified live (preview→create→cleanup); tests 65+5+8 all OK; bundle served (ask-user + greeting in Hub chunk); ping OK |

## Coverage of user items

1. Rail collapsed by default — IconRail is always-collapsed 48px; defaults visible ✓
2. Composer focus jump — removed; transitions only on first send ✓
3. Greeting — "What can I do for you." ✓
4. "already exists" confusion — BUG-2 fixed + friendly already_exists result ✓
5. Provider/model suggestions — list_provider_options tool + instructions (never ask non-experts; suggest + tell) ✓
6. Multi-level confirmation — GATHER/PLAN/EXECUTE/REPORT single-confirm flow in instructions ✓
7. UI tool calling — ask_user tool (backend) + HubAskUser renderer (frontend) + instructions ✓
8. Create-agent failure — BUG-1 fixed; exact failing call verified working live ✓
9. History icon dead — forwardRef fix ✓

## Notes

- Nothing committed/pushed (needs explicit confirmation).
- Live browser pass recommended: ask the hub to build something small; watch ask_user cards, single confirmation, provider auto-pick.
