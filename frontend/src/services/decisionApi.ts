import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * Decision Model option for pickers and dropdowns
 */
export interface DecisionModel {
  name: string;
  model_key: string;
  model_name: string;
  family: string;
  canonical_version: string;
  display_name: string;
  enabled: number;
  context_limit: number;
  state_limit: number;
  deployments?: DecisionDeployment[];
}

/**
 * Decision Deployment (admin only)
 */
export interface DecisionDeployment {
  name: string;
  deployment_name: string;
  provider: string;
  provider_model_id: string;
  wire_protocol: string;
  enabled: number;
  is_default_for_model: number;
  priority: number;
  health_status: string;
  last_healthcheck: string;
  latency_budget_ms: number;
}

/**
 * Answer to a single question in a decision response
 */
export interface DecisionAnswer {
  question_id: string;
  kind: string;
  value: unknown;
  probabilities: Record<string, number> | null;
  confidence: number;
  backend_metadata?: Record<string, unknown>;
}

/**
 * Identity of the model/deployment that handled the decision
 */
export interface DecisionIdentity {
  model_class: string;
  model_family: string;
  canonical_model: string;
  canonical_version: string;
  provider: string;
  deployment: string;
  provider_model_id: string;
}

/**
 * Usage statistics for a decision run
 */
export interface DecisionUsage {
  input_tokens: number;
  output_tokens: number;
  cost: number;
  cost_source: string;
}

/**
 * Response from a decision run (in run_decision result)
 */
export interface DecisionResponse {
  status: string;
  answers: Record<string, DecisionAnswer>;
  identity: DecisionIdentity;
  requested_identity: DecisionIdentity;
  backend_adapter: string;
  requested_model: string;
  requested_model_version: string;
  resolved_model: string;
  resolved_model_version: string;
  usage: DecisionUsage;
  latency_ms: number;
  error_code: string | null;
  policy_fallback_action: string | null;
  gate_result: string | null;
  deployment_selection_source: string;
  deployment_fallback_count: number;
  deployment_fallback_chain: string[];
}

/**
 * Result from run_decision
 */
export interface RunDecisionResult {
  status: string;
  decision_call: string;
  fallback_action: string | null;
  response: DecisionResponse | null;
}

/**
 * Candidate/option for select/score questions
 */
export interface DecisionCandidate {
  id: string;
  description: string;
}

/**
 * Run a decision for the Playground or public API.
 *
 * Supports either a published policy or an ad-hoc definition.
 * Requires `decision.run` capability. Ad-hoc definitions also require `decision.author`.
 */
export async function runDecision(params: {
  policy?: string;
  definition?: Record<string, unknown> | string;
  decision_model?: string;
  state?: string | Record<string, unknown>;
  candidates?: DecisionCandidate[];
  candidate_source?: string;
  candidate_resolver_id?: string;
  policy_version?: string;
  pinned_deployment?: string;
  latency_budget_ms?: number;
  surface?: string;
  origin_type?: 'Playground' | 'API';
}): Promise<RunDecisionResult> {
  try {
    const result = await call.post('huf.ai.decision.api.run_decision', {
      policy: params.policy,
      definition: typeof params.definition === 'string' ? params.definition : JSON.stringify(params.definition),
      decision_model: params.decision_model,
      state: typeof params.state === 'string' ? params.state : JSON.stringify(params.state),
      candidates: params.candidates ? JSON.stringify(params.candidates) : undefined,
      candidate_source: params.candidate_source,
      candidate_resolver_id: params.candidate_resolver_id,
      policy_version: params.policy_version,
      pinned_deployment: params.pinned_deployment,
      latency_budget_ms: params.latency_budget_ms,
      surface: params.surface,
      origin_type: params.origin_type || 'Playground',
    });
    return result.message as RunDecisionResult;
  } catch (error) {
    handleFrappeError(error, 'Error running decision');
    throw error;
  }
}

/**
 * List Decision Models for the Playground picker and Decision tab.
 *
 * Non-admin users see only enabled models without deployment details.
 * Admin users see all models (enabled and disabled) with full deployment chains.
 * Requires `decision.run` capability.
 */
export async function listDecisionModels(): Promise<DecisionModel[]> {
  try {
    const result = await call.get('huf.ai.decision.api.list_decision_models', {});
    return result.message as DecisionModel[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching decision models');
    return [];
  }
}

/**
 * Get a single Decision Call for detail view.
 *
 * Visibility is governed by D5 (owner of originating run or decision.admin).
 * Raw fields (answer_json, state_snapshot) are only included for admin users.
 * Requires `decision.run` capability.
 */
export async function getDecisionCall(name: string): Promise<Record<string, unknown>> {
  try {
    const result = await call.get('huf.ai.decision.api.get_decision_call', {
      name,
    });
    return result.message as Record<string, unknown>;
  } catch (error) {
    handleFrappeError(error, `Error fetching decision call ${name}`);
    throw error;
  }
}

/**
 * Pagination response for decision calls
 */
export interface DecisionCallListResponse {
  rows: Record<string, unknown>[];
  total: number;
  limit_start: number;
  limit_page_length: number;
}

/**
 * List Decision Calls for the Executions tab.
 *
 * Supports filtering by: surface, policy, policy_version, mode, status, origin_type,
 * decision_model, agent, agent_run, flow_run, automation, conversation, owner_user.
 * Row visibility is governed by D5.
 * Requires `decision.run` capability.
 */
export async function listDecisionCalls(params?: {
  filters?: Record<string, unknown>;
  limit_start?: number;
  limit_page_length?: number;
  order_by?: string;
}): Promise<DecisionCallListResponse> {
  try {
    const result = await call.get('huf.ai.decision.api.list_decision_calls', {
      filters: params?.filters ? JSON.stringify(params.filters) : undefined,
      limit_start: params?.limit_start,
      limit_page_length: params?.limit_page_length,
      order_by: params?.order_by,
    });
    return result.message as DecisionCallListResponse;
  } catch (error) {
    handleFrappeError(error, 'Error fetching decision calls');
    return { rows: [], total: 0, limit_start: 0, limit_page_length: 50 };
  }
}

/**
 * Validation result for a policy definition
 */
export interface ValidatePolicyResult {
  valid: boolean;
  error_code?: string;
  message?: string;
  policy_id?: string;
  fingerprint?: string;
  question_count?: number;
  question_ids?: string[];
  required_modalities?: string[];
}

/**
 * Validate an ad-hoc/draft policy definition.
 *
 * Does not save or run the policy. Returns validation errors without throwing.
 * Requires `decision.author` capability.
 */
export async function validatePolicyDefinition(definition: Record<string, unknown>): Promise<ValidatePolicyResult> {
  try {
    const result = await call.post('huf.ai.decision.api.validate_policy_definition', {
      definition: JSON.stringify(definition),
    });
    return result.message as ValidatePolicyResult;
  } catch (error) {
    handleFrappeError(error, 'Error validating policy definition');
    return { valid: false, error_code: 'error', message: 'Validation failed' };
  }
}

/**
 * Publish a Decision Policy version.
 *
 * Creates a new Decision Policy Version from the current definition_json.
 * Requires `decision.admin` capability.
 */
export async function publishPolicyVersion(
  policy: string
): Promise<{ policy: string; version: string }> {
  try {
    const result = await call.post('huf.ai.decision.api.publish_policy_version', {
      policy,
    });
    return result.message as { policy: string; version: string };
  } catch (error) {
    handleFrappeError(error, `Error publishing policy version for ${policy}`);
    throw error;
  }
}

/**
 * Catalog entry for setup wizard
 */
export interface SetupCatalogEntry {
  provider_brand: string;
  model_name: string;
  canonical_model: string;
  model_family: string;
  model_class: string;
  wire_protocol: string;
  endpoint_path: string;
  base_url: string;
  provider_ready: boolean;
}

/**
 * Get setup catalog for the setup wizard.
 *
 * Lists available deployment options from the catalog, filtered to providers
 * that have API keys configured (or use local backends).
 * Requires `decision.admin` capability.
 */
export async function getSetupCatalog(): Promise<SetupCatalogEntry[]> {
  try {
    const result = await call.get('huf.ai.decision.api.get_setup_catalog', {});
    return result.message as SetupCatalogEntry[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching setup catalog');
    return [];
  }
}

/**
 * Setup result
 */
export interface SetupDeploymentResult {
  deployment: string;
  ai_model: string;
  probe: {
    status: 'success' | 'failed';
    latency_ms: number;
    error_code: string | null;
  };
}

/**
 * Set up a Decision Deployment idempotently.
 *
 * Creates or reuses AI Model and the Decision Model hierarchy, creates a Deployment,
 * and runs a test probe. If probe succeeds, deployment is enabled; if it fails, it
 * is saved disabled with the error.
 * Requires `decision.admin` capability.
 */
export async function setupDeployment(
  provider: string,
  model_name: string
): Promise<SetupDeploymentResult> {
  try {
    const result = await call.post('huf.ai.decision.api.setup_deployment', {
      provider,
      model_name,
    });
    return result.message as SetupDeploymentResult;
  } catch (error) {
    handleFrappeError(error, 'Error setting up deployment');
    throw error;
  }
}

/**
 * Test result for a deployment
 */
export interface TestDeploymentResult {
  status: 'success' | 'failed';
  latency_ms: number;
  error_code: string | null;
}

/**
 * Test a Decision Deployment connection.
 *
 * Sends a minimal judge probe through the backend and records the result in
 * the deployment's health status fields.
 * Requires `decision.admin` capability.
 */
export async function testDeployment(deployment: string): Promise<TestDeploymentResult> {
  try {
    const result = await call.post('huf.ai.decision.api.test_deployment', {
      deployment,
    });
    return result.message as TestDeploymentResult;
  } catch (error) {
    handleFrappeError(error, `Error testing deployment ${deployment}`);
    throw error;
  }
}
