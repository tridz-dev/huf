import { ReactNode } from 'react';
import { Outlet } from 'react-router-dom';
import { AppSidebar } from '../components/app-sidebar';
import { UnifiedHeader } from './UnifiedHeader';
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from '../components/ui/sidebar';
import { Separator } from '../components/ui/separator';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface UnifiedLayoutProps {
  children?: ReactNode;
  sidebarContent?: ReactNode;
  hideHeader?: boolean;
  headerActions?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
}

export function UnifiedLayout({ children, hideHeader, headerActions, breadcrumbs }: UnifiedLayoutProps) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        {!hideHeader && (
          <header className="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-12 border-b">
            <div className="flex items-center gap-2 px-4 w-full">
              <SidebarTrigger className="-ml-1" />
              <Separator orientation="vertical" className="mr-2 h-4" />
              <UnifiedHeader actions={headerActions} breadcrumbs={breadcrumbs} />
            </div>
          </header>
        )}
        <main className="flex-1 overflow-hidden flex flex-col">
          {children || <Outlet />}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
