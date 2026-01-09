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
    if (path.startsWith('/providers')) return 'AI Providers';
    if (path.startsWith('/settings')) return 'Settings';
    if (path.startsWith('/help')) return 'Help';
    if (path.startsWith('/chat')) return 'Chat';
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
                      <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                    ) : crumb.href ? (
                      <BreadcrumbLink href={crumb.href} asChild>
                        <Link to={crumb.href}>{crumb.label}</Link>
                      </BreadcrumbLink>
                    ) : (
                      <span>{crumb.label}</span>
                    )}
                  </BreadcrumbItem>
                </div>
                {index < breadcrumbs.length - 1 && <BreadcrumbSeparator className="hidden md:block mt-0.5" />}
                </Fragment>
              ))}
            </BreadcrumbList>
          </Breadcrumb>
        ) : (
          <span className="text-sm font-medium">{getPageTitle()}</span>
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
        {actions}
      </div>
    </div>
  );
}
