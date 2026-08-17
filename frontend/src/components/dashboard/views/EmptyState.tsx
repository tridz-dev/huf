import { LucideIcon, PackageOpen } from 'lucide-react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// Empty-state variants, per HUF UI System spec ("26 / EMPTY STATES", lines
// 2376-2452): "There are only four situations, and they differ in one
// thing: whether the user can do something about it. That decides whether
// there is a button."
//
//   A / create      — nothing has been made yet. Primary create button
//                      (same action as the page toolbar) plus an optional
//                      plain-text secondary link ("How flows work").
//   B / no-results   — a filter/search excluded everything. No primary
//                      button; a single secondary "Clear filters" action.
//   C / passive      — the region fills itself over time. No primary
//                      button; a single secondary action that points
//                      upstream to whatever produces the data.
//
// The fourth situation (a single stat/metric with no value, spec line
// 2416-2425) is visually a different shape entirely — an em dash and a
// caption, no icon, no title, never a button — so it is not a variant of
// this component. It is the sibling export `EmptyStat` below.
const emptyStateVariants = cva(
  'flex flex-col items-center justify-center text-center p-10',
  {
    variants: {
      variant: {
        create: '',
        'no-results': '',
        passive: '',
      },
    },
    defaultVariants: {
      variant: 'create',
    },
  },
);

interface EmptyStateAction {
  label: string;
  onClick: () => void;
}

export interface EmptyStateProps extends VariantProps<typeof emptyStateVariants> {
  icon?: LucideIcon;
  title?: string;
  description?: string;
  /**
   * Filter/search term that produced an empty result. Only read by the
   * `no-results` variant, to interpolate a default description ("Nothing
   * matches \"invoice\"."). Ignored if `description` is also passed.
   */
  filterTerm?: string;
  /**
   * Primary call to action. Only rendered for the `create` variant (spec:
   * "One button, and only when the user can act" — the `no-results` and
   * `passive` situations never get a primary create button).
   */
  action?: EmptyStateAction;
  /**
   * Secondary action. Meaning depends on the variant:
   *  - `create`: a plain text link under the primary button (e.g. "How
   *    flows work").
   *  - `no-results`: the "Clear filters" button.
   *  - `passive`: the button that points upstream to what fills the
   *    region (e.g. "Start a chat").
   */
  secondaryAction?: EmptyStateAction;
  className?: string;
}

export function EmptyState({
  variant,
  icon: Icon = PackageOpen,
  title = 'Nothing here yet',
  description,
  filterTerm,
  action,
  secondaryAction,
  className,
}: EmptyStateProps) {
  const resolvedVariant = variant ?? 'create';
  const resolvedDescription =
    description ??
    (resolvedVariant === 'no-results' && filterTerm
      ? `Nothing matches "${filterTerm}".`
      : 'Items you create will show up here.');

  return (
    <div className={cn(emptyStateVariants({ variant: resolvedVariant }), className)}>
      {Icon && <Icon className="h-[22px] w-[22px] text-steel-soft" />}
      {title && <h3 className="text-[15px] font-medium text-ink mt-3">{title}</h3>}
      {resolvedDescription && (
        <p className="font-body text-[13px] text-steel mt-1 max-w-[30ch] text-pretty">
          {resolvedDescription}
        </p>
      )}
      {resolvedVariant === 'create' && action && (
        <Button size="sm" className="mt-5" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
      {resolvedVariant === 'create' && secondaryAction && (
        <Button
          variant="link"
          size="sm"
          className="mt-1 h-auto p-0 text-[12px]"
          onClick={secondaryAction.onClick}
        >
          {secondaryAction.label}
        </Button>
      )}
      {(resolvedVariant === 'no-results' || resolvedVariant === 'passive') &&
        secondaryAction && (
          <Button
            variant="outline"
            size="sm"
            className="mt-5"
            onClick={secondaryAction.onClick}
          >
            {secondaryAction.label}
          </Button>
        )}
    </div>
  );
}

export interface EmptyStatProps {
  /** e.g. "Cache ratio" */
  label: string;
  /** e.g. "No completed runs in this period." */
  caption: string;
  /**
   * Optional longer explanation shown below a hairline, e.g. "Nothing
   * failed; there is simply nothing to divide." Per spec: never render the
   * word "Unavailable" — the em dash already says that.
   */
  footnote?: string;
  className?: string;
}

/**
 * Stat/metric no-value state (spec "D / NO VALUE", lines 2416-2425): an
 * em dash in tertiary grey standing in for a figure that cannot be
 * computed, plus a caption. Never a button — there is nothing to act on.
 * Kept as a sibling export rather than an `EmptyState` variant because the
 * shape is unrelated: no icon, no title, no action slot, and it sits
 * inline in a stat tile instead of centred in a content well.
 */
export function EmptyStat({ label, caption, footnote, className }: EmptyStatProps) {
  return (
    <div className={cn('flex flex-col gap-3.5', className)}>
      <div className="flex flex-col gap-1">
        <div className="text-[13px] font-medium text-ink">{label}</div>
        <div className="text-[30px] font-medium leading-none tracking-tight text-steel-soft">
          &mdash;
        </div>
        <div className="text-[12px] text-steel-soft">{caption}</div>
      </div>
      {footnote && (
        <p className="text-[12px] leading-relaxed text-steel border-t border-line pt-3">
          {footnote}
        </p>
      )}
    </div>
  );
}
