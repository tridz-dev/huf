/**
 * Option lists the agent form needs (providers, models, prompts, SSH, execution profiles,
 * memory policies, tool types, skills). Each lookup is independent: a denied or failed one
 * must not blank fields that loaded fine (a Huf User cannot list some of these).
 */
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { db } from '@/lib/frappe-sdk';
import { getProviders, getModels } from '@/services/providerApi';
import { getToolTypes } from '@/services/toolApi';
import { getSkillOptions } from '@/services/skillApi';
import { checkCacheableModels } from '@/services/agentApi';
import type { AIModel, AIProvider, AgentToolType } from '@/types/agent.types';
import type { AgentPromptOption } from '../PromptTemplateSection';
import type { ExecutionProfileOption, SSHConnectionOption, MemoryPolicyOption } from '../AdvancedTab';

type Row = Record<string, string | number | null | undefined>;

async function list(doctype: string, fields: string[], filters?: [string, '=', number][]): Promise<Row[]> {
  return (await db.getDocList(doctype, {
    fields, filters: filters as never, limit: 500, orderBy: { field: 'modified', order: 'desc' },
  })) as Row[];
}

const toPromptOption = (p: Row): AgentPromptOption => ({
  value: String(p.name),
  label: String(p.title || p.name),
  description: (p.description as string) || undefined,
  version: typeof p.version === 'number' ? p.version : undefined,
  isLatest: p.is_latest === 1,
});

/** Load one list into state, with an optional toast on failure. */
function useList<T>(load: () => Promise<T[]>, failure?: string): [T[], boolean, React.Dispatch<React.SetStateAction<T[]>>] {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    load()
      .then((r) => { if (!cancelled) setItems(r); })
      .catch((e) => {
        console.error(failure ?? 'Error loading list', e);
        if (!cancelled && failure) toast.error(failure);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return [items, loading, setItems];
}

export function useAgentOptions(provider: string | undefined, model: string | undefined, cachingOn: boolean) {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [allModels, setAllModels] = useState<AIModel[]>([]);
  const [toolTypes, setToolTypes] = useState<AgentToolType[]>([]);
  const [skillOptions, setSkillOptions] = useState<{ value: string; label: string; subtitle?: string }[]>([]);

  const reloadProviders = async () => {
    setProviders((await getProviders()) as AIProvider[]);
  };
  const reloadModels = async () => {
    const m = await getModels();
    setAllModels(Array.isArray(m) ? m : (m as { items: AIModel[] }).items);
  };

  useEffect(() => {
    const labels = ['providers', 'models', 'tool types', 'skill options'];
    Promise.allSettled([getProviders(), getModels(), getToolTypes(), getSkillOptions()]).then((results) => {
      results.forEach((r, i) => {
        if (r.status === 'rejected') { console.error(`Error loading ${labels[i]}:`, r.reason); toast.error(`Failed to load ${labels[i]}`); }
      });
      const [p, m, t, s] = results;
      if (p.status === 'fulfilled') setProviders(p.value as AIProvider[]);
      if (m.status === 'fulfilled') setAllModels(Array.isArray(m.value) ? m.value : (m.value as { items: AIModel[] }).items);
      if (t.status === 'fulfilled') setToolTypes(t.value);
      if (s.status === 'fulfilled') setSkillOptions((s.value || []) as { value: string; label: string; subtitle?: string }[]);
    });
  }, []);

  const [promptRows, loadingPrompts, setPromptRows] = useList(
    async () => (await list('Agent Prompt', ['name', 'title', 'version', 'is_latest', 'description'], [['is_active', '=', 1]])).map(toPromptOption),
    'Failed to load Agent Prompt templates');
  const [summaryRows, loadingSummaryPrompts, setSummaryRows] = useList(
    async () => (await list('Agent Summary Prompt', ['name', 'title', 'version', 'is_latest', 'description'], [['is_active', '=', 1]])).map(toPromptOption),
    'Failed to load Agent Summary Prompt templates');
  const [sshConnectionOptions, loadingSSHConnections, setSSH] = useList<SSHConnectionOption>(
    async () => (await list('SSH Connection', ['name', 'display_name', 'host', 'username'], [['enabled', '=', 1]])).map((r) => ({
      value: String(r.name), label: String(r.display_name || r.name),
      description: [r.username, r.host].filter(Boolean).join('@') || undefined,
    })), 'Failed to load SSH connections');
  const [executionProfileOptions, loadingExecutionProfiles, setExec] = useList<ExecutionProfileOption>(
    async () => (await list('Execution Profile', ['name', 'profile_name', 'approval_mode'], [['disabled', '=', 0]])).map((r) => ({
      value: String(r.name), label: String(r.profile_name || r.name), approvalMode: (r.approval_mode as string) || undefined,
    })), 'Failed to load execution profiles');
  const [memoryPolicyOptions, loadingMemoryPolicies] = useList<MemoryPolicyOption>(
    async () => (await list('Memory Policy', ['name', 'policy_name'], [['enabled', '=', 1]])).map((r) => ({
      value: String(r.name), label: String(r.policy_name || r.name),
    })));

  const [cacheStatus, setCacheStatus] = useState<{ supported: boolean; alternatives: string[] } | null>(null);
  useEffect(() => {
    if (!cachingOn || !provider || !model) { setCacheStatus(null); return; }
    let cancelled = false;
    checkCacheableModels(provider, model).then((res) => { if (!cancelled) setCacheStatus(res); });
    return () => { cancelled = true; };
  }, [cachingOn, provider, model]);

  return {
    providers, allModels, toolTypes, skillOptions, reloadProviders, reloadModels,
    promptOptions: promptRows, setPromptOptions: setPromptRows, loadingPrompts,
    summaryPromptOptions: summaryRows, setSummaryPromptOptions: setSummaryRows, loadingSummaryPrompts,
    sshConnectionOptions, setSSHConnectionOptions: setSSH, loadingSSHConnections,
    executionProfileOptions, setExecutionProfileOptions: setExec, loadingExecutionProfiles,
    memoryPolicyOptions, loadingMemoryPolicies, cacheStatus,
  };
}
