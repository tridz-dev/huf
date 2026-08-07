import { Link, useLocation } from 'react-router-dom';
import { Fragment, ReactNode } from 'react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '../components/ui/breadcrumb';
import { BreadcrumbItem as BreadcrumbItemType } from './UnifiedLayout';
import { ApprovalsBell } from '../components/ApprovalsBell';

interface UnifiedHeaderProps {
  actions?: ReactNode;
  breadcrumbs?: BreadcrumbItemType[];
}

/**
 * Ancestry-only breadcrumb: renders the chain of ancestors leading up to the
 * current page, but never the trailing/current-page crumb. Used both inside
 * PageFrame's 52px bar and by the standalone 60px topbar (via UnifiedHeader
 * below) — in both places the page itself already names the current record
 * once (an h1, InlineEditName, or similar), so repeating that name in the
 * breadcrumb would name the page twice. Renders nothing when there is no
 * real ancestry (a single-item or empty breadcrumb list).
 */
export function AncestryCrumb({ breadcrumbs }: { breadcrumbs?: BreadcrumbItemType[] }) {
  if (!breadcrumbs || breadcrumbs.length < 2) return null;
  const ancestors = breadcrumbs.slice(0, -1);

  return (
    <div className="flex items-center gap-2 shrink-0">
      <Breadcrumb>
        <BreadcrumbList>
          {ancestors.map((crumb, index) => (
            <Fragment key={index}>
              <BreadcrumbItem className={index === 0 ? 'hidden md:block' : ''}>
                {crumb.href ? (
                  <BreadcrumbLink href={crumb.href} asChild>
                    <Link to={crumb.href}>{crumb.label}</Link>
                  </BreadcrumbLink>
                ) : (
                  <span className="font-mono text-[11px] uppercase tracking-widest text-steel">{crumb.label}</span>
                )}
              </BreadcrumbItem>
              <BreadcrumbSeparator className="hidden md:block mt-0.5" />
            </Fragment>
          ))}
        </BreadcrumbList>
      </Breadcrumb>
    </div>
  );
}

export function UnifiedHeader({ actions, breadcrumbs }: UnifiedHeaderProps) {
  const location = useLocation();

  const getPageTitle = () => {
    const path = location.pathname;
    if (path === '/') return 'Dashboard';
    if (path.startsWith('/agents')) return 'Agent';
    if (path.startsWith('/flows')) return 'Flows';
    if (path.startsWith('/data')) return 'Data';
    if (path.startsWith('/providers')) return 'AI providers';
    if (path.startsWith('/integration-services')) return 'Integration catalog';
    if (path.startsWith('/integrations')) return 'Integrations';
    if (path.startsWith('/gateways')) return 'Gateways';
    if (path.startsWith('/settings')) return 'Settings';
    if (path.startsWith('/playground')) return 'Playground';
    if (path.startsWith('/console')) return 'Playground';
    if (path.startsWith('/help')) return 'Help';
    if (path.startsWith('/chat')) return 'Chat';
    if (path.startsWith('/executions')) return 'Executions';
    if (path.startsWith('/knowledge')) return 'Knowledge';
    if (path.startsWith('/mcp')) return 'MCP servers';
    if (path.startsWith('/prompts')) return 'Prompts';
    if (path.startsWith('/summary-prompts')) return 'Prompts';
    if (path.startsWith('/members')) return 'Members';
    if (path.startsWith('/users')) return 'Users';
    if (path.startsWith('/roles')) return 'Roles';
    if (path.startsWith('/models')) return 'Models';
    if (path.startsWith('/execution-profiles')) return 'Code execution';
    if (path.startsWith('/ssh-connections')) return 'SSH connections';
    if (path.startsWith('/apps')) return 'Apps';
    if (path.startsWith('/memory')) return 'Memory';
    if (path.startsWith('/skills')) return 'Skills';
    if (path.startsWith('/ssh')) return 'SSH execution';
    return 'HufAI';
  };

  const ancestryCrumb = <AncestryCrumb breadcrumbs={breadcrumbs} />;
  const hasAncestry = !!breadcrumbs && breadcrumbs.length >= 2;

  return (
    <div className="flex items-center justify-between flex-1">
      <div className="flex items-center gap-2">
        {hasAncestry ? (
          ancestryCrumb
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
        <ApprovalsBell />
        {actions}
      </div>
    </div>
  );
}
