import { Link, useLocation } from 'react-router-dom';
import { Fragment, ReactNode } from 'react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '../components/ui/breadcrumb';
import { BreadcrumbItem as BreadcrumbItemType } from './UnifiedLayout';
// import { ApprovalsBell } from '../components/ApprovalsBell';  // TEMP disabled: see flow_api.py get_pending_approvals

interface UnifiedHeaderProps {
  actions?: ReactNode;
  breadcrumbs?: BreadcrumbItemType[];
}

export function UnifiedHeader({ actions, breadcrumbs }: UnifiedHeaderProps) {
  const location = useLocation();

  const getPageTitle = () => {
    const path = location.pathname;
    if (path === '/') return 'Dashboard';
    if (path.startsWith('/agents')) return 'Agent';
    if (path.startsWith('/flows')) return 'Flows';
    if (path.startsWith('/data')) return 'Data';
    if (path.startsWith('/providers')) return 'AI Providers & Models';
    if (path.startsWith('/integration-services')) return 'Integration Catalog';
    if (path.startsWith('/integrations')) return 'Integrations';
    if (path.startsWith('/gateways')) return 'Gateways';
    if (path.startsWith('/settings')) return 'Settings';
    if (path.startsWith('/playground')) return 'Playground';
    if (path.startsWith('/console')) return 'Playground';
    if (path.startsWith('/help')) return 'Help';
    if (path.startsWith('/chat')) return 'Chat';
    if (path.startsWith('/executions')) return 'Executions';
    if (path.startsWith('/knowledge')) return 'Knowledge';
    if (path.startsWith('/mcp')) return 'MCP Servers';
    if (path.startsWith('/prompts')) return 'Prompts';
    if (path.startsWith('/summary-prompts')) return 'Prompts';
    if (path.startsWith('/members')) return 'Members';
    if (path.startsWith('/users')) return 'Users';
    if (path.startsWith('/roles')) return 'Roles';
    if (path.startsWith('/models')) return 'AI Providers & Models';
    if (path.startsWith('/execution-profiles')) return 'Code Execution';
    if (path.startsWith('/ssh-connections')) return 'SSH Connections';
    if (path.startsWith('/apps')) return 'Apps';
    if (path.startsWith('/memory')) return 'Intelligence';
    if (path.startsWith('/skills')) return 'Skills';
    if (path.startsWith('/ssh')) return 'SSH Execution';
    return 'HufAI';
  };

  return (
    <div className="flex items-center justify-between flex-1">
      <div className="flex items-center gap-2">
        {breadcrumbs && breadcrumbs.length > 0 ? (
          <Breadcrumb>
            <BreadcrumbList>
              {breadcrumbs.map((crumb, index) => (
                <Fragment key={index}>
                <div className="flex items-center">
                  <BreadcrumbItem className={index === 0 ? 'hidden md:block' : ''}>
                    {index === breadcrumbs.length - 1 ? (
                      <BreadcrumbPage className="font-mono text-[11px] uppercase tracking-widest text-ink">{crumb.label}</BreadcrumbPage>
                    ) : crumb.href ? (
                      <BreadcrumbLink href={crumb.href} asChild>
                        <Link to={crumb.href} className="font-mono text-[11px] uppercase tracking-widest text-steel hover:text-ink">{crumb.label}</Link>
                      </BreadcrumbLink>
                    ) : (
                      <span className="font-mono text-[11px] uppercase tracking-widest text-steel">{crumb.label}</span>
                    )}
                  </BreadcrumbItem>
                </div>
                {index < breadcrumbs.length - 1 && <BreadcrumbSeparator className="hidden md:block mt-0.5 text-steel-soft" />}
                </Fragment>
              ))}
            </BreadcrumbList>
          </Breadcrumb>
        ) : (
          <span className="font-mono text-[11px] uppercase tracking-widest text-steel">{getPageTitle()}</span>
        )}
      </div>

      {/* <div className="flex items-center gap-2 flex-1 justify-center max-w-md mx-auto">
        <div className="relative w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search... (⌘K)"
            className="w-full pl-9"
          />
        </div>
      </div> */}

      <div className="flex items-center gap-2">
        {/* <ApprovalsBell />  TEMP disabled: get_pending_approvals returns 403 even for Admin */}
        {actions}
      </div>
    </div>
  );
}
