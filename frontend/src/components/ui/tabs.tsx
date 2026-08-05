import * as React from 'react';
import * as TabsPrimitive from '@radix-ui/react-tabs';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const Tabs = TabsPrimitive.Root;

type TabsVariant = 'underline' | 'pill';

const TabsVariantContext = React.createContext<TabsVariant>('underline');
const TabsSizeContext = React.createContext<'default' | 'compact'>('default');

const tabsListVariants = cva('gap-0', {
  variants: {
    variant: {
      // DESIGN.md §6.5: the single tab vocabulary — underline style, IBM Plex
      // Sans 13px medium, sentence case, steel → ink when active, 2px signal
      // bottom border on the shared 1px ink baseline.
      underline:
        'inline-flex items-center justify-start border-b border-ink bg-transparent p-0',
      // Apple/iOS segmented control: a sunken track (bg-paper-deep, the app's
      // canonical recessed-surface token — see AgentRunDetailPage.tsx,
      // ToolCard.tsx) framing the raised active segment.
      pill: 'inline-flex items-center justify-center rounded-lg bg-paper-deep p-1',
    },
    layout: {
      inline: '',
      grid: 'grid w-full',
      scroll:
        'flex h-auto w-full justify-start overflow-x-auto overflow-y-hidden scrollbar-hidden',
    },
    size: {
      default: '',
      compact: 'h-8',
    },
  },
  defaultVariants: {
    variant: 'underline',
    layout: 'inline',
    size: 'default',
  },
});

const tabsTriggerVariants = cva(
  'inline-flex items-center justify-center whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 transition-colors',
  {
    variants: {
      variant: {
        underline:
          'border-b-2 border-transparent px-4 py-2 font-body text-[13px] font-medium text-steel hover:text-ink data-[state=active]:-mb-px data-[state=active]:border-signal data-[state=active]:text-ink',
        // flex-1: equal-width segments (a no-op inside layout="grid" parents,
        // which already get equal columns via the `cols` style hook — see
        // CategoryModal.tsx / ChatListing.tsx — but keeps a bare inline pill
        // list from shrink-wrapping to each label's width). shadow-md (not
        // shadow-sm/DEFAULT, both of which map to --shadow-flat: none) is
        // required for the active segment's "raised" lift to be visible at
        // all in the apple-quiet theme.
        pill: 'flex-1 rounded-md px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-md',
      },
      size: {
        default: '',
        compact: 'h-7',
      },
    },
    defaultVariants: {
      variant: 'underline',
      size: 'default',
    },
  },
);

interface TabsListProps
  extends React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>,
    VariantProps<typeof tabsListVariants> {
  cols?: number;
}

const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  TabsListProps
>(({ className, variant = 'underline', layout = 'inline', size = 'default', cols, style, ...props }, ref) => (
  <TabsVariantContext.Provider value={variant ?? 'underline'}>
    <TabsSizeContext.Provider value={size ?? 'default'}>
      <TabsPrimitive.List
        ref={ref}
        style={
          layout === 'grid' && cols
            ? { ...style, gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }
            : style
        }
        className={cn(tabsListVariants({ variant, layout, size }), className)}
        {...props}
      />
    </TabsSizeContext.Provider>
  </TabsVariantContext.Provider>
));
TabsList.displayName = TabsPrimitive.List.displayName;

interface TabsTriggerProps
  extends React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>,
    VariantProps<typeof tabsTriggerVariants> {}

const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  TabsTriggerProps
>(({ className, variant, size, ...props }, ref) => {
  const contextVariant = React.useContext(TabsVariantContext);
  const contextSize = React.useContext(TabsSizeContext);

  return (
    <TabsPrimitive.Trigger
      ref={ref}
      className={cn(
        tabsTriggerVariants({
          variant: variant ?? contextVariant,
          size: size ?? contextSize,
        }),
        className,
      )}
      {...props}
    />
  );
});
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      'mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
      className,
    )}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;

export { Tabs, TabsList, TabsTrigger, TabsContent };
