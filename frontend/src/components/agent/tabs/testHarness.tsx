// Test helper: renders a tab with a real react-hook-form instance and exposes it.
import { useEffect, type ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { render } from '@testing-library/react';
import type { AgentFormValues } from '../types';

export const baseValues: Partial<AgentFormValues> = {
  agent_name: 'support', agent_modality: 'Both', prompt_mode: 'Local', instructions: 'Be helpful', provider: '', model: '',
  temperature: 0.7, top_p: 1, disabled: false, allow_chat: true, persist_conversation: true, persist_user_history: true,
  enable_multi_run: false, starter_prompts: [], allowed_users: [], allowed_roles: [], ssh_connections: [], default_plan: [],
  summary_prompt_mode: 'Local', agent_skill: [], allow_all_users: false, allow_guest: false,
};

export function renderTab(
  ui: (form: UseFormReturn<AgentFormValues>) => ReactElement,
  values: Partial<AgentFormValues> = {},
  onForm?: (f: UseFormReturn<AgentFormValues>) => void,
) {
  function Harness() {
    const form = useForm<AgentFormValues>({ defaultValues: { ...baseValues, ...values } as AgentFormValues });
    useEffect(() => { onForm?.(form); });
    return <MemoryRouter>{ui(form)}</MemoryRouter>;
  }
  return render(<Harness />);
}
