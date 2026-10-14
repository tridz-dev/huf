import { Link } from 'react-router-dom';
import { Check, CheckCheck, Circle, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import type { MessageLogItem } from '@/services/whatsappApi';
import { cn } from '@/lib/utils';
import { agentRunPath, sentByLabel, statusTicks, statusTimeline, type TickTone } from './messageLogModel';
import { TemplateSend } from './TemplateSend';

export const TONE_CLASS: Record<TickTone, string> = { neutral: 'text-steel', good: 'text-good', danger: 'text-destructive' };

export function StatusTicks({ status }: { status?: string | null }) {
  const t = statusTicks(status);
  const Icon = t.tone === 'danger' ? X : t.ticks === 2 ? CheckCheck : t.ticks === 1 ? Check : Circle;
  return (
    <span className={cn('inline-flex items-center gap-1 text-xs', TONE_CLASS[t.tone])}>
      <Icon className="h-3.5 w-3.5" aria-hidden />{t.label}
    </span>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-[11px] uppercase tracking-wide text-steel">{label}</dt>
      <dd className="text-xs text-ink">{children}</dd>
    </div>
  );
}

export function MessageDetailSheet({
  item, agentTitle, gateway, onClose,
}: { item: MessageLogItem | null; agentTitle?: string; gateway?: string; onClose: () => void }) {
  const runPath = item ? agentRunPath(item) : null;
  return (
    <Sheet open={!!item} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full space-y-5 overflow-y-auto sm:max-w-md">
        {item && (
          <>
            <SheetHeader>
              <SheetTitle>{item.direction === 'in' ? 'Message received' : 'Message sent'}</SheetTitle>
              <SheetDescription className="font-mono">{item.profile_name ? `${item.profile_name} · ${item.phone}` : item.phone}</SheetDescription>
            </SheetHeader>
            <p className="whitespace-pre-wrap rounded-sm border border-line bg-paper-deep p-3 text-sm text-ink">
              {item.text || `[${item.content_type || 'message'}]`}
            </p>
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-ink">Status</h4>
              {item.direction === 'out' ? (
                <ol className="flex items-center gap-3">
                  {statusTimeline(item.status).map((s) => (
                    <li key={s.key} className={cn('flex items-center gap-1 text-xs', !s.reached ? 'text-steel opacity-50' : s.key === 'failed' ? 'text-destructive' : s.key === 'read' ? 'text-good' : 'text-ink')}>
                      {s.key === 'failed' ? <X className="h-3.5 w-3.5" /> : s.reached ? <Check className="h-3.5 w-3.5" /> : <Circle className="h-3.5 w-3.5" />}
                      {s.label}
                    </li>
                  ))}
                </ol>
              ) : (
                <StatusTicks status={item.status} />
              )}
              {item.error && <p role="alert" className="text-xs text-destructive">{item.error}</p>}
            </div>
            <dl className="grid grid-cols-2 gap-3">
              <Field label="Time">{item.creation}</Field>
              <Field label="Gateway">{item.gateway}</Field>
              <Field label="Type">{item.content_type || 'text'}</Field>
              <Field label="Template">{item.template ? <Badge variant="chip">{item.template}</Badge> : 'None'}</Field>
              <Field label="Handled by">{sentByLabel(item.sent_by, agentTitle ?? item.agent)}</Field>
              <Field label="Message ID"><span className="break-all font-mono">{item.message_id || 'None'}</span></Field>
            </dl>
            <div className="flex flex-wrap gap-3 text-xs">
              {runPath && <Link to={runPath} className="text-signal-ink underline">Open agent run</Link>}
              {item.event && <a href={`/app/gateway-event/${encodeURIComponent(item.event)}`} target="_blank" rel="noreferrer" className="text-signal-ink underline">Open gateway event</a>}
            </div>
            <div className="space-y-1 border-t border-line pt-4">
              <h4 className="text-xs font-semibold text-ink">Send template to this number</h4>
              <TemplateSend gateway={gateway} to={item.phone} />
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
