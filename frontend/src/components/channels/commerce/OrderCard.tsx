import { useEffect, useState } from 'react';
import { ShoppingBag } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { listConversationOrders, type OrderRow } from '@/services/commerceApi';

/** Compact order summary above a conversation's messages; renders nothing without orders. */
export function OrderCard({ conversation }: { conversation: string }) {
  const [orders, setOrders] = useState<OrderRow[]>([]);
  useEffect(() => {
    let live = true;
    void Promise.resolve(listConversationOrders(conversation)).then((res) => {
      if (live && res?.ok && Array.isArray(res.data)) setOrders(res.data);
    }).catch(() => undefined);
    return () => { live = false; };
  }, [conversation]);
  if (!orders.length) return null;
  return (
    <div className="space-y-1 border-b border-line px-4 py-2">
      {orders.map((o) => (
        <div key={o.name} data-order-card className="flex items-center gap-2 text-xs text-ink">
          <ShoppingBag className="h-3.5 w-3.5 text-steel" aria-hidden />
          <span className="font-mono">{o.name}</span>
          <span>{o.currency} {o.total}</span>
          <Badge variant="chip" size="sm">{o.status}</Badge>
          <Link to="../commerce/orders" className="ml-auto underline">View</Link>
        </div>
      ))}
    </div>
  );
}
