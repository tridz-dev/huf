import { NavLink } from 'react-router-dom';
import { Plus, Folder, FileText, Clock, ArrowLeft } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatRailScope } from './chatRailScope';

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

const NAV_ROW_CLASS =
  'flex h-chat-row items-center gap-[9px] rounded-chat-row px-2 text-[13px] text-ink transition-colors';

export interface ChatRailNavProps {
  className?: string;
  /** Global by default. Pass a project scope to switch to the project-scoped rail header. */
  scope?: ChatRailScope;
}

export function ChatRailNav({ className, scope = { kind: 'global' } }: ChatRailNavProps) {
  if (scope.kind === 'project') {
    return (
      <nav className={cn('flex flex-none flex-col px-2 pb-2', className)}>
        <NavLink
          to="/chat/new"
          className="flex h-chat-row items-center gap-[9px] rounded-chat-row px-2 text-[13px] text-steel transition-colors hover:bg-chat-row-hover"
        >
          <ArrowLeft className="h-[15px] w-[15px] shrink-0" />
          All chats
        </NavLink>
        <div className="mx-2 my-[5px] h-px bg-line" />
        <NavLink
          to={`/chat/projects/${scope.projectId}`}
          className={({ isActive }) =>
            cn(NAV_ROW_CLASS, 'font-medium', isActive ? 'bg-chat-row-selected' : 'hover:bg-chat-row-hover')
          }
        >
          <Folder className="h-[15px] w-[15px] shrink-0 text-steel" />
          <span className="truncate">{scope.projectName}</span>
        </NavLink>
        <NavLink
          to={`/chat/new?project=${encodeURIComponent(scope.projectId)}`}
          end
          className={({ isActive }) =>
            cn(NAV_ROW_CLASS, 'font-medium', isActive ? 'bg-chat-row-selected' : 'hover:bg-chat-row-hover')
          }
        >
          <Plus className="h-[15px] w-[15px] shrink-0 text-steel" />
          New chat
        </NavLink>
      </nav>
    );
  }

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
            cn(NAV_ROW_CLASS, emphasis && 'font-medium', isActive ? 'bg-chat-row-selected' : 'hover:bg-chat-row-hover')
          }
        >
          <Icon className="h-[15px] w-[15px] shrink-0 text-steel" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
