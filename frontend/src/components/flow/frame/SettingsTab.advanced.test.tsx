// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('../forms/__tests__/formTestKit')).contextMock());
vi.mock('@/contexts/FlowContext.tsx', async () => (await import('../forms/__tests__/formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('../forms/__tests__/formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('../forms/__tests__/formTestKit')).catalogMock());
vi.mock('../../../services/toolApi', () => ({ getFlowTools: vi.fn().mockResolvedValue([]) }));

import { SettingsTab } from './SettingsTab';
import { flow } from '../forms/__tests__/formTestKit';

afterEach(cleanup);

describe('Settings tab: the raw JSON of a step', () => {
  it('is behind a collapsed "Advanced" disclosure with plain help, and only read-only', async () => {
    const node = flow.nodes.find((n) => n.id === 'step')!;
    render(<MemoryRouter><SettingsTab node={node as never} /></MemoryRouter>);
    const toggle = screen.getByTestId('flow-view-as-json-toggle');
    expect(toggle.textContent).toContain('Advanced');
    expect(screen.queryByTestId('flow-view-as-json-text')).toBeNull();
    fireEvent.click(toggle);
    expect(await screen.findByTestId('flow-json-step-stored-help')).toHaveTextContent('only here to read and copy');
    expect(screen.getByTestId('flow-view-as-json-text')).toBeTruthy();
    expect(screen.queryByTestId('flow-json-step-stored-input')).toBeNull(); // no editable box
  });
});
