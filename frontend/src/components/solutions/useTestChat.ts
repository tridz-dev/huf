import { useCallback, useRef, useState } from 'react';
import { simulateRoute } from '@/services/solutionsApi';
import type { RouteDecision, SimulateRequest } from '@/types/solutions';

export type TraceLine = { k: 'win' | 'skip' | 'info'; t: string };

export interface ChatMessage {
  id: number;
  from: 'me' | 'bot' | 'sys';
  text: string;
  /** Caption above a bot bubble, e.g. "Support desk · Care agent". */
  who?: string;
}

export interface ChatPin {
  solution: string;
  hoursLeft: number;
}

interface Options {
  gateway: string;
  solutionLabels?: Record<string, string>;
}

const DEFAULT_PIN_HOURS = 24;

function hoursFromExpiry(expiresAt: string | undefined): number {
  if (!expiresAt) return DEFAULT_PIN_HOURS;
  const ms = Date.parse(expiresAt.replace(' ', 'T'));
  if (Number.isNaN(ms)) return DEFAULT_PIN_HOURS;
  return Math.max(0, Math.ceil((ms - Date.now()) / 3_600_000));
}

/**
 * Simulation-only chat state. Every send calls simulate_route; nothing real is
 * sent and no agent is run. The pin is held locally and fed back each call.
 */
export function useTestChat({ gateway, solutionLabels }: Options) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [trace, setTrace] = useState<TraceLine[]>([]);
  const [pin, setPin] = useState<ChatPin | null>(null);
  const [triagePending, setTriagePending] = useState(false);
  const [keywordBeatsPin, setKeywordBeatsPin] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [seen, setSeen] = useState<string[]>([]);
  const nextId = useRef(1);

  const labelOf = useCallback(
    (name: string | null | undefined) => (name ? (solutionLabels?.[name] ?? name) : ''),
    [solutionLabels],
  );

  const push = useCallback((m: Omit<ChatMessage, 'id'>) => {
    setMessages((prev) => [...prev, { ...m, id: nextId.current++ }]);
  }, []);

  const send = useCallback(
    async (text: string, ref?: string) => {
      const body = text.trim();
      if ((!body && !ref) || loading) return;
      push({ from: 'me', text: ref ? `(taps ad, tag ${ref})` : body });
      setError(null);
      setLoading(true);
      const request: SimulateRequest = {
        gateway,
        text: body,
        state: {
          ...(pin ? { pin: { solution: pin.solution, hours_left: pin.hoursLeft } } : {}),
          ...(triagePending ? { triage_pending: true } : {}),
        },
        keyword_beats_pin: keywordBeatsPin,
      };
      if (ref) request.ref = ref;
      try {
        const d: RouteDecision = await simulateRoute(request);
        setTrace(d.trace ?? []);
        setTriagePending(d.reason === 'triage_prompt');
        if (d.pin) {
          setPin({ solution: d.pin.solution, hoursLeft: hoursFromExpiry(d.pin.expires_at) });
        }
        if (d.solution) setSeen((prev) => (prev.includes(d.solution!) ? prev : [...prev, d.solution!]));
        if (d.reply_text) {
          push({ from: 'bot', text: d.reply_text });
        } else if (d.solution) {
          const target = d.agent || d.flow;
          const caption = target ? `${labelOf(d.solution)} · ${target}` : labelOf(d.solution);
          push({ from: 'bot', text: `Routed to ${labelOf(d.solution)}`, who: caption });
        } else {
          push({ from: 'sys', text: 'No solution matched this message' });
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not simulate this message');
      } finally {
        setLoading(false);
      }
    },
    [gateway, keywordBeatsPin, labelOf, loading, pin, push, triagePending],
  );

  const expire = useCallback(() => {
    setPin((p) => (p ? { ...p, hoursLeft: 0 } : p));
    setTrace([{ k: 'info', t: '25 hours passed. The pin expired, so the next message is routed from scratch.' }]);
  }, []);

  const handOff = useCallback(
    (to: string) => {
      if (!pin || !to || to === pin.solution) return;
      const from = labelOf(pin.solution);
      const target = labelOf(to);
      setPin({ solution: to, hoursLeft: DEFAULT_PIN_HOURS });
      setTriagePending(false);
      push({ from: 'sys', text: `Handed off from ${from} to ${target}` });
      setTrace([{ k: 'win', t: `Handoff rewrote the pin: ${from} → ${target}` }]);
    },
    [labelOf, pin, push],
  );

  const clear = useCallback(() => {
    setMessages([]);
    setTrace([]);
    setPin(null);
    setTriagePending(false);
    setError(null);
  }, []);

  const handOffOptions = Array.from(new Set([...Object.keys(solutionLabels ?? {}), ...seen])).filter(
    (s) => s !== pin?.solution,
  );

  return {
    messages, trace, pin, triagePending, keywordBeatsPin, setKeywordBeatsPin,
    loading, error, send, expire, handOff, clear, handOffOptions, labelOf,
  };
}
