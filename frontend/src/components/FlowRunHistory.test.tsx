// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { FlowRunHistory } from './FlowRunHistory';

vi.mock('../services/flowService', () => ({ flowService: { listFlowRuns: () => Promise.resolve([]) } }));
vi.mock('@/lib/serverTime', () => ({ useSiteTimezone: () => null }));
vi.mock('@/contexts/UserContext', () => ({ useUser: () => ({ user: null }) }));
vi.mock('@/hooks/flow/useFlowPermissions', () => ({ useFlowPermissions: () => ({ canManage: true }) }));
vi.mock('@/lib/ui/responsive', () => ({ useViewport: () => ({ isPhone: false }) }));

const w = window as unknown as { frappe?: unknown };
const emptyText = async () => {
  render(<FlowRunHistory flowId="f1" open onOpenChange={() => {}} onSelectRun={() => {}} />);
  return (await screen.findByTestId('flow-run-history-empty')).textContent;
};

afterEach(() => {
  cleanup();
  delete w.frappe;
});

describe('FlowRunHistory empty state', () => {
  it('suggests publishing outside the embed', async () => {
    expect(await emptyText()).toContain('publish it');
  });

  it('does not mention publishing in the embed', async () => {
    w.frappe = { boot: { huf_embed: { allowed_origins: [] } } };
    expect(await emptyText()).not.toMatch(/publish/i);
  });
});
