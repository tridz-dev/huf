import { useEffect, useMemo, useState } from 'react';
import { Save } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { SkillSourcesEditor } from '@/components/settings/SkillSourcesEditor';
import { SkillSourcesReadOnly } from '@/components/settings/SkillSourcesReadOnly';
import { loadCodeFlowStatus, refreshCodeFlowStatus, useCodeFlowStatus } from '@/lib/flow-graph/useCodeFlowStatus';
import { getAgentSettings, updateAgentSettings } from '@/services/agentSettingsApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { jsonFromRows, problemWithRows, rowsFromStored, type SkillSourceRow } from '@/lib/skills/skillSources';
import { PageFrame } from '@/layouts/PageFrame';

/** Code and skills: whether flows may run code, and where skills can be imported from. Only a system administrator can change either. */
export function AgentSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<SkillSourceRow[]>(() => rowsFromStored(null));
  const [savedJson, setSavedJson] = useState(() => jsonFromRows(rowsFromStored(null)));
  const { status: codeStatus } = useCodeFlowStatus();
  const [togglingCode, setTogglingCode] = useState(false);

  useEffect(() => {
    // Agent Settings can only be read by a System Manager: ask whether this person is one first, and never ask the server
    // for a document it will refuse (a refused read shows up as a failing call and a console error for everyone else).
    loadCodeFlowStatus()
      .then(async (status) => {
        if (status?.can_manage === false) return;
        const result = await getAgentSettings().then((doc) => ({ doc, error: null as unknown })).catch((error) => ({ doc: undefined, error }));
        if (result.error) toast.error(getFrappeErrorMessage(result.error) || 'Failed to load these settings');
        const loaded = rowsFromStored(result.doc?.skill_destinations);
        setRows(loaded);
        setSavedJson(jsonFromRows(loaded));
      })
      .finally(() => setLoading(false));
  }, []);

  const canManage = Boolean(codeStatus?.can_manage);
  const dirty = useMemo(() => jsonFromRows(rows) !== savedJson, [rows, savedJson]);

  const handleToggleCode = async (next: boolean) => {
    setTogglingCode(true);
    try {
      await updateAgentSettings({ allow_code_in_flows: next ? 1 : 0 });
      await refreshCodeFlowStatus();
      toast.success(next ? 'Flows can now run code' : 'Flows can no longer run code');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Could not change this setting');
    } finally {
      setTogglingCode(false);
    }
  };

  const handleSave = async () => {
    const problem = problemWithRows(rows);
    if (problem) {
      toast.error(problem);
      return;
    }
    setSaving(true);
    try {
      const json = jsonFromRows(rows);
      await updateAgentSettings({ skill_destinations: json });
      setSavedJson(json);
      toast.success('Skill sources saved');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Could not save the skill sources');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-muted-foreground">Loading settings...</div>
      </div>
    );
  }

  const serverAllows = Boolean(codeStatus?.server_switch);

  return (
    <PageFrame title="Code and skills" className="max-w-4xl">
      <Card data-testid="settings-code-in-flows">
        <CardHeader>
          <CardTitle>Code in flows</CardTitle>
          <CardDescription>
            Lets a flow step run a short piece of code you write. It is off until a system administrator turns it on.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="allow_code_in_flows">Allow code in flows</Label>
            <Switch
              id="allow_code_in_flows"
              data-testid="settings-code-in-flows-switch"
              checked={Boolean(codeStatus?.allowed)}
              disabled={!canManage || togglingCode}
              onCheckedChange={handleToggleCode}
            />
          </div>
          {codeStatus && !canManage && (
            <p className="text-sm text-muted-foreground" data-testid="settings-code-in-flows-note">
              Only a system administrator can change this.
            </p>
          )}
          {codeStatus && (
            <p
              className={serverAllows ? 'text-sm text-good' : 'text-sm text-warning'}
              data-testid="settings-code-in-flows-status"
            >
              {serverAllows
                ? canManage
                  ? 'Your server administrator allows code to run on this site.'
                  : 'Code can run on this site once a system administrator allows it.'
                : 'Code cannot run on this site yet. Ask your server administrator to turn it on first.'}
            </p>
          )}
        </CardContent>
      </Card>

      {canManage ? (
        <Card data-testid="settings-skill-sources-editor">
          <CardHeader>
            <CardTitle>Skill sources</CardTitle>
            <CardDescription>
              Where skills can be imported from. The first one, huf-skills, is the official collection.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <SkillSourcesEditor rows={rows} onChange={setRows} />
            <div className="flex justify-end">
              <Button onClick={handleSave} disabled={saving || !dirty} data-testid="settings-skill-sources-save">
                {saving && <span className="mr-2 animate-spin">⟳</span>}
                <Save className="mr-2 h-4 w-4" />
                Save skill sources
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <SkillSourcesReadOnly />
      )}
    </PageFrame>
  );
}

export default AgentSettingsPage;
