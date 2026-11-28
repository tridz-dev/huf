// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useFlowRunRoom } from './useFlowRunRoom';

const state = vi.hoisted(() => ({ socket: null as unknown }));
vi.mock('@/contexts/SocketContext', () => ({ useSocket: () => state.socket }));

function fakeSocket(connected = true) {
  const handlers = new Set<() => void>();
  return {
    connected,
    emit: vi.fn(),
    on: vi.fn((_event: string, fn: () => void) => handlers.add(fn)),
    off: vi.fn((_event: string, fn: () => void) => handlers.delete(fn)),
    connect: () => handlers.forEach((fn) => fn()),
  };
}

describe('useFlowRunRoom', () => {
  let socket: ReturnType<typeof fakeSocket>;
  beforeEach(() => {
    socket = fakeSocket();
    state.socket = socket;
  });

  it('joins the run room and leaves it on close', () => {
    const { unmount } = renderHook(() => useFlowRunRoom('FR-1'));
    expect(socket.emit).toHaveBeenCalledWith('doc_subscribe', 'Agent Flow Run', 'FR-1');
    unmount();
    expect(socket.emit).toHaveBeenLastCalledWith('doc_unsubscribe', 'Agent Flow Run', 'FR-1');
  });

  it('follows the open run', () => {
    const { rerender } = renderHook(({ id }) => useFlowRunRoom(id), { initialProps: { id: 'FR-1' } });
    rerender({ id: 'FR-2' });
    expect(socket.emit.mock.calls.slice(1)).toEqual([
      ['doc_unsubscribe', 'Agent Flow Run', 'FR-1'],
      ['doc_subscribe', 'Agent Flow Run', 'FR-2'],
    ]);
  });

  it('stays joined while another view of the same run is open', () => {
    const first = renderHook(() => useFlowRunRoom('FR-1'));
    const second = renderHook(() => useFlowRunRoom('FR-1'));
    first.unmount();
    expect(socket.emit).not.toHaveBeenCalledWith('doc_unsubscribe', 'Agent Flow Run', 'FR-1');
    second.unmount();
    expect(socket.emit).toHaveBeenLastCalledWith('doc_unsubscribe', 'Agent Flow Run', 'FR-1');
  });

  it('joins on connect and again after a reconnect', () => {
    socket.connected = false;
    renderHook(() => useFlowRunRoom('FR-1'));
    expect(socket.emit).not.toHaveBeenCalled();
    socket.connect();
    socket.connect();
    expect(socket.emit).toHaveBeenCalledTimes(2);
  });

  it('does nothing without a run or a socket', () => {
    renderHook(() => useFlowRunRoom(null));
    expect(socket.emit).not.toHaveBeenCalled();
    state.socket = null;
    expect(() => renderHook(() => useFlowRunRoom('FR-1'))).not.toThrow();
  });
});
