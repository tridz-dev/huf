/**
 * Step types that installed apps add: loaded once per page load and shared by the palette, the step form and the
 * publish check. They are kept apart from the built-in palette (`data/actions.ts`).
 */
import { useEffect, useState } from 'react';
import { actionOptions } from '@/data/actions';
import { embedApp, isBackendTypeAllowed, setScopeTypes } from '@/components/flow/palette/embedScope';
import type { ActionOption } from '@/types/modal.types';
import { listNodeTypes, type AppNodeType, type SchemaProp } from '@/services/flow/steps/nodeTypesApi';
import { BUILTIN_SCHEMA_STEPS, builtinSchemaStep } from './builtinSchemaSteps';

let cached: AppNodeType[] | null = null;
let inFlight: Promise<AppNodeType[]> | null = null;
const listeners = new Set<() => void>();

export function setAppNodeTypes(types: AppNodeType[] | null) {
  cached = types;
  listeners.forEach((fn) => fn());
}

export function loadAppNodeTypes(): Promise<AppNodeType[]> {
  if (cached) return Promise.resolve(cached);
  const app = embedApp();
  inFlight ??= listNodeTypes(app ?? undefined)
    // A failure is not cached: the scope stays empty (embedded) and the next call asks again.
    .then((rows) => {
      if (app !== null) setScopeTypes(rows.map((r) => r.type));
      const types = rows.filter((r) => !r.builtin);
      setAppNodeTypes(types);
      return types;
    })
    .finally(() => { inFlight = null; });
  return inFlight;
}

/** The app step types, `loaded` once the server has answered. */
export function useAppNodeTypes(): { types: AppNodeType[]; loaded: boolean } {
  const [, tick] = useState(0);
  useEffect(() => {
    const on = () => tick((n) => n + 1);
    listeners.add(on);
    loadAppNodeTypes().catch(() => undefined);
    return () => { listeners.delete(on); };
  }, []);
  return { types: cached ?? [], loaded: cached !== null };
}

export const appNodeTypesLoaded = (): boolean => cached !== null;
export const getAppNodeType = (type: unknown): AppNodeType | undefined =>
  (typeof type === 'string' ? cached?.find((t) => t.type === type) : undefined) ?? builtinSchemaStep(type);

/** The app steps, then the built-in steps drawn by the schema form (an app cannot shadow a built-in). */
export function schemaStepTypes(types: AppNodeType[]): AppNodeType[] {
  const builtins = BUILTIN_SCHEMA_STEPS.filter((t) => isBackendTypeAllowed(t.type));
  return [...types.filter((t) => !builtinSchemaStep(t.type)), ...builtins];
}

const BUILTIN_STEP_PREFIXES = new Set(['agent', 'tool', 'router', 'doc', 'flow', 'state', 'code', 'member', 'trigger']);

/** The words shown when a step's app is gone: `{app}` is the part of the step type before the dot. */
export const appMissingMessage = (app: string): string =>
  `This step comes from ${app}, which is not installed on this site. Remove the step or install the app.`;

/** An app step whose type is not in the loaded catalog (its app was removed): the app's name, else null. */
export function missingAppStep(backendType: unknown): { app: string } | null {
  if (!appNodeTypesLoaded() || typeof backendType !== 'string' || getAppNodeType(backendType)) return null;
  // Embedded: another app's step was left out of the list on purpose, not removed from the site.
  if (embedApp() !== null && !isBackendTypeAllowed(backendType)) return null;
  const app = backendType.split('.')[0];
  return backendType.includes('.') && app && !BUILTIN_STEP_PREFIXES.has(app) ? { app } : null;
}

const BUILTIN_CATEGORIES = new Set<ActionOption['category']>(['agent', 'control', 'people', 'data', 'apps', 'advanced']);

/** Palette entries for app step types: they sit in their own category when it matches one, else under Apps. */
export function appActionOptions(types: AppNodeType[]): ActionOption[] {
  return schemaStepTypes(types).map((t) => ({
    id: t.type,
    name: t.label,
    description: t.description,
    icon: t.icon,
    category: BUILTIN_CATEGORIES.has(t.category as ActionOption['category']) ? (t.category as ActionOption['category']) : 'apps',
    keywords: [t.app],
  }));
}

/** One palette entry by id, built-in or from an app. */
export function findActionOption(id: string): ActionOption | undefined {
  return actionOptions.find((a) => a.id === id) ?? appActionOptions(cached ?? []).find((a) => a.id === id);
}

/** The required settings of an app step that are still empty, with the plain message for each. */
export function schemaRequiredIssues(schema: SchemaProp | undefined, cfg: Record<string, unknown>): Array<{ field: string; message: string }> {
  const props = schema?.properties ?? {};
  return (schema?.required ?? [])
    .filter((key) => {
      const v = cfg[key];
      return v == null || (typeof v === 'string' && v.trim() === '') || (Array.isArray(v) && v.length === 0);
    })
    .map((key) => ({ field: key, message: `Fill in ${props[key]?.title ?? key}.` }));
}
