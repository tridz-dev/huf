// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useNavigate, useParams } from 'react-router-dom';

import { SkillFormPage } from '@/pages/SkillFormPage';
import { getSkill } from '@/services/skillApi';
import { getToolFunctions } from '@/services/toolApi';
import { getKnowledgeSources } from '@/services/knowledgeApi';
import { getAgentPrompts } from '@/services/agentPromptApi';
import { getMCPServers } from '@/services/mcpApi';
import { getCategories } from '@/services/categoryApi';
import type { SkillDoc } from '@/types/skill.types';

vi.mock('react-router-dom', () => ({
  useNavigate: vi.fn(),
  useParams: vi.fn(),
}));

vi.mock('@/services/skillApi', () => ({
  getSkill: vi.fn(),
  createSkill: vi.fn(),
  updateSkill: vi.fn(),
  exportSkillAsHuf: vi.fn(),
}));

vi.mock('@/services/toolApi', () => ({
  getToolFunctions: vi.fn(),
}));

vi.mock('@/services/knowledgeApi', () => ({
  getKnowledgeSources: vi.fn(),
}));

vi.mock('@/services/agentPromptApi', () => ({
  getAgentPrompts: vi.fn(),
}));

vi.mock('@/services/mcpApi', () => ({
  getMCPServers: vi.fn(),
}));

vi.mock('@/services/categoryApi', () => ({
  getCategories: vi.fn(),
}));

vi.mock('@/components/category/CategoryTab', () => ({
  CategoryTab: () => null,
}));

vi.mock('@/components/category/CategoryModal', () => ({
  CategoryModal: () => null,
}));

vi.mock('@/components/ui/multi-select-combobox', () => ({
  MultiSelectCombobox: ({
    options,
    values,
    onValuesChange,
  }: {
    options: { value: string; label: string }[];
    values: string[];
    onValuesChange: (values: string[]) => void;
  }) => (
    <div>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={values.includes(option.value)}
          onClick={() =>
            onValuesChange(
              values.includes(option.value)
                ? values.filter((value) => value !== option.value)
                : [...values, option.value]
            )
          }
        >
          Select {option.label}
        </button>
      ))}
    </div>
  ),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

const existingSkill: SkillDoc = {
  name: 'skill-1',
  owner: 'Administrator',
  creation: '2026-01-01 00:00:00',
  modified: '2026-01-01 00:00:00',
  modified_by: 'Administrator',
  docstatus: 0,
  idx: 0,
  doctype: 'Skill',
  skill_name: 'existing_skill',
  title: 'Existing skill',
  source_type: 'Local',
  status: 'Active',
  skill_tools: [{ tool: 'tool-one', tool_name: 'Tool One', description: 'First tool' }],
};

describe('SkillFormPage tool selection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useNavigate).mockReturnValue(vi.fn());
    vi.mocked(useParams).mockReturnValue({ id: 'new' });
    vi.mocked(getToolFunctions).mockResolvedValue([
      { name: 'tool-one', tool_name: 'Tool One', description: 'First tool' },
      { name: 'tool-two', tool_name: 'Tool Two', description: 'Second tool' },
    ]);
    vi.mocked(getKnowledgeSources).mockResolvedValue({ items: [], hasMore: false });
    vi.mocked(getAgentPrompts).mockResolvedValue([]);
    vi.mocked(getMCPServers).mockResolvedValue([]);
    vi.mocked(getCategories).mockResolvedValue([]);
    vi.mocked(getSkill).mockResolvedValue(existingSkill);
  });

  it('adds multiple selected tools at once and ignores tools already linked to the skill', async () => {
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    );
    const user = userEvent.setup();
    vi.mocked(useParams).mockReturnValue({ id: existingSkill.name });
    render(<SkillFormPage />);

    await user.click(await screen.findByRole('tab', { name: 'Tools' }));
    const addButton = screen.getByRole('button', { name: 'Add Tool' });
    expect(addButton).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Select Tool One' }));
    await user.click(screen.getByRole('button', { name: 'Select Tool Two' }));

    expect(addButton).toBeEnabled();
    await user.click(addButton);

    expect(screen.getByRole('button', { name: 'Select Tool One' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    expect(screen.getByRole('button', { name: 'Select Tool Two' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    const toolRows = screen.getByText('Tool Two').closest<HTMLElement>('.grid');
    if (!toolRows) throw new Error('Tool rows container was not rendered');
    expect(within(toolRows).getAllByText('Tool One')).toHaveLength(1);
    expect(within(toolRows).getAllByText('Tool Two')).toHaveLength(1);
  });
});
