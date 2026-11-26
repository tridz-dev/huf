// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useForm } from 'react-hook-form';
import { Form } from '@/components/ui/form';
import { ChannelsTab } from './ChannelsTab';
import { useAgentSections } from '../form/useAgentSections';
import { mapAgentDocToFormValues } from '../form/agentFormModel';
import type { AgentFormValues } from '../types';

const remote = vi.hoisted(() => ({ get: vi.fn(), getAgentSection: vi.fn(), updateAgentSection: vi.fn() }));
vi.mock('@/lib/frappe-sdk', async (orig) => ({ ...(await orig<typeof import('@/lib/frappe-sdk')>()), call: { get: remote.get, post: vi.fn() } }));
vi.mock('@/services/agentApi', async (orig) => ({
  ...(await orig<typeof import('@/services/agentApi')>()),
  getAgentSection: remote.getAgentSection,
  updateAgentSection: remote.updateAgentSection,
  getAgentDesktopAccess: vi.fn().mockResolvedValue({}),
}));
vi.mock('../AutomationsTab', () => ({ AutomationsTab: () => <div>automations-ui</div> }));
vi.mock('@/services/voiceSettingsApi', () => ({ listVoiceEngines: async () => [], getVoiceConfigSchema: async () => [] }));
vi.mock('sonner', () => ({ toast: { warning: vi.fn() } }));

let api: ReturnType<typeof useForm<AgentFormValues>>;
function Harness({ defaults = {}, agentId }: { defaults?: Partial<AgentFormValues>; agentId?: string }) {
  api = useForm<AgentFormValues>({ defaultValues: { allow_chat: false, persist_conversation: true, enable_multi_run: false, embed_enabled: false, voice_enabled: false, agent_modality: 'Text', ...defaults } as AgentFormValues });
  return <Form {...api}><ChannelsTab form={api} allModels={[]} agentId={agentId} /></Form>;
}
const sw = (name: string) => screen.getByRole('switch', { name });

describe('ChannelsTab', () => {
  it('hides every channel setting while off', () => {
    render(<Harness />);
    expect(screen.queryByLabelText('Allowed domains')).toBeNull();
    expect(screen.queryByLabelText('Remember conversations')).toBeNull();
    expect(screen.queryByText('Voice engine')).toBeNull();
  });

  it('chat on sets allow_chat and persist_conversation and reveals children', async () => {
    render(<Harness defaults={{ persist_conversation: false }} />);
    await userEvent.click(sw('Chat in HUF'));
    expect(api.getValues('allow_chat')).toBe(true);
    expect(api.getValues('persist_conversation')).toBe(true);
    await userEvent.click(sw('Remember conversations'));
    expect(api.getValues('persist_conversation')).toBe(false);
    expect(api.getValues('allow_chat')).toBe(false);
  });

  it('per-user history label no longer says legacy only', async () => {
    render(<Harness defaults={{ allow_chat: true }} />);
    expect(sw('Separate history per user')).toBeTruthy();
    expect(screen.queryByText(/older doc-event/i)).toBeNull();
    expect(screen.queryByText(/does not apply to scheduled runs/i)).toBeNull();
  });

  it('website widget reveals key and origins', async () => {
    render(<Harness />);
    await userEvent.click(sw('Website widget'));
    expect(api.getValues('embed_enabled')).toBe(true);
    expect(screen.getByLabelText('Publishable key')).toHaveAttribute('readonly');
    expect(screen.getByLabelText('Allowed domains')).toBeInTheDocument();
  });

  it('shows a copyable voice embed snippet for a saved agent', async () => {
    render(<Harness agentId="A1" defaults={{ embed_enabled: true, publishable_key: 'pk_abc' } as Partial<AgentFormValues>} />);
    const pre = document.getElementById('widget-snippet')!;
    expect(pre.textContent).toContain('huf-voice.js');
    expect(pre.textContent).toContain('HufVoice.init');
    expect(pre.textContent).toContain('"pk_abc"');
    expect(pre.textContent).toContain('"A1"');
    expect(screen.getByRole('button', { name: 'Copy snippet' })).toBeInTheDocument();
  });

  it('voice on lifts Text modality to Both and reveals voice fields', async () => {
    render(<Harness />);
    await userEvent.click(sw('Voice calls'));
    expect(api.getValues('voice_enabled')).toBe(true);
    expect(api.getValues('agent_modality')).toBe('Both');
    expect(await screen.findByText('Voice engine')).toBeInTheDocument();
    expect(screen.getByLabelText('Greeting')).toBeInTheDocument();
  });

  it('multi-step reveals the plan; automations render once opened', async () => {
    render(<Harness agentId="A1" />);
    expect(screen.getByText('automations-ui')).toBeInTheDocument();
    await userEvent.click(sw('Multi-step runs'));
    expect(api.getValues('enable_multi_run')).toBe(true);
  });
});

describe('default plan generation', () => {
  const planStatus = (state: string, error: string | null = null) => remote.get.mockResolvedValue({ message: { state, error } });

  it('shows progress while the plan is generated', async () => {
    planStatus('generating');
    render(<Harness agentId="A1" defaults={{ enable_multi_run: true, default_plan: [] }} />);
    expect(await screen.findByText('Generating plan...')).toBeInTheDocument();
  });

  it('shows why generation failed', async () => {
    planStatus('failed', 'provider down');
    render(<Harness agentId="A1" defaults={{ enable_multi_run: true, default_plan: [] }} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('provider down');
  });

  it('adopts generated rows without a conflict and keeps edits made meanwhile saveable', async () => {
    planStatus('done');
    const server: Record<string, unknown> = { name: 'A1', agent_name: 'Bot', prompt_mode: 'Local', template_version_at_attach: 0,
      summary_prompt_mode: 'Local', summary_template_version_at_attach: 0, description: 'd', instructions: 'i', enable_multi_run: 1, default_plan: [] };
    let rows: unknown[] = [];
    let release!: () => void;
    const ready = new Promise<void>((resolve) => { release = resolve; });
    remote.get.mockImplementation(async () => { await ready; rows = [{ step_index: 1, instruction: 'first', status: 'pending' }]; return { message: { state: 'done' } }; });
    remote.getAgentSection.mockImplementation(async () => ({ name: 'A1', modified: 'r1', values: { ...server, default_plan: rows } }));
    remote.updateAgentSection.mockImplementation(async (_n: string, _s: string, values: object) => { Object.assign(server, values); return { name: 'A1', modified: 'r2' }; });
    remote.updateAgentSection.mockClear();
    const abilities = { tools: [], mcp: [], knowledge: [], skills: [], dirty: { tools: false, knowledge: false, skills: false }, hydrate: vi.fn(), markSaved: vi.fn() } as never;
    const { result } = renderHook(() => {
      const form = useForm<AgentFormValues>({ defaultValues: mapAgentDocToFormValues({}) });
      const sections = useAgentSections({ id: 'A1', isNew: false, form, abilities, canSave: true, onRenamed: vi.fn(), onTabWithError: vi.fn() });
      return { form, sections };
    });
    await waitFor(() => expect(result.current.sections.loading).toBe(false));
    act(() => { result.current.form.setValue('description', 'edited meanwhile'); });
    // A behaviour save made before the rows are adopted must not send (and so wipe) the plan.
    act(() => { result.current.form.setValue('allow_ask_user', true); });
    await act(async () => { await result.current.sections.saveNow(); });
    const early = remote.updateAgentSection.mock.calls.find((c) => c[1] === 'behavior')!;
    expect(early[2]).toHaveProperty('allow_ask_user');
    expect(early[2]).not.toHaveProperty('default_plan');
    remote.updateAgentSection.mockClear();
    act(() => { result.current.form.setValue('description', 'edited again'); });
    await act(async () => { release(); });
    await waitFor(() => expect(result.current.form.getValues('default_plan')).toHaveLength(1));
    expect(result.current.sections.conflictFields).toEqual([]);
    expect(result.current.form.getValues('description')).toBe('edited again');
    await act(async () => { await result.current.sections.saveNow(); });
    expect(remote.updateAgentSection).toHaveBeenCalledTimes(1);
    expect(remote.updateAgentSection.mock.calls[0][1]).toBe('general');
    expect(remote.updateAgentSection.mock.calls[0][3]).toBe('r1'); // generation did not move the revision
  });
});
