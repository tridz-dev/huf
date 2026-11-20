// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  getAgentSection: vi.fn(),
  updateAgentSection: vi.fn(),
}));
vi.mock('@/services/agentApi', async (orig) => ({
  ...(await orig<typeof import('@/services/agentApi')>()),
  getAgentSection: api.getAgentSection,
  updateAgentSection: api.updateAgentSection,
  getAgentDesktopAccess: vi.fn().mockResolvedValue({}),
  updateAgentDesktopAccess: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('@/services/toolApi', () => ({ getToolFunctionsByName: vi.fn().mockResolvedValue([]) }));
vi.mock('@/services/mcpApi', () => ({ getMCPServer: vi.fn() }));
vi.mock('@/components/chat/useChatAgentIdentity', () => ({ writeToolDetailsSetting: vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { useAgentSections } from './useAgentSections';
import { mapAgentDocToFormValues } from './agentFormModel';
import type { AgentFormValues } from '../types';

const abilities = {
  tools: [], mcp: [], knowledge: [], skills: [],
  dirty: { tools: false, knowledge: false, skills: false },
  hydrate: vi.fn(), markSaved: vi.fn(),
} as never;

let server: Record<string, unknown>;
let rev: string;

function useHarness() {
  const form = useForm<AgentFormValues>({ defaultValues: mapAgentDocToFormValues({}) });
  const sections = useAgentSections({ id: 'AG-1', isNew: false, form, abilities, canSave: true, onRenamed: vi.fn(), onTabWithError: vi.fn() });
  return { form, sections };
}

async function mount() {
  const hook = renderHook(useHarness);
  await waitFor(() => expect(hook.result.current.sections.loading).toBe(false));
  return hook;
}

beforeEach(() => {
  vi.clearAllMocks();
  server = { name: 'AG-1', agent_name: 'Bot', prompt_mode: 'Local', template_version_at_attach: 0, summary_prompt_mode: 'Local', summary_template_version_at_attach: 0, description: 'd', instructions: 'i' };
  rev = 'r1';
  api.getAgentSection.mockImplementation(async () => ({ name: 'AG-1', modified: rev, values: { ...server } }));
  api.updateAgentSection.mockImplementation(async () => ({ name: 'AG-1', modified: 'r-new' }));
});

describe('useAgentSections', () => {
  it('FEF-A: loading an agent with 0 template versions triggers no save', async () => {
    const { result } = await mount();
    await act(async () => { await new Promise((r) => setTimeout(r, 1900)); }); // past the 1500ms autosave debounce
    expect(api.updateAgentSection).not.toHaveBeenCalled();
    expect(result.current.sections.hasUnsaved).toBe(false);
  });

  it('FEF-B: an explicit save made during an in-flight autosave is rerun as explicit', async () => {
    const { result } = await mount();
    let release!: () => void;
    api.updateAgentSection.mockImplementationOnce(() => new Promise((res) => { release = () => res({ name: 'AG-1', modified: 'r2' }); }));
    act(() => { result.current.form.setValue('description', 'one'); });
    let first!: Promise<void>;
    act(() => { first = result.current.sections.saveNow(); });
    await waitFor(() => expect(api.updateAgentSection).toHaveBeenCalledTimes(1));
    // An autosave-style pending first, then an explicit one: explicit must win.
    act(() => { result.current.form.setValue('agent_name', 'Renamed'); });
    await act(async () => { await result.current.sections.saveNow(); });
    await act(async () => { release(); await first; });
    await waitFor(() => expect(api.updateAgentSection).toHaveBeenCalledTimes(2));
    const payload = api.updateAgentSection.mock.calls[1][2] as Record<string, unknown>;
    expect(payload.agent_name).toBe('Renamed');
  });
});
