import { useEffect, useState } from 'react';
import { Save } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
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

  useEffect(() => {
    getAgentSettings()
      .then((doc) => {
        setJsonValue(formatDestinations(doc?.skill_destinations));
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
      title="Agent Settings"
      subtitle="Global configuration for agents and skills"
      className="max-w-4xl mx-auto"
    >
      <Card>
        <CardHeader>
          <CardTitle>Skill Destinations</CardTitle>
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
