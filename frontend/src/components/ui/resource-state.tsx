/**
 * Shared loading / empty / error states for server-backed regions, driven by
 * the `useResource` contract.
 *
 *   const res = useResource(key, fetcher);
 *   <ResourceBoundary resource={res} empty={{ title: 'No agents yet' }}>
 *     {(data) => <AgentList items={data} />}
 *   </ResourceBoundary>
 *
 * Order: error without data -> ErrorState (with retry); loading -> LoadingState;
 * empty data -> EmptyState; otherwise children. If data exists, an error from a
 * background revalidate does not replace it.
 *
 * Do NOT use for: streaming chat, or regions that are not a copy of server data.
 * Copy must stay plain product language (no Frappe/REST mechanics).
 */
import type { ReactNode } from 'react';
import { AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { EmptyState, type EmptyStateProps } from '@/components/dashboard/views/EmptyState';
import type { ApiError } from '@/lib/api';
import { cn } from '@/lib/utils';

export { EmptyState };

export function LoadingState({ label = 'Loading', className }: { label?: string; className?: string }) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 p-10 text-center', className)}>
      <Spinner className="text-steel-soft" />
      <p className="font-body text-[13px] text-steel">{label}</p>
    </div>
  );
}

export interface ErrorStateProps {
  title?: string;
  /** Error or message; the message is shown as plain text. */
  error?: Pick<ApiError, 'message'> | string | null;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = 'Something went wrong',
  error,
  onRetry,
  className,
}: ErrorStateProps) {
  const message = typeof error === 'string' ? error : error?.message;
  return (
    <div
      role="alert"
      className={cn('flex flex-col items-center justify-center text-center p-10', className)}
    >
      <AlertCircle className="h-[22px] w-[22px] text-steel-soft" />
      <h3 className="text-[15px] font-medium text-ink mt-3">{title}</h3>
      {message && (
        <p className="font-body text-[13px] text-steel mt-1 max-w-[40ch] text-pretty">{message}</p>
      )}
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-5" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export interface ResourceLike<T> {
  data: T | undefined;
  error: Pick<ApiError, 'message'> | undefined;
  isLoading: boolean;
  refetch: () => Promise<unknown>;
}

export interface ResourceBoundaryProps<T> {
  resource: ResourceLike<T>;
  children: (data: T) => ReactNode;
  /** Props for the empty state, or false to disable empty handling. */
  empty?: EmptyStateProps | false;
  /** Custom emptiness test. Default: empty array. */
  isEmpty?: (data: T) => boolean;
  loadingLabel?: string;
  errorTitle?: string;
  className?: string;
}

function defaultIsEmpty(data: unknown): boolean {
  return Array.isArray(data) && data.length === 0;
}

export function ResourceBoundary<T>({
  resource,
  children,
  empty,
  isEmpty = defaultIsEmpty,
  loadingLabel,
  errorTitle,
  className,
}: ResourceBoundaryProps<T>) {
  const { data, error, isLoading, refetch } = resource;
  if (data === undefined) {
    if (error) {
      return (
        <ErrorState
          title={errorTitle}
          error={error}
          onRetry={() => void refetch().catch(() => {})}
          className={className}
        />
      );
    }
    if (isLoading) return <LoadingState label={loadingLabel} className={className} />;
    return null;
  }
  if (empty !== false && isEmpty(data)) {
    return <EmptyState variant="passive" className={className} {...empty} />;
  }
  return <>{children(data)}</>;
}
