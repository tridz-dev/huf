// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

// jsdom's built-in Blob doesn't implement `arrayBuffer()` (used by
// `blobToBase64`) — swap in Node's spec-compliant Blob for this suite so
// both the pure-function tests and the hook tests share one working Blob.
import { Blob as NodeBlob } from 'node:buffer';
(globalThis as unknown as { Blob: unknown }).Blob = NodeBlob;

vi.mock('@/services/meetingApi', () => ({
  uploadChunk: vi.fn(),
}));

import {
  computeBackoffDelayMs,
  chunkRecordId,
  blobToBase64,
  MAX_AUTO_RETRIES,
  DEFAULT_TIMESLICE_MS,
} from './useMeetingRecorder';

describe('computeBackoffDelayMs', () => {
  it('doubles the delay for each retry, starting at 2s', () => {
    expect(computeBackoffDelayMs(0)).toBe(2_000);
    expect(computeBackoffDelayMs(1)).toBe(4_000);
    expect(computeBackoffDelayMs(2)).toBe(8_000);
    expect(computeBackoffDelayMs(3)).toBe(16_000);
  });

  it('caps the delay at 60s', () => {
    expect(computeBackoffDelayMs(10)).toBe(60_000);
    expect(computeBackoffDelayMs(MAX_AUTO_RETRIES)).toBeLessThanOrEqual(60_000);
  });

  it('treats negative retry counts as the first attempt', () => {
    expect(computeBackoffDelayMs(-1)).toBe(2_000);
  });
});

describe('chunkRecordId', () => {
  it('builds a stable, sortable-by-meeting key from meeting + sequence', () => {
    expect(chunkRecordId('MEETING-001', 0)).toBe('MEETING-001:0');
    expect(chunkRecordId('MEETING-001', 12)).toBe('MEETING-001:12');
  });

  it('produces distinct keys for different meetings with the same sequence', () => {
    expect(chunkRecordId('MEETING-001', 3)).not.toBe(chunkRecordId('MEETING-002', 3));
  });
});

describe('blobToBase64', () => {
  it('round-trips small binary content to base64', async () => {
    const bytes = new Uint8Array([104, 101, 108, 108, 111]); // "hello"
    const blob = new Blob([bytes], { type: 'audio/webm' });
    const b64 = await blobToBase64(blob);
    expect(b64).toBe(Buffer.from(bytes).toString('base64'));
  });

  it('handles an empty blob', async () => {
    const blob = new Blob([], { type: 'audio/webm' });
    const b64 = await blobToBase64(blob);
    expect(b64).toBe('');
  });
});

describe('constants', () => {
  it('keeps the default segment length within the 30-60s target window', () => {
    expect(DEFAULT_TIMESLICE_MS).toBeGreaterThanOrEqual(30_000);
    expect(DEFAULT_TIMESLICE_MS).toBeLessThanOrEqual(60_000);
  });
});

// ---------------------------------------------------------------------------
// Browser API mocks for the hook-level tests below
// ---------------------------------------------------------------------------

class FakeMediaStreamTrack {
  kind: string;
  readyState: 'live' | 'ended' = 'live';
  enabled = true;
  onended: (() => void) | null = null;

  constructor(kind: string) {
    this.kind = kind;
  }

  stop() {
    this.readyState = 'ended';
  }
}

class FakeMediaStream {
  private tracks: FakeMediaStreamTrack[];

  constructor(tracks: FakeMediaStreamTrack[]) {
    this.tracks = tracks;
  }

  getTracks() {
    return this.tracks;
  }

  getAudioTracks() {
    return this.tracks.filter((t) => t.kind === 'audio');
  }

  getVideoTracks() {
    return this.tracks.filter((t) => t.kind === 'video');
  }
}

const fakeMediaRecorderInstances: FakeMediaRecorder[] = [];

class FakeMediaRecorder {
  static isTypeSupported = () => true;
  state: 'recording' | 'inactive' | 'paused' = 'recording';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  private listeners: Record<string, Array<() => void>> = {};

  constructor(public stream: unknown, public options: unknown) {
    fakeMediaRecorderInstances.push(this);
  }

  start() {
    this.state = 'recording';
  }

  stop() {
    this.state = 'inactive';
    (this.listeners.stop || []).forEach((cb) => cb());
  }

  addEventListener(event: string, cb: () => void) {
    this.listeners[event] = this.listeners[event] || [];
    this.listeners[event].push(cb);
  }
}

class FakeAudioNode {
  connect = vi.fn();
  disconnect = vi.fn();
}

class FakeAudioContext {
  state = 'running';
  createMediaStreamSource = vi.fn(() => new FakeAudioNode());
  createMediaStreamDestination = vi.fn(() => ({
    ...new FakeAudioNode(),
    stream: new FakeMediaStream([new FakeMediaStreamTrack('audio')]),
  }));
  close = vi.fn(async () => {
    this.state = 'closed';
  });
}

function installBrowserMocks({ displaySupported = true }: { displaySupported?: boolean } = {}) {
  const getUserMedia = vi.fn(async () => new FakeMediaStream([new FakeMediaStreamTrack('audio')]));
  const getDisplayMedia = displaySupported
    ? vi.fn(
        async () =>
          new FakeMediaStream([new FakeMediaStreamTrack('audio'), new FakeMediaStreamTrack('video')]),
      )
    : undefined;

  const mediaDevices = {
    getUserMedia,
    ...(getDisplayMedia ? { getDisplayMedia } : {}),
  };
  Object.defineProperty(window.navigator, 'mediaDevices', {
    value: mediaDevices,
    configurable: true,
  });

  (window as unknown as { MediaRecorder: unknown }).MediaRecorder = FakeMediaRecorder;
  (globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder = FakeMediaRecorder;
  (window as unknown as { AudioContext: unknown }).AudioContext = FakeAudioContext;
  (globalThis as unknown as { AudioContext: unknown }).AudioContext = FakeAudioContext;

  return { getUserMedia, getDisplayMedia };
}

// Minimal in-memory fake IndexedDB — just enough of the API surface
// (open/transaction/objectStore/index put+delete+getAll) for this hook's
// queue helpers (putQueuedChunk/getQueuedChunksForMeeting/getMaxQueuedSequence)
// to work against real records, so the sequence-continuity behavior can be
// exercised end-to-end rather than only via the "IndexedDB unavailable"
// fallback path.
function installFakeIndexedDb() {
  const rows = new Map<string, Record<string, unknown>>();

  function makeRequest<T>(run: () => T) {
    const request: {
      result?: T;
      error?: unknown;
      onsuccess: (() => void) | null;
      onerror: (() => void) | null;
    } = { onsuccess: null, onerror: null };
    queueMicrotask(() => {
      try {
        request.result = run();
        request.onsuccess?.();
      } catch (error) {
        request.error = error;
        request.onerror?.();
      }
    });
    return request;
  }

  const store = {
    put: (record: Record<string, unknown>) => makeRequest(() => rows.set(record.id as string, record)),
    delete: (id: string) => makeRequest(() => rows.delete(id)),
    getAll: () => makeRequest(() => [...rows.values()]),
    createIndex: () => {},
    index: () => ({
      getAll: (meeting: string) =>
        makeRequest(() => [...rows.values()].filter((r) => r.meeting === meeting)),
    }),
  };

  const tx = {
    objectStore: () => store,
    oncomplete: null as (() => void) | null,
    onerror: null as (() => void) | null,
  };
  // Fire tx.oncomplete shortly after any operation so put()/delete()'s
  // wrapping promise (which resolves on tx.oncomplete) settles.
  const originalPut = store.put;
  const originalDelete = store.delete;
  store.put = (record) => {
    const req = originalPut(record);
    queueMicrotask(() => queueMicrotask(() => tx.oncomplete?.()));
    return req;
  };
  store.delete = (id) => {
    const req = originalDelete(id);
    queueMicrotask(() => queueMicrotask(() => tx.oncomplete?.()));
    return req;
  };

  const db = { transaction: () => tx, objectStoreNames: { contains: () => true } };

  const fakeIndexedDb = {
    open: () => {
      const request: {
        result: typeof db;
        onupgradeneeded: (() => void) | null;
        onsuccess: (() => void) | null;
        onerror: (() => void) | null;
      } = { result: db, onupgradeneeded: null, onsuccess: null, onerror: null };
      queueMicrotask(() => {
        request.onupgradeneeded?.();
        request.onsuccess?.();
      });
      return request;
    },
  };

  Object.defineProperty(window, 'indexedDB', { value: fakeIndexedDb, configurable: true });
}

describe('useMeetingRecorder — display/tab audio mixing', () => {
  let useMeetingRecorder: typeof import('./useMeetingRecorder').useMeetingRecorder;

  beforeEach(async () => {
    vi.resetModules();
    installFakeIndexedDb();
    ({ useMeetingRecorder } = await import('./useMeetingRecorder'));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reports unsupported browsers via onError instead of crashing', async () => {
    installBrowserMocks({ displaySupported: false });
    const onError = vi.fn();
    const { result } = renderHook(() => useMeetingRecorder({ meetingName: 'MEETING-1', onError }));

    await act(async () => {
      await result.current.start();
    });

    await act(async () => {
      await result.current.shareTabAudio();
    });

    expect(onError).toHaveBeenCalledWith(expect.any(Error));
    expect(onError.mock.calls[0][0].message).toMatch(/not supported/i);
    expect(result.current.tabAudioActive).toBe(false);
  });

  it('reports denied getDisplayMedia permission via onError', async () => {
    installBrowserMocks();
    (
      window.navigator.mediaDevices.getDisplayMedia as unknown as ReturnType<typeof vi.fn>
    ).mockRejectedValueOnce(new Error('Permission denied'));
    const onError = vi.fn();
    const { result } = renderHook(() => useMeetingRecorder({ meetingName: 'MEETING-1', onError }));

    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await result.current.shareTabAudio();
    });

    expect(onError).toHaveBeenCalledWith(expect.any(Error));
    expect(result.current.tabAudioActive).toBe(false);
  });

  it('sets tabAudioActive to false when the display track ends', async () => {
    installBrowserMocks();
    const { result } = renderHook(() => useMeetingRecorder({ meetingName: 'MEETING-1' }));

    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await result.current.shareTabAudio();
    });
    expect(result.current.tabAudioActive).toBe(true);

    // Simulate the user clicking Chrome's native "Stop sharing" UI.
    const displayCall = (
      window.navigator.mediaDevices.getDisplayMedia as unknown as ReturnType<typeof vi.fn>
    ).mock.results[0].value as Promise<FakeMediaStream>;
    const displayStream = await displayCall;
    const audioTrack = displayStream.getAudioTracks()[0];

    await act(async () => {
      audioTrack.onended?.();
    });

    await waitFor(() => expect(result.current.tabAudioActive).toBe(false));
  });

  it('mute only disables the mic track, never the tab-audio track', async () => {
    installBrowserMocks();
    const { result } = renderHook(() => useMeetingRecorder({ meetingName: 'MEETING-1' }));

    await act(async () => {
      await result.current.start();
    });
    const micCall = (
      window.navigator.mediaDevices.getUserMedia as unknown as ReturnType<typeof vi.fn>
    ).mock.results[0].value as Promise<FakeMediaStream>;
    const micStream = await micCall;

    await act(async () => {
      await result.current.shareTabAudio();
    });
    const displayCall = (
      window.navigator.mediaDevices.getDisplayMedia as unknown as ReturnType<typeof vi.fn>
    ).mock.results[0].value as Promise<FakeMediaStream>;
    const displayStream = await displayCall;

    act(() => {
      result.current.toggleMute();
    });

    expect(result.current.isMuted).toBe(true);
    expect(micStream.getAudioTracks()[0].enabled).toBe(false);
    expect(displayStream.getAudioTracks()[0].enabled).toBe(true);
  });
});

describe('useMeetingRecorder — sequence continuity on resume', () => {
  let useMeetingRecorder: typeof import('./useMeetingRecorder').useMeetingRecorder;
  let putQueuedChunkDirect: (record: {
    id: string;
    meeting: string;
    sequence: number;
    blob: Blob;
    mimeType: string;
    clientStartedAt: string;
    durationSeconds: number;
    retryCount: number;
    createdAt: number;
  }) => Promise<void>;

  beforeEach(async () => {
    vi.resetModules();
    installFakeIndexedDb();
    const mod = await import('./useMeetingRecorder');
    useMeetingRecorder = mod.useMeetingRecorder;
    // The module's internal `putQueuedChunk` isn't exported, so seed a
    // queued record for a "prior interrupted session" by writing directly
    // through the same fake IndexedDB the hook itself will use.
    putQueuedChunkDirect = (record) =>
      new Promise((resolve, reject) => {
        const request = window.indexedDB.open('huf_meeting_recorder', 1);
        request.onsuccess = () => {
          const db = request.result as unknown as {
            transaction: (name: string, mode: string) => {
              objectStore: (name: string) => { put: (r: unknown) => { onsuccess: (() => void) | null } };
              oncomplete: (() => void) | null;
            };
          };
          const tx = db.transaction('pending_chunks', 'readwrite');
          tx.objectStore('pending_chunks').put(record);
          tx.oncomplete = () => resolve();
        };
        request.onerror = () => reject(request.error);
      });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('seeds the sequence counter from the max already-queued sequence, not 0', async () => {
    installBrowserMocks();
    const { uploadChunk } = await import('@/services/meetingApi');
    (uploadChunk as unknown as ReturnType<typeof vi.fn>).mockReset();
    (uploadChunk as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    fakeMediaRecorderInstances.length = 0;

    // Simulate a prior interrupted session for this meeting that left
    // sequences 0 and 1 queued in IndexedDB (unconfirmed uploads).
    await putQueuedChunkDirect({
      id: 'MEETING-1:0',
      meeting: 'MEETING-1',
      sequence: 0,
      blob: new Blob(['a']),
      mimeType: 'audio/webm',
      clientStartedAt: new Date().toISOString(),
      durationSeconds: 45,
      retryCount: 0,
      createdAt: Date.now(),
    });
    await putQueuedChunkDirect({
      id: 'MEETING-1:1',
      meeting: 'MEETING-1',
      sequence: 1,
      blob: new Blob(['b']),
      mimeType: 'audio/webm',
      clientStartedAt: new Date().toISOString(),
      durationSeconds: 45,
      retryCount: 0,
      createdAt: Date.now(),
    });

    const { result } = renderHook(() => useMeetingRecorder({ meetingName: 'MEETING-1' }));

    await act(async () => {
      await result.current.start();
    });

    // Emit a new segment via the recorder's ondataavailable handler and
    // confirm it uploads under sequence 2, not 0 or 1 — reusing either
    // would overwrite the still-queued IndexedDB record at that key.
    const recorder = fakeMediaRecorderInstances[fakeMediaRecorderInstances.length - 1];
    await act(async () => {
      recorder.ondataavailable?.({ data: new Blob(['c'], { type: 'audio/webm' }) });
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => expect(uploadChunk).toHaveBeenCalled());
    const call = (uploadChunk as unknown as ReturnType<typeof vi.fn>).mock.calls.at(-1)![0];
    expect(call.sequence).toBe(2);
  });

  it('falls back to sequence 0 for a fresh meeting with nothing queued', async () => {
    installBrowserMocks();
    const { uploadChunk } = await import('@/services/meetingApi');
    (uploadChunk as unknown as ReturnType<typeof vi.fn>).mockReset();
    (uploadChunk as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    fakeMediaRecorderInstances.length = 0;

    const { result } = renderHook(() => useMeetingRecorder({ meetingName: 'MEETING-FRESH' }));

    await act(async () => {
      await result.current.start();
    });

    const recorder = fakeMediaRecorderInstances[fakeMediaRecorderInstances.length - 1];
    await act(async () => {
      recorder.ondataavailable?.({ data: new Blob(['c'], { type: 'audio/webm' }) });
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => expect(uploadChunk).toHaveBeenCalled());
    const call = (uploadChunk as unknown as ReturnType<typeof vi.fn>).mock.calls.at(-1)![0];
    expect(call.sequence).toBe(0);
  });
});
