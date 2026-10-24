import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createSolution, getIntents, getNumberSummary, goLive, SolutionsApiError } from '@/services/solutionsApi';
import { getGateways, type GatewayDoc } from '@/services/gatewayApi';
import { getAgents } from '@/services/agentApi';
import { getFlowDefinitions } from '@/services/flowApi';
import { errorText, listTemplates, type WhatsAppTemplate } from '@/services/whatsappApi';
import type { Intent, NumberSummary, SolutionSummary } from '@/types/solutions';
import {
  addKeyword,
  applyIntent,
  applyMode,
  buildDraft,
  buildPayload,
  canContinue,
  describeError,
  findIntent,
  initialWizardState,
  type ExistingTarget,
  type WizardState,
} from './wizardModel';

export interface TargetOption {
  type: 'Agent' | 'Flow';
  name: string;
  label: string;
}

export interface WizardParams {
  purpose?: string | null;
  mode?: string | null;
  gateway?: string | null;
}

export function useWizardState(params: WizardParams = {}) {
  const [state, setState] = useState<WizardState>(initialWizardState);
  const [intents, setIntents] = useState<Intent[]>([]);
  const [gateways, setGateways] = useState<GatewayDoc[]>([]);
  const [summaries, setSummaries] = useState<Record<string, NumberSummary>>({});
  const [targets, setTargets] = useState<TargetOption[]>([]);
  const [templates, setTemplates] = useState<WhatsAppTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templatesError, setTemplatesError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const applied = useRef(false);

  // Initial data. Nothing here writes anything.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [ints, gws, agents, flows] = await Promise.all([
        getIntents().catch(() => [] as Intent[]),
        getGateways().catch(() => [] as GatewayDoc[]),
        getAgents().catch(() => []),
        getFlowDefinitions().catch(() => []),
      ]);
      if (cancelled) return;
      const wa = gws.filter((g) => g.provider === 'WhatsApp');
      setIntents(ints);
      setGateways(wa);
      const agentList = (Array.isArray(agents) ? agents : (agents as { agents?: unknown[] }).agents ?? []) as Array<{
        name: string;
        agent_name?: string;
      }>;
      setTargets([
        ...agentList.map((a) => ({ type: 'Agent' as const, name: a.name, label: a.agent_name || a.name })),
        ...(flows as Array<{ name: string; flow_name?: string }>).map((f) => ({
          type: 'Flow' as const,
          name: f.name,
          label: f.flow_name || f.name,
        })),
      ]);
      setLoaded(true);
      wa.forEach((g) => {
        getNumberSummary(g.name)
          .then((s) => !cancelled && setSummaries((prev) => ({ ...prev, [g.name]: s })))
          .catch(() => undefined);
      });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Preselect from query params once the data is in.
  useEffect(() => {
    if (!loaded || applied.current) return;
    applied.current = true;
    setState((s) => {
      let next = s;
      const gw = params.gateway && gateways.some((g) => g.name === params.gateway) ? params.gateway : gateways[0]?.name;
      if (gw) next = { ...next, gateway: gw };
      const intent = findIntent(intents, params.purpose ?? null);
      if (intent) next = applyIntent(next, intent);
      else if (params.mode === 'existing' || params.mode === 'blank') next = applyMode(next, params.mode);
      return next;
    });
  }, [loaded, gateways, intents, params.gateway, params.purpose, params.mode]);

  const intent = useMemo(() => findIntent(intents, state.intentId), [intents, state.intentId]);

  // Approved templates of the chosen number's account.
  useEffect(() => {
    if (!state.gateway) return;
    let cancelled = false;
    setTemplatesLoading(true);
    setTemplatesError('');
    listTemplates(state.gateway)
      .then((res) => {
        if (cancelled) return;
        if (res.success) setTemplates(res.templates ?? []);
        else {
          setTemplates([]);
          setTemplatesError(errorText(res));
        }
      })
      .catch((e) => {
        if (cancelled) return;
        setTemplates([]);
        setTemplatesError(e instanceof Error ? e.message : 'Could not load templates.');
      })
      .finally(() => !cancelled && setTemplatesLoading(false));
    return () => {
      cancelled = true;
    };
  }, [state.gateway]);

  const patch = useCallback((p: Partial<WizardState>) => setState((s) => ({ ...s, ...p })), []);

  const actions = {
    setName: (name: string) => patch({ name, nameEdited: true }),
    selectIntent: (i: Intent) => setState((s) => applyIntent(s, i)),
    selectMode: (m: 'existing' | 'blank') =>
      setState((s) => {
        const next = applyMode(s, m);
        if (m === 'existing' && !next.existing && targets[0]) {
          return { ...next, existing: { type: targets[0].type, name: targets[0].name } };
        }
        return next;
      }),
    setExisting: (t: ExistingTarget) => patch({ existing: t }),
    setGateway: (gateway: string) => patch({ gateway, templates: [], draftTemplate: false }),
    addKeyword: (raw: string) => setState((s) => ({ ...s, keywords: addKeyword(s.keywords, raw) })),
    removeKeyword: (k: string) => setState((s) => ({ ...s, keywords: s.keywords.filter((x) => x !== k) })),
    setRef: (ref: string) => patch({ ref }),
    toggleTriage: () => setState((s) => ({ ...s, triage: !s.triage })),
    addEntryPointsAnyway: () => patch({ inbound: true }),
    toggleTemplate: (name: string) =>
      setState((s) => ({
        ...s,
        templates: s.templates.includes(name) ? s.templates.filter((t) => t !== name) : [...s.templates, name],
      })),
    toggleDraftTemplate: () => setState((s) => ({ ...s, draftTemplate: !s.draftTemplate })),
    setTestMode: (testMode: boolean) => patch({ testMode }),
    next: () => setState((s) => (s.step < 4 && canContinue(s) ? { ...s, step: (s.step + 1) as WizardState['step'] } : s)),
    back: () => setState((s) => (s.step > 1 ? { ...s, step: (s.step - 1) as WizardState['step'] } : s)),
  };

  const payload = useMemo(() => buildPayload(state, intent), [state, intent]);
  const draft = useMemo(() => buildDraft(state, intent), [state, intent]);

  /** createSolution, then goLive unless test mode. Returns the created solution or null on error. */
  const submit = useCallback(async (): Promise<SolutionSummary | null> => {
    setSubmitting(true);
    setError('');
    try {
      const created = await createSolution(payload);
      if (!payload.test_mode) await goLive(created.name);
      return created;
    } catch (e) {
      if (e instanceof SolutionsApiError) setError(describeError(e.code, e.message));
      else setError(describeError(undefined, e instanceof Error ? e.message : ''));
      return null;
    } finally {
      setSubmitting(false);
    }
  }, [payload]);

  return {
    state, intent, intents, gateways, summaries, targets, templates, templatesLoading, templatesError,
    loaded, submitting, error, payload, draft, actions, submit,
    canContinue: canContinue(state),
  };
}

export type WizardApi = ReturnType<typeof useWizardState>;
