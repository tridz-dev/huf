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
 *   - `shareTabAudio()` / `tabAudioActive` — explicit opt-in add-on that
 *     mixes browser/tab audio (other participants, e.g. a Google Meet tab)
 *     into the mic recording via `getDisplayMedia` + Web Audio API. Must be
 *     called from a real user gesture (click handler) — cannot auto-start.
 *     `tabAudioActive` flips to `false` if the user stops sharing via the
 *     browser's native UI; callers should show a banner when that happens.
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

/** Highest `sequence` already queued in IndexedDB for a meeting, or -1 if
 * none. Used to seed `sequenceRef` on `start()` so a resumed session never
 * reuses a sequence number that still has a queued (unconfirmed) record —
 * reusing one would overwrite that record (same `${meeting}:${sequence}`
 * primary key) and send a duplicate sequence to the backend. */
export async function getMaxQueuedSequence(meeting: string): Promise<number> {
  const queued = await getQueuedChunksForMeeting(meeting);
  return queued.reduce((max, record) => Math.max(max, record.sequence), -1);
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
  /** True once `shareTabAudio()` has successfully mixed in a live
   * display-audio track; false initially and after that track ends (either
   * because the user stopped sharing, or `stop()` was called). Callers can
   * show a "tab audio stopped" banner when this flips from true to false
   * while `status === 'recording'`. */
  tabAudioActive: boolean;
  start: () => Promise<void>;
  pause: () => void;
  resume: () => Promise<void>;
  toggleMute: () => void;
  stop: () => Promise<void>;
  /** Explicit opt-in add-on: prompts the user (via `getDisplayMedia`, which
   * requires a real user gesture — call this only from a click handler) to
   * share a browser tab/window, discards its video track immediately, and
   * mixes its audio into the already-running mic recording via a Web Audio
   * `AudioContext` graph. Reports unsupported browsers / denied permission
   * through `onError` rather than throwing into the caller's event handler
   * uncaught — callers may still `await` it to know when it settles. */
  shareTabAudio: () => Promise<void>;
  /** Re-attempts upload for every queued segment of a past meeting without
   * starting a new recording (used from the resume-recovery prompt). */
  resumeQueuedUploads: (meetingName: string, options?: { manual?: boolean }) => Promise<void>;
  /** Drops all queued segments for a meeting — used when the user declines
   * to resume an interrupted session. */
  discardQueuedUploads: (meetingName: string) => Promise<void>;
}

/** Feature-detects tab/window audio capture. Safari doesn't support
 * `getDisplayMedia` audio capture at all; Firefox supports display capture
 * but never offers tab audio. There's no reliable static capability check
 * for "will an audio track actually come back", so this only guards against
 * the API being entirely absent — the real signal is whether `shareTabAudio`
 * gets back a stream with an audio track. */
function isDisplayAudioCaptureSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getDisplayMedia === 'function'
  );
}

export function useMeetingRecorder(options: UseMeetingRecorderOptions): UseMeetingRecorderReturn {
  const { meetingName, timesliceMs = DEFAULT_TIMESLICE_MS, onError } = options;

  const [status, setStatus] = useState<RecorderStatus>('idle');
  const [isMuted, setIsMuted] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [pendingUploadCount, setPendingUploadCount] = useState(0);
  const [resumableMeeting, setResumableMeeting] = useState<ResumableMeeting | null>(null);
  const [tabAudioActive, setTabAudioActive] = useState(false);

  // Three separate stream refs, deliberately not collapsed into one:
  //  - micStreamRef: raw `getUserMedia` mic capture. Mute toggles tracks
  //    only on this stream, so muting yourself never silences tab audio.
  //  - displayStreamRef: raw `getDisplayMedia` capture, video track
  //    discarded immediately after grant — only the audio track is kept.
  //  - mixedStreamRef: the `AudioContext` destination stream that actually
  //    feeds `MediaRecorder`. Built from mic (+ display, once shared) via
  //    two `MediaStreamAudioSourceNode`s into one
  //    `MediaStreamAudioDestinationNode`.
  const micStreamRef = useRef<MediaStream | null>(null);
  const displayStreamRef = useRef<MediaStream | null>(null);
  const mixedStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const micSourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const displaySourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const destinationNodeRef = useRef<MediaStreamAudioDestinationNode | null>(null);
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

  /** Ensures the AudioContext + destination node exist and the mic stream
   * is wired into it. Safe to call more than once — reuses the existing
   * graph rather than rebuilding it, so `shareTabAudio()` can add a second
   * source into an already-running graph. */
  const ensureAudioGraph = useCallback((micStream: MediaStream) => {
    if (!audioContextRef.current) {
      const AudioContextCtor =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      audioContextRef.current = new AudioContextCtor();
    }
    const audioContext = audioContextRef.current;
    if (!destinationNodeRef.current) {
      destinationNodeRef.current = audioContext.createMediaStreamDestination();
      mixedStreamRef.current = destinationNodeRef.current.stream;
    }
    if (!micSourceNodeRef.current) {
      micSourceNodeRef.current = audioContext.createMediaStreamSource(micStream);
      micSourceNodeRef.current.connect(destinationNodeRef.current);
    }
    return { audioContext, destination: destinationNodeRef.current };
  }, []);

  const teardownAudioGraph = useCallback(() => {
    micSourceNodeRef.current?.disconnect();
    micSourceNodeRef.current = null;
    displaySourceNodeRef.current?.disconnect();
    displaySourceNodeRef.current = null;
    destinationNodeRef.current = null;
    mixedStreamRef.current = null;
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      void audioContextRef.current.close().catch(() => {});
    }
    audioContextRef.current = null;
  }, []);

  const start = useCallback(async () => {
    if (!meetingName) {
      throw new Error('Cannot start recording before a meeting has been created');
    }
    try {
      const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = micStream;
      const { destination } = ensureAudioGraph(micStream);
      // Seed the sequence counter from whatever is already queued for this
      // meeting in IndexedDB (e.g. a resumed session after a reload) so new
      // segments never reuse a sequence number a still-queued record holds.
      let nextSequence = 0;
      try {
        nextSequence = (await getMaxQueuedSequence(meetingName)) + 1;
      } catch {
        // IndexedDB unavailable — fall back to starting at 0.
      }
      sequenceRef.current = nextSequence;
      elapsedBeforePauseRef.current = 0;
      setElapsedSeconds(0);
      setIsMuted(false);
      createRecorder(destination.stream);
      setStatus('recording');
      startTimer();
    } catch (error) {
      onErrorRef.current?.(
        error instanceof Error ? error : new Error('Microphone access failed'),
      );
      throw error;
    }
  }, [meetingName, ensureAudioGraph, createRecorder, startTimer]);

  const shareTabAudio = useCallback(async () => {
    if (!isDisplayAudioCaptureSupported()) {
      onErrorRef.current?.(
        new Error('Sharing tab audio is not supported in this browser'),
      );
      return;
    }
    try {
      const displayStream = await navigator.mediaDevices.getDisplayMedia({
        audio: true,
        video: true,
      });
      // Video is only requested because some browsers require it to be
      // present to grant `getDisplayMedia` at all — discard it immediately,
      // only the audio track is needed.
      displayStream.getVideoTracks().forEach((track) => track.stop());
      const audioTracks = displayStream.getAudioTracks();
      if (audioTracks.length === 0) {
        displayStream.getTracks().forEach((track) => track.stop());
        onErrorRef.current?.(
          new Error('The shared tab/window did not include audio — this browser may not support tab audio capture'),
        );
        return;
      }
      if (!micStreamRef.current) {
        // start() hasn't run yet — there's no audio graph to mix into.
        displayStream.getTracks().forEach((track) => track.stop());
        onErrorRef.current?.(new Error('Start recording before sharing tab audio'));
        return;
      }
      const { audioContext, destination } = ensureAudioGraph(micStreamRef.current);
      displaySourceNodeRef.current?.disconnect();
      const displaySource = audioContext.createMediaStreamSource(displayStream);
      displaySource.connect(destination);
      displaySourceNodeRef.current = displaySource;
      displayStreamRef.current = displayStream;
      setTabAudioActive(true);
      audioTracks[0].onended = () => {
        // The user stopped sharing via the browser's native "Stop sharing"
        // UI (or the track otherwise ended). Don't try to silently
        // re-acquire it — surface it so the caller can show a banner;
        // recording continues mic-only.
        setTabAudioActive(false);
        displaySourceNodeRef.current?.disconnect();
        displaySourceNodeRef.current = null;
        displayStreamRef.current?.getTracks().forEach((track) => track.stop());
        displayStreamRef.current = null;
      };
    } catch (error) {
      onErrorRef.current?.(
        error instanceof Error ? error : new Error('Sharing tab audio failed or was denied'),
      );
    }
  }, [ensureAudioGraph]);

  const pause = useCallback(() => {
    if (status !== 'recording' || !recorderRef.current) return;
    // Flush the in-flight partial segment for this span, then leave the
    // streams/audio graph open so resume() can start a fresh MediaRecorder
    // instantly.
    recorderRef.current.stop();
    recorderRef.current = null;
    elapsedBeforePauseRef.current = elapsedSeconds;
    stopTimer();
    setStatus('paused');
  }, [status, elapsedSeconds, stopTimer]);

  const resume = useCallback(async () => {
    if (status !== 'paused') return;
    let micStream = micStreamRef.current;
    // Mic re-acquisition only — display media is intentionally NOT
    // re-acquired here. It can't be silently re-granted (requires a fresh
    // user gesture), so once tab audio stops it stays stopped for the rest
    // of this recording session; the user must call `shareTabAudio()`
    // again explicitly (the graph stays open to allow that).
    if (!micStream || micStream.getAudioTracks().every((track) => track.readyState === 'ended')) {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = micStream;
      // Rebuild the mic source node against the fresh stream.
      micSourceNodeRef.current?.disconnect();
      micSourceNodeRef.current = null;
    }
    const { destination } = ensureAudioGraph(micStream);
    if (isMuted) {
      micStream.getAudioTracks().forEach((track) => {
        track.enabled = false;
      });
    }
    createRecorder(destination.stream);
    setStatus('recording');
    startTimer();
  }, [status, isMuted, ensureAudioGraph, createRecorder, startTimer]);

  const toggleMute = useCallback(() => {
    // Mute targets the mic source track only — never the tab-audio track —
    // so muting yourself never silences the other meeting participants in
    // the recording.
    const micStream = micStreamRef.current;
    if (!micStream) return;
    setIsMuted((prev) => {
      const next = !prev;
      micStream.getAudioTracks().forEach((track) => {
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
    micStreamRef.current?.getTracks().forEach((track) => track.stop());
    micStreamRef.current = null;
    displayStreamRef.current?.getTracks().forEach((track) => track.stop());
    displayStreamRef.current = null;
    teardownAudioGraph();
    setTabAudioActive(false);
    for (const timer of pendingTimersRef.current.values()) {
      clearTimeout(timer);
    }
    pendingTimersRef.current.clear();
    setStatus('stopped');
  }, [status, stopTimer, teardownAudioGraph]);

  const resumeQueuedUploads = useCallback(
    async (targetMeeting: string, options?: { manual?: boolean }) => {
      let queued = await getQueuedChunksForMeeting(targetMeeting);
      if (options?.manual) {
        // A manual resume is an intentional retry request from the user —
        // reset chunks that hit the automatic-retry ceiling (F8) so they
        // aren't permanently stuck in the queue never being retried again.
        queued = await Promise.all(
          queued.map(async (record) => {
            if (record.retryCount < MAX_AUTO_RETRIES) return record;
            const reset: QueuedChunkRecord = { ...record, retryCount: 0 };
            try {
              await putQueuedChunk(reset);
            } catch {
              // Best-effort persistence; retry with in-memory reset regardless.
            }
            return reset;
          }),
        );
      }
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
      micStreamRef.current?.getTracks().forEach((track) => track.stop());
      displayStreamRef.current?.getTracks().forEach((track) => track.stop());
      teardownAudioGraph();
      for (const timer of pendingTimersRef.current.values()) {
        clearTimeout(timer);
      }
    };
  }, [stopTimer, teardownAudioGraph]);

  return {
    status,
    isMuted,
    elapsedSeconds,
    pendingUploadCount,
    minutesRecorded: Math.floor(elapsedSeconds / 60),
    resumableMeeting,
    tabAudioActive,
    start,
    pause,
    resume,
    toggleMute,
    stop,
    shareTabAudio,
    resumeQueuedUploads,
    discardQueuedUploads,
  };
}
