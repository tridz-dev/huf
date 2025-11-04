import { useState } from 'react';
import { Home, Bot, Workflow, Database, Plug, Settings, HelpCircle, User, ChevronDown, ChevronRight } from 'lucide-react';
import { NavLink, useLocation } from 'react-router-dom';

const navSections = [
  { id: 'home', label: 'Home', icon: Home, path: '/' },
  { id: 'agents', label: 'Agents', icon: Bot, path: '/agents' },
  { id: 'flows', label: 'Flows', icon: Workflow, path: '/flows' },
  { id: 'data', label: 'Data', icon: Database, path: '/data' },
  { id: 'integrations', label: 'Integrations', icon: Plug, path: '/integrations' },
];

const bottomSections = [
  { id: 'settings', label: 'Settings', icon: Settings, path: '/settings' },
  { id: 'help', label: 'Help', icon: HelpCircle, path: '/help' },
];

export function AppSidebar() {
  const location = useLocation();
  const [sectionsExpanded, setSectionsExpanded] = useState(true);

  return (
    <div className="w-60 h-screen bg-sidebar border-r border-sidebar-border flex flex-col">
      <div className="p-4 border-b border-sidebar-border">
        <h2 className="text-sm font-semibold text-sidebar-foreground">AgentFlo</h2>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="p-2">
          <div className="mb-4">
            <button
              className="flex items-center gap-2 w-full px-2 py-1.5 text-sm text-sidebar-foreground hover:bg-sidebar-accent rounded-md"
              onClick={() => setSectionsExpanded(!sectionsExpanded)}
            >
              {sectionsExpanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
              <span className="flex-1 text-left">Navigation</span>
            </button>
            {sectionsExpanded && (
              <div className="ml-6 mt-1 space-y-0.5">
                {navSections.map((section) => {
                  const isActive = location.pathname === section.path ||
                    (section.path !== '/' && location.pathname.startsWith(section.path));

                  return (
                    <NavLink
                      key={section.id}
                      to={section.path}
                      className={`flex items-center gap-2 px-2 py-1.5 text-sm text-sidebar-foreground hover:bg-sidebar-accent rounded-md transition-colors ${
                        isActive ? 'bg-sidebar-accent' : ''
                      }`}
                    >
                      <section.icon className="w-4 h-4" />
                      <span className="flex-1">{section.label}</span>
                    </NavLink>
                  );
                })}
              </div>
            )}
          </div>

          <div>
            <div className="text-xs text-muted-foreground px-2 py-1 mt-4">System</div>
            <div className="space-y-0.5 ml-6">
              {bottomSections.map((section) => {
                const isActive = location.pathname === section.path;

                return (
                  <NavLink
                    key={section.id}
                    to={section.path}
                    className={`flex items-center gap-2 px-2 py-1.5 text-sm text-sidebar-foreground hover:bg-sidebar-accent rounded-md transition-colors ${
                      isActive ? 'bg-sidebar-accent' : ''
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
            <div className="text-sm font-medium text-sidebar-foreground truncate">User</div>
            <div className="text-xs text-muted-foreground truncate">user@agentflo.com</div>
          </div>
        </div>
      </div>
    </div>
  );
}
