import { useContext } from 'react';
import { PermissionsContext } from '@/contexts/PermissionsContext';
import { PUBLISH_SENSITIVE_CAPABILITY } from '@/lib/flow/flowPublishGuard';
import { EXECUTE_CODE_CAPABILITY } from '@/lib/flow-graph/codeFlow';

export const FLOW_READ_ONLY_REASON = 'You have view-only access to flows. Ask an admin for permission to change or run them.';

/** Tooltip on the "View only" pill in the editor header. */
export const FLOW_VIEW_ONLY_HINT = 'You can look at this flow, its steps and its runs, but not change or run it. Ask a flow editor to give you edit access.';

/** The role says "manage flows" but the account's own permissions would refuse every save (B28): say that, not just "view only". */
export const FLOW_ROLE_NOT_APPLIED_REASON = 'Your role includes editing flows, but your account is not set up to save them. Ask an administrator to check your role.';

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
  /** The Huf Role grants flow editing that the server would refuse (so the screens are view-only, and say why). */
  roleNotApplied: boolean;
}

/**
 * What the signed-in user may do with flows, from the capabilities the app already loads for the sidebar.
 * Outside a PermissionsProvider (tests, shared components) everything is allowed and the server stays the judge.
 */
export function useFlowPermissions(): FlowPermissions {
  const ctx = useContext(PermissionsContext);
  if (!ctx || ctx.isLoading) return { canCreate: true, canManage: true, canPublishSensitive: true, canExecuteCode: true, readOnlyReason: null, roleNotApplied: false };
  const canCreate = ctx.hasCapability('flows.create');
  const canManage = ctx.hasCapability('flows.manage');
  const canPublishSensitive = ctx.hasCapability(PUBLISH_SENSITIVE_CAPABILITY);
  const canExecuteCode = ctx.hasCapability(EXECUTE_CODE_CAPABILITY);
  const roleNotApplied = !canManage && ctx.withheldCapabilities.some((c) => c === 'flows.manage' || c === 'flows.create');
  return {
    canCreate,
    canManage,
    canPublishSensitive,
    canExecuteCode,
    readOnlyReason: canManage && canCreate ? null : roleNotApplied ? FLOW_ROLE_NOT_APPLIED_REASON : FLOW_READ_ONLY_REASON,
    roleNotApplied,
  };
}
