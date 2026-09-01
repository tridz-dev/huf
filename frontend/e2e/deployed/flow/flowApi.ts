/**
 * Thin REST helpers for setup / teardown / outcome assertions in the flow
 * e2e suite. These call the same whitelisted methods the frontend's
 * services/flowApi.ts uses, but directly over HTTP with the API token —
 * no browser page required, so they're usable from beforeAll/afterAll and
 * from within a test to check backend state a UI assertion can't see.
 */
import { APIRequestContext, request } from '@playwright/test';

export interface FlowRunDetail {
  flow_run_id: string;
  flow_id: string;
  status: string;
  current_node_id: string;
  last_error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

const AUTH_HEADER = 'token 245085c4b670453:0a099501ac09c1d';

export function authHeaders(): Record<string, string> {
  return { Authorization: AUTH_HEADER };
}

/** Build a request context pointed at the site origin (not the /huf/ SPA mount). */
export async function newApiContext(baseOrigin: string): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: baseOrigin,
    extraHTTPHeaders: {
      Authorization: AUTH_HEADER,
      Accept: 'application/json',
    },
  });
}

/** List Flow Definition docs whose flow_name matches a prefix. Used for cleanup sweeps. */
export async function listFlowsByNamePrefix(
  api: APIRequestContext,
  prefix: string,
): Promise<Array<{ name: string; flow_id: string; flow_name: string }>> {
  const res = await api.get('/api/method/frappe.client.get_list', {
    params: {
      doctype: 'Flow Definition',
      filters: JSON.stringify([['flow_name', 'like', `${prefix}%`]]),
      fields: JSON.stringify(['name', 'flow_id', 'flow_name']),
      limit_page_length: '0',
    },
  });
  if (!res.ok()) throw new Error(`listFlowsByNamePrefix failed: ${res.status()} ${await res.text()}`);
  const json = await res.json();
  return json.message ?? [];
}

/** Delete a Flow Definition doc directly via the REST resource endpoint. */
export async function deleteFlowByName(api: APIRequestContext, docName: string): Promise<void> {
  const res = await api.delete(`/api/resource/Flow Definition/${encodeURIComponent(docName)}`);
  if (!res.ok() && res.status() !== 404) {
    throw new Error(`deleteFlowByName(${docName}) failed: ${res.status()} ${await res.text()}`);
  }
}

/** Fetch a Flow Run doc (status/error) for outcome assertions. */
export async function getFlowRun(api: APIRequestContext, flowRunId: string): Promise<FlowRunDetail> {
  const res = await api.get('/api/method/huf.ai.flow_api.get_flow_run', {
    params: { flow_run_id: flowRunId },
  });
  if (!res.ok()) throw new Error(`getFlowRun(${flowRunId}) failed: ${res.status()} ${await res.text()}`);
  const json = await res.json();
  return json.message as FlowRunDetail;
}

/** Check a Flow Definition still exists (used to assert deletion took effect). */
export async function flowExists(api: APIRequestContext, docName: string): Promise<boolean> {
  const res = await api.get(`/api/resource/Flow Definition/${encodeURIComponent(docName)}`);
  return res.ok();
}

/** Generate a unique, greppable flow name for a test run. */
export function uniqueFlowName(prefix = 'e2e-flow'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
