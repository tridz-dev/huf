import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export type FlowMemberStatus = 'Active' | 'Waiting' | 'Completed' | 'Exited';

export interface FlowMemberRow {
  /** Masked by the server. */
  member_key: string;
  /** Opaque handle for removing this person. */
  member_ref: string;
  status: FlowMemberStatus;
  current_node_id?: string | null;
  active_flow_run?: string | null;
  last_event_at?: string | null;
}

/** The longest this site keeps saved data, in seconds; 0 means no ceiling. */
export async function getFlowStateLimits(): Promise<{ max_ttl_seconds: number }> {
  try {
    const result = await call.get('huf.ai.flow.runs.members_api.get_flow_state_limits');
    return result.message as { max_ttl_seconds: number };
  } catch (error) {
    handleFrappeError(error, 'Error loading saved-data limits');
  }
}

export async function listFlowMembers(flow: string): Promise<FlowMemberRow[]> {
  try {
    const result = await call.get('huf.ai.flow.runs.members_api.list_flow_members', { flow });
    return (result.message as FlowMemberRow[]) ?? [];
  } catch (error) {
    handleFrappeError(error, `Error loading people of flow ${flow}`);
  }
}

/** Editors: forget a person and cancel their waiting run. */
export async function removeFlowMember(flow: string, memberRef: string): Promise<{ removed: boolean }> {
  try {
    const result = await call.post('huf.ai.flow.runs.members_api.remove_flow_member', { flow, member_ref: memberRef });
    return result.message as { removed: boolean };
  } catch (error) {
    handleFrappeError(error, `Error removing a person from flow ${flow}`);
  }
}
