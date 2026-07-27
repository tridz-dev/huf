import { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, Home } from 'lucide-react';
import { useUser } from '@/contexts/UserContext';
import { usePermissions } from '@/contexts/PermissionsContext';
import { AuthenticatingPage } from './AuthenticatingPage';
import { Button } from './ui/button';

interface ProtectedRouteProps {
  children: ReactNode;
  /**
   * Capability required to view this route (see huf/permissions.py
   * CAPABILITIES). Only pass this for routes that are exclusively a
   * creation/management action distinct from viewing (e.g. "/data/new") —
   * a route shared between viewing and editing (e.g. "/agents/:id") must
   * gate edit/save affordances inside the page instead, since a viewer
   * without edit rights should still be able to open the page.
   */
  requiredCapability?: string;
}

export function ProtectedRoute({ children, requiredCapability }: ProtectedRouteProps) {
  const { isLoading, isAuthenticated } = useUser();
  const { isLoading: permissionsLoading, hasCapability } = usePermissions();
  const navigate = useNavigate();

  if (isLoading || (requiredCapability && permissionsLoading)) {
    return <AuthenticatingPage />;
  }

  if (!isAuthenticated) {
    // The redirect will be handled by UserContext
    return null;
  }

  if (requiredCapability && !hasCapability(requiredCapability)) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-6 max-w-md">
          <div className="flex justify-center">
            <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center">
              <AlertCircle className="w-8 h-8 text-destructive" />
            </div>
          </div>
          <div>
            <h2 className="text-xl font-semibold mb-2">No permission</h2>
            <p className="text-steel">
              You don't have permission to access this page. Contact a Huf Admin or Manager for access.
            </p>
          </div>
          <Button onClick={() => navigate('/')}>
            <Home className="w-4 h-4 mr-2" />
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}


