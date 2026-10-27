import { lazy, Suspense } from 'react';
import { ProtectedRoute } from '../ProtectedRoute';
import { PageLoader } from '../PageLoader';
import { UnifiedLayout } from '../../layouts/UnifiedLayout';

const LinkAccountPage = lazy(() =>
  import('./LinkAccountPage').then((m) => ({ default: m.LinkAccountPage }))
);

/** Element for the /link-account route. */
export function LinkAccountRoute() {
  return (
    <ProtectedRoute>
      <UnifiedLayout>
        <Suspense fallback={<PageLoader />}>
          <LinkAccountPage />
        </Suspense>
      </UnifiedLayout>
    </ProtectedRoute>
  );
}
