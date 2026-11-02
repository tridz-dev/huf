import { toast } from 'sonner';

/**
 * Clears the toasts that only report something that already happened (success, info, a plain message without a button), so a
 * dialog that opens next starts with a clear screen. Never touches an error or warning (the reason must stay readable), a
 * loading toast, or a toast with a button (Undo): those stay until their own timer or the person closes them.
 */
export function dismissPassiveToasts(): void {
  const list = (toast as { getToasts?: () => Array<{ id: string | number; type?: string; action?: unknown; cancel?: unknown; dismiss?: boolean }> }).getToasts?.();
  if (!list) return; // test doubles of sonner have no getToasts
  for (const t of list) {
    if (t.dismiss) continue;
    const passive = !t.type || t.type === 'normal' || t.type === 'success' || t.type === 'info' || t.type === 'default';
    if (passive && !t.action && !t.cancel) toast.dismiss(t.id);
  }
}
