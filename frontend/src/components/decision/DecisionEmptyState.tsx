import { LucideIcon, Package } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * Action handler for empty state buttons
 */
export interface EmptyStateAction {
  label: string;
  onClick: () => void;
}

/**
 * Props for DecisionEmptyState component
 */
export interface DecisionEmptyStateProps {
  /**
   * Icon to display. Defaults to Package.
   */
  icon?: LucideIcon;

  /**
   * Title text, e.g. "No policies yet"
   */
  title?: string;

  /**
   * Description text, e.g. "Create your first decision policy to get started."
   */
  description?: string;

  /**
   * Primary action button (e.g. Create Policy).
   * Omitted if not provided.
   */
  action?: EmptyStateAction;

  /**
   * Secondary action button (e.g. Learn more).
   * Rendered as an outline button below the primary action if provided.
   */
  secondaryAction?: EmptyStateAction;

  /**
   * Additional CSS class to apply to the container
   */
  className?: string;
}

/**
 * Reusable empty state component for Decision Runtime screens.
 *
 * Follows the HUF UI System empty-state pattern (spec §5.4). Displays when a
 * list, tab, or region is empty and provides action buttons to create or navigate.
 * Renders title, description, and up to two action buttons (primary and secondary).
 *
 * Example usage:
 * ```tsx
 * <DecisionEmptyState
 *   title="No policies yet"
 *   description="Create your first decision policy to get started."
 *   action={{ label: 'Create policy', onClick: () => navigate('/decisions/new') }}
 *   secondaryAction={{ label: 'View examples', onClick: () => ... }}
 * />
 * ```
 */
export function DecisionEmptyState({
  icon: Icon = Package,
  title = 'Nothing here yet',
  description,
  action,
  secondaryAction,
  className,
}: DecisionEmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center text-center p-10', className)}>
      {Icon && <Icon className="h-[22px] w-[22px] text-steel-soft" />}
      {title && <h3 className="text-[15px] font-medium text-ink mt-3">{title}</h3>}
      {description && (
        <p className="font-body text-[13px] text-steel mt-1 max-w-[30ch] text-pretty">
          {description}
        </p>
      )}
      {action && (
        <Button size="sm" className="mt-5" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
      {secondaryAction && (
        <Button
          variant={action ? 'link' : 'outline'}
          size="sm"
          className={cn('mt-1 h-auto p-0 text-[12px]', !action && 'mt-5')}
          onClick={secondaryAction.onClick}
        >
          {secondaryAction.label}
        </Button>
      )}
    </div>
  );
}
