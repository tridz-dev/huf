// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { UseFormReturn } from 'react-hook-form';
import type { AgentFormValues } from '../types';
import { AdvancedPresetsTab, type AdvancedPresetsTabProps } from './AdvancedPresetsTab';
import { renderTab } from './testHarness';

// Radix Slider needs ResizeObserver, absent in jsdom.
vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });

vi.mock('@/components/ui/select', () => import('./selectMock').then((m) => m.selectMock()));

function mount(values: Partial<AgentFormValues> = {}, props: Partial<AdvancedPresetsTabProps> = {}) {
  let form!: UseFormReturn<AgentFormValues>;
  renderTab((f) => <AdvancedPresetsTab form={f} allModels={[]} summaryPromptOptions={[]} {...props} />, values, (f) => { form = f; });
  return () => form;
}

describe('AdvancedPresetsTab', () => {
  it('Creativity presets write temperature', async () => {
    const f = mount({ temperature: 1 });
    expect(screen.getByRole('radio', { name: /Creative/ })).toHaveAttribute('aria-checked', 'true');
    await userEvent.click(screen.getByRole('radio', { name: /Precise/ }));
    expect(f().getValues('temperature')).toBe(0.2);
    await userEvent.click(screen.getByRole('radio', { name: /Balanced/ }));
    expect(f().getValues('temperature')).toBe(0.7);
  });

  it('an unmatched temperature selects Custom and keeps its value', () => {
    const f = mount({ temperature: 1.4 });
    expect(screen.getAllByRole('radio', { name: /Custom/ })[0]).toHaveAttribute('aria-checked', 'true');
    expect(f().getValues('temperature')).toBe(1.4);
  });

  it('Thinking presets write reasoning mode and effort', async () => {
    const f = mount();
    await userEvent.click(screen.getByRole('radio', { name: /Deep/ }));
    expect(f().getValues('reasoning_mode')).toBe('On');
    expect(f().getValues('reasoning_effort')).toBe('High');
    await userEvent.click(screen.getByRole('radio', { name: /^Off/ }));
    expect(f().getValues('reasoning_mode')).toBe('Off');
  });

  it('keeps raw fields behind collapsed Developer options and reaches them', async () => {
    mount({ context_strategy: 'Summarize', enable_memory: true, allow_file_upload: true });
    expect(screen.queryByText(/Top P/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Show developer options/ }));
    for (const t of [/Top P/, 'Run immediately', 'Prompt caching', 'Summary ratio', 'Summary model', 'Allow conversation data management', 'Enable memory',
      'Enable memory search tool', 'Memory policy', 'Agent color', 'Show tool execution details', 'Name conversations automatically', 'Image Generation Model',
      'Allow file upload', 'Enable OCR', 'Max upload size (MB)', 'Summary prompt']) {
      expect(screen.getAllByText(t).length, String(t)).toBeGreaterThan(0);
    }
  });

  it('says what memory does when no policy is chosen', async () => {
    mount({ enable_memory: true });
    await userEvent.click(screen.getByRole('button', { name: /Show developer options/ }));
    expect(screen.getByText(/No policy selected: facts are saved and recalled automatically/)).toBeInTheDocument();
  });

  it('shows the plain policy hint when a policy is selected', async () => {
    mount({ enable_memory: true, memory_policy: 'Research' });
    await userEvent.click(screen.getByRole('button', { name: /Show developer options/ }));
    expect(screen.queryByText(/No policy selected/)).not.toBeInTheDocument();
    expect(screen.getByText('Which memories may be stored and recalled.')).toBeInTheDocument();
  });

  it('shows the Advanced caching controls only in Advanced mode with caching on', async () => {
    mount({ prompt_cache_mode: 'Advanced', enable_prompt_caching: true }, { cacheStatus: { supported: false, alternatives: ['claude-x'] } });
    await userEvent.click(screen.getByRole('button', { name: /Show developer options/ }));
    expect(screen.getByText('Cache system message')).toBeInTheDocument();
    expect(screen.getByText('Cache conversation history')).toBeInTheDocument();
    expect(screen.getByTestId('attention-banner')).toHaveTextContent('claude-x');
  });

  it('renders the limits fields and the danger zone slot', () => {
    mount({}, { dangerZone: <div data-testid="dz">Delete</div> });
    for (const l of ['History limit', 'Max turns', 'Max knowledge tokens', 'Max context characters', 'When a conversation gets long']) expect(screen.getByText(l)).toBeInTheDocument();
    expect(screen.getByTestId('dz')).toBeInTheDocument();
  });

  it('voice-only hides text-model blocks', () => {
    mount({ agent_modality: 'Voice' });
    expect(screen.queryByText('Creativity', { selector: 'h2' })).not.toBeInTheDocument();
    expect(screen.queryByText('Limits')).not.toBeInTheDocument();
    expect(screen.getByText('Thinking', { selector: 'h2' })).toBeInTheDocument();
  });
});
