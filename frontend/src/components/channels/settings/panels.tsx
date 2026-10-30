import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { updateGateway, WHATSAPP_GATEWAY_FIELDS, type GatewayDoc } from '@/services/gatewayApi';
import type { GatewayHealthStatus, TokenCheckSummary, WhatsAppAccountSummary } from '@/services/whatsappHealthApi';
import { ConnectionCard } from '@/components/whatsapp/overview/ConnectionCard';
import { CredentialsCard } from '@/components/whatsapp/overview/CredentialsCard';
import { PolicySection } from '@/components/whatsapp/overview/PolicySection';
import { AccessTab } from '@/components/whatsapp/AccessTab';
import { WhatsAppChannelSettings } from '@/components/integrations/WhatsAppChannelSettings';
import { validateRunAs, WEEKDAYS, type BusinessHourRow, type BusinessHolidayRow, type GatewayFull } from './model';

const save = (name: string, patch: Record<string, unknown>) => updateGateway(name, patch as Partial<GatewayDoc>);

export interface PanelProps {
  gw: string;
  health: GatewayHealthStatus;
  gateway: GatewayFull | null;
  accounts: WhatsAppAccountSummary[];
  /** In-shell link to the credentials section (replaces the old gateway detour). */
  credentialsHref: string;
  onCheckToken: () => Promise<TokenCheckSummary>;
  onSaved: () => void;
}

export function ConnectionPanel({ health, accounts, credentialsHref }: PanelProps) {
  const account = accounts.find((a) => a.name === health.whatsapp_account);
  return (
    <div className="space-y-4">
      <ConnectionCard
        webhookUrl={health.webhook_url}
        verifyTokenPresent={health.verify_token_present}
        phoneNumberId={health.phone_number_id}
        phone={health.token_check?.phone}
        metaLinks={health.meta_links}
        integrationSettingsHref={credentialsHref}
      />
      <Card>
        <CardHeader><CardTitle className="text-sm">Gateway</CardTitle></CardHeader>
        <CardContent>
          <dl className="grid gap-3 sm:grid-cols-2">
            <div><dt className="text-xs text-steel">Status</dt><dd className="text-sm text-ink">{health.enabled ? 'On' : 'Off'}</dd></div>
            <div><dt className="text-xs text-steel">Linked WhatsApp account</dt>
              <dd className="text-sm text-ink">{health.whatsapp_account || 'None'}{account?.status ? ` (${account.status})` : ''}</dd></div>
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}

export function CredentialsPanel({ health, onCheckToken, credentialsHref }: PanelProps) {
  return (
    <CredentialsCard
      accessTokenPresent={health.access_token_present}
      appSecretPresent={health.app_secret_present}
      verifyTokenPresent={health.verify_token_present}
      appIdPresent={health.app_id_present}
      tokenCheck={health.token_check}
      onCheckToken={onCheckToken}
      integrationSettingsHref={credentialsHref}
    />
  );
}

export function PolicyPanel({ health }: PanelProps) {
  return (
    <PolicySection
      fallbackTemplate={health.fallback_template}
      fallbackTemplateLanguage={health.fallback_template_language}
      fallbackTemplateApproved={health.fallback_template_approved}
      policy={health.policy}
      defaultOpen
    />
  );
}

export function AccessPanel({ gw }: PanelProps) {
  return <AccessTab gateway={gw} />;
}

export function RunAsPanel({ gw, gateway, onSaved }: PanelProps) {
  const [user, setUser] = useState(gateway?.run_as_user ?? '');
  const [profile, setProfile] = useState(gateway?.run_as_role_profile ?? '');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    const err = validateRunAs(user);
    if (err) { setError(err); return; }
    setError('');
    setBusy(true);
    try {
      await save(gw, { run_as_user: user.trim(), run_as_role_profile: profile.trim() });
      toast.success('Run-as saved');
      onSaved();
    } catch (e) {
      setError(getFrappeErrorMessage(e));
    }
    setBusy(false);
  };
  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">Run as</CardTitle></CardHeader>
      <CardContent className="grid max-w-md gap-3">
        <p className="text-xs text-steel">Agents answering on this number act as this user. Never Administrator. Admins (System Manager or integrations-manage users) are rejected.</p>
        <Field label="Run as user" error={error} size="sm">
          {(fp) => <Input {...fp} value={user} onChange={(e) => setUser(e.target.value)} placeholder="user@example.com" />}
        </Field>
        <Field label="Run as role profile" size="sm">
          {(fp) => <Input {...fp} value={profile} onChange={(e) => setProfile(e.target.value)} />}
        </Field>
        <div><Button onClick={submit} disabled={busy}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}Save</Button></div>
      </CardContent>
    </Card>
  );
}

export function HoursPanel({ gw, gateway, onSaved }: PanelProps) {
  const [enabled, setEnabled] = useState(!!gateway?.business_hours_enabled);
  const [rows, setRows] = useState<BusinessHourRow[]>(gateway?.business_hours ?? []);
  const [holidays, setHolidays] = useState<BusinessHolidayRow[]>(gateway?.holidays ?? []);
  const [holidayList, setHolidayList] = useState(gateway?.holiday_list ?? '');
  const [mode, setMode] = useState(gateway?.after_hours_mode ?? 'agent_24_7');
  const [message, setMessage] = useState(gateway?.away_message ?? '');
  const [template, setTemplate] = useState(gateway?.away_template ?? '');
  const [busy, setBusy] = useState(false);
  const setRow = (i: number, patch: Partial<BusinessHourRow>) =>
    setRows((r) => r.map((row, j) => (j === i ? { ...row, ...patch } : row)));
  const setHolidayRow = (i: number, patch: Partial<BusinessHolidayRow>) =>
    setHolidays((r) => r.map((row, j) => (j === i ? { ...row, ...patch } : row)));
  const submit = async () => {
    setBusy(true);
    try {
      await save(gw, {
        business_hours_enabled: enabled ? 1 : 0, business_hours: rows,
        holidays: holidays.filter((h) => h.holiday_date),
        holiday_list: holidayList,
        after_hours_mode: mode, away_message: message, away_template: template,
      });
      toast.success('Business hours saved');
      onSaved();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e));
    }
    setBusy(false);
  };
  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">Business hours</CardTitle></CardHeader>
      <CardContent className="grid max-w-xl gap-3">
        <Field label="Use business hours" size="sm">
          {(fp) => <div className="flex h-control-md items-center"><Switch {...fp} checked={enabled} onCheckedChange={setEnabled} /></div>}
        </Field>
        {rows.map((row, i) => (
          <div key={i} className="flex items-end gap-2">
            <Field label="Day" size="sm">
              {(fp) => (
                <Select value={row.weekday} onValueChange={(v) => setRow(i, { weekday: v })}>
                  <SelectTrigger id={fp.id} aria-label={`Day ${i + 1}`}><SelectValue /></SelectTrigger>
                  <SelectContent>{WEEKDAYS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
                </Select>
              )}
            </Field>
            <Field label="From" size="sm">{(fp) => <Input {...fp} type="time" value={row.start_time} onChange={(e) => setRow(i, { start_time: e.target.value })} />}</Field>
            <Field label="To" size="sm">{(fp) => <Input {...fp} type="time" value={row.end_time} onChange={(e) => setRow(i, { end_time: e.target.value })} />}</Field>
            <Button variant="ghost" onClick={() => setRows((r) => r.filter((_, j) => j !== i))}>Remove</Button>
          </div>
        ))}
        <div><Button variant="outline" onClick={() => setRows((r) => [...r, { weekday: 'Monday', start_time: '09:00', end_time: '17:00' }])}>Add hours</Button></div>
        <div className="grid gap-2">
          <span className="text-sm font-medium">Holidays</span>
          {holidays.map((h, i) => (
            <div key={i} className="flex items-end gap-2">
              <Field label="Date" size="sm">
                {(fp) => <Input {...fp} type="date" aria-label={`Holiday date ${i + 1}`} value={h.holiday_date} onChange={(e) => setHolidayRow(i, { holiday_date: e.target.value })} />}
              </Field>
              <Field label="Description" size="sm">
                {(fp) => <Input {...fp} value={h.description ?? ''} onChange={(e) => setHolidayRow(i, { description: e.target.value })} />}
              </Field>
              <Button variant="ghost" onClick={() => setHolidays((r) => r.filter((_, j) => j !== i))}>Remove</Button>
            </div>
          ))}
          <div><Button variant="outline" onClick={() => setHolidays((r) => [...r, { holiday_date: '', description: '' }])}>Add holiday</Button></div>
        </div>
        <Field label="ERPNext Holiday List name (optional)" size="sm">{(fp) => <Input {...fp} value={holidayList} onChange={(e) => setHolidayList(e.target.value)} />}</Field>
        <Field label="After hours" size="sm">
          {(fp) => (
            <Select value={mode} onValueChange={(v) => setMode(v as typeof mode)}>
              <SelectTrigger id={fp.id}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="agent_24_7">Agent keeps answering</SelectItem>
                <SelectItem value="away_message">Send an away message</SelectItem>
                <SelectItem value="away_template">Send an away template</SelectItem>
              </SelectContent>
            </Select>
          )}
        </Field>
        {mode === 'away_message' && (
          <Field label="Away message" size="sm">{(fp) => <Textarea {...fp} value={message} onChange={(e) => setMessage(e.target.value)} />}</Field>
        )}
        {mode === 'away_template' && (
          <Field label="Away template" size="sm">{(fp) => <Input {...fp} value={template} onChange={(e) => setTemplate(e.target.value)} />}</Field>
        )}
        <div><Button onClick={submit} disabled={busy}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}Save</Button></div>
      </CardContent>
    </Card>
  );
}

export function RepliesPanel({ gw, gateway, onSaved }: PanelProps) {
  const [doc, setDoc] = useState<GatewayDoc | null>(gateway);
  const [busy, setBusy] = useState(false);
  if (!doc) return <p className="text-sm text-steel">Could not load the number's settings.</p>;
  const submit = async () => {
    setBusy(true);
    try {
      await save(gw, Object.fromEntries(WHATSAPP_GATEWAY_FIELDS.map((f) => [f, doc[f] ?? null])));
      toast.success('Settings saved');
      onSaved();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e));
    }
    setBusy(false);
  };
  return (
    <div className="space-y-4">
      <WhatsAppChannelSettings gateway={doc} onChange={(p) => setDoc((d) => (d ? { ...d, ...p } : d))} />
      <Button onClick={submit} disabled={busy}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}Save</Button>
    </div>
  );
}

export function DangerPanel({ gw, health, onSaved }: PanelProps) {
  const [open, setOpen] = useState(false);
  const disable = async () => {
    try {
      await save(gw, { is_enabled: 0 });
      toast.success('Number turned off');
      onSaved();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e));
    }
    setOpen(false);
  };
  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">Turn off this number</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-steel">The agent stops replying and incoming messages are ignored until you turn it back on.</p>
        <Button variant="destructive" disabled={!health.enabled} onClick={() => setOpen(true)}>
          {health.enabled ? 'Disable gateway' : 'Already off'}
        </Button>
        <AlertDialog open={open} onOpenChange={setOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Disable this gateway?</AlertDialogTitle>
              <AlertDialogDescription>Nobody will get replies on this number until it is turned on again.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={disable}>Disable</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  );
}
