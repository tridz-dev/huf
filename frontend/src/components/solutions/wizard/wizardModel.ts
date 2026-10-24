import type {
  CreateEntryInput,
  CreateSolutionPayload,
  Intent,
  SimulateDraft,
  SolutionPurpose,
} from '@/types/solutions';

export type WizardMode = 'intent' | 'existing' | 'blank';
export type WizardStep = 1 | 2 | 3 | 4;

export interface ExistingTarget {
  type: 'Agent' | 'Flow';
  name: string;
}

export interface WizardState {
  step: WizardStep;
  mode: WizardMode;
  intentId: string | null;
  name: string;
  nameEdited: boolean;
  existing: ExistingTarget | null;
  gateway: string;
  inbound: boolean;
  keywords: string[];
  ref: string;
  triage: boolean;
  templates: string[];
  draftTemplate: boolean;
  testMode: boolean;
}

export const initialWizardState: WizardState = {
  step: 1,
  mode: 'blank',
  intentId: null,
  name: '',
  nameEdited: false,
  existing: null,
  gateway: '',
  inbound: true,
  keywords: [],
  ref: '',
  triage: false,
  templates: [],
  draftTemplate: false,
  testMode: false,
};

export function findIntent(intents: Intent[], id: string | null): Intent | undefined {
  return id ? intents.find((i) => i.id === id) : undefined;
}

/** Pick a purpose: prefills name (until edited), keywords, ad tag, templates and inbound. */
export function applyIntent(state: WizardState, intent: Intent): WizardState {
  return {
    ...state,
    mode: 'intent',
    intentId: intent.id,
    existing: null,
    name: state.nameEdited ? state.name : intent.sample_name,
    keywords: [...intent.keywords],
    ref: intent.ref || '',
    triage: false,
    inbound: intent.entry !== 'none',
    templates: [...intent.suggested_templates],
    draftTemplate: false,
  };
}

export function applyMode(state: WizardState, mode: 'existing' | 'blank'): WizardState {
  return {
    ...state,
    mode,
    intentId: null,
    existing: mode === 'existing' ? state.existing : null,
    name: state.nameEdited ? state.name : '',
    keywords: [],
    ref: '',
    triage: false,
    inbound: true,
    templates: [],
    draftTemplate: false,
  };
}

export function addKeyword(keywords: string[], raw: string): string[] {
  const k = raw.trim().toLowerCase();
  return !k || keywords.includes(k) ? keywords : [...keywords, k];
}

/** True when the purpose adds a catch-all rule. */
function wantsCatchAll(state: WizardState, intent: Intent | undefined): boolean {
  if (!state.inbound) return false;
  if (intent && (intent.entry === 'catchall' || intent.entry === 'allowlist')) return true;
  return !state.keywords.length && !state.ref.trim() && !state.triage;
}

export function buildEntries(state: WizardState, intent: Intent | undefined): CreateEntryInput[] {
  if (!state.inbound) return [];
  const entries: CreateEntryInput[] = [];
  if (state.keywords.length) entries.push({ match_type: 'Keyword', match_values: [...state.keywords] });
  if (state.ref.trim()) entries.push({ match_type: 'Ad or link tag', match_values: [state.ref.trim()] });
  if (wantsCatchAll(state, intent)) entries.push({ match_type: 'Catch-all', match_values: [] });
  return entries;
}

export function draftTemplateName(name: string): string {
  const slug = (name || 'new').toLowerCase().replace(/\W+/g, '_').replace(/^_+|_+$/g, '') || 'new';
  return `${slug}_quote`;
}

export function buildPayload(state: WizardState, intent: Intent | undefined): CreateSolutionPayload {
  const entries = buildEntries(state, intent);
  if (state.inbound && state.triage) entries.push({ match_type: 'Triage', match_values: [] });
  const payload: CreateSolutionPayload = {
    title: state.name.trim(),
    mode: state.mode,
    gateway: state.gateway,
    entries,
    inbound: state.inbound,
    templates: [...state.templates],
    test_mode: state.testMode,
  };
  if (state.mode === 'intent' && intent) payload.purpose = intent.id as SolutionPurpose;
  if (state.mode === 'existing' && state.existing) payload.existing_target = state.existing;
  if (state.draftTemplate) {
    payload.draft_template = {
      name: draftTemplateName(state.name),
      language: 'en',
      category: 'UTILITY',
      status: 'Draft',
    };
  }
  return payload;
}

/** Rules sent to simulate_route as `draft` so the test step saves nothing. */
export function buildDraft(state: WizardState, intent: Intent | undefined): SimulateDraft {
  const payload = buildPayload(state, intent);
  const entries = payload.entries.map((e) => ({
    match_type: e.match_type as SimulateDraft['entries'][number]['match_type'],
    match_values: e.match_values,
  }));
  const draft: SimulateDraft = {
    title: state.name.trim(),
    gateway: state.gateway,
    inbound: state.inbound,
    entries,
    catch_all: entries.some((e) => e.match_type === 'Catch-all'),
  };
  if (intent) draft.intent = intent.id;
  return draft;
}

export function canContinue(state: WizardState): boolean {
  if (state.step === 1) {
    if (!state.name.trim()) return false;
    if (state.mode === 'existing' && !state.existing) return false;
  }
  return true;
}

/** Friendly text for the contract error codes; falls back to the server message. */
export function describeError(code: string | undefined, message: string): string {
  switch (code) {
    case 'invalid_payload':
      return `Some details are not valid. ${message}`.trim();
    case 'not_permitted':
      return 'You do not have permission to create this. Ask an administrator to manage integrations.';
    case 'shared_template':
      return `A selected template is shared with another solution and cannot be changed here. ${message}`.trim();
    case 'cap_exceeds_ceiling':
      return `A daily limit is higher than this number allows. ${message}`.trim();
    case 'scope_loosening':
      return `A setting is broader than the number allows. ${message}`.trim();
    case 'not_found':
      return `Something it refers to no longer exists. ${message}`.trim();
    default:
      return message || 'Something went wrong. Nothing was saved.';
  }
}
