// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/contexts/PermissionsContext', () => ({ usePermissions: () => ({ hasCapability: () => false }) }));
vi.mock('@/contexts/FlowContext', () => ({ useFlowContext: () => ({ undo: vi.fn(), redo: vi.fn(), canUndo: false, canRedo: false, undoLabel: '', redoLabel: '' }) }));
const openShortcuts = vi.fn();
vi.mock('@/components/shortcuts/ShortcutsHelpContext', () => ({ useShortcutsHelp: () => ({ open: false, setOpen: openShortcuts }) }));
vi.mock('../../ExecutionApprovalsBell', () => ({ ExecutionApprovalsBell: () => null }));
vi.mock('../shortcuts/flowCommands', () => ({ runFlowCommand: vi.fn() }));
vi.mock('../shortcuts/shortcutHints', () => ({ shortcutText: () => '' }));

import { HeaderOverflowMenu } from './HeaderOverflowMenu';

const props = {
  statusKind: 'draft' as const, canManage: true, readOnlyReason: null, hasSteps: true, convertedProcedure: null,
  onOpenRuns: vi.fn(), onOpenSettings: vi.fn(), onTidy: vi.fn(), onConvert: vi.fn(), editTools: true,
};
const open = (extra: Record<string, unknown> = {}) => {
  render(<MemoryRouter><HeaderOverflowMenu {...props} {...extra} /></MemoryRouter>);
  fireEvent.pointerDown(screen.getByTestId('flow-header-more'), { button: 0, ctrlKey: false });
  fireEvent.keyDown(screen.getByTestId('flow-header-more'), { key: 'Enter' });
};

describe('HeaderOverflowMenu: Help & shortcuts', () => {
  it('has a "Help & shortcuts" item that opens the same help as the Help button', async () => {
    open();
    fireEvent.click(await screen.findByText('Help & shortcuts'));
    expect(await screen.findByTestId('flow-help-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('flow-help-shortcuts')).toBeInTheDocument();
  });

  it('in the narrow-desktop band (1200-1359px) the menu holds only that item', async () => {
    open({ helpOnly: true });
    expect(await screen.findByText('Help & shortcuts')).toBeInTheDocument();
    expect(screen.queryByTestId('flow-runs')).toBeNull();
    expect(screen.queryByTestId('flow-settings')).toBeNull();
  });
});
