# Decision Runtime PR 2 schema proposal

Status: preparation only. This note does not implement DocTypes and must not be merged as PR 2 implementation until PR 1 contracts are accepted.

## Dependency boundary

PR 2 consumes the PR 1 identity fields (`model_class`, `model_family`, `canonical_model`, `canonical_version`, `provider`, `deployment`, `provider_model_id`) and `DecisionPolicy`/`DecisionPolicyVersion` fingerprints. It must not introduce provider-specific identity into canonical model fields or change the normalized backend contract.

## Recommended first slice

Implement these persisted concepts as separate DocTypes:

1. **Decision Model Class** — `class_key`, display name, description, enabled, capability schema metadata.
2. **Decision Model Family** — `family_key`, display name, link to class, developer, enabled, capabilities metadata. No provider fields.
3. **Decision Model** — `model_key`, display name, link to family, canonical version, enabled, capability/state limits, metadata.
4. **Decision Provider** — `adapter_id` (stable hook ID), enabled, local flag, validated API base URL, encrypted credential, timeout/retry configuration. Never persist an arbitrary Python import path.
5. **Decision Deployment** — name, canonical model link, provider link, provider model ID, enabled/default/priority, capability overrides, input modalities, limit/pricing overrides, health metadata.
6. **Decision Policy** and **Decision Policy Version** — portable policy definition/fingerprint, target family/model (optional explicit deployment pin), state bindings, fallback action, activation/version metadata.
7. **Decision Call** — requested and resolved canonical identities plus provider/deployment/provider model ID, deployment selection source/chain/count, policy fallback action, normalized answers, usage, state hash, and redacted optional snapshot.
8. **Agent Decision Binding** — opt-in surface binding to a policy/model/family/deployment; absent bindings preserve current behavior.

If implementation scope must be reduced, keep Family + Provider + Deployment as the minimum, but preserve Class and Model as explicit concepts in stable keys/fields and document the migration path.

## Constraints and indexes

- Unique stable keys for class, family, model, provider adapter ID, and deployment name within their intended namespace.
- A model belongs to exactly one family; a deployment references one canonical model and one provider.
- `provider_model_id` is deployment-scoped and never used as canonical model identity.
- At most one enabled default deployment per canonical model/provider selection scope; priority is deterministic, not probabilistic.
- Policy versions are immutable after activation; fingerprint covers questions, state bindings, modalities, limits, and fallback semantics.
- Decision Call is append-oriented and stores sanitized labels only; credentials and raw provider payloads are excluded.
- Provider credentials use encrypted Frappe fields; adapter resolution remains hook/registry based.

## Seed records for later PR 3

- Class: `system_one`
- Family: `jev`
- Model: `jev-1.13`, canonical version `1.13`
- Provider: `opencode_zen`, adapter ID resolved through installed-app hooks
- Deployment: `jev-1.13-opencode`, provider model ID `jev-1.13-free`

This proposal intentionally leaves Jev transport and structured LLM implementation to PR 3. Sanitized live response fixtures are prepared separately in the PR 3 fixture worktree.

## Acceptance checks before implementation

- Verify current Frappe DocType naming/JSON conventions and encrypted-field patterns.
- Verify PR 1 branch is accepted/stable and no identity field changes remain.
- Add migration/seed strategy and permission rules before creating schema files.
- Add round-trip tests proving the same canonical model can reference multiple deployments/providers without changing policy identity.
