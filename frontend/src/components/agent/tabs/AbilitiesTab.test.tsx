// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AbilitiesTab, type AbilitiesTabProps } from './AbilitiesTab';

vi.mock('../ProcedureBindingsTab', () => ({ ProcedureBindingsTab: () => <div>procedures-ui</div> }));

const base = (o: Partial<AbilitiesTabProps> = {}): AbilitiesTabProps => ({
  knowledgeSources: [{ knowledge_source: 'Returns policy', mode: 'Optional', priority: 0, max_chunks: 5, token_budget: 1000 }],
  knowledgeStatus: { 'Returns policy': { state: 'failed' } },
  onAddKnowledge: vi.fn(), onEditKnowledge: vi.fn(), onRemoveKnowledge: vi.fn(), onKnowledgeModeChange: vi.fn(),
  selectedTools: [{ name: 't1', tool_name: 'Get order', description: 'Looks up an order' }],
  onAddTools: vi.fn(), onRemoveTool: vi.fn(),
  mcpServers: [{ name: 'm1', mcp_server: 'shop', server_name: 'Shop MCP', enabled: 1 }],
  onToggleMCP: vi.fn(),
  skills: [], skillOptions: [], onSkillsChange: vi.fn(),
  ...o,
});
const r = (p: AbilitiesTabProps) => render(<MemoryRouter><AbilitiesTab {...p} /></MemoryRouter>);

describe('AbilitiesTab', () => {
  it('renders knowledge with status/mode and merged actions', () => {
    r(base());
    expect(screen.getByText('Returns policy')).toBeInTheDocument();
    expect(screen.getByText('Search when relevant')).toBeInTheDocument();
    expect(screen.getByText('Failed to index')).toBeInTheDocument();
    expect(screen.getByText('Get order')).toBeInTheDocument();
    expect(screen.getByText('Shop MCP')).toBeInTheDocument();
    expect(screen.getAllByTestId('toggle-row')).toHaveLength(3);
  });

  it('MCP switch maps to enabled; tool switch off detaches', async () => {
    const p = base();
    r(p);
    const sw = screen.getAllByRole('switch');
    await userEvent.click(sw[2]);
    expect(p.onToggleMCP).toHaveBeenCalledWith('m1', false);
    await userEvent.click(sw[1]);
    expect(p.onRemoveTool).toHaveBeenCalledWith('t1');
    await userEvent.click(sw[0]);
    expect(p.onRemoveKnowledge).toHaveBeenCalledWith(0);
  });

  it('keeps advanced group collapsed, then shows skills and procedures', async () => {
    r(base());
    expect(screen.queryByText('procedures-ui')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: /Skills, MCP servers, procedures/ }));
    expect(screen.getByText('procedures-ui')).toBeInTheDocument();
  });

  it('changes knowledge mode via preset dialog', async () => {
    const p = base();
    r(p);
    await userEvent.click(screen.getByRole('button', { name: 'More actions for Returns policy' }));
    await userEvent.click(await screen.findByText('Change mode'));
    await userEvent.click(await screen.findByRole('radio', { name: /Always include/ }));
    expect(p.onKnowledgeModeChange).toHaveBeenCalledWith(0, 'Mandatory');
  });

  it('add buttons call back', async () => {
    const p = base();
    r(p);
    await userEvent.click(screen.getByRole('button', { name: /Add tool/ }));
    await userEvent.click(screen.getByRole('button', { name: /Add knowledge/ }));
    expect(p.onAddTools).toHaveBeenCalled();
    expect(p.onAddKnowledge).toHaveBeenCalled();
  });
});
