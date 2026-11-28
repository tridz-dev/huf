import { lazy, Suspense } from 'react';
import { PageLoader } from '@/components/PageLoader';

const EmbedFlowPage = lazy(() => import('./EmbedFlowPage'));

export const EMBED_PATHS = ['/embed/flow/:flowId', '/embed/*'];

export function EmbedRoute() {
  return (
    <Suspense fallback={<PageLoader />}>
      <EmbedFlowPage />
    </Suspense>
  );
}
