import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * Scope values accepted by the Huf API Key backend.
 */
export type ApiKeyScope =
  | 'agents:read'
  | 'agents:run'
  | 'conversations:read'
  | 'conversations:write'
  | 'files:read'
  | 'files:write'
  | 'voice:use'
  | 'ocr:use';

export type ApiKeyAgentRestrictionMode = 'all' | 'selected';

export type ApiKeyStatus = 'Active' | 'Revoked' | 'Expired' | string;

/**
 * A key as returned by list/create (without the raw secret).
 */
export interface ApiKey {
  key_id: string;
  label: string;
  status: ApiKeyStatus;
  scopes: ApiKeyScope[];
  agent_restriction_mode: ApiKeyAgentRestrictionMode;
  restricted_agents: string[] | null;
  expires_at: string | null;
  last_used_at: string | null;
  creation: string;
}

/**
 * Response from create_api_key: includes the one-time raw secret.
 */
export interface CreatedApiKey extends ApiKey {
  raw_secret: string;
}

function unwrap<T>(result: { message?: T } | T): T {
  return (result as { message?: T })?.message !== undefined
    ? (result as { message: T }).message
    : (result as T);
}

/**
 * Create a new API key. `raw_secret` on the response is shown to the user
 * exactly once and can never be retrieved again.
 */
export async function createApiKey(
  label: string,
  scopes: ApiKeyScope[],
  agentRestrictionMode: ApiKeyAgentRestrictionMode = 'all',
  restrictedAgents?: string[],
  expiresAt?: string,
): Promise<CreatedApiKey> {
  try {
    const result = await call.post(
      'huf.huf.doctype.huf_api_key.huf_api_key.create_api_key',
      {
        label,
        scopes,
        agent_restriction_mode: agentRestrictionMode,
        restricted_agents: restrictedAgents,
        expires_at: expiresAt,
      },
    );
    return unwrap<CreatedApiKey>(result);
  } catch (error) {
    handleFrappeError(error, 'Error creating API key');
  }
}

/**
 * Revoke an existing API key by id.
 */
export async function revokeApiKey(
  keyId: string,
): Promise<{ key_id: string; status: ApiKeyStatus }> {
  try {
    const result = await call.post(
      'huf.huf.doctype.huf_api_key.huf_api_key.revoke_api_key',
      { key_id: keyId },
    );
    return unwrap<{ key_id: string; status: ApiKeyStatus }>(result);
  } catch (error) {
    handleFrappeError(error, 'Error revoking API key');
  }
}

/**
 * List the caller's API keys. Never includes raw or hashed secrets.
 */
export async function listApiKeys(): Promise<ApiKey[]> {
  try {
    const result = await call.get(
      'huf.huf.doctype.huf_api_key.huf_api_key.list_api_keys',
    );
    return unwrap<ApiKey[]>(result) || [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching API keys');
    return [];
  }
}
