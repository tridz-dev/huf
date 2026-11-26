// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useForm } from 'react-hook-form';
import { Form } from '@/components/ui/form';
import { ChannelsTab } from './ChannelsTab';
import type { AgentFormValues } from '../types';

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
