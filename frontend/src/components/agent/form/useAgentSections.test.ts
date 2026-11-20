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

  it('FEF-C: after a conflict, retry refreshes revisions and reports conflicting fields', async () => {
    const { result } = await mount();
    act(() => { result.current.form.setValue('description', 'mine'); result.current.form.setValue('instructions', 'mine-i'); });
    api.updateAgentSection.mockRejectedValueOnce(new Error('Document has been modified after you have opened it'));
    await act(async () => { await result.current.sections.saveNow(); });
    expect(result.current.sections.conflict).toBe(true);

    server = { ...server, description: 'theirs', agent_name: 'Server Name' }; // description conflicts, agent_name does not
    rev = 'r9';
    await act(async () => { await result.current.sections.retry(); });
    expect(result.current.sections.conflictFields).toEqual(['description']);
    expect(result.current.form.getValues('agent_name')).toBe('Server Name');
    expect(api.updateAgentSection).toHaveBeenCalledTimes(1); // only the original failed save; no auto-save after reload
  });

  async function conflicted() {
    const hook = await mount();
    act(() => { hook.result.current.form.setValue('description', 'mine'); hook.result.current.form.setValue('instructions', 'mine-i'); });
    api.updateAgentSection.mockRejectedValueOnce(new Error('Document has been modified after you have opened it'));
    await act(async () => { await hook.result.current.sections.saveNow(); });
    server = { ...server, description: 'theirs' };
    rev = 'r9';
    api.updateAgentSection.mockClear();
    await act(async () => { await hook.result.current.sections.retry(); });
    return hook;
  }

  it('conflict: no save call until resolved', async () => {
    const { result } = await conflicted();
    expect(result.current.sections.conflictFields).toEqual(['description']);
    expect(api.updateAgentSection).not.toHaveBeenCalled();
    await act(async () => { await result.current.sections.saveNow(); });
    expect(api.updateAgentSection).not.toHaveBeenCalled();
  });

  it('Use theirs takes the server value', async () => {
    const { result } = await conflicted();
    act(() => { result.current.sections.resolveConflict('description', 'theirs'); });
    expect(result.current.form.getValues('description')).toBe('theirs');
    expect(result.current.sections.conflictFields).toEqual([]);
  });

  it('Keep mine saves the local value with the fresh revision', async () => {
    const { result } = await conflicted();
    act(() => { result.current.sections.resolveConflict('description', 'mine'); });
    await act(async () => { await result.current.sections.saveNow(); });
    const last = api.updateAgentSection.mock.calls.at(-1)!;
    expect((last[2] as Record<string, unknown>).description).toBe('mine');
    expect(last[3]).toBe('r9');
  });

  it('Keep mine force-saves immediately without another click', async () => {
    const { result } = await conflicted();
    api.updateAgentSection.mockClear();
    await act(async () => { result.current.sections.resolveConflict('description', 'mine'); await new Promise((r) => setTimeout(r, 20)); });
    const last = api.updateAgentSection.mock.calls.at(-1)!;
    expect((last[2] as Record<string, unknown>).description).toBe('mine');
    expect(last[3]).toBe('r9');
    expect(result.current.sections.status).toBe('saved');
  });

  it('partial reload keeps the error and does not save', async () => {
    const { result } = await mount();
    act(() => { result.current.form.setValue('description', 'mine'); });
    api.updateAgentSection.mockRejectedValueOnce(new Error('Document has been modified after you have opened it'));
    await act(async () => { await result.current.sections.saveNow(); });
    api.updateAgentSection.mockClear();
    api.getAgentSection.mockImplementation(async (_id: string, sec: string) => {
      if (sec === 'tools') throw new Error('down');
      return { name: 'AG-1', modified: rev, values: { ...server } };
    });
    await act(async () => { await result.current.sections.retry(); });
    expect(api.updateAgentSection).not.toHaveBeenCalled();
    expect(result.current.sections.status).toBe('error');
  });
});
