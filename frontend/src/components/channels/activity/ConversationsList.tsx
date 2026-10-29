import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { TimeStamp } from '@/components/whatsapp/TimeStamp';
import { listConversations, type ChannelConversation, type ConversationStatus } from '@/services/channelsApi';

const STATUS_PILL: Record<ConversationStatus, { label: string; variant: 'pill-success' | 'pill-warning' | 'pill-neutral' }> = {
  ai: { label: 'AI', variant: 'pill-success' },
  handed_off: { label: 'Handed off', variant: 'pill-warning' },
  closed: { label: 'Closed', variant: 'pill-neutral' },
};

type Filter = ConversationStatus | 'all';
const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'ai', label: 'AI' },
  { key: 'handed_off', label: 'Handed off' },
  { key: 'closed', label: 'Closed' },
];

export function ConversationsList({
  gateway,
  selected,
  onSelect,
  reloadKey = 0,
}: {
  gateway?: string;
  selected?: string;
  onSelect?: (name: string) => void;
  reloadKey?: number;
}) {
  const [filter, setFilter] = useState<Filter>('all');
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
    void listConversations(gateway, filter === 'all' ? {} : { status: filter }).then((res) => {
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
  }, [gateway, filter, reloadKey]);

  let content;
  if (loading) {
    content = (
      <div className="flex items-center gap-2 p-3 text-xs text-steel">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading conversations...
      </div>
    );
  } else if (error) content = <p role="alert" className="p-3 text-sm text-destructive">{error}</p>;
  else if (items.length === 0) content = <p className="p-6 text-center text-xs text-steel">No conversations yet.</p>;
  else
    content = (
      <ul className="divide-y divide-line">
        {items.map((c) => {
          const pill = STATUS_PILL[c.status] ?? STATUS_PILL.closed;
          return (
            <li key={c.name} data-conversation={c.name}>
              <button
                type="button"
                aria-current={selected === c.name}
                onClick={() => onSelect?.(c.name)}
                className={cn('flex w-full items-center gap-3 px-3 py-2 text-left', selected === c.name && 'bg-paper-deep')}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-ink">{c.contact_name || c.contact_handle || c.name}</div>
                  <div className="truncate text-xs text-steel">{c.last_message_preview || 'No messages'}</div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <Badge variant={pill.variant}>{pill.label}</Badge>
                  <span className="flex items-center gap-1 whitespace-nowrap text-xs text-steel">
                    {c.within_24h && <Badge variant="chip" size="sm">24h</Badge>}
                    <TimeStamp value={c.modified} />
                  </span>
                </div>
              </button>
            </li>
          );
        })}
        {hasMore && <li className="px-3 py-2 text-center text-xs text-steel">Showing the most recent conversations.</li>}
      </ul>
    );
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div role="group" aria-label="Status filter" className="flex flex-wrap gap-1 border-b border-line p-2">
        {FILTERS.map((f) => (
          <Button key={f.key} size="sm" variant={filter === f.key ? 'secondary' : 'ghost'} aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label}
          </Button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">{content}</div>
    </div>
  );
}
