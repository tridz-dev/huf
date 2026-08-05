import * as React from 'react';

import { cn } from '@/lib/utils';

type CardDensity = 'default' | 'compact';

// Density is set once on <Card> and read by the sub-components below.
// A React context is used (over a `density` prop repeated on every
// sub-component) so callers state intent once at the <Card> callsite —
// that's the whole point of introducing this control. The alternative
// (explicit prop on each sub-component) is exactly the per-callsite
// repetition this change is meant to eliminate.
const CardDensityContext = React.createContext<CardDensity>('default');
const useCardDensity = () => React.useContext(CardDensityContext);

// Spacing scale: 4/8/12/16/24/32/48. Default keeps the existing 24px (p-6);
// compact uses 16px (p-4), a step down on the same scale.
const headerPadding: Record<CardDensity, string> = {
  default: 'p-6',
  compact: 'p-4',
};
const contentPadding: Record<CardDensity, string> = {
  default: 'p-6 pt-0',
  compact: 'p-4 pt-0',
};
const footerPadding: Record<CardDensity, string> = {
  default: 'p-6 pt-0',
  compact: 'p-4 pt-0',
};

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Controls padding density of CardHeader/CardContent/CardFooter. Defaults to 'default' (today's padding, unchanged). */
  density?: CardDensity;
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, density = 'default', ...props }, ref) => (
    <CardDensityContext.Provider value={density}>
      <div
        ref={ref}
        className={cn(
          // HUF: --panel bg, 1px --line border, 14px radius (var(--r-lg)), no shadow
          'rounded-lg border border-line bg-panel text-card-foreground',
          className
        )}
        {...props}
      />
    </CardDensityContext.Provider>
  )
);
Card.displayName = 'Card';

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => {
  const density = useCardDensity();
  return (
    <div
      ref={ref}
      className={cn('flex flex-col space-y-1.5', headerPadding[density], className)}
      {...props}
    />
  );
});
CardHeader.displayName = 'CardHeader';

const CardTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn('font-semibold leading-none tracking-tight', className)}
    {...props}
  />
));
CardTitle.displayName = 'CardTitle';

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn('text-sm text-muted-foreground', className)}
    {...props}
  />
));
CardDescription.displayName = 'CardDescription';

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => {
  const density = useCardDensity();
  return (
    <div ref={ref} className={cn(contentPadding[density], className)} {...props} />
  );
});
CardContent.displayName = 'CardContent';

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => {
  const density = useCardDensity();
  return (
    <div
      ref={ref}
      className={cn('flex items-center', footerPadding[density], className)}
      {...props}
    />
  );
});
CardFooter.displayName = 'CardFooter';

const CardAction = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('absolute right-4 top-4', className)}
    {...props}
  />
));
CardAction.displayName = 'CardAction';

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardDescription,
  CardContent,
  CardAction,
};
