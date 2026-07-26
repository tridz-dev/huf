import { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { useUser } from '@/contexts/UserContext';
import { usePermissions } from '@/contexts/PermissionsContext';
import { AuthenticatingPage } from './AuthenticatingPage';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';

interface ProtectedRouteProps {
  children: ReactNode;
  capability?: string;
}

function AccessDenied({ capability }: { capability?: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center p-6 bg-background">
      <Card className="w-full max-w-md text-center">
        <CardContent className="pt-8 pb-8">
          <ShieldAlert className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
          <h1 className="text-2xl font-semibold text-foreground mb-2">Access Denied</h1>
          <p className="text-muted-foreground mb-6">
            {capability
              ? `You need the "${capability}" permission to view this page. Contact your administrator if you think this is a mistake.`
              : "You don't have permission to view this page. Contact your administrator if you think this is a mistake."}
          </p>
          <Button asChild variant="outline">
            <Link to="/">Go to Dashboard</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export function ProtectedRoute({ children, capability }: ProtectedRouteProps) {
  const { isLoading: userLoading, isAuthenticated } = useUser();
  const { hasCapability, isLoading: permissionsLoading } = usePermissions();

  if (userLoading) {
    return <AuthenticatingPage />;
  }

  if (!isAuthenticated) {
    // The redirect will be handled by UserContext
    return null;
  }

  if (capability) {
    if (permissionsLoading) {
      return <AuthenticatingPage />;
    }
    if (!hasCapability(capability)) {
      return <AccessDenied capability={capability} />;
    }
  }

  return <>{children}</>;
}


