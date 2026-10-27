import { z } from 'zod';
import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

const API = 'huf.ai.gateways.bindings_api';

export const MATCH_TYPES = [
  'Any conversation',
  'Direct message',
  'Room or channel',
  'Thread',
  'Sender',
] as const;
export type BindingMatchType = (typeof MATCH_TYPES)[number];
export type BindingTargetType = 'Agent' | 'Flow';

export interface GatewayBinding {
  name: string;
  gateway: string;
  priority: number;
  is_enabled: 0 | 1;
  match_type: BindingMatchType;
  match_value?: string | null;
  target_type: BindingTargetType;
  agent?: string | null;
  flow?: string | null;
  description?: string | null;
}

export interface SaveBindingInput {
  name?: string;
  match_type: BindingMatchType;
  match_value?: string;
  target_type: BindingTargetType;
  agent?: string;
  flow?: string;
  is_enabled?: 0 | 1;
  description?: string;
}

export interface PickerItem {
  id: string;
  label: string;
  kind: 'public' | 'private' | 'dm' | 'user';
  is_member: boolean;
}

export interface PickerResult {
  supported: boolean;
  items: PickerItem[];
  next_cursor: string | null;
  error: string | null;
}

export interface RoutePreview {
  status: string;
  binding?: string | null;
  target_type?: BindingTargetType;
  agent?: string | null;
  flow?: string | null;
  reason?: string;
}

export interface RouteSample {
  conversation_id?: string;
  thread_id?: string;
  sender_id?: string;
}

// ---- pure helpers ---------------------------------------------------------

export const bindingFormSchema = z
  .object({
    match_type: z.enum(MATCH_TYPES),
    match_value: z.string().trim().optional(),
    target_type: z.enum(['Agent', 'Flow']),
    agent: z.string().optional(),
    flow: z.string().optional(),
    description: z.string().optional(),
  })
  .superRefine((v, ctx) => {
    if (v.match_type === 'Any conversation') {
      if (v.match_value) {
        ctx.addIssue({ code: 'custom', path: ['match_value'], message: 'Leave this empty for any conversation.' });
      }
    } else if (!v.match_value) {
      ctx.addIssue({ code: 'custom', path: ['match_value'], message: 'Enter a value.' });
    }
    if (v.target_type === 'Agent' && !v.agent) {
      ctx.addIssue({ code: 'custom', path: ['agent'], message: 'Choose an agent.' });
    }
    if (v.target_type === 'Flow' && !v.flow) {
      ctx.addIssue({ code: 'custom', path: ['flow'], message: 'Choose a flow.' });
    }
  });
export type BindingFormValues = z.infer<typeof bindingFormSchema>;

/** Rules in the order they are evaluated. */
export function sortByPriority<T extends { priority: number; name: string }>(rules: T[]): T[] {
  return [...rules].sort((a, b) => a.priority - b.priority || a.name.localeCompare(b.name));
}

/** Move one item by delta positions (clamped); returns a new array. */
export function moveItem<T>(items: T[], index: number, delta: number): T[] {
  const target = Math.min(Math.max(index + delta, 0), items.length - 1);
  if (index < 0 || index >= items.length || target === index) return [...items];
  const next = [...items];
  const [item] = next.splice(index, 1);
  next.splice(target, 0, item);
  return next;
}

/** Plain-language summary of what a rule does. */
export function describeRule(
  rule: Pick<GatewayBinding, 'match_type' | 'match_value' | 'target_type' | 'agent' | 'flow'>,
  labelFor?: (value: string) => string | undefined
): string {
  const raw = rule.match_value ?? '';
  const value = labelFor?.(raw) ?? raw;
  const target = rule.target_type === 'Agent' ? rule.agent : rule.flow;
  const dest = `${target ?? 'nothing'} ${rule.target_type === 'Agent' ? 'agent' : 'flow'}`;
  switch (rule.match_type) {
    case 'Any conversation':
      return `When any message arrives, send it to ${dest}`;
    case 'Direct message':
      return `When someone sends a direct message (${value}), send it to ${dest}`;
    case 'Room or channel':
      return `When a message arrives in ${value}, send it to ${dest}`;
    case 'Thread':
      return `When a message arrives in thread ${value}, send it to ${dest}`;
    case 'Sender':
      return `When ${value} sends a message, send it to ${dest}`;
  }
}

// ---- API ------------------------------------------------------------------

export async function listBindings(gateway: string): Promise<GatewayBinding[]> {
  try {
    const res = await call.post(`${API}.list_bindings`, { gateway });
    return (res.message as GatewayBinding[]) ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error loading routing rules');
  }
}

export async function saveBinding(gateway: string, binding: SaveBindingInput): Promise<GatewayBinding> {
  try {
    const res = await call.post(`${API}.save_binding`, { gateway, binding });
    return res.message as GatewayBinding;
  } catch (error) {
    handleFrappeError(error, 'Error saving routing rule');
  }
}

export async function deleteBinding(name: string): Promise<void> {
  try {
    await call.post(`${API}.delete_binding`, { name });
  } catch (error) {
    handleFrappeError(error, 'Error deleting routing rule');
  }
}

export async function reorderBindings(gateway: string, orderedNames: string[]): Promise<GatewayBinding[]> {
  try {
    const res = await call.post(`${API}.reorder_bindings`, { gateway, ordered_names: orderedNames });
    return (res.message as GatewayBinding[]) ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error reordering routing rules');
  }
}

export async function testRoute(gateway: string, sample: RouteSample): Promise<RoutePreview> {
  try {
    const res = await call.post(`${API}.test_route`, { gateway, sample });
    return res.message as RoutePreview;
  } catch (error) {
    handleFrappeError(error, 'Error testing routing');
  }
}

async function pick(method: string, gateway: string, query?: string, cursor?: string): Promise<PickerResult> {
  try {
    const res = await call.post(`${API}.${method}`, { gateway, query, cursor });
    return res.message as PickerResult;
  } catch (error) {
    handleFrappeError(error, 'Error loading Slack list');
  }
}

export const listSlackChannels = (gateway: string, query?: string, cursor?: string) =>
  pick('list_slack_channels', gateway, query, cursor);
export const listSlackUsers = (gateway: string, query?: string, cursor?: string) =>
  pick('list_slack_users', gateway, query, cursor);
