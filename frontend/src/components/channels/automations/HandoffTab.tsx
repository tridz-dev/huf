import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { updateGateway, type GatewayDoc } from '@/services/gatewayApi';
import { getEcosystemApps, type EcosystemApps } from '@/services/channels/channelsRulesApi';

export interface HandoffTabProps {
  gw: string;
  gateway: { handoff_target?: string; handoff_message?: string } | null;
  onSaved: () => void;
}

export function HandoffTab({ gw, gateway, onSaved }: HandoffTabProps) {
  const [target, setTarget] = useState(gateway?.handoff_target || 'none');
  const [message, setMessage] = useState(gateway?.handoff_message ?? '');
  const [apps, setApps] = useState<EcosystemApps>({ helpdesk: true, crm: true });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => { void getEcosystemApps().then(setApps); }, []);

  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      await updateGateway(gw, { handoff_target: target, handoff_message: message } as unknown as Partial<GatewayDoc>);
      toast.success('Handoff saved');
      onSaved();
    } catch (e) {
      setError(getFrappeErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">Handoff rules</CardTitle></CardHeader>
      <CardContent className="grid max-w-md gap-3">
        <p className="text-xs text-steel">
          A chat is handed to a person when a keyword rule with target Human matches, or when an agent asks for one.
          Add that rule under Routing rules.
        </p>
        <Field label="Hand off to" size="sm">
          {() => (
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger aria-label="Handoff target"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                <SelectItem value="helpdesk" disabled={!apps.helpdesk}>Help Desk{apps.helpdesk ? '' : ' (Not installed)'}</SelectItem>
                <SelectItem value="crm" disabled={!apps.crm}>CRM{apps.crm ? '' : ' (Not installed)'}</SelectItem>
              </SelectContent>
            </Select>
          )}
        </Field>
        <Field label="Message sent to the customer" size="sm">
          {(fp) => <Textarea {...fp} rows={3} value={message} onChange={(e) => setMessage(e.target.value)} />}
        </Field>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <div><Button onClick={submit} disabled={busy}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}Save</Button></div>
      </CardContent>
    </Card>
  );
}
