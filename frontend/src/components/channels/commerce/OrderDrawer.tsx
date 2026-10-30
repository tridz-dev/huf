import { useEffect, useState } from 'react';
import { Copy } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { copyText } from '@/lib/clipboard';
import { createPaymentLink, getOrder, type OrderDetail } from '@/services/channels/commerceApi';

export function OrderDrawer({ name, onClose, onChanged }: { name: string | null; onClose: () => void; onChanged?: () => void }) {
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setOrder(null);
    setError('');
    if (!name) return;
    let live = true;
    void getOrder(name).then((res) => {
      if (!live) return;
      if (res.ok) setOrder(res.data);
      else setError(res.error);
    });
    return () => { live = false; };
  }, [name]);

  const makeLink = async () => {
    if (!name) return;
    setBusy(true);
    setError('');
    const res = await createPaymentLink(name);
    setBusy(false);
    if (!res.ok) return setError(res.error);
    if (!res.data.success || !res.data.url) return setError(res.data.error || 'Could not create the payment link.');
    setOrder((o) => (o ? { ...o, payment_link: res.data.url } : o));
    onChanged?.();
  };

  const copy = async (url: string) => {
    if (await copyText(url)) toast.success('Link copied');
    else toast.error("Couldn't copy. Select the link and copy it yourself.");
  };

  return (
    <Sheet open={!!name} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent aria-label="Order detail">
        <SheetHeader><SheetTitle>Order {name}</SheetTitle></SheetHeader>
        <div className="mt-4 space-y-3 text-sm text-ink">
          {error && <p role="alert" className="text-destructive">{error}</p>}
          {order && (
            <>
              <p className="text-xs text-steel">{order.contact_handle} · {order.status} · {order.payment_status || 'Unpaid'}</p>
              <ul aria-label="Order items" className="divide-y divide-line rounded-sm border border-line">
                {(order.items ?? []).map((it, i) => (
                  <li key={i} className="flex justify-between gap-2 px-3 py-1.5">
                    <span>{it.item_name || it.retailer_id} × {it.qty}</span>
                    <span className="text-steel">{it.currency} {it.price}</span>
                  </li>
                ))}
              </ul>
              <p className="font-medium">Total {order.currency} {order.total}</p>
              {order.customer_note && <p className="text-xs text-steel">Note: {order.customer_note}</p>}
              {order.payment_link ? (
                <div className="flex items-center gap-2">
                  <a href={order.payment_link} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate text-xs underline">{order.payment_link}</a>
                  <Button size="sm" variant="outline" onClick={() => void copy(order.payment_link!)}><Copy className="mr-1 h-3 w-3" />Copy link</Button>
                </div>
              ) : null}
              <Button size="sm" disabled={busy} onClick={() => void makeLink()}>
                {order.payment_link ? 'Create a new payment link' : 'Create payment link'}
              </Button>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
