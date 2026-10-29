import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { TimeStamp } from '@/components/whatsapp/TimeStamp';
import { listConversations, type ChannelConversation, type ConversationStatus } from '@/services/channelsApi';

const STATUS_PILL: Record<ConversationStatus, { label: string; variant: 'pill-success' | 'pill-warning' | 'pill-neutral' }> = {
  ai: { label: 'AI', variant: 'pill-success' },
  handed_off: { label: 'Handed off', variant: 'pill-warning' },
  closed: { label: 'Closed', variant: 'pill-neutral' },
};

export function ConversationsList({ gateway }: { gateway?: string }) {
  const [items, setItems] = useState<ChannelConversation[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!gateway) {
      setLoading(false);
      return;
    }
    let live = true;
    setLoading(true);
    setError('');
    void listConversations(gateway).then((res) => {
      if (!live) return;
      if (res.ok) {
        setItems(res.data.items);
        setHasMore(res.data.has_more);
      } else setError(res.error);
      setLoading(false);
    });
    return () => {
      live = false;
    };
  }, [gateway]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-steel">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading conversations...
      </div>
    );
  }
  if (error) return <p role="alert" className="text-sm text-destructive">{error}</p>;
  if (items.length === 0) {
    return <p className="rounded-sm border border-line p-6 text-center text-xs text-steel">No conversations yet.</p>;
  }
  return (
    <ul className="divide-y divide-line rounded-sm border border-line">
      {items.map((c) => {
        const pill = STATUS_PILL[c.status] ?? STATUS_PILL.closed;
        return (
          <li key={c.name} data-conversation={c.name} className="flex items-center gap-3 px-3 py-2">
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm text-ink">{c.contact_name || c.contact_handle || c.name}</div>
              <div className="truncate text-xs text-steel">{c.last_message_preview || 'No messages'}</div>
            </div>
            <Badge variant={pill.variant}>{pill.label}</Badge>
            {c.within_24h && <Badge variant="chip" size="sm">24h</Badge>}
            <span className="whitespace-nowrap text-xs text-steel"><TimeStamp value={c.modified} /></span>
          </li>
        );
      })}
      {hasMore && <li className="px-3 py-2 text-center text-xs text-steel">Showing the most recent conversations.</li>}
    </ul>
  );
}
