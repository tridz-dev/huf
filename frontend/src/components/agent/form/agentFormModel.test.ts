// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { mapAgentDocToFormValues } from './agentFormModel';
import type { AgentDoc } from '@/types/agent.types';

describe('mapAgentDocToFormValues template normalisation', () => {
  it('Local mode has no template or version; 0 becomes undefined', () => {
    const v = mapAgentDocToFormValues({ prompt_mode: 'Local', template_version_at_attach: 0, summary_prompt_mode: 'Local', summary_template_version_at_attach: 0 } as Partial<AgentDoc>);
    expect(v.template_version_at_attach).toBeUndefined();
    expect(v.summary_template_version_at_attach).toBeUndefined();
    expect(v.agent_prompt).toBe('');
  });
  it('Template mode keeps a real version, drops 0', () => {
    const v = mapAgentDocToFormValues({ prompt_mode: 'Template', agent_prompt: 'P', template_version_at_attach: 3, summary_prompt_mode: 'Template', summary_prompt_template: 'S', summary_template_version_at_attach: 0 } as Partial<AgentDoc>);
    expect(v.template_version_at_attach).toBe(3);
    expect(v.summary_template_version_at_attach).toBeUndefined();
  });
});
