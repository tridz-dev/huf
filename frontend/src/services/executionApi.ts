import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

// ─── Types ───────────────────────────────────────────────────────────

/** Execution kind of a parked agent execution awaiting approval */
export type ExecutionApprovalKind = 'code_execution' | 'ssh_exec';

/**
 * Pending agent execution approval, as returned by
 * `huf.ai.execution_api.get_pending_agent_execution_approvals`.
 *
 * `code_ref` is a SHA-256 hash of the parked code/command, never the raw
 * source — it is not meant to be rendered.
 */
export interface PendingExecutionApproval {
  name: string;
  agent_tool_call: string | null;
  execution_kind: ExecutionApprovalKind | string;
  requested_capability: string;
  code_ref: string;
  expires_on: string;
  approver_role: string | null;
  requested_by: string | null;
  agent_name: string | null;
  can_decide: boolean;
}

/** Result of approving/rejecting an execution approval */
export interface ExecutionApprovalDecisionResult {
  name: string;
  status: string;
  agent_tool_call: string | null;
}

// ─── Execution Approval APIs ─────────────────────────────────────────

/** List pending agent execution approvals the current user may decide */
export async function getPendingExecutionApprovals(): Promise<PendingExecutionApproval[]> {
  try {
    const result = await call.get('huf.ai.execution_api.get_pending_agent_execution_approvals');
    return result.message as PendingExecutionApproval[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching pending execution approvals');
  }
}

/** Approve a parked code/SSH execution and dispatch it */
export async function approveExecution(
  name: string,
  comment?: string
): Promise<ExecutionApprovalDecisionResult> {
  try {
    const result = await call.post(
      'huf.huf.doctype.agent_execution_approval.agent_execution_approval.approve_execution',
      {
        agent_execution_approval_name: name,
        comment,
      }
    );
    return result.message as ExecutionApprovalDecisionResult;
  } catch (error) {
    handleFrappeError(error, `Error approving execution ${name}`);
  }
}

/** Reject a parked code/SSH execution */
export async function rejectExecution(
  name: string,
  comment?: string
): Promise<ExecutionApprovalDecisionResult> {
  try {
    const result = await call.post(
      'huf.huf.doctype.agent_execution_approval.agent_execution_approval.reject_execution',
      {
        agent_execution_approval_name: name,
        comment,
      }
    );
    return result.message as ExecutionApprovalDecisionResult;
  } catch (error) {
    handleFrappeError(error, `Error rejecting execution ${name}`);
  }
}
