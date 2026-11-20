/**
 * ConfirmDestructive (DESIGN.md §6.11.10): the one confirm dialog for
 * deleting or replacing something people depend on. States the consequence
 * with real numbers, lists dependents, optionally requires typing the name,
 * and says whether it can be restored. Never acts without this dialog.
 */
import { useEffect, useState, type ReactNode } from 'react';
import {
  AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';

export interface Dependent {
  label: string;
  /** What kind of thing depends on it, e.g. "Agent", "Flow". */
  kind?: string;
  detail?: string;
}

export interface ConfirmDestructiveProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** "Removes all 1,284 rows and 7 fields." */
  consequence: ReactNode;
  dependents?: Dependent[];
  /** Require typing this exact text to enable the action. */
  confirmText?: string;
  /** "You can restore it for 30 days." / "This can't be undone." */
  recovery?: string;
  actionLabel: string;
  onConfirm: () => void | Promise<void>;
  /** A gentler alternative, e.g. "Turn off instead". */
  alternative?: { label: string; onClick: () => void };
}

export function ConfirmDestructive({
  open, onOpenChange, title, consequence, dependents = [], confirmText, recovery, actionLabel, onConfirm, alternative,
}: ConfirmDestructiveProps) {
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!open) setTyped(''); }, [open]);
  const ready = !confirmText || typed.trim() === confirmText;
  const go = async () => {
    setBusy(true);
    try { await onConfirm(); onOpenChange(false); } finally { setBusy(false); }
  };
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>
            {consequence}
            {recovery && <span className="mt-1 block">{recovery}</span>}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {dependents.length > 0 && (
          <div className="rounded-lg border border-warning/30 bg-warning-tint px-4 py-3">
            <p className="text-micro font-medium text-warning">
              {dependents.length === 1 ? '1 thing uses this and will stop working:' : `${dependents.length} things use this and will stop working:`}
            </p>
            <ul data-testid="dependents" className="mt-1.5 space-y-1 text-ui-text">
              {dependents.map((d) => (
                <li key={`${d.kind}-${d.label}`} className="flex gap-2">
                  {d.kind && <span className="w-14 shrink-0 text-micro text-steel">{d.kind}</span>}
                  <span className="text-ink">{d.label}</span>
                  {d.detail && <span className="text-micro text-steel">{d.detail}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {confirmText && (
          <Field label={<>Type <span className="font-mono">{confirmText}</span> to confirm</>}>
            <Input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} />
          </Field>
        )}
        <AlertDialogFooter>
          {alternative && <Button variant="ghost" className="sm:mr-auto" onClick={alternative.onClick}>{alternative.label}</Button>}
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <Button variant="destructive" disabled={!ready || busy} onClick={() => void go()}>{actionLabel}</Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
