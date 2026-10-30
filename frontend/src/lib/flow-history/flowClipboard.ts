/**
 * Copy and paste of steps, within a flow and across flows. The copy waits in localStorage (shared by every tab of the app), so it
 * survives switching flows. What goes in is stripped of anything private: secrets, tokens, pinned example data. What comes out
 * has new ids and its connections remapped.
 */
import { generateWebhookSecret } from '../flow-graph/flowWebhookUi';
import type { FlowNode } from '../../types/flow.types';
import { cloneSteps, type Graph } from './cloneSteps';

export const CLIPBOARD_KEY = 'huf.flow.clipboard.v1';

export interface ClipboardPayload {
  v: 1;
  kind: 'huf-flow-steps';
  copiedAt: number;
  fromFlowId: string | null;
  nodes: FlowNode[];
  edges: Graph['edges'];
}

/** Field names that hold a credential. A literal value under one of these is never copied. */
const SENSITIVE_KEY = /(secret|token|password|passwd|api[-_ ]?key|authorization|bearer|credential|private[-_ ]?key)/i;
const SECRET_LOOKING_VALUE = /^(bearer|basic)\s+\S+/i;

/** `value` with every literal credential emptied. References (`{"$from": ...}`) point at data, not at a secret, and stay. */
export function stripSecrets<T>(value: T): T {
  const walk = (v: unknown, key?: string): unknown => {
    if (typeof v === 'string') return (key && SENSITIVE_KEY.test(key) && v !== '') || SECRET_LOOKING_VALUE.test(v) ? '' : v;
    if (Array.isArray(v)) return v.map((x) => walk(x, key));
    if (v && typeof v === 'object') {
      return Object.fromEntries(Object.entries(v as Record<string, unknown>).map(([k, x]) => [k, walk(x, k)]));
    }
    return v;
  };
  return walk(value) as T;
}

/** A step as it travels on the clipboard: no view state, no run status, no pinned example, no credentials. */
export function sanitizeForClipboard(node: FlowNode): FlowNode {
  const copy = JSON.parse(JSON.stringify(node)) as FlowNode;
  const data = stripSecrets({ ...copy.data, sample: undefined, status: undefined });
  const trigger = data.triggerConfig as ({ type?: string; secret?: unknown; secret_hidden?: unknown } & Record<string, unknown>) | undefined;
  if (trigger) {
    delete trigger.secret;
    delete trigger.secret_hidden;
  }
  const out = { ...copy, data, selected: false, dragging: false } as FlowNode;
  for (const key of ['width', 'height', 'positionAbsolute'] as const) delete (out as unknown as Record<string, unknown>)[key];
  return out;
}

export function buildClipboard(graph: Graph, ids: string[], fromFlowId: string | null, now: number): ClipboardPayload | null {
  const wanted = new Set(ids);
  const nodes = graph.nodes.filter((n) => wanted.has(n.id)).map(sanitizeForClipboard);
  if (nodes.length === 0) return null;
  const kept = new Set(nodes.map((n) => n.id));
  const edges = graph.edges
    .filter((e) => kept.has(e.source) && kept.has(e.target))
    .map((e) => JSON.parse(JSON.stringify({ ...e, selected: false })) as typeof e);
  return { v: 1, kind: 'huf-flow-steps', copiedAt: now, fromFlowId, nodes, edges };
}

function storage(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

export function writeClipboard(payload: ClipboardPayload): boolean {
  const store = storage();
  if (!store) return false;
  try {
    store.setItem(CLIPBOARD_KEY, JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

/** The copied steps, or null when there are none or what is stored is not a copy made by this editor. */
export function readClipboard(): ClipboardPayload | null {
  const store = storage();
  if (!store) return null;
  try {
    const raw = store.getItem(CLIPBOARD_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ClipboardPayload>;
    if (parsed?.v !== 1 || parsed.kind !== 'huf-flow-steps' || !Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges) || parsed.nodes.length === 0) return null;
    return parsed as ClipboardPayload;
  } catch {
    return null;
  }
}

export const hasClipboard = (): boolean => readClipboard() !== null;

const NODE_WIDTH = 236;

export interface PasteResult extends Graph {
  addedIds: string[];
  /** A trigger was in the copy, but this flow already has one. */
  skippedTrigger: boolean;
}

/**
 * Add the copied steps to `target`. `pasteCount` is how many times this copy was already pasted into this flow (each paste
 * lands a little further along, so copies never pile up). Into the flow they came from they land beside the originals; into
 * another flow they land to the right of what is there.
 */
export function pasteSteps(payload: ClipboardPayload, target: Graph, flowId: string | null, now: number, pasteCount = 0): PasteResult {
  const hasTrigger = target.nodes.some((n) => n.data.nodeType === 'trigger');
  const usable = payload.nodes.filter((n) => !(n.data.nodeType === 'trigger' && hasTrigger));
  const skippedTrigger = usable.length !== payload.nodes.length;
  if (usable.length === 0) return { ...target, addedIds: [], skippedTrigger };

  const sameFlow = Boolean(flowId) && payload.fromFlowId === flowId;
  const minX = Math.min(...usable.map((n) => n.position.x));
  const minY = Math.min(...usable.map((n) => n.position.y));
  const step = pasteCount + 1;
  let dx = 48 * step;
  let dy = 72 * step;
  if (!sameFlow && target.nodes.length > 0) {
    const maxX = Math.max(...target.nodes.map((n) => n.position.x + NODE_WIDTH));
    const topY = Math.min(...target.nodes.map((n) => n.position.y));
    dx = maxX + 80 - minX + 48 * pasteCount;
    dy = topY - minY + 72 * pasteCount;
  } else if (!sameFlow) {
    dx = 48 * pasteCount;
    dy = 72 * pasteCount;
  }
  const clone = cloneSteps({ nodes: payload.nodes, edges: payload.edges }, usable.map((n) => n.id), target.nodes.map((n) => n.id), {
    now,
    takenLabels: target.nodes.map((n) => n.data.label),
    keepTitles: !sameFlow,
    place: (n) => ({ x: n.position.x + dx, y: n.position.y + dy }),
    adjust: (copy) => {
      const trigger = copy.data.triggerConfig as ({ type?: string } & Record<string, unknown>) | undefined;
      if (copy.data.nodeType === 'trigger' && trigger?.type === 'webhook') {
        return { ...copy, data: { ...copy.data, triggerConfig: { ...trigger, secret: generateWebhookSecret() } as never } };
      }
      return copy;
    },
  });
  return {
    nodes: [...target.nodes.map((n) => ({ ...n, selected: false })), ...clone.nodes.map((n) => ({ ...n, selected: true }))],
    edges: [...target.edges, ...clone.edges],
    addedIds: usable.map((n) => clone.idMap.get(n.id) as string),
    skippedTrigger,
  };
}
