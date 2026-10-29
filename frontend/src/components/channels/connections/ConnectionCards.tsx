import { useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, Headset, Lock, Package, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { EcosystemApp, EcosystemKey } from '@/services/channelsApi';

export type ConnState = 'connected' | 'installed' | 'absent';

export function connState(app?: EcosystemApp): ConnState {
  if (!app?.installed) return 'absent';
  return app.enabled_for_whatsapp ? 'connected' : 'installed';
}

const STATE_PILL: Record<ConnState, { label: string; variant: 'pill-success' | 'pill-warning' | 'pill-neutral' }> = {
  connected: { label: 'Connected', variant: 'pill-success' },
  installed: { label: 'Installed — not connected', variant: 'pill-warning' },
  absent: { label: 'Not installed', variant: 'pill-neutral' },
};

export interface CardDef {
  key: Exclude<EcosystemKey, 'lms' | 'ravan'>;
  title: string;
  value: string;
  creates: string;
  Icon: typeof Headset;
  docs: string;
}

export const CARDS: CardDef[] = [
  { key: 'helpdesk', title: 'Help Desk', value: 'Hand tough chats to your support team as tickets.', creates: 'HD Ticket', Icon: Headset, docs: 'https://frappe.io/helpdesk' },
  { key: 'crm', title: 'CRM', value: 'Turn every new contact into a lead automatically.', creates: 'CRM Lead', Icon: Users, docs: 'https://frappe.io/crm' },
  { key: 'erpnext', title: 'ERPNext', value: 'Let customers order over chat; you confirm the sale.', creates: 'draft Sales Order', Icon: Package, docs: 'https://frappe.io/erpnext' },
];

export function ConnectionCard({ def, app, isAdmin }: { def: CardDef; app?: EcosystemApp; isAdmin: boolean }) {
  const state = connState(app);
  const pill = STATE_PILL[state];
  const [confirm, setConfirm] = useState(false);
  const { Icon } = def;
  return (
    <section aria-label={def.title} data-state={state} className="flex flex-col gap-3 rounded-sm border border-line bg-card p-4">
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 h-5 w-5 text-steel" aria-hidden />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium text-ink">{def.title}</h3>
          <p className="text-xs text-steel">{def.value}</p>
        </div>
        <Badge variant={pill.variant}>{pill.label}</Badge>
      </div>
      {state !== 'absent' && (
        <>
          <p className="text-xs text-steel">Detected{app?.version ? ` · v${app.version}` : ''}</p>
          <p className="text-xs text-ink">Handoffs create a <span className="font-mono">{def.creates}</span>.</p>
          <div>
            <Button size="sm" variant="outline" onClick={() => setConfirm(true)}>Test handoff</Button>
          </div>
          <AlertDialog open={confirm} onOpenChange={setConfirm}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Test handoff to {def.title}</AlertDialogTitle>
                <AlertDialogDescription>
                  A real handoff creates a {def.creates}. To test it, send a message from the owner phone that asks for a human,
                  then check {def.title} for the new record. Delete the test record afterwards. Nothing is created from this screen.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Close</AlertDialogCancel>
                <AlertDialogAction asChild>
                  <Link to="../activity">Open Activity</Link>
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </>
      )}
      {state === 'absent' && (
        <div className="flex items-center gap-2">
          {isAdmin ? (
            <Button size="sm" asChild><a href="/apps">Add to Huf</a></Button>
          ) : (
            <span className="text-xs text-steel">Ask an admin to add this.</span>
          )}
          <a className="text-xs text-steel underline" href={def.docs} target="_blank" rel="noreferrer">Learn more</a>
        </div>
      )}
    </section>
  );
}

export function LmsCard() {
  return (
    <section aria-label="LMS" className="flex items-start gap-3 rounded-sm border border-line bg-card p-4 opacity-60">
      <BookOpen className="mt-0.5 h-5 w-5 text-steel" aria-hidden />
      <div className="min-w-0 flex-1">
        <h3 className="text-sm font-medium text-ink">LMS</h3>
        <p className="text-xs text-steel">Answer course questions and enroll learners.</p>
      </div>
      <Badge variant="chip" size="sm">P3</Badge>
    </section>
  );
}

export function RavanCard({ app }: { app?: EcosystemApp }) {
  return (
    <section aria-label="Ravan" className="flex items-start gap-3 rounded-sm border border-dashed border-line p-4">
      <Lock className="mt-0.5 h-5 w-5 text-steel" aria-hidden />
      <div className="min-w-0 flex-1">
        <h3 className="text-sm font-medium text-ink">Ravan</h3>
        <p className="text-xs text-steel">Team chat handoffs are coming.{app?.installed ? ` Detected${app.version ? ` · v${app.version}` : ''}.` : ''}</p>
      </div>
      <Badge variant="pill-neutral">Coming soon</Badge>
    </section>
  );
}
