import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { AlertTriangle, ExternalLink, Loader2 } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { FieldHelp as FormDescription } from '@/components/decision/FieldHelp';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { formatTimeAgo } from '@/utils/time';
import { usePermissions } from '@/contexts/PermissionsContext';
import { QuestionBuilder, type PolicyDefinition } from '@/components/decision/QuestionBuilder';
import { RuntimeDisabledBanner } from '@/components/decision/RuntimeDisabledBanner';
import {
  listDecisionModels,
  validatePolicyDefinition,
  publishPolicyVersion,
  type DecisionModel,
} from '@/services/decisionApi';

export { DecisionPolicyEditor };
export default DecisionPolicyEditor;

const PURPOSE_OPTIONS = [
  'Generic',
  'Flow Routing',
  'Model Routing',
  'Agent Routing',
  'Tool Selection',
  'Skill Selection',
  'Procedure Selection',
  'RAG Filtering',
  'Context Relevance',
  'Input Guardrail',
  'Output Guardrail',
  'Output Verification',
];

interface DecisionPolicyDoc {
  name: string;
  policy_name?: string;
  purpose?: string;
  default_model?: string;
  description?: string;
  enabled?: 0 | 1;
  current_version?: string;
  definition_json?: string;
  fingerprint?: string;
  allow_api_access?: 0 | 1;
  max_candidates?: number;
}

interface PolicyVersionRow {
  name: string;
  version_number: number;
  status: 'Draft' | 'Published' | 'Retired';
  published_at?: string;
}

function emptyDefinition(policyId: string): PolicyDefinition {
  return { policy_id: policyId, questions: [], state_bindings: [] };
}

function parseDefinition(policyId: string, raw?: string): PolicyDefinition {
  if (!raw) return emptyDefinition(policyId);
  try {
    const parsed = JSON.parse(raw) as Partial<PolicyDefinition>;
    return {
      policy_id: parsed.policy_id || policyId,
      questions: parsed.questions || [],
      state_bindings: parsed.state_bindings || [],
      version: parsed.version,
      minimum_confidence: parsed.minimum_confidence,
      fallback_action: parsed.fallback_action,
      store_state: parsed.store_state,
      max_state_bytes: parsed.max_state_bytes,
      required_modalities: parsed.required_modalities,
    };
  } catch {
    return emptyDefinition(policyId);
  }
}

function DecisionPolicyEditor() {
  const { name } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { hasCapability } = usePermissions();
  const canAuthor = hasCapability('decision.author');
  const isAdmin = hasCapability('decision.admin');
  const isNew = !name || name === 'new';

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [doc, setDoc] = useState<DecisionPolicyDoc | null>(null);
  const [versions, setVersions] = useState<PolicyVersionRow[]>([]);
  const [models, setModels] = useState<DecisionModel[]>([]);

  // New-policy form fields (used only while isNew).
  const [newPolicyName, setNewPolicyName] = useState('');
  const [newPurpose, setNewPurpose] = useState('Generic');
  const [newModel, setNewModel] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newDefinitionJson, setNewDefinitionJson] = useState<string | undefined>(undefined);
  const [templates, setTemplates] = useState<DecisionPolicyDoc[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);

  // Existing-policy editable state.
  const [purpose, setPurpose] = useState('Generic');
  const [defaultModel, setDefaultModel] = useState('');
  const [description, setDescription] = useState('');
  const [allowApiAccess, setAllowApiAccess] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const [definition, setDefinition] = useState<PolicyDefinition>(emptyDefinition('new-policy'));

  const load = useCallback(async () => {
    if (isNew || !name) return;
    setLoading(true);
    try {
      const [policyDoc, versionRows] = await Promise.all([
        db.getDoc(doctype['Decision Policy'], name) as Promise<DecisionPolicyDoc>,
        db.getDocList(doctype['Decision Policy Version'], {
          fields: ['name', 'version_number', 'status', 'published_at'],
          filters: [['policy', '=', name]],
          orderBy: { field: 'version_number', order: 'desc' },
          limit: 100,
        }) as Promise<PolicyVersionRow[]>,
      ]);
      setDoc(policyDoc);
      setVersions(versionRows);
      setPurpose(policyDoc.purpose || 'Generic');
      setDefaultModel(policyDoc.default_model || '');
      setDescription(policyDoc.description || '');
      setAllowApiAccess(Boolean(policyDoc.allow_api_access));
      setEnabled(policyDoc.enabled !== 0);
      setDefinition(parseDefinition(policyDoc.name, policyDoc.definition_json));
    } catch (error) {
      handleFrappeError(error, `Error loading decision policy ${name}`);
    } finally {
      setLoading(false);
    }
  }, [isNew, name]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    listDecisionModels()
      .then(setModels)
      .catch((error) => handleFrappeError(error, 'Error loading decision models'));
  }, []);

  // "Start from a template" -- seeded example policies that were never published
  // (current_version unset), offered on the New policy screen (PLAN.md §3.4/§5.3).
  useEffect(() => {
    if (!isNew) return;
    setTemplatesLoading(true);
    db.getDocList(doctype['Decision Policy'], {
      fields: ['name', 'policy_name', 'purpose', 'default_model', 'description', 'definition_json'],
      filters: [['current_version', '=', '']],
      orderBy: { field: 'modified', order: 'desc' },
      limit: 20,
    })
      .then((rows) => setTemplates(rows as DecisionPolicyDoc[]))
      .catch((error) => handleFrappeError(error, 'Error loading policy templates'))
      .finally(() => setTemplatesLoading(false));
  }, [isNew]);

  function applyTemplate(template: DecisionPolicyDoc) {
    setSelectedTemplate(template.name);
    setNewPurpose(template.purpose || 'Generic');
    setNewModel(template.default_model || '');
    setNewDescription(template.description || '');
    setNewDefinitionJson(template.definition_json);
  }

  const modelsByName = useMemo(() => Object.fromEntries(models.map((m) => [m.name, m])), [models]);

  const selectedModel = isNew ? newModel : defaultModel;
  const unreachable = useMemo(() => {
    if (!isAdmin || !selectedModel) return false;
    const model = modelsByName[selectedModel];
    if (!model || !model.deployments) return false;
    return !model.deployments.some((d) => d.enabled);
  }, [isAdmin, selectedModel, modelsByName]);

  const latestVersion = versions[0];
  const publishedVersion = versions.find((v) => v.status === 'Published');

  async function handleCreate() {
    if (!newPolicyName.trim()) {
      toast.error('Policy name is required');
      return;
    }
    setSaving(true);
    try {
      const trimmedName = newPolicyName.trim();
      let definitionJson = newDefinitionJson;
      if (definitionJson) {
        try {
          const parsed = JSON.parse(definitionJson) as Partial<PolicyDefinition>;
          definitionJson = JSON.stringify({ ...parsed, policy_id: trimmedName });
        } catch {
          definitionJson = undefined;
        }
      }
      const created = (await db.createDoc(doctype['Decision Policy'], {
        policy_name: trimmedName,
        purpose: newPurpose,
        default_model: newModel || undefined,
        description: newDescription || undefined,
        definition_json: definitionJson,
      })) as DecisionPolicyDoc;
      toast.success('Policy created');
      navigate(`/decisions/${encodeURIComponent(created.name)}`, { replace: true });
    } catch (error) {
      handleFrappeError(error, 'Error creating decision policy');
    } finally {
      setSaving(false);
    }
  }

  async function handleSave() {
    if (!doc) return;
    if (definition.questions.length === 0) {
      toast.error('Add at least one question before saving');
      return;
    }
    setSaving(true);
    try {
      const result = await validatePolicyDefinition({ ...definition, policy_id: doc.name });
      if (!result.valid) {
        toast.error(result.message || 'Invalid policy definition');
        setSaving(false);
        return;
      }
      const updated = (await db.updateDoc(doctype['Decision Policy'], doc.name, {
        purpose,
        default_model: defaultModel || undefined,
        description: description || undefined,
        enabled: enabled ? 1 : 0,
        allow_api_access: allowApiAccess ? 1 : 0,
        definition_json: JSON.stringify({ ...definition, policy_id: doc.name }),
      })) as DecisionPolicyDoc;
      setDoc(updated);
      toast.success('Draft saved');
    } catch (error) {
      handleFrappeError(error, 'Error saving decision policy');
    } finally {
      setSaving(false);
    }
  }

  async function handlePublish() {
    if (!doc) return;
    setPublishing(true);
    try {
      await publishPolicyVersion(doc.name);
      toast.success('Policy published');
      await load();
    } catch (error) {
      handleFrappeError(error, `Error publishing ${doc.name}`);
    } finally {
      setPublishing(false);
    }
  }

  if (isNew) {
    return (
      <PageFrame title="New policy">
        <RuntimeDisabledBanner />
        <div className="max-w-xl space-y-5">
          {(templatesLoading || templates.length > 0) && (
            <div className="rounded-lg border border-line bg-panel p-4 space-y-2">
              <Label size="eyebrow">Start from a template</Label>
              <FormDescription>
                Copy the purpose, model, description and questions from a seeded example policy,
                then adjust it. Optional — leave unselected to start blank.
              </FormDescription>
              {templatesLoading ? (
                <div className="flex items-center gap-2 text-xs text-steel">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading templates...
                </div>
              ) : (
                <div className="flex flex-wrap gap-2 pt-1">
                  {templates.map((t) => (
                    <Button
                      key={t.name}
                      type="button"
                      variant={selectedTemplate === t.name ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => applyTemplate(t)}
                      disabled={!canAuthor}
                    >
                      {t.policy_name || t.name}
                    </Button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div>
            <Label htmlFor="policy-name">Policy name</Label>
            <Input
              id="policy-name"
              value={newPolicyName}
              onChange={(e) => setNewPolicyName(e.target.value)}
              placeholder="e.g. Support Urgency"
              className="mt-1.5"
              disabled={!canAuthor}
            />
            <FormDescription className="mt-1.5">
              Shown wherever this policy can be picked — flows, agent bindings, automations.
            </FormDescription>
          </div>

          <div>
            <Label htmlFor="policy-purpose">Purpose</Label>
            <Select value={newPurpose} onValueChange={setNewPurpose} disabled={!canAuthor}>
              <SelectTrigger id="policy-purpose" className="mt-1.5">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PURPOSE_OPTIONS.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FormDescription className="mt-1.5">
              What kind of decision this policy is used for — helps surfaces suggest the right
              policy when binding one.
            </FormDescription>
          </div>

          <div>
            <Label htmlFor="policy-model">Default model</Label>
            <Select value={newModel} onValueChange={setNewModel} disabled={!canAuthor}>
              <SelectTrigger id="policy-model" className="mt-1.5">
                <SelectValue placeholder="e.g. Jev 1.13" />
              </SelectTrigger>
              <SelectContent>
                {models.map((m) => (
                  <SelectItem key={m.name} value={m.name}>
                    {m.display_name || m.model_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FormDescription className="mt-1.5">
              The decision model this policy asks by default. Can be changed later; bindings can
              also pin a different one.
            </FormDescription>
          </div>

          <div>
            <Label htmlFor="policy-description">Description</Label>
            <Textarea
              id="policy-description"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              rows={3}
              placeholder="e.g. Flags support tickets that need urgent attention."
              className="mt-1.5"
              disabled={!canAuthor}
            />
          </div>

          <div className="flex gap-2 pt-2">
            <Button variant="outline" onClick={() => navigate('/decisions')} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!canAuthor || saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create policy
            </Button>
          </div>
          {!canAuthor && (
            <Alert variant="warning">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                You need the "Author decision policies" capability to create a policy. Ask a
                Decision Runtime admin to grant it.
              </AlertDescription>
            </Alert>
          )}
        </div>
      </PageFrame>
    );
  }

  if (loading) {
    return (
      <PageFrame title="Decision policy">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
        </div>
      </PageFrame>
    );
  }

  if (!doc) {
    return (
      <PageFrame title="Decision policy">
        <Alert variant="destructive" className="max-w-2xl">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Not found</AlertTitle>
          <AlertDescription>Decision policy "{name}" could not be loaded.</AlertDescription>
        </Alert>
      </PageFrame>
    );
  }

  const readOnly = !canAuthor;
  const statusLabel = publishedVersion
    ? `Published v${publishedVersion.version_number}`
    : latestVersion
      ? `${latestVersion.status} v${latestVersion.version_number}`
      : 'Draft';

  return (
    <PageFrame
      title={doc.policy_name || doc.name}
      badge={<Badge variant={publishedVersion ? 'success' : 'outline'}>{statusLabel}</Badge>}
      actions={
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              navigate(
                `/playground?mode=decision&policy=${encodeURIComponent(doc.name)}${
                  defaultModel ? `&model=${encodeURIComponent(defaultModel)}` : ''
                }`
              )
            }
          >
            Run in Playground
            <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
          </Button>
          {canAuthor && (
            <Button variant="outline" size="sm" onClick={handleSave} disabled={saving}>
              {saving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              Save
            </Button>
          )}
          {isAdmin && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button size="sm" onClick={handlePublish} disabled={publishing || definition.questions.length === 0}>
                    {publishing && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                    Publish
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>
                Publishes the saved draft as a new immutable version. The previous published
                version is retired; runs already pinned to it keep using it.
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      }
    >
      <RuntimeDisabledBanner />
      {readOnly && (
        <Alert className="mb-4">
          <AlertTitle>Read-only</AlertTitle>
          <AlertDescription>
            You have run access but not author access to this policy. Ask a Decision Runtime
            author or admin to make changes.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(300px,360px)]">
        {/* Input column */}
        <div className="min-w-0 space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label size="eyebrow">Purpose</Label>
              <Select value={purpose} onValueChange={setPurpose} disabled={readOnly}>
                <SelectTrigger className="mt-1.5">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PURPOSE_OPTIONS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription className="mt-1.5">
                What kind of decision this is used for.
              </FormDescription>
            </div>

            <div>
              <Label size="eyebrow">Model</Label>
              <Select value={defaultModel} onValueChange={setDefaultModel} disabled={readOnly}>
                <SelectTrigger className="mt-1.5">
                  <SelectValue placeholder="Choose a decision model" />
                </SelectTrigger>
                <SelectContent>
                  {models.map((m) => (
                    <SelectItem key={m.name} value={m.name}>
                      {m.display_name || m.model_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription className="mt-1.5">
                The decision model this policy asks by default.
              </FormDescription>
              {unreachable && (
                <Alert variant="warning" className="mt-2">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    This model has no enabled deployment. Publishing is still allowed, but runs
                    will fail until one is enabled on the Decision tab.
                  </AlertDescription>
                </Alert>
              )}
            </div>
          </div>

          <div>
            <Label size="eyebrow">Description</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              disabled={readOnly}
              placeholder="e.g. Flags support tickets that need urgent attention."
              className="mt-1.5"
            />
          </div>

          <div className="border-t border-line pt-6">
            <Label size="eyebrow">Questions</Label>
            <div className="mt-3">
              <QuestionBuilder value={definition} onChange={setDefinition} readOnly={readOnly} />
            </div>
          </div>

          {isAdmin && (
            <div className="border-t border-line pt-6 space-y-3">
              <Label size="eyebrow">API access</Label>
              <div className="flex items-center gap-3">
                <Switch checked={allowApiAccess} onCheckedChange={setAllowApiAccess} disabled={readOnly} />
                <span className="text-sm text-ink">Allow external API calls</span>
              </div>
              <FormDescription>
                When enabled, this policy can be called through the public Decision API using an
                API key, not just from inside Huf. Requires the policy to be published.
              </FormDescription>

              <div className="flex items-center gap-3 pt-2">
                <Switch checked={enabled} onCheckedChange={setEnabled} disabled={readOnly} />
                <span className="text-sm text-ink">Enabled</span>
              </div>
              <FormDescription>
                Disabling this policy makes every binding, flow node, and automation using it take
                its fallback path instead of calling the model.
              </FormDescription>
            </div>
          )}
        </div>

        {/* Consequence column */}
        <aside className="min-w-0 self-start xl:sticky xl:top-16 space-y-4">
          <div className="rounded-lg border border-line bg-panel p-4 space-y-2">
            <h3 className="font-mono text-eyebrow uppercase text-steel">Preview</h3>
            <p className="text-sm text-ink">
              {definition.questions.length} question{definition.questions.length === 1 ? '' : 's'}
            </p>
            {definition.questions.length > 0 && (
              <ul className="text-xs text-steel space-y-1">
                {definition.questions.map((q, i) => (
                  <li key={i} className="truncate">
                    <span className="font-mono">{q.kind}</span> — {q.id || `question ${i + 1}`}
                  </li>
                ))}
              </ul>
            )}
            <div className="pt-2 border-t border-line text-xs text-steel space-y-1">
              <div>
                Low confidence: <span className="text-ink">{definition.fallback_action || 'uncertain'}</span>
              </div>
              {definition.minimum_confidence !== undefined && (
                <div>
                  Minimum confidence: <span className="text-ink">{definition.minimum_confidence}</span>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-line bg-panel p-4 space-y-2">
            <h3 className="font-mono text-eyebrow uppercase text-steel">Versions</h3>
            {versions.length === 0 ? (
              <p className="text-xs text-steel">
                Not published yet. Save a draft, then Publish to create v1.
              </p>
            ) : (
              <ul className="text-xs space-y-1.5">
                {versions.map((v) => (
                  <li key={v.name} className="flex items-center justify-between gap-2">
                    <span className="font-mono text-ink">v{v.version_number}</span>
                    <Badge variant={v.status === 'Published' ? 'success' : v.status === 'Retired' ? 'secondary' : 'outline'} size="sm">
                      {v.status}
                    </Badge>
                    <span className="text-steel-soft truncate">
                      {v.published_at ? formatTimeAgo(v.published_at) : '—'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>
    </PageFrame>
  );
}
