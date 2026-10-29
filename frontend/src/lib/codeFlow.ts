/** Execute code in Flows: constants and pure helpers (no network). The shared status lives in useCodeFlowStatus.ts. */
import type { CodeFlowProfile, CodeFlowStatus } from '@/services/codeFlowApi';
import type { FlowNode } from '@/types/flow.types';

/** Capability a user needs to add, edit and publish Execute code steps (mirrors the server rule). */
export const EXECUTE_CODE_CAPABILITY = 'flows.execute_code';

export const CODE_RUN_ACTION = 'code-run';
export const DEFAULT_CODE_PROFILE = 'Flow Scratch';
export const DEFAULT_CODE_TIMEOUT_S = 30;
export const MAX_CODE_BYTES = 65536;

export const CODE_OFF_MESSAGE = 'Execute code is turned off. An administrator can turn it on in Settings.';
export const CODE_NO_PERMISSION_NOTE = 'You need permission to run code to edit this step.';

/** Profiles a step may pick from: the ones the server marks usable. */
export function usableProfiles(status: CodeFlowStatus | null): CodeFlowProfile[] {
  return (status?.profiles ?? []).filter((p) => p.usable);
}

/** "Flow Scratch - runs automatically" / "Restricted - asks for approval". */
export function profileLabel(profile: Pick<CodeFlowProfile, 'name' | 'approval_mode'>): string {
  return `${profile.name} - ${profile.approval_mode === 'Auto Approve' ? 'runs automatically' : 'asks for approval'}`;
}

/** Whether a flow has at least one Execute code step. */
export function hasCodeStep(nodes: Array<Pick<FlowNode, 'data'>>): boolean {
  return nodes.some((n) => (n.data?.actionConfig as { type?: string } | undefined)?.type === CODE_RUN_ACTION);
}

/** Why publishing is blocked because of Execute code steps, or null. Unknown status never blocks (the server stays the judge). */
export function codePublishBlockedReason(nodes: Array<Pick<FlowNode, 'data'>>, status: CodeFlowStatus | null): string | null {
  if (!hasCodeStep(nodes) || !status) return null;
  if (!status.enabled) return CODE_OFF_MESSAGE;
  if (!status.can_execute) return 'This flow has an Execute code step. Only people allowed to run code can publish it. Ask an admin to publish it for you.';
  return null;
}

/** UTF-8 size in bytes of a string. */
export function byteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}
