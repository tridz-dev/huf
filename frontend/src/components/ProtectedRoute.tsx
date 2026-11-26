import { useResourceAccess, type Resource } from '@/hooks/permissions/useResourceAccess';
import { useLocation } from 'react-router-dom';
import { ReactNode } from 'react';
import { useUser } from '@/contexts/UserContext';
import { usePermissions } from '@/contexts/PermissionsContext';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { hasPageAccess, type PageCapability } from '@/lib/permissions/pageAccess';

export { PAGE_ACCESS, PAGE_ACCESS_ANY } from '@/lib/permissions/pageAccess';
import { AuthenticatingPage } from './AuthenticatingPage';
import { NoAccessPanel } from './common/NoAccessPanel';

interface ProtectedRouteProps {
  children: ReactNode;
  /**
   * Capability (or list of alternatives; see lib/permissions/pageAccess.ts) required to view this route. A person without it
   * gets a friendly "You don't have access to this page" in place of the page, so the page never mounts and never asks the
   * server for data its role may not read. A route shared between viewing and editing (e.g. "/agents/:id") should still gate
   * its edit and save controls inside the page.
   */
  requiredCapability?: PageCapability;
  /** Name used in the "no access" sentence, e.g. "Executions". */
  pageName?: string;
  /** On the route's ".../new" URL, block people who may not create this. */
  createResource?: Resource;
}

export function ProtectedRoute({ children, requiredCapability, pageName, createResource }: ProtectedRouteProps) {
  const { isLoading, isAuthenticated } = useUser();
  const { isLoading: permissionsLoading, capabilities } = usePermissions();

  const { pathname } = useLocation();
  const access = useResourceAccess(createResource ?? 'role');
  const isCreating = Boolean(createResource) && pathname.replace(/\/+$/, '').endsWith('/new');

  if (isLoading || ((requiredCapability || isCreating) && permissionsLoading)) {
    return <AuthenticatingPage />;
  }

  if (!isAuthenticated) {
    // The redirect will be handled by UserContext
    return null;
  }

  if (requiredCapability && !hasPageAccess(capabilities, requiredCapability)) {
    return (
      <UnifiedLayout>
        <NoAccessPanel pageName={pageName} />
      </UnifiedLayout>
    );
  }

  if (isCreating && !access.canCreate) {
    return (
      <UnifiedLayout>
        <NoAccessPanel pageName="Creating this" />
      </UnifiedLayout>
    );
  }

  return <>{children}</>;
}
