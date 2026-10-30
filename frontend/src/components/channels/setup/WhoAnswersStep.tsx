import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getAvailableAgents } from '@/services/gatewayApi';
import { bindAgent } from './setupApi';

export interface WhoAnswersStepProps {
  gateway: string;
  onBound: () => void;
}

export function WhoAnswersStep({ gateway, onBound }: WhoAnswersStepProps) {
  const [agents, setAgents] = useState<{ name: string; agent_name: string }[] | null>(null);
  const [agent, setAgent] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void getAvailableAgents().then((a) => live && setAgents(a));
    return () => {
      live = false;
    };
  }, []);

  const save = async () => {
    setSaving(true);
    setError(null);
    const res = await bindAgent(gateway, agent);
    setSaving(false);
    if (res.ok) onBound();
    else setError(res.error);
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-steel">Pick the agent that replies when someone messages this number.</p>
      <div className="space-y-1.5">
        <Label htmlFor="wa-agent">Agent</Label>
        <Select value={agent} onValueChange={setAgent}>
          <SelectTrigger id="wa-agent">
            <SelectValue placeholder={agents === null ? 'Loading agents...' : 'Choose an agent'} />
          </SelectTrigger>
          <SelectContent>
            {(agents ?? []).map((a) => (
              <SelectItem key={a.name} value={a.name}>
                {a.agent_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={!agent || saving}>
          {saving ? 'Saving...' : 'Use this agent'}
        </Button>
        <Link className="text-sm text-primary underline-offset-2 hover:underline" to={`/solutions/new?gateway=${encodeURIComponent(gateway)}`}>
          Start from a Solution template
        </Link>
      </div>
      <p className="text-xs text-steel">
        Handoff to Help Desk or CRM and routing rules are set later in{' '}
        <Link className="text-primary underline-offset-2 hover:underline" to={`/channels/whatsapp/n/${encodeURIComponent(gateway)}/automations`}>
          Automations
        </Link>
        .
      </p>
    </div>
  );
}
