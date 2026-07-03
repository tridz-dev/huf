import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getAgentSettings, updateAgentSettings, type AgentSettingsDoc } from '@/services/agentSettingsApi';
import { getProviders, getModels } from '@/services/providerApi';
import type { AIProvider, AIModel } from '@/types/agent.types';

export { AgentSettingsPage };
export default AgentSettingsPage;

function AgentSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);
  const [defaultProvider, setDefaultProvider] = useState<string | undefined>();
  const [defaultModel, setDefaultModel] = useState<string | undefined>();

  useEffect(() => {
    (async () => {
      setLoading(true);
      const [providersRes, settings] = await Promise.all([getProviders(), getAgentSettings()]);
      setProviders(Array.isArray(providersRes) ? providersRes : providersRes.items);
      setDefaultProvider(settings?.default_provider || undefined);
      setDefaultModel(settings?.default_model || undefined);
      setLoading(false);
    })();
  }, []);

  useEffect(() => {
    if (!defaultProvider) {
      setModels([]);
      return;
    }
    getModels(defaultProvider).then(setModels);
  }, [defaultProvider]);

  const handleSave = async () => {
    if (defaultModel && !models.some((m) => m.name === defaultModel)) {
      toast.error('Default Model must belong to the selected Default Provider');
      return;
    }
    setSaving(true);
    try {
      const data: AgentSettingsDoc = {
        default_provider: defaultProvider || undefined,
        default_model: defaultModel || undefined,
      };
      await updateAgentSettings(data);
      toast.success('Agent Settings saved');
    } catch {
      // handleFrappeError in the service already surfaces a toast
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-2xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Agent Settings</h1>
          <p className="text-sm text-muted-foreground">
            Default provider and model applied when a new agent doesn't specify its own.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Defaults</CardTitle>
            <CardDescription>
              Used as a fallback for new agents that don't select a provider/model explicitly.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Default Provider</Label>
              <Select
                value={defaultProvider || ''}
                onValueChange={(v) => {
                  setDefaultProvider(v || undefined);
                  setDefaultModel(undefined);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((p) => (
                    <SelectItem key={p.name} value={p.name}>
                      {p.provider_name || p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Default Model</Label>
              <Select
                value={defaultModel || ''}
                onValueChange={(v) => setDefaultModel(v || undefined)}
                disabled={!defaultProvider}
              >
                <SelectTrigger>
                  <SelectValue placeholder={defaultProvider ? 'Select model' : 'Select a provider first'} />
                </SelectTrigger>
                <SelectContent>
                  {models.map((m) => (
                    <SelectItem key={m.name} value={m.name}>
                      {m.model_name || m.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
          <div className="flex justify-end p-6 pt-0">
            <Button onClick={handleSave} disabled={saving}>
              {saving && <Loader2 className="h-4 w-4 animate-spin" />}
              Save
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
