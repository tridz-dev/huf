# auth_status.json — Claude Code CLI

- **Status:** REAL (live captured run), sanitized
- **CLI version:** `2.1.281 (Claude Code)`
- **Exact command run:** `claude auth status`
- **Sanitization applied:** `projectsDirectory`/`configDirectory` had the real home dir replaced with `<HOME>`; `email`, `orgId`, `orgName` replaced with placeholders (values were the real Anthropic account email, org id and org name — all real values, redacted here).
- **Confirms:** PLAN.md §16's assumption that `claude auth status` returns machine-readable JSON with an explicit `authMethod` (here `"claude.ai"` = subscription OAuth) distinct from `apiProvider: "firstParty"`. This is the field HUF's adapter should probe to confirm subscription (not API-key/Console) login before attempting a run. `subscriptionType: "max"` is also present and could gate plan-tier features.
- **Not captured live:** the JSON shape when NOT logged in (would require logging out this real account, which was not done to avoid disrupting the user's environment). Treat the logged-out/error shape as unverified until captured separately.
