/**
 * ChangeImpactNotice (DESIGN.md §6.11.9): before a schema edit that touches
 * existing data (type change, delete field, mode "replace"), say what will
 * happen to the data in counts: "1,180 values convert · 104 will be cleared".
 * Safe lines are quiet; loss lines take the tone. Shown inline in the form
 * that makes the change, above its save button — never only in a toast.
 */
import type { ReactNode } from 'react';
import { AlertTriangle, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';

export interface ImpactLine {
  count: number;
  /** Plain words after the count: "values convert to numbers". */
  label: string;
  /** `loss` lines are emphasised; `safe` lines are quiet. */
  kind?: 'safe' | 'loss';
}

export interface ChangeImpactNoticeProps {
  title: ReactNode;
  lines?: ImpactLine[];
  /** While the impact is being counted. */
  checking?: boolean;
  /** `error` when the change loses data that can't be restored. */
  severity?: 'attention' | 'error';
  action?: ReactNode;
  /** Optional footer: confirm applies the change. Destructive styling when data is lost. */
  onConfirm?: () => void;
  onCancel?: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
  /** While the change is being applied: confirm shows a spinner, both disabled. */
  confirming?: boolean;
  className?: string;
}

export function ChangeImpactNotice({
  title, lines = [], checking, severity = 'attention', action, onConfirm, onCancel, confirmLabel = 'Apply change', cancelLabel = 'Cancel', confirming, className,
}: ChangeImpactNoticeProps) {
  const lossy = lines.some((l) => l.kind === 'loss' && l.count > 0);
  const tint = !lossy ? 'border-line bg-paper-deep' : severity === 'error' ? 'border-destructive/30 bg-destructive-tint' : 'border-warning/30 bg-warning-tint';
  const Icon = lossy ? AlertTriangle : Info;
  return (
    <div role={lossy ? 'alert' : 'status'} data-testid="change-impact" aria-busy={checking || undefined}
      className={cn('rounded-lg border px-4 py-3 text-ui-text', tint, className)}>
      <p className={cn('flex items-center gap-2 font-medium', lossy ? (severity === 'error' ? 'text-destructive' : 'text-warning') : 'text-ink')}>
        <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
        {title}
      </p>
      {checking ? (
        <p className="mt-1 flex items-center gap-2 pl-6 text-micro text-steel"><Spinner role="presentation" aria-hidden="true" className="h-3 w-3" /> Checking your data…</p>
      ) : lines.length > 0 && (
        <ul className="mt-1 space-y-0.5 pl-6 text-micro">
          {lines.map((l) => (
            <li key={l.label} className={l.kind === 'loss' && l.count > 0 ? 'font-medium text-ink' : 'text-steel'}>
              <span className="font-mono">{l.count.toLocaleString()}</span> {l.label}
            </li>
          ))}
        </ul>
      )}
      {action && <div className="mt-2 pl-6">{action}</div>}
      {(onConfirm || onCancel) && (
        <div className="mt-3 flex justify-end gap-2" data-testid="change-impact-footer">
          {onCancel && <Button size="sm" variant="ghost" onClick={onCancel} disabled={confirming}>{cancelLabel}</Button>}
          {onConfirm && (
            <Button size="sm" variant={lossy ? 'destructive' : 'default'} onClick={onConfirm} disabled={checking || confirming} className="gap-1.5">
              {confirming && <Spinner role="presentation" aria-hidden="true" className="h-3 w-3" />}
              {confirmLabel}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
