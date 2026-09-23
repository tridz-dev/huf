import { useEffect, useState } from 'react';
import { Save } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import {
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
} from '@/components/ui/form';
import { Switch } from '@/components/ui/switch';
import { getAgentSettings, updateAgentSettings, type AgentSettingsDoc } from '@/services/agentSettingsApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { PageFrame } from '@/layouts/PageFrame';
import { usePermissions } from '@/contexts/PermissionsContext';

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
  const [settings, setSettings] = useState<AgentSettingsDoc | undefined>();
  const { hasCapability } = usePermissions();

  const canEditDecisionRuntime = hasCapability('decision.admin');

  useEffect(() => {
    getAgentSettings()
      .then((doc) => {
        if (doc) {
          setSettings(doc);
          setJsonValue(formatDestinations(doc.skill_destinations));
        }
      })
      .catch((error) => {
        toast.error(getFrappeErrorMessage(error) || 'Failed to load Agent Settings');
        setJsonValue(formatDestinations(''));
      })
      .finally(() => setLoading(false));
  }, []);

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
      const updates: Partial<AgentSettingsDoc> = {
        skill_destinations: JSON.stringify(parsed),
      };

      // Add Decision Runtime settings if user has permission
      if (canEditDecisionRuntime && settings) {
        updates.decision_runtime_enabled = settings.decision_runtime_enabled;
        updates.decision_shadow_rate_per_minute = settings.decision_shadow_rate_per_minute;
      }

      await updateAgentSettings(updates);
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

      {canEditDecisionRuntime && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Decision Runtime</CardTitle>
            <CardDescription>
              Enable and configure the Decision Runtime for policy-based decisions.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <FormItem className="flex flex-row items-center justify-between rounded-md border p-4">
              <div className="space-y-0.5 pr-4 flex-1">
                <FormLabel className="text-base">Decision Runtime Enabled</FormLabel>
                <FormDescription>
                  When off, all Decision policies are bypassed and no Decision calls will be made.
                  Flows follow their uncertain path, and bindings behave as Off.
                </FormDescription>
              </div>
              <FormControl>
                <Switch
                  checked={settings?.decision_runtime_enabled === 1}
                  onCheckedChange={(checked) => {
                    if (settings) {
                      setSettings({
                        ...settings,
                        decision_runtime_enabled: checked ? 1 : 0,
                      });
                    }
                  }}
                />
              </FormControl>
            </FormItem>

            <FormItem>
              <FormLabel>Shadow Rate Per Minute</FormLabel>
              <FormControl>
                <Input
                  type="number"
                  placeholder="120"
                  value={settings?.decision_shadow_rate_per_minute || '120'}
                  onChange={(e) => {
                    if (settings) {
                      setSettings({
                        ...settings,
                        decision_shadow_rate_per_minute: parseInt(e.target.value, 10) || 120,
                      });
                    }
                  }}
                />
              </FormControl>
              <FormDescription>
                Maximum number of shadow Decision calls per minute site-wide. Shadow calls measure
                policy impact without affecting production behavior.
              </FormDescription>
            </FormItem>
          </CardContent>
        </Card>
      )}
    </PageFrame>
  );
}

export default AgentSettingsPage;
