import { useContext } from 'react';
import { PermissionsContext } from '@/contexts/PermissionsContext';

/**
 * Who may create / change / delete each kind of thing, mirroring what the server enforces.
 *
 * `doctype`: the server checks the DocType's own role permissions (reported by get_me as `doc_permissions`).
 * `capability`: the server checks a Huf capability (API guard or the controller's has_permission).
 */
export const RESOURCE_ACCESS = {
  prompt: { doctype: 'Agent Prompt' },
  summaryPrompt: { doctype: 'Agent Summary Prompt' },
  // The skill import APIs do not check permissions themselves; the DocType rule is the declared intent.
  skill: { doctype: 'Skill' },
  automation: { doctype: 'Automation' },
  meeting: { doctype: 'Meeting' },
  knowledge: { doctype: 'Knowledge Source' },
  memoryPolicy: { doctype: 'Memory Policy' },
  mcp: { doctype: 'MCP Server' },
  provider: { doctype: 'AI Provider' },
  model: { doctype: 'AI Model' },
  integration: { doctype: 'Integration Settings' },
  integrationService: { doctype: 'Integration Service' },
  gateway: { doctype: 'Gateway' },
  dataTable: { capability: 'data.tables.manage' },
  executionProfile: { capability: 'execution_profile.manage' },
  sshConnection: { capability: 'ssh_connection.manage' },
  networkPolicy: { capability: 'network_access_policy.manage' },
  role: { capability: 'roles.manage' },
} as const satisfies Record<string, { doctype: string } | { capability: string }>;

export type Resource = keyof typeof RESOURCE_ACCESS;

export interface ResourceAccess {
  canCreate: boolean;
  canWrite: boolean;
  canDelete: boolean;
  isLoading: boolean;
}

/**
 * While permissions load nothing is offered. Outside a PermissionsProvider (tests, shared components), and against a
 * server that does not report `doc_permissions` yet, DocType-gated actions are offered and the server stays the judge.
 */
export function useResourceAccess(resource: Resource): ResourceAccess {
  const ctx = useContext(PermissionsContext);
  if (!ctx) return { canCreate: true, canWrite: true, canDelete: true, isLoading: false };
  if (ctx.isLoading) return { canCreate: false, canWrite: false, canDelete: false, isLoading: true };
  const rule: { doctype?: string; capability?: string } = RESOURCE_ACCESS[resource];
  if (rule.capability) {
    const allowed = ctx.hasCapability(rule.capability);
    return { canCreate: allowed, canWrite: allowed, canDelete: allowed, isLoading: false };
  }
  const perms = ctx.docPermissions?.[rule.doctype as string];
  return { canCreate: perms?.create ?? true, canWrite: perms?.write ?? true, canDelete: perms?.delete ?? true, isLoading: false };
}
