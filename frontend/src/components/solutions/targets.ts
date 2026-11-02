import { getAgents } from '@/services/agentApi';
import { getFlowDefinitions } from '@/services/flowApi';

export interface TargetOption {
  type: 'Agent' | 'Flow';
  name: string;
  label: string;
}

export function toTargetOptions(agents: unknown, flows: unknown): TargetOption[] {
  const agentList = (Array.isArray(agents) ? agents : (agents as { agents?: unknown[] } | null)?.agents ?? []) as Array<{
    name: string;
    agent_name?: string;
  }>;
  const flowList = (Array.isArray(flows) ? flows : []) as Array<{ name: string; flow_name?: string }>;
  return [
    ...agentList.map((a) => ({ type: 'Agent' as const, name: a.name, label: a.agent_name || a.name })),
    ...flowList.map((f) => ({ type: 'Flow' as const, name: f.name, label: f.flow_name || f.name })),
  ];
}

/** Agents and flows an entry can be answered by. Failures yield an empty list. */
export async function loadTargets(): Promise<TargetOption[]> {
  const [agents, flows] = await Promise.all([getAgents().catch(() => []), getFlowDefinitions().catch(() => [])]);
  return toTargetOptions(agents, flows);
}
