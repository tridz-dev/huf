// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PermissionsContext } from '@/contexts/PermissionsContext';
import { AgentPromptsHeaderActions } from '@/components/AgentPromptsHeaderActions';
import { SkillsHeaderActions } from '@/components/skills/SkillsHeaderActions';
import { ExecutionProfilesHeaderActions } from '@/components/ExecutionProfilesHeaderActions';
import { SSHConnectionsHeaderActions } from '@/components/SSHConnectionsHeaderActions';
import { MeetingsHeaderActions } from '@/components/meetings/MeetingsHeaderActions';
import { KnowledgeHeaderActions } from '@/components/KnowledgeHeaderActions';
import { McpHeaderActions } from '@/components/McpHeaderActions';
import { HomeHeaderActions } from '@/components/HomeHeaderActions';
import { ProtectedRoute } from '@/components/ProtectedRoute';

vi.mock('@/contexts/UserContext', () => ({ useUser: () => ({ isLoading: false, isAuthenticated: true }) }));
vi.mock('@/layouts/UnifiedLayout', () => ({ UnifiedLayout: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/NoAccessPanel', () => ({ NoAccessPanel: () => <p>no access</p> }));

afterEach(cleanup);

type Perms = Record<string, { create: boolean; delete: boolean }>;

function wrap(node: ReactNode, { caps = [] as string[], docs, isLoading = false, path = '/' }: { caps?: string[]; docs?: Perms; isLoading?: boolean; path?: string } = {}) {
  return render(
    <PermissionsContext.Provider
      value={{ hufRole: null, capabilities: caps, withheldCapabilities: [], docPermissions: docs, isLoading, hasCapability: (c) => caps.includes(c), refresh: async () => {} }}
    >
      <MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>
    </PermissionsContext.Provider>,
  );
}

const all = (doctype: string, allowed: boolean): Perms => ({ [doctype]: { create: allowed, delete: allowed } });

describe('DocType-gated header actions', () => {
  const cases: [string, () => ReactNode, string, RegExp][] = [
    ['prompts', () => <AgentPromptsHeaderActions />, 'Agent Prompt', /new agent prompt/i],
    ['skills import', () => <SkillsHeaderActions />, 'Skill', /import/i],
    ['skills marketplace', () => <SkillsHeaderActions />, 'Skill', /marketplace/i],
    ['meetings', () => <MeetingsHeaderActions />, 'Meeting', /quick start/i],
    ['knowledge', () => <KnowledgeHeaderActions />, 'Knowledge Source', /new knowledge source/i],
    ['mcp', () => <McpHeaderActions />, 'MCP Server', /new mcp server/i],
  ];

  it.each(cases)('%s follows the DocType permission and hides while loading', (_name, node, doctype, label) => {
    const allowed = wrap(node(), { docs: all(doctype, true) });
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    allowed.unmount();
    const denied = wrap(node(), { docs: all(doctype, false) });
    expect(screen.queryByRole('button', { name: label })).toBeNull();
    denied.unmount();
    wrap(node(), { docs: all(doctype, true), isLoading: true });
    expect(screen.queryByRole('button', { name: label })).toBeNull();
  });

  it('keeps offering the action when the server does not report DocType permissions', () => {
    wrap(<AgentPromptsHeaderActions />);
    expect(screen.getByRole('button', { name: /new agent prompt/i })).toBeInTheDocument();
  });
});

describe('capability-gated header actions', () => {
  it.each([
    [() => <ExecutionProfilesHeaderActions />, 'execution_profile.manage', /new execution profile/i],
    [() => <SSHConnectionsHeaderActions />, 'ssh_connection.manage', /new ssh connection/i],
  ])('needs the capability', (node, capability, label) => {
    const denied = wrap(node());
    expect(screen.queryByRole('button', { name: label })).toBeNull();
    denied.unmount();
    wrap(node(), { caps: [capability] });
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
  });

  it('hides the dashboard menu when there is nothing to open', () => {
    wrap(<HomeHeaderActions />);
    expect(screen.queryByRole('button', { name: /new/i })).toBeNull();
  });
});

describe('"/new" routes', () => {
  const route = (
    <ProtectedRoute createResource="prompt">
      <p>form</p>
    </ProtectedRoute>
  );

  it('blocks creating without permission', () => {
    wrap(route, { docs: all('Agent Prompt', false), path: '/prompts/new' });
    expect(screen.getByText('no access')).toBeInTheDocument();
    expect(screen.queryByText('form')).toBeNull();
  });

  it('leaves existing records readable', () => {
    wrap(route, { docs: all('Agent Prompt', false), path: '/prompts/abc' });
    expect(screen.getByText('form')).toBeInTheDocument();
  });

  it('does not mount the form while permissions load', () => {
    wrap(route, { isLoading: true, path: '/prompts/new' });
    expect(screen.queryByText('form')).toBeNull();
    expect(screen.queryByText('no access')).toBeNull();
  });

  it('allows creating with permission', () => {
    wrap(route, { docs: all('Agent Prompt', true), path: '/prompts/new' });
    expect(screen.getByText('form')).toBeInTheDocument();
  });
});
