import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { actConfirm, actPrepare, TelegramAppError, type TgActPrepare } from '@/services/telegramAppApi';
import { haptic } from './telegramWebApp';
import { isDestructiveAction } from './model';
import { ConfirmSheet } from './ConfirmSheet';

interface Props {
  doctype: string;
  name: string;
  actions: string[];
  onDone?: () => void;
}

/** Action buttons -> act_prepare -> confirm sheet (shows description) -> act_confirm. */
export function ActionPanel({ doctype, name, actions, onDone }: Props) {
  const [prepared, setPrepared] = useState<TgActPrepare | null>(null);
  const [busy, setBusy] = useState(false);

  if (!actions.length) return null;

  const fail = (e: unknown) => {
    haptic('error');
    toast.error(e instanceof TelegramAppError ? e.message : 'Something went wrong.');
  };

  const prepare = async (action: string) => {
    setBusy(true);
    try {
      setPrepared(await actPrepare(doctype, name, action));
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!prepared) return;
    setBusy(true);
    try {
      const res = await actConfirm(prepared.nonce);
      haptic('success');
      toast.success(res.result);
      setPrepared(null);
      onDone?.();
    } catch (e) {
      fail(e);
      setPrepared(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {actions.map((a) => (
          <Button
            key={a}
            variant={isDestructiveAction(a) ? 'destructive' : 'default'}
            disabled={busy}
            onClick={() => void prepare(a)}
          >
            {a}
          </Button>
        ))}
      </div>
      <ConfirmSheet
        open={!!prepared}
        title={prepared ? `${prepared.action.action}: ${prepared.action.name}` : ''}
        description={prepared?.description ?? ''}
        busy={busy}
        destructive={prepared ? isDestructiveAction(prepared.action.action) : false}
        onConfirm={() => void confirm()}
        onCancel={() => setPrepared(null)}
      />
    </>
  );
}
