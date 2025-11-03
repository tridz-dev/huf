import { ReactNode } from 'react';
import { useUser } from '@/contexts/UserContext';
import { AuthenticatingPage } from './AuthenticatingPage';

interface ProtectedRouteProps {
  children: ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isLoading, isAuthenticated } = useUser();

  if (isLoading) {
    return <AuthenticatingPage />;
  }

  if (!isAuthenticated) {
    // The redirect will be handled by UserContext
    return null;
  }

  return <>{children}</>;
}


