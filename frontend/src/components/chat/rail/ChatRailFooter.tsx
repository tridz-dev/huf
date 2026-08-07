import { Home, SlidersHorizontal, LogOut, ChevronsUpDown } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { useUser } from '@/contexts/UserContext';
import { getInitials } from '@/utils/getInitials';
import { cn } from '@/lib/utils';

export interface ChatRailFooterProps {
  className?: string;
}

export function ChatRailFooter({ className }: ChatRailFooterProps) {
  const { user, isLoading, logout } = useUser();
  const navigate = useNavigate();

  if (isLoading) {
    return (
      <div
        className={cn(
          'flex h-chat-footer w-full flex-none items-center gap-[9px] border-t border-line px-3.5 text-left',
          className
        )}
      >
        <Skeleton className="h-[22px] w-[22px] flex-none rounded-full" />
        <Skeleton className="h-[13px] w-24" />
      </div>
    );
  }

  if (!user) {
    return null;
  }

  const displayName = user.full_name || user.name;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            'flex h-chat-footer w-full flex-none items-center gap-[9px] border-t border-line px-3.5 text-left transition-colors hover:bg-chat-row-hover',
            className
          )}
        >
          <span className="flex h-[22px] w-[22px] flex-none items-center justify-center rounded-full bg-signal text-[10px] text-white">
            {getInitials(displayName)}
          </span>
          <span className="min-w-0 flex-1 truncate text-[13px]">{displayName}</span>
          <ChevronsUpDown className="h-[15px] w-[15px] shrink-0 text-steel-soft" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" side="top" className="min-w-56">
        <DropdownMenuItem onClick={() => navigate('/')}>
          <Home className="mr-2 h-4 w-4" />
          Hub
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/settings/general')}>
          <SlidersHorizontal className="mr-2 h-4 w-4" />
          Settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => logout()}>
          <LogOut className="mr-2 h-4 w-4" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
