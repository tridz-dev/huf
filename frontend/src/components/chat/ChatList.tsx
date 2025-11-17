import { useEffect } from 'react';
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

interface Chat {
  id: string;
  title: string;
  lastMessage?: string;
  timestamp?: string;
}

const dummyChats: Chat[] = [
  {
    id: '1',
    title: 'User Greeting',
    lastMessage: 'Hello! How can I assist you today?',
    timestamp: '2 minutes ago',
  },
  {
    id: '2',
    title: 'React Hooks Discussion',
    lastMessage: 'React hooks like useState and useEffect are...',
    timestamp: '1 hour ago',
  },
  {
    id: '3',
    title: 'Weather Query',
    lastMessage: 'The weather in San Francisco is...',
    timestamp: '3 hours ago',
  },
  {
    id: '4',
    title: 'Project Planning',
    lastMessage: 'Let me help you plan your project...',
    timestamp: 'Yesterday',
  },
  {
    id: '5',
    title: 'Marketing Strategy',
    lastMessage: 'We can split the campaign into awareness and conversion phases.',
    timestamp: '2 days ago',
  },
  {
    id: '6',
    title: 'Sales Outreach',
    lastMessage: 'Drafted a personalized opener for the enterprise leads.',
    timestamp: '2 days ago',
  },
  {
    id: '7',
    title: 'Data Cleanup',
    lastMessage: 'Deduped the CRM export and fixed missing emails.',
    timestamp: '3 days ago',
  },
  {
    id: '8',
    title: 'Flow Builder Help',
    lastMessage: 'Need a conditional branch after the trigger.',
    timestamp: '3 days ago',
  },
  {
    id: '9',
    title: 'Support Escalation',
    lastMessage: 'Customer is blocked with a 403 on login.',
    timestamp: '4 days ago',
  },
  {
    id: '10',
    title: 'Design Review',
    lastMessage: 'Tweaked the chat bubble radius for better readability.',
    timestamp: '4 days ago',
  },
  {
    id: '11',
    title: 'Docs Update',
    lastMessage: 'Added the new quick start for Agent tools.',
    timestamp: '5 days ago',
  },
  {
    id: '12',
    title: 'API Keys Rotation',
    lastMessage: 'Staging credentials rotated successfully.',
    timestamp: '5 days ago',
  },
  {
    id: '13',
    title: 'Release Checklist',
    lastMessage: 'Still need QA sign-off for the chat page.',
    timestamp: '6 days ago',
  },
  {
    id: '14',
    title: 'Performance Audit',
    lastMessage: 'Found a slow query in the analytics widget.',
    timestamp: '6 days ago',
  },
  {
    id: '15',
    title: 'Integration Test',
    lastMessage: 'Webhook run passed but the payload differs.',
    timestamp: '7 days ago',
  },
  {
    id: '16',
    title: 'Cloud Costs',
    lastMessage: 'Switching to committed use could save 15%.',
    timestamp: '7 days ago',
  },
  {
    id: '17',
    title: 'Team Standup',
    lastMessage: 'Today: fix sidebar bug, prep demo.',
    timestamp: '7 days ago',
  },
  {
    id: '18',
    title: 'Bug Bash',
    lastMessage: 'Captured six issues from last night’s session.',
    timestamp: '8 days ago',
  },
  {
    id: '19',
    title: 'Analytics Dashboard',
    lastMessage: 'Need to add a retention cohort view.',
    timestamp: '8 days ago',
  },
  {
    id: '20',
    title: 'Security Review',
    lastMessage: 'Revalidating scopes on the public APIs.',
    timestamp: '9 days ago',
  },
  {
    id: '21',
    title: 'Content Calendar',
    lastMessage: 'Drafted posts through next Tuesday.',
    timestamp: '9 days ago',
  },
  {
    id: '22',
    title: 'Investor Update',
    lastMessage: 'Working on the monthly highlights slide.',
    timestamp: '10 days ago',
  },
  {
    id: '23',
    title: 'Hiring Pipeline',
    lastMessage: 'Two engineers moved to onsite stage.',
    timestamp: '10 days ago',
  },
  {
    id: '24',
    title: 'Roadmap Sync',
    lastMessage: 'Need alignment on Q3 bets and stretch goals.',
    timestamp: '2 weeks ago',
  },
];

interface ChatListProps {
  selectedChatId: string | null;
  onSelectChat: (chatId: string) => void;
}

export function ChatList({ selectedChatId, onSelectChat }: ChatListProps) {
  // Auto-select first chat if none is selected
  useEffect(() => {
    if (!selectedChatId && dummyChats.length > 0) {
      onSelectChat(dummyChats[0].id);
    }
  }, [selectedChatId, onSelectChat]);

  const handleDeleteChat = (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    // TODO: Implement chat deletion
    console.log('Delete chat', chatId);
  };

  return (
    <div className="flex flex-col w-64 h-full border-r border-border bg-sidebar">
      {/* Chat List */}
      <ScrollArea className="flex-1 overflow-y-auto">
        <div className="space-y-1">
          {dummyChats.map((chat) => {
            const isSelected = selectedChatId === chat.id;
            return (
              <div
                key={chat.id}
                onClick={() => onSelectChat(chat.id)}
                className={cn(
                  'group relative flex items-center gap-3 p-3 cursor-pointer transition-colors',
                  isSelected
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                    : 'hover:bg-sidebar-accent/50 text-sidebar-foreground'
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <p className="text-sm font-medium truncate">{chat.title}</p>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => handleDeleteChat(chat.id, e)}
                    >
                      <Trash2 className="w-3 h-3" />
                    </Button>
                  </div>
                  {chat.lastMessage && (
                    <p className="text-xs text-muted-foreground truncate">
                      {chat.lastMessage}
                    </p>
                  )}
                  {chat.timestamp && (
                    <p className="text-xs text-muted-foreground mt-1">
                      {chat.timestamp}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}

