import { NavLink } from 'react-router-dom';
import { Plus, Folder, FileText, Clock, ArrowLeft } from 'lucide-react';
import { cn } from '@/lib/utils';

// Rail navigation: Dashboard row sits above the items as the way back out of the chat shell.
// Four rows below it, each 26px tall, with a 13px label and a 15px icon. Geometry from
// spec section 28. Projects, Artifacts and Scheduled route to placeholder pages until
// each has something real behind it.
const NAV_ITEMS = [
  { label: 'New',       to: '/chat/new',       icon: Plus,     emphasis: true },
  { label: 'Projects',  to: '/chat/projects',  icon: Folder,   emphasis: false },
  { label: 'Artifacts', to: '/chat/artifacts', icon: FileText, emphasis: false },
  { label: 'Scheduled', to: '/chat/scheduled', icon: Clock,    emphasis: false },
] as const;

export interface ChatRailNavProps {
  className?: string;
}

export function ChatRailNav({ className }: ChatRailNavProps) {
  return (
    <nav className={cn('flex flex-none flex-col px-2 pb-2', className)}>
      <NavLink
        to="/"
        className="flex h-chat-row items-center gap-[9px] rounded-chat-row px-2 text-[13px] text-steel transition-colors hover:bg-chat-row-hover"
      >
        <ArrowLeft className="h-[15px] w-[15px] shrink-0" />
        Dashboard
      </NavLink>
      <div className="mx-2 my-[5px] h-px bg-line" />
      {NAV_ITEMS.map(({ label, to, icon: Icon, emphasis }) => (
        <NavLink
          key={to}
          to={to}
          end
          className={({ isActive }) =>
            cn(
              'flex h-chat-row items-center gap-[9px] rounded-chat-row px-2 text-[13px] text-ink transition-colors',
              emphasis && 'font-medium',
              isActive ? 'bg-chat-row-selected' : 'hover:bg-chat-row-hover'
            )
          }
        >
          <Icon className="h-[15px] w-[15px] shrink-0 text-steel" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
