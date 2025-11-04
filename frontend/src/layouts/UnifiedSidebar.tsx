import { Home, Bot, Workflow, Database, Plug, MessageSquare, Settings, HelpCircle, User, PanelLeftClose } from 'lucide-react';
import { NavLink, useLocation } from 'react-router-dom';
import { Button } from '../components/ui/button';

const navSections = [
  { id: 'home', label: 'Dashboard', icon: Home, path: '/' },
  { id: 'agents', label: 'Agents', icon: Bot, path: '/agents' },
  { id: 'flows', label: 'Flows', icon: Workflow, path: '/flows' },
  { id: 'chat', label: 'Chat', icon: MessageSquare, path: '/chat' },
  { id: 'data', label: 'Data', icon: Database, path: '/data' },
  { id: 'integrations', label: 'Integrations', icon: Plug, path: '/integrations' },
];

const bottomSections = [
  { id: 'settings', label: 'Settings', icon: Settings, path: '/settings' },
  { id: 'help', label: 'Help', icon: HelpCircle, path: '/help' },
];

interface UnifiedSidebarProps {
  children?: React.ReactNode;
  onToggle?: () => void;
}

export function UnifiedSidebar({ children, onToggle }: UnifiedSidebarProps) {
  const location = useLocation();

  return (
    <div className="w-60 h-screen bg-sidebar border-r border-sidebar-border flex flex-col">
      <div className="p-4 border-b border-sidebar-border">
        <h2 className="text-sm font-semibold text-sidebar-foreground">HufAI</h2>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="p-2">
          <div className="mb-4 space-y-0.5">
            {navSections.map((section) => {
              const isActive = location.pathname === section.path ||
                (section.path !== '/' && location.pathname.startsWith(section.path));

              return (
                <NavLink
                  key={section.id}
                  to={section.path}
                  className={`flex items-center gap-2 px-2 py-1.5 text-sm text-sidebar-foreground rounded-md transition-colors ${
                    isActive
                      ? 'bg-primary/10 text-primary'
                      : 'hover:bg-primary/10'
                  }`}
                >
                  <section.icon className="w-4 h-4" />
                  <span className="flex-1">{section.label}</span>
                </NavLink>
              );
            })}
          </div>

          {children}

          <div>
            <div className="text-xs text-muted-foreground px-2 py-1 mt-4">System</div>
            <div className="space-y-0.5">
              {bottomSections.map((section) => {
                const isActive = location.pathname === section.path;

                return (
                  <NavLink
                    key={section.id}
                    to={section.path}
                    className={`flex items-center gap-2 px-2 py-1.5 text-sm text-sidebar-foreground rounded-md transition-colors ${
                      isActive
                        ? 'bg-primary/10 text-primary'
                        : 'hover:bg-primary/10'
                    }`}
                  >
                    <section.icon className="w-4 h-4" />
                    <span className="flex-1">{section.label}</span>
                  </NavLink>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-sidebar-border p-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
            <User className="w-4 h-4 text-primary-foreground" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-sidebar-foreground truncate">Safwan Erooth</div>
            <div className="text-xs text-muted-foreground truncate">hey@tridz.com</div>
          </div>
          {onToggle && (
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onToggle}>
              <PanelLeftClose className="w-4 h-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
