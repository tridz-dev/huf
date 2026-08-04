import { ReactNode } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AppSidebar } from '../components/app-sidebar';
import { UnifiedHeader } from './UnifiedHeader';
import { AppTopbar } from './AppTopbar';
import {
  SidebarProvider,
  SidebarInset,
} from '../components/ui/sidebar';
import { ShortcutsHelpProvider } from '../components/shortcuts/ShortcutsHelpContext';

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
  const location = useLocation();
  const defaultOpen = location.pathname !== '/';

  return (
    <ShortcutsHelpProvider>
      <SidebarProvider defaultOpen={defaultOpen}>
        <AppSidebar />
        <SidebarInset className="h-svh max-h-svh overflow-hidden">
          {!hideHeader && (
            <AppTopbar>
              <UnifiedHeader actions={headerActions} breadcrumbs={breadcrumbs} />
            </AppTopbar>
          )}
          <main className="flex-1 overflow-hidden flex flex-col min-h-0">
            {children || <Outlet />}
          </main>
        </SidebarInset>
      </SidebarProvider>
    </ShortcutsHelpProvider>
  );
}
