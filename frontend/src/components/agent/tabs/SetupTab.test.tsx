// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { UseFormReturn } from 'react-hook-form';
import type { AgentFormValues } from '../types';
import { SetupTab, type SetupTabProps } from './SetupTab';
import { renderTab } from './testHarness';

vi.mock('@/components/ui/select', () => import('./selectMock').then((m) => m.selectMock()));

const providers = [{ name: 'gem', provider_name: 'Gemini' }, { name: 'oa', provider_name: 'OpenAI' }];
const models = [
  { name: 'flash', model_name: 'Gemini Flash', provider: 'gem', modalities: 'Text,Vision' },
  { name: 'imagen', model_name: 'Imagen', provider: 'gem', modalities: 'Image' },
  { name: 'gpt', model_name: 'GPT', provider: 'oa' },
];
const base: Omit<SetupTabProps, 'form'> = { providers, models, promptOptions: [], workspaceDefaultModel: { provider: 'gem', model: 'flash', label: 'Gemini Flash' } };

function mount(values: Partial<AgentFormValues> = {}, props: Partial<SetupTabProps> = {}) {
  let form!: UseFormReturn<AgentFormValues>;
  renderTab((f) => <SetupTab form={f} {...base} {...props} />, values, (f) => { form = f; });
  return () => form;
}

describe('SetupTab', () => {
  it('shows the recommended default model line instead of blank selects', () => {
    mount({ provider: 'gem', model: 'flash' });
    expect(screen.getByTestId('model-line')).toHaveTextContent('Gemini · Gemini Flash');
    expect(screen.getByTestId('model-line')).toHaveTextContent('Recommended');
    expect(screen.queryByText('Provider')).not.toBeInTheDocument();
  });

  it('fills the workspace default for a new agent', () => {
    const f = mount({}, { applyDefaultWhenEmpty: true });
    expect(f().getValues('provider')).toBe('gem');
    expect(f().getValues('model')).toBe('flash');
  });

  it('Change reveals provider and model fields with required markers', async () => {
    mount({ provider: 'gem', model: 'flash' });
    await userEvent.click(screen.getByRole('button', { name: 'Change' }));
    expect(screen.getByText('Provider')).toBeInTheDocument();
    expect(screen.getByText('Model', { selector: 'label' })).toBeInTheDocument();
    expect(document.querySelectorAll('[aria-hidden="true"].text-destructive').length).toBeGreaterThanOrEqual(2);
  });

  it('flags a saved non-chat model and offers the recommended one', async () => {
    const f = mount({ provider: 'gem', model: 'imagen' });
    expect(screen.getByTestId('attention-banner')).toHaveTextContent('not available for chat');
    await userEvent.click(screen.getByRole('button', { name: 'Use recommended' }));
    expect(f().getValues('model')).toBe('flash');
  });

  it('hides the Model section for voice-only agents and the starters', () => {
    mount({ agent_modality: 'Voice' });
    expect(screen.queryByText('The AI that writes the replies.')).not.toBeInTheDocument();
    expect(screen.queryByText('Conversation starters')).not.toBeInTheDocument();
  });

  it('shows inline errors from the form', async () => {
    const f = mount({ agent_name: '' }, { });
    await act(async () => { f().setError('agent_name', { message: 'Agent name is required' }); f().setError('instructions', { message: 'Add instructions so it knows what to do' }); });
    expect(await screen.findByText('Agent name is required')).toBeInTheDocument();
    expect(screen.getByText('Add instructions so it knows what to do')).toBeInTheDocument();
    expect(document.querySelector('#instructions[aria-invalid="true"]')).not.toBeNull();
  });

  it('limits starter prompts to 3', async () => {
    mount();
    const add = () => screen.getByRole('button', { name: /Add a starter/ });
    await userEvent.click(add());
    await userEvent.click(add());
    await userEvent.click(add());
    expect(screen.queryByRole('button', { name: /Add a starter/ })).not.toBeInTheDocument();
    expect(screen.getByText('3 of 3 added.')).toBeInTheDocument();
  });

  it('modality Text clears voice_enabled', async () => {
    const f = mount({ voice_enabled: true });
    await userEvent.click(screen.getByRole('radio', { name: /Text only/ }));
    expect(f().getValues('agent_modality')).toBe('Text');
    expect(f().getValues('voice_enabled')).toBe(false);
  });

  it('switches to template mode', async () => {
    const f = mount();
    await userEvent.click(screen.getByRole('radio', { name: /Use a template/ }));
    expect(f().getValues('prompt_mode')).toBe('Template');
  });
});
