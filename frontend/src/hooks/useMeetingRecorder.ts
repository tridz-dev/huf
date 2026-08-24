/**
 * useMeetingRecorder
 *
 * Core recording hook for the Meeting Recorder feature (Phase 3). Wraps the
 * browser `MediaRecorder` API to progressively capture audio in ~30-60s
 * segments, queues each segment in IndexedDB before it is confirmed
 * uploaded, and drives the Phase 2 `upload_chunk` API with retry/backoff.
 *
 * ## Public API shape
 *
 * `useMeetingRecorder({ meetingName })` returns:
 *   - `status`: `'idle' | 'recording' | 'paused' | 'stopped'` — mirrors the
 *     *client's* capture state, not `Meeting.status` on the server (callers
 *     that need the server status should read it from `meetingApi.getMeeting`
 *     separately; this hook does not poll the server).
 *   - `isMuted`, `elapsedSeconds`, `pendingUploadCount` — live UI state.
 *   - `resumableMeeting`: set on mount if IndexedDB holds unflushed segments
 *     for *any* meeting (i.e. the app was closed mid-recording). Callers
 *     decide the UX (offer "Resume recording" / discard).
 *   - `start()`, `pause()`, `resume()`, `toggleMute()`, `stop()` — the
 *     control surface used by `MeetingRecorderPage`/`RecorderControls`.
 *   - `resumeQueuedUploads(meetingName)` / `discardQueuedUploads(meetingName)`
 *     — flush or drop a previous session's unsent segments without starting
 *     a new recording.
 *
 * ## IndexedDB schema (db `huf_meeting_recorder`, store `pending_chunks`)
 *
 * One record per not-yet-confirmed segment, keyed by `${meeting}:${sequence}`:
 *   `{ id, meeting, sequence, blob, mimeType, clientStartedAt,
 *      durationSeconds, retryCount, createdAt }`
 * A record is written *before* the first upload attempt and deleted only
 * after the server returns success — so a tab crash/refresh mid-upload
 * never silently drops audio (see PLAN.md section D.2/K). An index on
 * `meeting` lets `resumableMeeting` be computed with a single cursor scan.
 *
 * ## Extension points for later phases
 *   - Phase 6 (realtime): subscribe to `meeting_chunk_uploaded` alongside
 *     this hook's `pendingUploadCount` to reconcile client vs. server state;
 *     no changes needed here, this hook only reports local queue depth.
 *   - Phase 7 (detail page): does not use this hook at all — it reads
 *     finished `Meeting`/`Meeting Recording Chunk` data via `meetingApi`.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { uploadChunk } from '@/services/meetingApi';

// ---------------------------------------------------------------------------
// Pure helpers (exported for unit testing without a DOM/MediaRecorder mock)
// ---------------------------------------------------------------------------

/** Default segment length: emit a chunk every 45s (within the 30-60s target). */
export const DEFAULT_TIMESLICE_MS = 45_000;

const BASE_RETRY_DELAY_MS = 2_000;
const MAX_RETRY_DELAY_MS = 60_000;
/** After this many automatic attempts, a chunk stays queued but is no
 * longer auto-retried — surfaced via `pendingUploadCount` until the user
 * (or `resumeQueuedUploads`) triggers another attempt. */
export const MAX_AUTO_RETRIES = 6;

/** Exponential backoff with a cap: 2s, 4s, 8s, 16s, 32s, 60s, 60s, ... */
export function computeBackoffDelayMs(retryCount: number): number {
  const delay = BASE_RETRY_DELAY_MS * 2 ** Math.max(0, retryCount);
  return Math.min(delay, MAX_RETRY_DELAY_MS);
}

/** Builds the IndexedDB primary key for a segment. */
export function chunkRecordId(meeting: string, sequence: number): string {
  return `${meeting}:${sequence}`;
}

/** Base64-encodes a Blob without relying on FileReader (works in the
 * browser and under Vitest's node environment alike). */
export async function blobToBase64(blob: Blob): Promise<string> {
  const buffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  if (typeof btoa === 'function') {
    return btoa(binary);
  }
  // Node/Vitest fallback (no global btoa in the vitest `node` environment).
  return Buffer.from(bytes).toString('base64');
}

export type RecorderStatus = 'idle' | 'recording' | 'paused' | 'stopped';

export interface QueuedChunkRecord {
  id: string;
  meeting: string;
  sequence: number;
  blob: Blob;
  mimeType: string;
  clientStartedAt: string;
  durationSeconds: number;
  retryCount: number;
  createdAt: number;
}

// ---------------------------------------------------------------------------
// IndexedDB queue
// ---------------------------------------------------------------------------

const DB_NAME = 'huf_meeting_recorder';
const DB_VERSION = 1;
const STORE_NAME = 'pending_chunks';
const MEETING_INDEX = 'meeting';

let dbPromise: Promise<IDBDatabase> | null = null;

function openQueueDb(): Promise<IDBDatabase> {
  if (typeof indexedDB === 'undefined') {
    return Promise.reject(new Error('IndexedDB is not available in this environment'));
  }
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
          store.createIndex(MEETING_INDEX, 'meeting', { unique: false });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
  return dbPromise;
}

async function putQueuedChunk(record: QueuedChunkRecord): Promise<void> {
  const db = await openQueueDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function deleteQueuedChunk(id: string): Promise<void> {
  const db = await openQueueDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getQueuedChunksForMeeting(meeting: string): Promise<QueuedChunkRecord[]> {
  const db = await openQueueDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const index = tx.objectStore(STORE_NAME).index(MEETING_INDEX);
    const request = index.getAll(meeting);
    request.onsuccess = () => resolve((request.result || []) as QueuedChunkRecord[]);
    request.onerror = () => reject(request.error);
  });
}

async function getAllQueuedChunks(): Promise<QueuedChunkRecord[]> {
  const db = await openQueueDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const request = tx.objectStore(STORE_NAME).getAll();
    request.onsuccess = () => resolve((request.result || []) as QueuedChunkRecord[]);
    request.onerror = () => reject(request.error);
  });
}

export interface ResumableMeeting {
  meetingName: string;
  pendingChunkCount: number;
}

/** Scans the queue for any meeting with unflushed segments. Exported so
 * pages that want to check before mounting the hook (e.g. the meetings
 * list) can do so directly. */
export async function findResumableMeeting(): Promise<ResumableMeeting | null> {
  try {
    const all = await getAllQueuedChunks();
    if (all.length === 0) return null;
    const counts = new Map<string, number>();
    for (const record of all) {
      counts.set(record.meeting, (counts.get(record.meeting) || 0) + 1);
    }
    const [meetingName, pendingChunkCount] = [...counts.entries()][0];
    return { meetingName, pendingChunkCount };
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseMeetingRecorderOptions {
  /** The `Meeting.name` this recording session belongs to. Uploads are
   * inert until this is set (created via `meetingApi.createMeeting`). */
  meetingName: string | null;
  /** How often `MediaRecorder` emits a segment. Defaults to 45s. */
  timesliceMs?: number;
  /** Called whenever a chunk permanently fails after `MAX_AUTO_RETRIES`, or
   * mic access fails. Non-fatal to the recording itself. */
  onError?: (error: Error) => void;
}

export interface UseMeetingRecorderReturn {
  status: RecorderStatus;
  isMuted: boolean;
  /** Seconds elapsed since `start()`, paused time excluded. */
  elapsedSeconds: number;
  /** Segments written to the local queue but not yet confirmed uploaded. */
  pendingUploadCount: number;
  /** Whole minutes captured so far, for "N minutes recorded" copy. */
  minutesRecorded: number;
  /** Set on mount (and after `stop()`) if the local queue holds unflushed
   * segments belonging to a meeting other than an active recording. */
  resumableMeeting: ResumableMeeting | null;
  start: () => Promise<void>;
  pause: () => void;
  resume: () => Promise<void>;
  toggleMute: () => void;
  stop: () => Promise<void>;
  /** Re-attempts upload for every queued segment of a past meeting without
   * starting a new recording (used from the resume-recovery prompt). */
  resumeQueuedUploads: (meetingName: string) => Promise<void>;
  /** Drops all queued segments for a meeting — used when the user declines
   * to resume an interrupted session. */
  discardQueuedUploads: (meetingName: string) => Promise<void>;
}

export function useMeetingRecorder(options: UseMeetingRecorderOptions): UseMeetingRecorderReturn {
  const { meetingName, timesliceMs = DEFAULT_TIMESLICE_MS, onError } = options;

  const [status, setStatus] = useState<RecorderStatus>('idle');
  const [isMuted, setIsMuted] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [pendingUploadCount, setPendingUploadCount] = useState(0);
  const [resumableMeeting, setResumableMeeting] = useState<ResumableMeeting | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const sequenceRef = useRef(0);
  const segmentStartedAtRef = useRef<number>(0);
  const timerIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const elapsedBeforePauseRef = useRef(0);
  const runStartedAtRef = useRef<number>(0);
  const pendingTimersRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const refreshPendingCount = useCallback(async () => {
    if (!meetingName) return;
    try {
      const queued = await getQueuedChunksForMeeting(meetingName);
      setPendingUploadCount(queued.length);
    } catch {
      // IndexedDB unavailable — pending count just stays at its last value.
    }
  }, [meetingName]);

  // On mount, check whether a previous session left unflushed segments.
  useEffect(() => {
    let cancelled = false;
    findResumableMeeting().then((found) => {
      if (!cancelled) setResumableMeeting(found);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const attemptUpload = useCallback(
    async (record: QueuedChunkRecord) => {
      try {
        const audioB64 = await blobToBase64(record.blob);
        await uploadChunk({
          meeting: record.meeting,
          sequence: record.sequence,
          clientStartedAt: record.clientStartedAt,
          durationSeconds: record.durationSeconds,
          audioB64: `data:${record.mimeType};base64,${audioB64}`,
        });
        await deleteQueuedChunk(record.id);
        pendingTimersRef.current.delete(record.id);
        await refreshPendingCount();
      } catch (error) {
        const nextRetryCount = record.retryCount + 1;
        if (nextRetryCount > MAX_AUTO_RETRIES) {
          onErrorRef.current?.(
            error instanceof Error ? error : new Error('Some of this recording could not be saved'),
          );
          return;
        }
        const updated: QueuedChunkRecord = { ...record, retryCount: nextRetryCount };
        try {
          await putQueuedChunk(updated);
        } catch {
          // Best-effort persistence; retry timer still fires from memory.
        }
        const delay = computeBackoffDelayMs(nextRetryCount);
        const timer = setTimeout(() => {
          attemptUpload(updated);
        }, delay);
        pendingTimersRef.current.set(record.id, timer);
      }
    },
    [refreshPendingCount],
  );

  const enqueueSegment = useCallback(
    async (blob: Blob, mimeType: string, clientStartedAt: string, durationSeconds: number) => {
      if (!meetingName) return;
      const sequence = sequenceRef.current;
      sequenceRef.current += 1;
      const record: QueuedChunkRecord = {
        id: chunkRecordId(meetingName, sequence),
        meeting: meetingName,
        sequence,
        blob,
        mimeType,
        clientStartedAt,
        durationSeconds,
        retryCount: 0,
        createdAt: Date.now(),
      };
      try {
        await putQueuedChunk(record);
      } catch (error) {
        onErrorRef.current?.(
          error instanceof Error ? error : new Error('Failed to save part of the recording locally'),
        );
      }
      await refreshPendingCount();
      void attemptUpload(record);
    },
    [meetingName, attemptUpload, refreshPendingCount],
  );

  const attachRecorderHandlers = useCallback(
    (recorder: MediaRecorder, mimeType: string) => {
      recorder.ondataavailable = (event: BlobEvent) => {
        if (!event.data || event.data.size === 0) return;
        const durationSeconds = (Date.now() - segmentStartedAtRef.current) / 1000;
        const clientStartedAt = new Date(segmentStartedAtRef.current).toISOString();
        segmentStartedAtRef.current = Date.now();
        void enqueueSegment(event.data, mimeType, clientStartedAt, durationSeconds);
      };
    },
    [enqueueSegment],
  );

  const stopTimer = useCallback(() => {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
  }, []);

  const startTimer = useCallback(() => {
    stopTimer();
    runStartedAtRef.current = Date.now();
    timerIntervalRef.current = setInterval(() => {
      const runningSeconds = (Date.now() - runStartedAtRef.current) / 1000;
      setElapsedSeconds(Math.floor(elapsedBeforePauseRef.current + runningSeconds));
    }, 1000);
  }, [stopTimer]);

  const createRecorder = useCallback(
    (stream: MediaStream) => {
      const mimeType =
        typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported?.('audio/webm')
          ? 'audio/webm'
          : 'audio/webm';
      const recorder = new MediaRecorder(stream, { mimeType });
      attachRecorderHandlers(recorder, mimeType);
      segmentStartedAtRef.current = Date.now();
      recorder.start(timesliceMs);
      recorderRef.current = recorder;
    },
    [attachRecorderHandlers, timesliceMs],
  );

  const start = useCallback(async () => {
    if (!meetingName) {
      throw new Error('Cannot start recording before a meeting has been created');
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      sequenceRef.current = 0;
      elapsedBeforePauseRef.current = 0;
      setElapsedSeconds(0);
      setIsMuted(false);
      createRecorder(stream);
      setStatus('recording');
      startTimer();
    } catch (error) {
      onErrorRef.current?.(
        error instanceof Error ? error : new Error('Microphone access failed'),
      );
      throw error;
    }
  }, [meetingName, createRecorder, startTimer]);

  const pause = useCallback(() => {
    if (status !== 'recording' || !recorderRef.current) return;
    // Flush the in-flight partial segment for this span, then leave the
    // stream open so resume() can start a fresh MediaRecorder instantly.
    recorderRef.current.stop();
    recorderRef.current = null;
    elapsedBeforePauseRef.current = elapsedSeconds;
    stopTimer();
    setStatus('paused');
  }, [status, elapsedSeconds, stopTimer]);

  const resume = useCallback(async () => {
    if (status !== 'paused') return;
    let stream = streamRef.current;
    if (!stream || stream.getAudioTracks().every((track) => track.readyState === 'ended')) {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
    }
    if (isMuted) {
      stream.getAudioTracks().forEach((track) => {
        track.enabled = false;
      });
    }
    createRecorder(stream);
    setStatus('recording');
    startTimer();
  }, [status, isMuted, createRecorder, startTimer]);

  const toggleMute = useCallback(() => {
    const stream = streamRef.current;
    if (!stream) return;
    setIsMuted((prev) => {
      const next = !prev;
      stream.getAudioTracks().forEach((track) => {
        track.enabled = !next;
      });
      return next;
    });
  }, []);

  const stop = useCallback(async () => {
    if (status === 'idle' || status === 'stopped') return;
    stopTimer();
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      await new Promise<void>((resolve) => {
        const recorder = recorderRef.current;
        if (!recorder) {
          resolve();
          return;
        }
        recorder.addEventListener('stop', () => resolve(), { once: true });
        recorder.stop();
      });
    }
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    for (const timer of pendingTimersRef.current.values()) {
      clearTimeout(timer);
    }
    pendingTimersRef.current.clear();
    setStatus('stopped');
  }, [status, stopTimer]);

  const resumeQueuedUploads = useCallback(
    async (targetMeeting: string) => {
      const queued = await getQueuedChunksForMeeting(targetMeeting);
      await Promise.all(queued.map((record) => attemptUpload(record)));
      const found = await findResumableMeeting();
      setResumableMeeting(found);
    },
    [attemptUpload],
  );

  const discardQueuedUploads = useCallback(async (targetMeeting: string) => {
    const queued = await getQueuedChunksForMeeting(targetMeeting);
    await Promise.all(queued.map((record) => deleteQueuedChunk(record.id)));
    const found = await findResumableMeeting();
    setResumableMeeting(found);
  }, []);

  useEffect(() => {
    void refreshPendingCount();
  }, [refreshPendingCount]);

  // Cleanup on unmount: stop any live stream/timers, but never touch the
  // IndexedDB queue — those segments still need to reach the server.
  useEffect(() => {
    return () => {
      stopTimer();
      recorderRef.current?.state !== 'inactive' && recorderRef.current?.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      for (const timer of pendingTimersRef.current.values()) {
        clearTimeout(timer);
      }
    };
  }, [stopTimer]);

  return {
    status,
    isMuted,
    elapsedSeconds,
    pendingUploadCount,
    minutesRecorded: Math.floor(elapsedSeconds / 60),
    resumableMeeting,
    start,
    pause,
    resume,
    toggleMute,
    stop,
    resumeQueuedUploads,
    discardQueuedUploads,
  };
}
