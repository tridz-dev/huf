import { useCallback, useEffect, useRef, useState } from 'react';
import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

export type VoiceCallStatus = 'idle' | 'connecting' | 'live' | 'error' | 'ended';

export interface TranscriptTurn {
  id: string;
  role: 'user' | 'agent';
  text: string;
  /** True once the turn is known-final (no more deltas will arrive for it). */
  final: boolean;
}

export interface UseVoiceCallResult {
  status: VoiceCallStatus;
  error: string | null;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  mute: () => void;
  unmute: () => void;
  isMuted: boolean;
  transcript: TranscriptTurn[];
}

/**
 * Real response shapes returned by `huf.ai.voice.api.start_session`
 * (see huf/ai/voice/README.md — this is the frozen contract).
 */
interface ElevenLabsStartSessionResult {
  engine: 'elevenlabs_convai';
  signed_url: string;
  agent_id: string;
  conversation_id?: string;
  dynamic_variables?: Record<string, string>;
}

interface LitellmRealtimeStartSessionResult {
  engine: 'litellm_realtime';
  session_id: string;
  sidecar_ws_path: string;
  conversation_id?: string;
}

type StartSessionResult = ElevenLabsStartSessionResult | LitellmRealtimeStartSessionResult;

// PCM16 mono @ 16kHz is ElevenLabs' documented default input format for the
// browser Conversational AI WebSocket path. If a deployment overrides the
// agent's input audio format, this capture rate would need to follow suit.
const CAPTURE_SAMPLE_RATE = 16000;

/**
 * Downsample/convert a Float32 audio buffer (native AudioContext sample rate)
 * into 16-bit PCM at CAPTURE_SAMPLE_RATE, little-endian, mono. Conservative,
 * dependency-free implementation — good enough for a mic capture path, not a
 * general-purpose resampler.
 */
function floatTo16kPcm16(input: Float32Array, inputSampleRate: number): ArrayBuffer {
  const ratio = inputSampleRate / CAPTURE_SAMPLE_RATE;
  const outLength = Math.floor(input.length / ratio);
  const out = new Int16Array(outLength);
  for (let i = 0; i < outLength; i += 1) {
    const srcIndex = Math.floor(i * ratio);
    const sample = Math.max(-1, Math.min(1, input[srcIndex]));
    out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return out.buffer;
}

let transcriptIdCounter = 0;

/** Dependency-free id generator — good enough for keying local transcript turns. */
function nextTranscriptId(): string {
  transcriptIdCounter += 1;
  return `turn-${Date.now()}-${transcriptIdCounter}`;
}

function base64FromArrayBuffer(buffer: ArrayBuffer): string {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * useVoiceCall — opens a live voice call against an Agent's configured voice
 * engine, per the contract in huf/ai/voice/api.py and huf/ai/voice/README.md.
 *
 * Deliberately framework-agnostic in its internals (no JSX): this is meant to
 * be a clean reference for the wire protocol even for callers that don't use
 * React.
 *
 * Known assumptions (flagged, not silently guessed):
 * - ElevenLabs: sends `conversation_initiation_client_data` as the first
 *   WebSocket message when `dynamic_variables` are present, per ElevenLabs'
 *   documented Conversational AI WebSocket client-data message shape.
 * - ElevenLabs: captures mic audio as PCM16 mono @ 16kHz, base64-encoded into
 *   `{"user_audio_chunk": "<base64>"}` messages — ElevenLabs' documented
 *   default input format for the browser client path.
 * - litellm_realtime: the sidecar is assumed reverse-proxied at the SAME
 *   origin as the frontend under `sidecar_ws_path`. If no separate sidecar
 *   origin is configured for a given deployment, this constructs
 *   `wss://<current host><sidecar_ws_path>`. No frontend env var for a
 *   sidecar base URL was found in this repo at implementation time — if one
 *   is added later (e.g. VITE_REALTIME_WS_BASE), this should read it first.
 *
 * Transcript event shapes (NOT re-verified against live provider docs in
 * this pass — same "flagged, not silently guessed" convention as above):
 * - ElevenLabs: `{type: "user_transcript", user_transcription_event:
 *   {user_transcript}}` for recognized user speech, and `{type:
 *   "agent_response", agent_response_event: {agent_response}}` for the
 *   agent's spoken response — both arrive as single, already-final frames
 *   (no delta/done split, per ElevenLabs' documented Conversational AI
 *   WebSocket event shapes). An `interruption` event type likely also
 *   exists but was not observed in this pass, so it is not handled.
 * - litellm_realtime: `response.audio_transcript.delta` (`{delta}`, partial)
 *   and `response.audio_transcript.done` (`{transcript}`, final) for the
 *   agent's spoken text — this matches exactly what the sidecar itself
 *   parses in `_try_persist_agent_turn` (huf/ai/voice/sidecar/app.py), so
 *   confidence here is high. User-side transcription
 *   (`conversation.item.input_audio_transcription.completed`) is NOT
 *   implemented: the sidecar never sends a `session.update` enabling input
 *   transcription, so there is no evidence the provider ever emits it for
 *   these sessions — left as a documented gap rather than fabricated.
 */
export function useVoiceCall(
  agentName: string,
  conversationId: string | undefined,
): UseVoiceCallResult {
  const [status, setStatus] = useState<VoiceCallStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [isMuted, setIsMuted] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const engineRef = useRef<StartSessionResult['engine'] | null>(null);
  const isMutedRef = useRef(false);
  const playbackTimeRef = useRef(0);
  // Tracks the latest status so close/error listeners registered at start()
  // time can check "were we actually live" without stale closures.
  const statusRef = useRef(status);
  // litellm_realtime streams the agent's transcript as delta/done events
  // with no turn id of its own to key off — this tracks the in-progress
  // turn's locally-generated id so successive deltas update the same entry,
  // and is cleared on "done" so the next response starts a fresh turn.
  const streamingAgentTurnIdRef = useRef<string | null>(null);

  useEffect(() => {
    isMutedRef.current = isMuted;
  }, [isMuted]);

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  const teardownAudio = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current.onaudioprocess = null;
      processorRef.current = null;
    }
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }
    if (mediaStreamRef.current) {
      for (const track of mediaStreamRef.current.getTracks()) {
        track.stop();
      }
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close().catch(() => undefined);
      audioContextRef.current = null;
    }
    if (playbackContextRef.current) {
      void playbackContextRef.current.close().catch(() => undefined);
      playbackContextRef.current = null;
    }
    playbackTimeRef.current = 0;
  }, []);

  const closeSocket = useCallback(() => {
    if (wsRef.current) {
      const ws = wsRef.current;
      wsRef.current = null;
      // Avoid firing onclose/onerror handlers after a deliberate stop().
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      try {
        ws.close();
      } catch {
        // Already closed/closing — nothing to do.
      }
    }
  }, []);

  const playIncomingPcm16 = useCallback((buffer: ArrayBuffer, sampleRate = CAPTURE_SAMPLE_RATE) => {
    if (!playbackContextRef.current) {
      return;
    }
    const ctx = playbackContextRef.current;
    const pcm16 = new Int16Array(buffer);
    const float32 = new Float32Array(pcm16.length);
    for (let i = 0; i < pcm16.length; i += 1) {
      float32[i] = pcm16[i] / 0x8000;
    }
    const audioBuffer = ctx.createBuffer(1, float32.length, sampleRate);
    audioBuffer.copyToChannel(float32, 0);
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    const startAt = Math.max(ctx.currentTime, playbackTimeRef.current);
    source.start(startAt);
    playbackTimeRef.current = startAt + audioBuffer.duration;
  }, []);

  /**
   * Insert or update one transcript turn by id. `append: true` concatenates
   * onto the existing turn's text (streaming deltas); otherwise `text`
   * replaces it outright (a final/complete transcript).
   */
  const upsertTranscriptTurn = useCallback(
    (id: string, role: TranscriptTurn['role'], text: string, final: boolean, append = false) => {
      setTranscript((prev) => {
        const index = prev.findIndex((turn) => turn.id === id);
        if (index === -1) {
          return [...prev, { id, role, text, final }];
        }
        const next = [...prev];
        const existing = next[index];
        next[index] = { ...existing, text: append ? existing.text + text : text, final };
        return next;
      });
    },
    [],
  );

  const startMicCapture = useCallback(
    async (onFrame: (pcm16: ArrayBuffer) => void) => {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const AudioContextCtor = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const audioContext = new AudioContextCtor();
      audioContextRef.current = audioContext;

      const source = audioContext.createMediaStreamSource(stream);
      sourceNodeRef.current = source;

      // ScriptProcessorNode is deprecated but remains the most broadly
      // supported low-latency capture path across browsers without shipping
      // a separate AudioWorklet module; kept deliberately simple here.
      const bufferSize = 4096;
      const processor = audioContext.createScriptProcessor(bufferSize, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (event) => {
        if (isMutedRef.current) {
          return;
        }
        const input = event.inputBuffer.getChannelData(0);
        const pcm16 = floatTo16kPcm16(input, audioContext.sampleRate);
        onFrame(pcm16);
      };

      source.connect(processor);
      // Some browsers require the processor to be connected to a
      // destination to keep firing onaudioprocess; route to a silent gain
      // so we don't actually play the mic back to the user.
      const silentGain = audioContext.createGain();
      silentGain.gain.value = 0;
      processor.connect(silentGain);
      silentGain.connect(audioContext.destination);
    },
    [],
  );

  const stop = useCallback(async () => {
    const engine = engineRef.current;
    const sessionId = sessionIdRef.current;

    closeSocket();
    teardownAudio();

    // ElevenLabs has no server-side session to end (base-class no-op per the
    // README) — only litellm_realtime carries a real session_id to release.
    if (engine === 'litellm_realtime' && sessionId) {
      try {
        await call.post('huf.ai.voice.api.end_session', {
          agent: agentName,
          session_id: sessionId,
        });
      } catch {
        // Best-effort — the call is already torn down locally either way.
      }
    }

    sessionIdRef.current = null;
    engineRef.current = null;
    setIsMuted(false);
    setStatus('ended');
  }, [agentName, closeSocket, teardownAudio]);

  const handleTransportError = useCallback(
    (message: string) => {
      closeSocket();
      teardownAudio();
      sessionIdRef.current = null;
      engineRef.current = null;
      setError(message);
      setStatus('error');
    },
    [closeSocket, teardownAudio],
  );

  const start = useCallback(async () => {
    if (status === 'connecting' || status === 'live') {
      return;
    }
    setError(null);
    setStatus('connecting');
    setTranscript([]);
    streamingAgentTurnIdRef.current = null;

    let result: StartSessionResult;
    try {
      const response = await call.post('huf.ai.voice.api.start_session', {
        agent: agentName,
        conversation_id: conversationId,
      });
      result = (response?.message ?? response) as StartSessionResult;
    } catch (err) {
      setError(getFrappeErrorMessage(err) || 'Failed to start voice call');
      setStatus('error');
      return;
    }

    engineRef.current = result.engine;

    try {
      // Playback context is created up front so incoming frames can be
      // scheduled as soon as they arrive, independent of mic capture.
      const AudioContextCtor = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      playbackContextRef.current = new AudioContextCtor();

      if (result.engine === 'elevenlabs_convai') {
        const ws = new WebSocket(result.signed_url);
        wsRef.current = ws;

        ws.addEventListener('open', () => {
          if (result.dynamic_variables) {
            // ElevenLabs Conversational AI: the client-data message must be
            // the first frame sent after the socket opens.
            ws.send(
              JSON.stringify({
                type: 'conversation_initiation_client_data',
                dynamic_variables: result.dynamic_variables,
              }),
            );
          }

          startMicCapture((pcm16) => {
            if (ws.readyState !== WebSocket.OPEN) {
              return;
            }
            ws.send(
              JSON.stringify({
                user_audio_chunk: base64FromArrayBuffer(pcm16),
              }),
            );
          }).catch((err) => {
            handleTransportError(err instanceof Error ? err.message : 'Microphone access failed');
          });

          setStatus('live');
        });

        ws.addEventListener('message', (event) => {
          if (typeof event.data !== 'string') {
            return;
          }
          try {
            const parsed = JSON.parse(event.data) as {
              type?: string;
              audio_event?: { audio_base_64?: string };
              user_transcription_event?: { user_transcript?: string };
              agent_response_event?: { agent_response?: string };
            };
            const base64Audio = parsed?.audio_event?.audio_base_64;
            if (parsed?.type === 'audio' && base64Audio) {
              const binary = atob(base64Audio);
              const bytes = new Uint8Array(binary.length);
              for (let i = 0; i < binary.length; i += 1) {
                bytes[i] = binary.charCodeAt(i);
              }
              playIncomingPcm16(bytes.buffer);
            } else if (parsed?.type === 'user_transcript') {
              const text = parsed.user_transcription_event?.user_transcript;
              if (text) {
                upsertTranscriptTurn(nextTranscriptId(), 'user', text, true);
              }
            } else if (parsed?.type === 'agent_response') {
              const text = parsed.agent_response_event?.agent_response;
              if (text) {
                upsertTranscriptTurn(nextTranscriptId(), 'agent', text, true);
              }
            }
            // Other control frames (interruption, ping, etc.) are still
            // ignored — this hook only handles audio + transcript text.
          } catch {
            // Malformed/non-JSON frames are ignored.
          }
        });

        ws.addEventListener('close', () => {
          if (statusRef.current === 'live' || statusRef.current === 'connecting') {
            handleTransportError('Voice call connection closed unexpectedly');
          }
        });
        ws.addEventListener('error', () => {
          handleTransportError('Voice call connection error');
        });
      } else {
        sessionIdRef.current = result.session_id;

        // No frontend env var for a sidecar base URL exists in this repo at
        // the time this was written — assumes the sidecar is reverse-proxied
        // at the same origin as the frontend. Adjust per-deployment if the
        // sidecar is hosted separately.
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const sidecarUrl = `${wsProtocol}//${window.location.host}${result.sidecar_ws_path}`;
        const ws = new WebSocket(sidecarUrl);
        wsRef.current = ws;

        ws.addEventListener('open', () => {
          startMicCapture((pcm16) => {
            if (ws.readyState !== WebSocket.OPEN) {
              return;
            }
            ws.send(pcm16);
          }).catch((err) => {
            handleTransportError(err instanceof Error ? err.message : 'Microphone access failed');
          });

          setStatus('live');
        });

        ws.addEventListener('message', (event) => {
          if (event.data instanceof ArrayBuffer) {
            playIncomingPcm16(event.data);
            return;
          }
          if (event.data instanceof Blob) {
            void event.data.arrayBuffer().then((buffer) => playIncomingPcm16(buffer));
            return;
          }
          if (typeof event.data !== 'string') {
            return;
          }
          // String frames are JSON control/status/transcript messages
          // relayed from the OpenAI Realtime API by the sidecar (see
          // huf/ai/voice/sidecar/app.py's own `_try_persist_agent_turn`,
          // which parses this same wire format for `response.audio_
          // transcript.done`). Defensive try/catch: a parse failure here
          // must never affect the live audio path above.
          try {
            const parsed = JSON.parse(event.data) as {
              type?: string;
              delta?: string;
              transcript?: string;
              item_id?: string;
              response_id?: string;
            };
            if (parsed?.type === 'response.audio_transcript.delta' && parsed.delta) {
              const id = streamingAgentTurnIdRef.current ?? parsed.item_id ?? parsed.response_id ?? nextTranscriptId();
              streamingAgentTurnIdRef.current = id;
              upsertTranscriptTurn(id, 'agent', parsed.delta, false, true);
            } else if (parsed?.type === 'response.audio_transcript.done') {
              const id = streamingAgentTurnIdRef.current ?? parsed.item_id ?? parsed.response_id ?? nextTranscriptId();
              upsertTranscriptTurn(id, 'agent', parsed.transcript ?? '', true, false);
              streamingAgentTurnIdRef.current = null;
            }
            // `conversation.item.input_audio_transcription.completed` (user
            // speech) is deliberately NOT handled here — the sidecar never
            // sends a session.update enabling input transcription, so there
            // is no evidence the provider emits it for these sessions. Left
            // as a documented gap rather than fabricated.
          } catch {
            // Non-JSON/malformed string frames are ignored.
          }
        });

        ws.addEventListener('close', () => {
          if (statusRef.current === 'live' || statusRef.current === 'connecting') {
            handleTransportError('Voice call connection closed unexpectedly');
          }
        });
        ws.addEventListener('error', () => {
          handleTransportError('Voice call connection error');
        });
      }
    } catch (err) {
      handleTransportError(err instanceof Error ? err.message : 'Failed to open voice call');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentName, conversationId, status, startMicCapture, playIncomingPcm16, handleTransportError, upsertTranscriptTurn]);

  const mute = useCallback(() => setIsMuted(true), []);
  const unmute = useCallback(() => setIsMuted(false), []);

  useEffect(
    () => () => {
      closeSocket();
      teardownAudio();
    },
    [closeSocket, teardownAudio],
  );

  return { status, error, start, stop, mute, unmute, isMuted, transcript };
}
