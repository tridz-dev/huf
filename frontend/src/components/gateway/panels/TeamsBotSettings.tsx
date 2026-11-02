import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  errorText,
  saveTeamsBotSettings,
  type TeamsPrivateOutputPolicy,
  type TeamsSettings,
} from '@/services/gateways/teamsApi';

export const DEFAULT_PRIVATE_OUTPUT_POLICY: TeamsPrivateOutputPolicy = 'Private when records touched';

interface TeamsBotSettingsProps {
  gateway: string;
  settings: TeamsSettings | null;
  disabled?: boolean;
}

/** Bot name, where private answers go, and custom help text. */
export function TeamsBotSettings({ gateway, settings, disabled }: TeamsBotSettingsProps) {
  const [handle, setHandle] = useState('');
  const [policy, setPolicy] = useState<TeamsPrivateOutputPolicy>(DEFAULT_PRIVATE_OUTPUT_POLICY);
  const [help, setHelp] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!settings) return;
    setHandle(settings.bot_handle ?? '');
    setPolicy(settings.private_output_policy || DEFAULT_PRIVATE_OUTPUT_POLICY);
    setHelp(settings.help_text_override ?? '');
  }, [settings]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await saveTeamsBotSettings(gateway, {
        bot_handle: handle,
        private_output_policy: policy,
        help_text_override: help,
      });
      toast.success('Bot settings saved');
    } catch (e) {
      setError(errorText(e, 'Could not save the bot settings'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="space-y-3" aria-labelledby="teams-bot-settings">
      <p id="teams-bot-settings" className="text-sm font-medium">Bot behaviour</p>
      <Field label="Bot name" hint="The name people type to mention the bot, for example @Huf." size="sm">
        {(fp) => <Input {...fp} value={handle} onChange={(e) => setHandle(e.target.value)} disabled={disabled || saving} />}
      </Field>
      <Field label="Where to send answers" hint="Private answers go to the person in a personal chat." size="sm">
        {(fp) => (
          <Select value={policy} onValueChange={(v) => setPolicy(v as TeamsPrivateOutputPolicy)} disabled={disabled || saving}>
            <SelectTrigger {...fp}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Always private">Always private</SelectItem>
              <SelectItem value="Private when records touched">Private when business records are touched</SelectItem>
              <SelectItem value="Channel">Reply in the channel</SelectItem>
            </SelectContent>
          </Select>
        )}
      </Field>
      <Field label="Help text" hint="Replaces the built-in reply to &quot;help&quot;. Leave empty for the default." size="sm">
        {(fp) => <Textarea {...fp} rows={3} value={help} onChange={(e) => setHelp(e.target.value)} disabled={disabled || saving} />}
      </Field>
      <Button type="button" size="sm" onClick={save} disabled={disabled || saving}>
        {saving && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
        Save bot settings
      </Button>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </section>
  );
}
