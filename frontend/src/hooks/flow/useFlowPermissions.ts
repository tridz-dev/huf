import { useContext } from 'react';
import { PermissionsContext } from '@/contexts/PermissionsContext';
import { PUBLISH_SENSITIVE_CAPABILITY } from '@/lib/flow/flowPublishGuard';
import { EXECUTE_CODE_CAPABILITY } from '@/lib/flow-graph/codeFlow';

export const FLOW_READ_ONLY_REASON = 'You have view-only access to flows. Ask an admin for permission to change or run them.';

/** Tooltip on the "View only" pill in the editor header. */
export const FLOW_VIEW_ONLY_HINT = 'You can look at this flow, its steps and its runs, but not change or run it. Ask a flow editor to give you edit access.';

export interface FlowPermissions {
  /** Create a new flow. */
  canCreate: boolean;
  /** Change, publish, run and delete flows (same people the server lets write to Flow Definition). */
  canManage: boolean;
  /** Publish a flow that has a Data trigger or a web request step. */
  canPublishSensitive: boolean;
  /** Add, edit and publish Execute code steps (flows.execute_code). */
  canExecuteCode: boolean;
  /** Plain explanation shown on disabled controls, or null when nothing is disabled. */
  readOnlyReason: string | null;
}

/**
 * What the signed-in user may do with flows, from the capabilities the app already loads for the sidebar.
 * Outside a PermissionsProvider (tests, shared components) everything is allowed and the server stays the judge.
 */
export function useFlowPermissions(): FlowPermissions {
  const ctx = useContext(PermissionsContext);
  if (!ctx || ctx.isLoading) return { canCreate: true, canManage: true, canPublishSensitive: true, canExecuteCode: true, readOnlyReason: null };
  const canCreate = ctx.hasCapability('flows.create');
  const canManage = ctx.hasCapability('flows.manage');
  const canPublishSensitive = ctx.hasCapability(PUBLISH_SENSITIVE_CAPABILITY);
  const canExecuteCode = ctx.hasCapability(EXECUTE_CODE_CAPABILITY);
  return { canCreate, canManage, canPublishSensitive, canExecuteCode, readOnlyReason: canManage && canCreate ? null : FLOW_READ_ONLY_REASON };
}
