import type { Page, Route } from '@playwright/test';
import type {
  EntryPoint,
  Intent,
  NumberSummary,
  RouteDecision,
  SimulateRequest,
  SolutionConversation,
  SolutionOverview,
  SolutionSummary,
} from '../../src/types/solutions';

/**
 * Offline mocks for the Solutions API (API_CONTRACT.md v1 + addenda).
 * Factories return contract-shaped objects; `mockSolutionsApi` answers every
 * huf.ai.solutions.read_models.* and huf.ai.solutions.crud.* call and records
 * what the UI sent. Register it AFTER mockOfflineApis (later routes win).
 */

export const READ = '**/api/method/huf.ai.solutions.read_models.';
export const CRUD = '**/api/method/huf.ai.solutions.crud.';

export const GW1 = { gateway: 'GW-1', label: 'Main counter', phone: '+1 555 0100' };
export const GW2 = { gateway: 'GW-2', label: 'Catering line', phone: '+1 555 0200' };

export function makeSolutionSummary(over: Partial<SolutionSummary> = {}): SolutionSummary {
  return {
    name: 'orders',
    title: 'Order desk',
    purpose: 'orders',
    status: 'Live',
    test_mode: false,
    runs_on: [GW1],
    shared: false,
    entry_count: 2,
    primary: { type: 'Agent', name: 'order-agent', label: 'Order agent' },
    chats_7d: 12,
    description: 'Takes orders.',
    ...over,
  };
}

export function makeSolutionOverview(over: Partial<SolutionOverview> = {}): SolutionOverview {
  return {
    ...makeSolutionSummary(),
    description: 'Takes orders.',
    health: { state: 'ok', gateway: 'GW-1', quality: null, blame: null },
    reach: { contacts_7d: 30, new_7d: 5 },
    activity: [{ ts: '2026-10-24T10:00:00Z', kind: 'chat', text: 'New order chat' }],
    cost: { sends_24h: 40, cap_share: 40, ceiling: 100 },
    limits: { per_day: null, scope: 'Any number' },
    ...over,
  };
}

export function makeEntryPoint(over: Partial<EntryPoint> = {}): EntryPoint {
  return {
    name: 'ep-1',
    gateway: 'GW-1',
    priority: 1,
    match_type: 'Keyword',
    match_values: ['order'],
    target_type: 'Agent',
    agent: 'order-agent',
    flow: null,
    cap_per_day: 30,
    scope_override: null,
    allow_first_message: false,
    ceiling: 100,
    ceiling_source: 'meta_tier',
    ...over,
  };
}

export function makeNumberSummary(over: Partial<NumberSummary> = {}): NumberSummary {
  return {
    gateway: 'GW-1',
    label: 'Main counter',
    phone: '+1 555 0100',
    solutions: [],
    routing_order: [],
    quality: { rating: null, source: 'unknown' },
    blame: null,
    ...over,
  };
}

export function makeRouteDecision(over: Partial<RouteDecision> = {}): RouteDecision {
  return {
    solution: 'orders',
    target_type: 'Agent',
    agent: 'order-agent',
    flow: null,
    binding: null,
    reason: 'keyword',
    pin: { solution: 'orders', expires_at: new Date(Date.now() + 24 * 3_600_000).toISOString() },
    trace: [{ k: 'win', t: 'Keyword "order" matched Order desk' }],
    reply_text: null,
    ...over,
  };
}

/** The six purposes, as returned by get_intents() (mirrors huf/ai/solutions/intents.py). */
export const INTENTS: Intent[] = [
  { id: 'answer', name: 'Answer questions', desc: 'Replies from your docs, FAQ or catalog. Hands off when unsure.', icon: 'circle-help', sample_name: 'Shop FAQ', entry: 'catchall', keywords: [], ref: '', suggested_templates: ['welcome_opt_in'], policy: ['Replies only inside the 24-hour window'] },
  { id: 'orders', name: 'Take orders', desc: 'Browse the menu, build an order, confirm pickup or delivery.', icon: 'shopping-bag', sample_name: 'Order desk', entry: 'keywords', keywords: ['order', 'menu', 'cake'], ref: 'weekend_special', suggested_templates: ['order_ready_pickup', 'weekend_croissant_special'], policy: ['Message first allowed with approved templates', 'Daily cap: 400 for this entry point'] },
  { id: 'support', name: 'Support & handoff', desc: 'Sort the problem, collect details, pass to a person.', icon: 'life-buoy', sample_name: 'Support desk', entry: 'keywords', keywords: ['help', 'refund', 'wrong', 'complaint'], ref: '', suggested_templates: ['care_request_received'], policy: ['Hand off to a person after 2 failed answers'] },
  { id: 'bookings', name: 'Bookings', desc: 'Appointments, reservations, quotes and reminders.', icon: 'calendar-days', sample_name: 'Catering bookings', entry: 'keywords', keywords: ['book', 'event', 'quote', 'catering'], ref: 'office_lunch', suggested_templates: ['catering_quote_ready', 'welcome_opt_in'], policy: ['Reminder templates on'] },
  { id: 'updates', name: 'Send updates', desc: 'Outbound only: order status, alerts and broadcasts using approved templates.', icon: 'bell', sample_name: 'Order updates', entry: 'none', keywords: [], ref: '', suggested_templates: ['order_ready_pickup', 'delivery_delay_notice'], policy: ['Templates only, with an opt-in check'] },
  { id: 'team', name: 'Team & internal', desc: 'Staff ask questions, log entries or approve requests from WhatsApp.', icon: 'users', sample_name: 'Staff desk', entry: 'allowlist', keywords: [], ref: '', suggested_templates: [], policy: ['Only allow-listed staff numbers may message'] },
];

/** `{error:{code,message}}`, the contract error shape (management._error). */
export const solutionsError = (code: string, message: string) => ({ error: { code, message } });

export interface SolutionsCall {
  method: string;
  /** Raw args as sent (query string or POST body). */
  args: Record<string, unknown>;
  /** Args whose value is a JSON string (request, payload, fields, entry), parsed. */
  parsed: Record<string, any>;
}

type Answer = (call: SolutionsCall) => unknown;

export interface SolutionsMockOptions {
  solutions?: SolutionSummary[];
  overviews?: Record<string, SolutionOverview>;
  entries?: Record<string, EntryPoint[]>;
  numberSummaries?: Record<string, NumberSummary>;
  conversations?: SolutionConversation[];
  intents?: Intent[];
  /** Per-method override; return an object (or solutionsError(...)) to answer with it. */
  handlers?: Record<string, Answer>;
}

function readArgs(route: Route): Record<string, unknown> {
  const request = route.request();
  const data = request.postData();
  if (data) {
    try { return JSON.parse(data); } catch { return Object.fromEntries(new URLSearchParams(data)); }
  }
  return Object.fromEntries(new URL(request.url()).searchParams);
}

/** Answers all Solutions read_models / crud calls. Returns the recorded calls. */
export async function mockSolutionsApi(page: Page, opts: SolutionsMockOptions = {}) {
  const calls: SolutionsCall[] = [];
  const solutions = opts.solutions ?? [];
  const intents = opts.intents ?? INTENTS;
  const answers: Record<string, Answer> = {
    list_solutions: ({ args }) =>
      solutions.filter((s) => !args.purpose || s.purpose === args.purpose),
    get_solution_overview: ({ args }) => {
      const o = opts.overviews?.[String(args.name)];
      return o ?? solutionsError('not_found', `No solution called ${String(args.name)}.`);
    },
    list_entry_points: ({ args }) => opts.entries?.[String(args.solution)] ?? [],
    get_number_summary: ({ args }) =>
      opts.numberSummaries?.[String(args.gateway)] ?? makeNumberSummary({ gateway: String(args.gateway) }),
    list_solution_conversations: () => opts.conversations ?? [],
    get_intents: () => intents,
    simulate_route: () => makeRouteDecision({ solution: null, target_type: null, agent: null, reason: 'unrouted', pin: null, trace: [] }),
    create_solution: ({ parsed }) =>
      makeSolutionSummary({ name: 'new-solution', title: parsed.payload?.title ?? 'New solution', status: 'Paused' }),
    update_solution: ({ args }) => makeSolutionSummary({ name: String(args.name) }),
    pause_solution: ({ args }) => makeSolutionSummary({ name: String(args.name), status: 'Paused' }),
    resume_solution: ({ args }) => makeSolutionSummary({ name: String(args.name), status: 'Live' }),
    go_live: ({ args }) => makeSolutionSummary({ name: String(args.name), status: 'Live' }),
    save_entry_point: ({ parsed }) => makeEntryPoint(parsed.entry ?? {}),
    delete_entry_point: () => ({ success: true }),
    reassign_conversation: () => ({ pin: { solution: 'orders' } }),
    ...opts.handlers,
  };

  const register = (base: string, methods: string[]) =>
    Promise.all(
      methods.map((method) =>
        page.route(`${base}${method}{,?*}`, (route) => {
          const args = readArgs(route);
          const parsed: Record<string, any> = {};
          for (const [k, v] of Object.entries(args)) {
            if (typeof v === 'string' && /^[{[]/.test(v)) {
              try { parsed[k] = JSON.parse(v); } catch { /* leave raw */ }
            }
          }
          const call = { method, args, parsed };
          calls.push(call);
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ message: answers[method](call) }) });
        }),
      ),
    );

  await register(READ, [
    'list_solutions', 'get_solution_overview', 'list_entry_points', 'get_number_summary',
    'list_solution_conversations', 'get_intents', 'simulate_route',
  ]);
  await register(CRUD, [
    'create_solution', 'update_solution', 'pause_solution', 'resume_solution',
    'save_entry_point', 'delete_entry_point', 'go_live', 'reassign_conversation',
  ]);
  return calls;
}

export const callsOf = (calls: SolutionsCall[], method: string) => calls.filter((c) => c.method === method);

export interface ResourceMockOptions {
  /** WhatsApp gateways the wizard and list page see. */
  gateways?: Array<{ name: string; gateway_name?: string }>;
  agents?: Array<{ name: string; agent_name?: string }>;
  flows?: Array<{ name: string; flow_name?: string }>;
}

/** Resource lists behind getGateways / getAgents / getFlowDefinitions (GET /api/resource/<Doctype>). */
export async function mockSolutionResources(page: Page, opts: ResourceMockOptions = {}) {
  const gateways = opts.gateways ?? [{ name: 'GW-1', gateway_name: 'Main counter' }, { name: 'GW-2', gateway_name: 'Catering line' }];
  const list = (rows: unknown[]) => (route: Route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: rows }) });
  await page.route(/\/api\/resource\/Gateway(\?|$)/, list(gateways.map((g) => ({ provider: 'WhatsApp', is_enabled: 1, direct_policy: 'Open', gateway_name: g.name, ...g }))));
  await page.route(/\/api\/resource\/Agent(\?|$)/, list(opts.agents ?? [{ name: 'order-agent', agent_name: 'Order agent' }, { name: 'care-agent', agent_name: 'Care agent' }]));
  await page.route(/\/api\/resource\/Flow%20Definition(\?|$)/, list(opts.flows ?? []));
}
