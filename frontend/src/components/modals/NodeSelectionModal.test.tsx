// @vitest-environment jsdom
import { MemoryRouter } from 'react-router-dom';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FIXTURE_REGISTRY } from '@/lib/flow-gateway/registryFixture';

let registry: typeof FIXTURE_REGISTRY | null = FIXTURE_REGISTRY;
const enabledSeen: boolean[] = [];
vi.mock('@/hooks/flow/useGatewayRegistry', () => ({
  useGatewayRegistry: (enabled: boolean) => (enabledSeen.push(enabled), { registry, loading: false, failed: false, reload: vi.fn() }),
}));
vi.mock('@/hooks/flow/useFlowPermissions', () => ({ useFlowPermissions: () => ({ canManage: true, canExecuteCode: false }) }));
vi.mock('@/lib/flow-graph/useCodeFlowStatus', () => ({ useCodeFlowStatus: () => ({ status: null }) }));

import { NodeSelectionModal } from './NodeSelectionModal';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
afterEach(() => {
  cleanup();
  registry = FIXTURE_REGISTRY;
  enabledSeen.length = 0;
});

const open = (onSaveTrigger = vi.fn()) => {
  render(<MemoryRouter><NodeSelectionModal open mode="trigger" onClose={() => {}} onSaveTrigger={onSaveTrigger} /></MemoryRouter>);
  return onSaveTrigger;
};

describe('trigger chooser with chat triggers', () => {
  it('offers the three chat cards in plain words beside the others', () => {
    open();
    expect(screen.getByTestId('flow-card-gateway').textContent).toContain('A chat message');
    expect(screen.getByTestId('flow-card-whatsapp').textContent).toContain('A WhatsApp message');
    expect(screen.getByTestId('flow-card-telegram').textContent).toContain('A Telegram message');
    expect(screen.getByTestId('flow-card-webhook')).toBeTruthy();
  });

  it('picking WhatsApp when one number is connected pre-picks it', () => {
    const save = open();
    fireEvent.click(screen.getByTestId('flow-card-whatsapp'));
    fireEvent.click(screen.getByTestId('flow-modal-add-trigger'));
    expect(save).toHaveBeenCalledWith({ type: 'whatsapp', gateway: 'Support WhatsApp' });
  });

  it('picking the generic chat trigger leaves the channel for the side panel', () => {
    const save = open();
    fireEvent.click(screen.getByTestId('flow-card-gateway'));
    fireEvent.click(screen.getByTestId('flow-modal-add-trigger'));
    expect(save).toHaveBeenCalledWith({ type: 'gateway' });
  });

  it('says so, with a link, when no number of that kind is connected yet; the card still works', () => {
    registry = { ...FIXTURE_REGISTRY, gateways: [] };
    const save = open();
    expect(screen.getByTestId('flow-card-connect-whatsapp').textContent).toContain('No WhatsApp number is connected yet');
    expect(screen.getByTestId('flow-card-connect-link-whatsapp').getAttribute('href')).toBe('/channels/whatsapp/setup');
    expect(screen.getByTestId('flow-card-connect-telegram')).toBeTruthy();
    expect(screen.queryByTestId('flow-card-connect-gateway')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-card-whatsapp'));
    fireEvent.click(screen.getByTestId('flow-modal-add-trigger'));
    expect(save).toHaveBeenCalledWith({ type: 'whatsapp' });
  });

  it('does not nag before the channel list is known', () => {
    registry = null;
    open();
    expect(screen.queryByTestId('flow-card-connect-whatsapp')).toBeNull();
  });

  it('only asks the server for channels while the chooser is open', () => {
    open();
    expect(enabledSeen.every((e) => e === true)).toBe(true);
    cleanup();
    enabledSeen.length = 0;
    render(<MemoryRouter><NodeSelectionModal open={false} mode="trigger" onClose={() => {}} /></MemoryRouter>);
    expect(enabledSeen.every((e) => e === false)).toBe(true);
  });
});
