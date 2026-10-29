import { useEffect, useState } from 'react';
import { Save } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { loadCodeFlowStatus, refreshCodeFlowStatus, useCodeFlowStatus } from '@/lib/flow-graph/useCodeFlowStatus';
import { getAgentSettings, updateAgentSettings } from '@/services/agentSettingsApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { PageFrame } from '@/layouts/PageFrame';

const DEFAULT_DESTINATIONS = {
  'huf-skills': {
    repo_url: 'https://github.com/tridz-dev/huf-skills',
    path: 'skills',
    ref: 'main',
  },
};

function formatDestinations(value: string | null | undefined): string {
  if (!value) return JSON.stringify(DEFAULT_DESTINATIONS, null, 2);
  try {
    const parsed = JSON.parse(value);
    return JSON.stringify({ ...DEFAULT_DESTINATIONS, ...parsed }, null, 2);
  } catch {
    return value;
  }
}

export function AgentSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [jsonValue, setJsonValue] = useState('');
  const { status: codeStatus } = useCodeFlowStatus();
  const [togglingCode, setTogglingCode] = useState(false);

  useEffect(() => {
    // Agent Settings can only be read by a System Manager: for anyone else a failed load is expected, not an error.
    Promise.all([getAgentSettings().then((doc) => ({ doc, error: null as unknown })).catch((error) => ({ doc: undefined, error })), loadCodeFlowStatus()])
      .then(([result, status]) => {
        if (result.error && status?.can_manage !== false) {
          toast.error(getFrappeErrorMessage(result.error) || 'Failed to load Agent Settings');
        }
        setJsonValue(formatDestinations(result.doc?.skill_destinations));
      })
      .finally(() => setLoading(false));
  }, []);

  const handleToggleCode = async (next: boolean) => {
    setTogglingCode(true);
    try {
      await updateAgentSettings({ allow_code_in_flows: next ? 1 : 0 });
      await refreshCodeFlowStatus();
      toast.success(next ? 'Code execution in Flows turned on' : 'Code execution in Flows turned off');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to change code execution in Flows');
    } finally {
      setTogglingCode(false);
    }
  };

  const handleSave = async () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(jsonValue);
    } catch {
      toast.error('Skill destinations is not valid JSON');
      return;
    }

    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      toast.error('Skill destinations must be a JSON object keyed by destination name');
      return;
    }

    setSaving(true);
    try {
      await updateAgentSettings({ skill_destinations: JSON.stringify(parsed) });
      toast.success('Agent Settings saved');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to save Agent Settings');
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

  return (
    <PageFrame
      title="Agent settings"
      className="max-w-4xl mx-auto"
    >
      <Card data-testid="settings-code-in-flows">
        <CardHeader>
          <CardTitle>Code in Flows</CardTitle>
          <CardDescription>
            Lets Flows run Python code inside a sandbox. Off by default.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="allow_code_in_flows">Allow code execution in Flows</Label>
            <Switch
              id="allow_code_in_flows"
              data-testid="settings-code-in-flows-switch"
              checked={Boolean(codeStatus?.allowed)}
              disabled={!codeStatus?.can_manage || togglingCode}
              onCheckedChange={handleToggleCode}
            />
          </div>
          {codeStatus && !codeStatus.can_manage && (
            <p className="text-xs text-muted-foreground" data-testid="settings-code-in-flows-note">
              Only a system administrator can change this.
            </p>
          )}
          {codeStatus && (
            <p
              className={codeStatus.server_switch ? 'text-xs text-good' : 'text-xs text-warning'}
              data-testid="settings-code-in-flows-status"
            >
              {codeStatus.server_switch
                ? 'Server switch: on'
                : 'Server switch: off - code cannot run until a server administrator turns on huf_python_execution_enabled in the site configuration.'}
            </p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Skill destinations</CardTitle>
          <CardDescription>
            Configure common skill sources used by the Skills import modal and marketplace.
            The default <code>huf-skills</code> destination points to the official curated registry.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="skill_destinations">Destinations JSON</Label>
            <Textarea
              id="skill_destinations"
              value={jsonValue}
              onChange={(e) => setJsonValue(e.target.value)}
              className="min-h-[280px] font-mono text-sm"
              placeholder='{"my-skills": {"repo_url": "https://github.com/org/repo", "path": "skills", "ref": "main"}}'
            />
            <p className="text-xs text-muted-foreground">
              Enter a JSON object keyed by destination name. Each value must include{' '}
              <code>repo_url</code>, optionally <code>path</code> and <code>ref</code>.
            </p>
          </div>
          <div className="flex justify-end">
            <Button onClick={handleSave} disabled={saving}>
              {saving && <span className="mr-2 animate-spin">⟳</span>}
              <Save className="w-4 h-4 mr-2" />
              Save destinations
            </Button>
          </div>
        </CardContent>
      </Card>
    </PageFrame>
  );
}

export default AgentSettingsPage;
