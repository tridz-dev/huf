import * as React from 'react';
import * as TabsPrimitive from '@radix-ui/react-tabs';
import { cva, type VariantProps } from 'class-variance-authority';
import { ChevronDown } from 'lucide-react';

import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

// Tracks the controlled value/onValueChange passed to `Tabs` so that
// `TabsList`'s layout="overflow" mode (several DOM levels below the Radix
// root) can tell which tab is active without Radix exposing that context
// publicly, and can move overflowed tabs back into view when selected via
// the "More" dropdown. Uncontrolled `Tabs` (defaultValue only, no
// value/onValueChange) simply leaves this context empty — layout="overflow"
// degrades to "always show the first N tabs" in that case, which no current
// caller relies on.
const TabsActiveContext = React.createContext<{
  value?: string;
  onValueChange?: (value: string) => void;
}>({});

const Tabs = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Root>
>(({ value, onValueChange, ...props }, ref) => (
  <TabsActiveContext.Provider value={{ value, onValueChange }}>
    <TabsPrimitive.Root ref={ref} value={value} onValueChange={onValueChange} {...props} />
  </TabsActiveContext.Provider>
));
Tabs.displayName = TabsPrimitive.Root.displayName;

type TabsVariant = 'underline' | 'pill';

const TabsVariantContext = React.createContext<TabsVariant>('underline');
const TabsSizeContext = React.createContext<'default' | 'compact'>('default');

// Beyond this many triggers, layout="overflow" collapses the rest into a
// "More" dropdown instead of letting the tab bar scroll or wrap.
const OVERFLOW_VISIBLE_COUNT = 6;

const tabsListVariants = cva('gap-0', {
  variants: {
    variant: {
      // Single underline-style tab vocabulary; apple-quiet system font stack,
      // sentence case, steel → ink when active, purple signal bottom border on
      // shared ink baseline.
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
      // Same row as "inline", but paired with overflow-collapsing logic in
      // TabsList below instead of horizontal scrolling — see
      // OVERFLOW_VISIBLE_COUNT.
      overflow: 'flex h-auto items-center justify-start',
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

/**
 * Splits `children` (expected to be TabsTrigger elements) into the triggers
 * shown inline and the ones collapsed into the "More" menu, keeping the
 * currently active tab always visible.
 *
 * If the active tab would otherwise land in the overflow bucket, it's
 * swapped in for the last inline slot (which drops into overflow instead) —
 * so the user never has to open the menu to see which tab they're on.
 */
function partitionOverflowTriggers(children: React.ReactNode, activeValue: string | undefined) {
  const items = React.Children.toArray(children).filter(React.isValidElement) as React.ReactElement<{
    value?: string;
    disabled?: boolean;
    children?: React.ReactNode;
  }>[];

  if (items.length <= OVERFLOW_VISIBLE_COUNT) {
    return { visible: items, overflow: [] as typeof items };
  }

  let visible = items.slice(0, OVERFLOW_VISIBLE_COUNT);
  let overflow = items.slice(OVERFLOW_VISIBLE_COUNT);

  const activeOverflowIndex = overflow.findIndex((item) => item.props.value === activeValue);
  if (activeOverflowIndex !== -1) {
    const activeItem = overflow[activeOverflowIndex];
    const displaced = visible[visible.length - 1];
    visible = [...visible.slice(0, -1), activeItem];
    overflow = [
      displaced,
      ...overflow.slice(0, activeOverflowIndex),
      ...overflow.slice(activeOverflowIndex + 1),
    ];
  }

  return { visible, overflow };
}

const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  TabsListProps
>(({ className, variant = 'underline', layout = 'inline', size = 'default', cols, style, children, ...props }, ref) => {
  const { value: activeValue, onValueChange } = React.useContext(TabsActiveContext);
  const isOverflow = layout === 'overflow';

  const { visible, overflow } = isOverflow
    ? partitionOverflowTriggers(children, activeValue)
    : { visible: null, overflow: [] as ReturnType<typeof partitionOverflowTriggers>['overflow'] };

  return (
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
        >
          {isOverflow ? (
            <>
              {visible}
              {overflow.length > 0 && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="inline-flex shrink-0 items-center whitespace-nowrap px-4 py-2 font-body text-[13px] font-medium text-steel-soft transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    >
                      More
                      <ChevronDown className="ml-1 size-[13px]" aria-hidden="true" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {overflow.map((item) => (
                      <DropdownMenuItem
                        key={item.props.value}
                        disabled={item.props.disabled}
                        onSelect={() => {
                          if (item.props.value) onValueChange?.(item.props.value);
                        }}
                      >
                        {item.props.children}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </>
          ) : (
            children
          )}
        </TabsPrimitive.List>
      </TabsSizeContext.Provider>
    </TabsVariantContext.Provider>
  );
});
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
