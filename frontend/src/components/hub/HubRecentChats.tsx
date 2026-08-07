import { useState } from 'react';
import { History, Loader2 } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { IconRailButton } from '@/components/IconRail';
import { getConversationsByAgent, ChatListItem } from '@/services/chatApi';
import { formatTimeAgo } from '@/utils/time';

interface HubRecentChatsProps {
  onSelect: (conversationId: string) => void;
}

/**
 * History flyout for the collapsed Hub sidebar.
 * Lists recent Hub Orchestrator chats (lazy-loaded on open) and lets the
 * user pick one to resume.
 */
export function HubRecentChats({ onSelect }: HubRecentChatsProps) {
  const [open, setOpen] = useState(false);
  const [chats, setChats] = useState<ChatListItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen || hasLoaded) return;
    setIsLoading(true);
    getConversationsByAgent('Hub Orchestrator', { limit: 10 })
      .then(res => setChats(res?.data ?? []))
      .catch(() => setChats([]))
      .finally(() => {
        setIsLoading(false);
        setHasLoaded(true);
      });
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <IconRailButton icon={History} label="Recent chats" />
      </PopoverTrigger>
      <PopoverContent side="right" align="start" sideOffset={8} className="w-72 p-1 bg-panel border-line">
        <p className="px-3 pt-2 pb-1 font-mono text-[11px] uppercase tracking-widest text-steel">
          Recent chats
        </p>
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-6 text-sm text-steel">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading…
          </div>
        ) : chats.length === 0 ? (
          <p className="px-3 py-6 text-sm text-steel-soft text-center">No recent chats yet.</p>
        ) : (
          <div className="max-h-80 overflow-y-auto">
            {chats.map(chat => (
              <Button
                key={chat.id}
                variant="ghost"
                onClick={() => {
                  setOpen(false);
                  onSelect(chat.id);
                }}
                className="group h-auto w-full flex-col items-start rounded-md px-3 py-2 text-left"
              >
                <p className="text-sm text-ink truncate">{chat.title}</p>
                <p className="text-xs text-steel-soft mt-0.5">{formatTimeAgo(chat.timestamp)}</p>
              </Button>
            ))}
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
