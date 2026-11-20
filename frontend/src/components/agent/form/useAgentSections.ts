/**
 * Loads an existing agent section by section and saves every dirty section sequentially.
 *
 * - Load: all nine backend sections are fetched up front (each with its own revision), merged into
 *   one form-values object, and stored as the baseline. A section that fails to load is never saved.
 * - Dirty: a section is dirty when its form fields (or its child-table state) differ from the baseline.
 * - Save: dirty sections go through update_agent_section one after another with expected_modified,
 *   re-syncing every revision after each call. Desktop access rides along with Access through its own
 *   document write. Autosave (debounced) skips a pending rename; an explicit save includes it.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { FieldErrors } from 'react-hook-form';
import { toast } from 'sonner';
import type { AutosaveState, FormError } from '@/components/builder';
import { getAgentSection, updateAgentSection, getAgentDesktopAccess, updateAgentDesktopAccess, DESKTOP_ACCESS_DOC_FIELDS, type AgentConfigSection } from '@/services/agentApi';
import { getToolFunctionsByName } from '@/services/toolApi';
import { getMCPServer, type MCPServerRef } from '@/services/mcpApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { AgentDoc } from '@/types/agent.types';
import { writeToolDetailsSetting } from '@/components/chat/useChatAgentIdentity';
import type { AgentFormValues } from '../types';
import {
  ALL_SECTIONS, SAVE_ORDER, SECTION_FIELDS, formValuesToDoc, isDesktopField, knowledgeRows, mapAgentDocToFormValues, mcpRows,
  pickFields, sig, skillRows, tabForField, toKnowledgeRows, toMcpRefs, toSkillRows, toolRows, type AgentMcpServerRow, type AgentToolRow, type TabKey,
} from './agentFormModel';
import type { AgentForm } from '../tabs/fields';
import type { useAgentAbilities } from './useAgentAbilities';

type Revisions = Partial<Record<AgentConfigSection, string>>;
type SaveMode = 'auto' | 'explicit';

function flattenErrors(errors: FieldErrors<AgentFormValues>, prefix = ''): FormError[] {
  const out: FormError[] = [];
  for (const [key, value] of Object.entries(errors as Record<string, unknown>)) {
    if (!value || key === 'ref') continue;
    const path = prefix ? `${prefix}.${key}` : key;
    const v = value as { message?: unknown } & Record<string, unknown>;
    if (typeof v.message === 'string') out.push({ fieldId: path, message: v.message });
    else out.push(...flattenErrors(v as FieldErrors<AgentFormValues>, path));
  }
  return out;
}

export interface UseAgentSectionsArgs {
  id?: string;
  isNew: boolean;
  form: AgentForm;
  abilities: ReturnType<typeof useAgentAbilities>;
  canSave: boolean;
  onRenamed: (name: string) => void;
  onTabWithError: (tab: TabKey) => void;
}

export function useAgentSections({ id, isNew, form, abilities, canSave, onRenamed, onTabWithError }: UseAgentSectionsArgs) {
  const [loading, setLoading] = useState(!isNew);
  const [meta, setMeta] = useState({ isSystem: false, owner: null as string | null, lastRun: null as string | null, totalRun: null as number | null });
  const [desktopAccessStatus, setDesktopAccessStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const baselineRef = useRef<AgentFormValues | null>(null);
  const revisionsRef = useRef<Revisions>({});
  const loadedRef = useRef<Set<AgentConfigSection>>(new Set());
  const [baselineVersion, setBaselineVersion] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FormError[]>([]);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const savingRef = useRef(false);
  const pendingRef = useRef(false);
  const abilitiesRef = useRef(abilities);
  abilitiesRef.current = abilities;
  const idRef = useRef(id);
  idRef.current = id;

  // ---------- load ----------
  useEffect(() => {
    if (!id || isNew) { setLoading(false); return; }
    let cancelled = false;
    baselineRef.current = null;
    loadedRef.current = new Set();
    setLoading(true);
    setDesktopAccessStatus('loading');
    (async () => {
      const results = await Promise.allSettled(ALL_SECTIONS.map((s) => getAgentSection(id, s)));
      if (cancelled) return;
      const general = results[ALL_SECTIONS.indexOf('general')];
      if (general.status === 'rejected') {
        console.error('Error loading agent:', general.reason);
        toast.error(getFrappeErrorMessage(general.reason) || 'Failed to load agent details');
        setLoading(false);
        return;
      }
      const revisions: Revisions = {};
      let merged: Partial<AgentDoc> = {};
      const failed: string[] = [];
      results.forEach((r, i) => {
        const section = ALL_SECTIONS[i];
        if (r.status === 'fulfilled') {
          revisions[section] = r.value.modified;
          loadedRef.current.add(section);
          merged = { ...merged, ...r.value.values };
        } else { failed.push(section); console.error(`Error loading ${section} section:`, r.reason); }
      });
      if (failed.length) toast.error(`Some settings could not be loaded (${failed.join(', ')}). They will not be saved.`);
      const data = { ...merged, name: general.value.name, modified: general.value.modified } as AgentDoc;

      let desktopOk = false;
      try {
        const desktop = await getAgentDesktopAccess(id);
        Object.assign(data, desktop);
        desktopOk = true;
      } catch (error) {
        console.error('Error loading desktop access:', error);
        toast.error('Failed to load desktop access settings');
      }
      if (cancelled) return;
      setDesktopAccessStatus(desktopOk ? 'ready' : 'error');

      const values = mapAgentDocToFormValues(data);
      form.reset(values);
      baselineRef.current = values;
      revisionsRef.current = revisions;
      setBaselineVersion((v) => v + 1);
      setMeta({ isSystem: data.is_system === 1, owner: data.owner ?? null, lastRun: data.last_run ?? null, totalRun: data.total_run ?? null });

      const knowledge = toKnowledgeRows(data.agent_knowledge as never);
      const skills = toSkillRows(data.agent_skill);
      abilities.hydrate({ knowledge, skills });
      const toolNames = ((data.agent_tool || []) as AgentToolRow[]).map((t) => t.tool).filter(Boolean) as string[];
      const tools = toolNames.length ? await getToolFunctionsByName(toolNames).catch((e) => { console.error('Error loading tool details:', e); return []; }) : [];
      const refs = toMcpRefs(data.agent_mcp_server as AgentMcpServerRow[] | undefined);
      const mcp: MCPServerRef[] = await Promise.all(refs.map(async (server) => {
        try {
          const doc = await getMCPServer(server.mcp_server);
          return { ...server, server_name: doc.server_name || server.server_name || server.mcp_server, description: doc.description || server.description,
            mcp_enabled: doc.enabled === 1 ? 1 : 0, server_url: doc.server_url || server.server_url };
        } catch { return { ...server, mcp_enabled: undefined }; }
      }));
      if (cancelled) return;
      abilities.hydrate({ tools, mcp });
      setLoading(false);
    })().catch((error) => {
      console.error('Error loading agent:', error);
      if (!cancelled) { toast.error(getFrappeErrorMessage(error) || 'Failed to load agent details'); setLoading(false); }
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isNew]);

  // ---------- dirty ----------
  const values = form.watch();
  const valuesSig = sig(values);
  const ab = abilities;
  const abilitiesSig = sig([toolRows(ab.tools), mcpRows(ab.mcp), knowledgeRows(ab.knowledge), skillRows(ab.skills)]);

  const fieldsFor = useCallback((section: AgentConfigSection, mode: SaveMode) =>
    SECTION_FIELDS[section].filter((f) => !(isDesktopField(f) && desktopAccessStatus !== 'ready') && !(mode === 'auto' && f === 'agent_name')),
  [desktopAccessStatus]);

  const dirtySections = useCallback((mode: SaveMode): AgentConfigSection[] => {
    const base = baselineRef.current;
    if (!base || isNew) return [];
    const current = form.getValues();
    return SAVE_ORDER.filter((section) => {
      if (!loadedRef.current.has(section)) return false;
      if (section === 'tools') return abilitiesRef.current.dirty.tools;
      if (section === 'knowledge') return abilitiesRef.current.dirty.knowledge;
      if (section === 'skills') return abilitiesRef.current.dirty.skills;
      const fields = fieldsFor(section, mode);
      return sig(pickFields(current, fields)) !== sig(pickFields(base, fields));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, isNew, fieldsFor, baselineVersion, valuesSig, abilitiesSig]);

  const explicitDirty = dirtySections('explicit');
  const autoDirty = dirtySections('auto');
  const hasUnsaved = explicitDirty.length > 0 || saving;

  // ---------- save ----------
  const saveAll = useCallback(async (mode: SaveMode) => {
    const target0 = idRef.current;
    if (!target0 || isNew || !baselineRef.current || !canSave) return;
    if (savingRef.current) { pendingRef.current = true; return; }
    if (Object.keys(form.formState.errors).length > 0) await form.trigger();
    const dirty = dirtySections(mode);
    if (dirty.length === 0) {
      if (Object.keys(form.formState.errors).length === 0) setErrors([]);
      return;
    }
    const valid = await form.trigger();
    if (!valid) {
      const fieldSet = new Set(dirty.flatMap((s) => SECTION_FIELDS[s] as readonly string[]));
      const errs = flattenErrors(form.formState.errors).filter((e) => fieldSet.has(e.fieldId.split('.')[0]));
      if (errs.length) {
        setErrors(errs);
        if (mode === 'explicit') {
          onTabWithError(tabForField(errs[0].fieldId.split('.')[0]));
          toast.error(errs.length === 1 ? 'One thing needs fixing before it can save' : `${errs.length} things need fixing before it can save`);
        }
        return;
      }
    }
    setErrors([]);
    setSaveError(null);
    savingRef.current = true;
    setSaving(true);

    const current = form.getValues();
    const doc = formValuesToDoc(current);
    const snap = { tools: [...ab.tools], mcp: [...ab.mcp], knowledge: [...ab.knowledge], skills: [...ab.skills] };
    let target = target0;
    let revision: string | undefined;
    const setAllRevisions = (rev: string) => { revision = rev; revisionsRef.current = Object.fromEntries(ALL_SECTIONS.map((s) => [s, rev])); };
    try {
      for (const section of dirty) {
        const expected = revision ?? revisionsRef.current[section];
        if (!expected) throw new Error('This section is not ready to save. Reload the agent and try again.');
        const fields = fieldsFor(section, mode).filter((f) => !isDesktopField(f));
        let payload: Record<string, unknown>;
        if (section === 'tools') payload = { agent_tool: toolRows(snap.tools), agent_mcp_server: mcpRows(snap.mcp) };
        else if (section === 'knowledge') payload = { agent_knowledge: knowledgeRows(snap.knowledge) };
        else if (section === 'skills') payload = { agent_skill: skillRows(snap.skills) };
        else payload = Object.fromEntries(fields.filter((f) => f in doc).map((f) => [f, doc[f]]));

        const result = await updateAgentSection(target, section, payload as Partial<AgentDoc>, expected);
        setAllRevisions(result.modified);
        target = result.name || target;

        const saved: Partial<AgentFormValues> = pickFields(current, fields) as Partial<AgentFormValues>;
        if (section === 'permissions' && desktopAccessStatus === 'ready') {
          const base = baselineRef.current!;
          const changed = DESKTOP_ACCESS_DOC_FIELDS.some((f) => current[f as keyof AgentFormValues] !== base[f as keyof AgentFormValues]);
          if (changed) {
            const modified = await updateAgentDesktopAccess(target, Object.fromEntries(DESKTOP_ACCESS_DOC_FIELDS.map((f) => [f, doc[f]])));
            if (modified) setAllRevisions(modified);
            Object.assign(saved, pickFields(current, DESKTOP_ACCESS_DOC_FIELDS as unknown as (keyof AgentFormValues)[]));
          }
        }
        baselineRef.current = { ...baselineRef.current!, ...saved } as AgentFormValues;
        if (section === 'tools') abilitiesRef.current.markSaved({ tools: snap.tools, mcp: snap.mcp });
        else if (section === 'knowledge') abilitiesRef.current.markSaved({ knowledge: snap.knowledge });
        else if (section === 'skills') abilitiesRef.current.markSaved({ skills: snap.skills });
        else if (section === 'advanced') writeToolDetailsSetting(target, !!current.show_tool_execution_details);
        setBaselineVersion((v) => v + 1);
      }
      setSavedAt(new Date());
      if (target !== target0) onRenamed(target);
    } catch (error) {
      console.error('Error saving agent:', error);
      const message = getFrappeErrorMessage(error) || (error as Error)?.message || "Couldn't save";
      setSaveError(message);
      toast.error(`Couldn't save: ${message}`);
    } finally {
      savingRef.current = false;
      setSaving(false);
      if (pendingRef.current) { pendingRef.current = false; window.setTimeout(() => void saveRef.current('auto'), 0); }
    }
  }, [ab.tools, ab.mcp, ab.knowledge, ab.skills, canSave, desktopAccessStatus, dirtySections, fieldsFor, form, isNew, onRenamed, onTabWithError]);
  const saveRef = useRef(saveAll);
  saveRef.current = saveAll;

  // Debounced autosave: waits for a pause in editing, never loops on an error (it only re-arms on a change).
  useEffect(() => {
    if (!canSave || loading || autoDirty.length === 0) return;
    const timer = window.setTimeout(() => void saveRef.current('auto'), 1500);
    return () => window.clearTimeout(timer);
  }, [canSave, loading, autoDirty.length, valuesSig, abilitiesSig]);

  // Leaving the page with unsaved edits (tab close / reload).
  useEffect(() => {
    if (!hasUnsaved) return;
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [hasUnsaved]);

  const status: AutosaveState = saving ? 'saving' : saveError || errors.length ? 'error' : explicitDirty.length ? 'dirty' : savedAt ? 'saved' : 'idle';
  const conflict = !!saveError && /modified|timestamp|changed|conflict/i.test(saveError);
  const errorText = errors.length ? 'Fix the highlighted fields' : conflict ? 'Someone else changed this' : undefined;

  return {
    loading, ...meta, owner: meta.owner, desktopAccessStatus, status, errorText, errors, setErrors, savedAt, hasUnsaved,
    saveNow: () => saveAll('explicit'), retry: () => saveAll('explicit'),
    persistedAllowChat: baselineRef.current?.allow_chat ?? false, baselineVersion,
  };
}
