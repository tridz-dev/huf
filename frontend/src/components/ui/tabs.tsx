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

// Reserve this much width for the "More" trigger itself when deciding how
// many tabs fit — its own rendered width isn't known until it's shown, and
// showing/hiding it to remeasure would flash. ~72px covers "More" + chevron
// + the row's 22px gap at the underline variant's font size.
const OVERFLOW_MORE_TRIGGER_WIDTH = 72;

const tabsListVariants = cva('gap-0', {
  variants: {
    variant: {
      // Single underline-style tab vocabulary; apple-quiet system font stack,
      // sentence case, steel → ink when active, ink rule on the shared hairline
      // baseline. Triggers carry no horizontal padding of their own — a
      // row-style tab bar is spaced by the 22px gap in compoundVariants below,
      // so labels read as a tight row rather than evenly-distributed buttons.
      underline:
        'inline-flex items-center justify-start border-b border-line bg-transparent p-0',
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
  // Row-style underline bars space their labels with a 22px gap (spec §25).
  // Deliberately NOT applied to layout="grid" (segments already get equal
  // columns via `cols`) or to variant="pill" (a segmented control's segments
  // must touch inside their sunken track).
  compoundVariants: [
    { variant: 'underline', layout: 'inline', class: 'gap-[22px]' },
    { variant: 'underline', layout: 'overflow', class: 'gap-[22px]' },
    { variant: 'underline', layout: 'scroll', class: 'gap-[22px]' },
  ],
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
        // No horizontal padding: the row is spaced by the list's 22px gap, so
        // each label's hit area ends with the text and the underline sits
        // exactly under the word (spec §25's agent-page tab row). The active
        // rule is 1.5px ink — violet is reserved for nav/selection state, the
        // tab underline in every page mockup is #1d1d1f.
        underline:
          'border-b-[1.5px] border-transparent pb-2.5 font-body text-[13px] text-steel hover:text-ink data-[state=active]:-mb-px data-[state=active]:border-ink data-[state=active]:font-[590] data-[state=active]:text-ink',
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
function partitionOverflowTriggers(
  children: React.ReactNode,
  activeValue: string | undefined,
  visibleCount: number,
) {
  const items = React.Children.toArray(children).filter(React.isValidElement) as React.ReactElement<{
    value?: string;
    disabled?: boolean;
    children?: React.ReactNode;
  }>[];

  if (items.length <= visibleCount) {
    return { visible: items, overflow: [] as typeof items };
  }

  let visible = items.slice(0, visibleCount);
  let overflow = items.slice(visibleCount);

  const activeOverflowIndex = overflow.findIndex((item) => item.props.value === activeValue);
  if (activeOverflowIndex !== -1 && visible.length > 0) {
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

/**
 * Measures how many of `items` fit in `containerWidth` (px), using a hidden
 * offscreen clone of each trigger's label rendered with the real trigger
 * classes so its width reflects actual font metrics. Recomputed whenever the
 * container resizes (ResizeObserver) or the item set changes.
 *
 * Falls back to showing everything until the first measurement lands, so
 * server-rendered/pre-hydration markup isn't empty.
 */
function useOverflowFit(
  items: React.ReactElement<{ children?: React.ReactNode }>[],
  hasOverflowCandidate: boolean,
) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const measureRef = React.useRef<HTMLDivElement>(null);
  const [visibleCount, setVisibleCount] = React.useState(items.length);

  const labels = items.map((item) => item.props.children);
  const labelsKey = labels.join('\u0000');

  React.useLayoutEffect(() => {
    if (!hasOverflowCandidate) {
      setVisibleCount(items.length);
      return;
    }

    const recompute = () => {
      const container = containerRef.current;
      const measure = measureRef.current;
      if (!container || !measure) return;

      const containerWidth = container.clientWidth;
      const gap = 22; // matches the underline layout="overflow" gap-[22px]
      const widths = Array.from(measure.children).map((el) => (el as HTMLElement).offsetWidth);

      let used = 0;
      let count = 0;
      for (let i = 0; i < widths.length; i += 1) {
        const next = used + widths[i] + (count > 0 ? gap : 0);
        const budget =
          i === widths.length - 1
            ? containerWidth
            : containerWidth - OVERFLOW_MORE_TRIGGER_WIDTH;
        if (next > budget && count > 0) break;
        used = next;
        count += 1;
      }
      setVisibleCount(Math.max(count, 1));
    };

    recompute();

    const container = containerRef.current;
    if (!container || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(recompute);
    observer.observe(container);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasOverflowCandidate, labelsKey]);

  return { containerRef, measureRef, visibleCount };
}

const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  TabsListProps
>(({ className, variant = 'underline', layout = 'inline', size = 'default', cols, style, children, ...props }, ref) => {
  const { value: activeValue, onValueChange } = React.useContext(TabsActiveContext);
  const isOverflow = layout === 'overflow';

  const allItems = React.Children.toArray(children).filter(React.isValidElement) as React.ReactElement<{
    value?: string;
    disabled?: boolean;
    children?: React.ReactNode;
  }>[];

  const { containerRef, measureRef, visibleCount } = useOverflowFit(allItems, isOverflow);

  const { visible, overflow } = isOverflow
    ? partitionOverflowTriggers(children, activeValue, visibleCount)
    : { visible: null, overflow: [] as ReturnType<typeof partitionOverflowTriggers>['overflow'] };

  const setRefs = React.useCallback(
    (node: HTMLDivElement | null) => {
      (containerRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
      if (typeof ref === 'function') ref(node as unknown as HTMLDivElement);
      else if (ref) (ref as React.MutableRefObject<HTMLDivElement | null>).current = node;
    },
    [containerRef, ref],
  );

  return (
    <TabsVariantContext.Provider value={variant ?? 'underline'}>
      <TabsSizeContext.Provider value={size ?? 'default'}>
        {isOverflow && (
          // Offscreen clone of every trigger label, rendered with the same
          // trigger classes, purely so useOverflowFit can read real widths
          // without flashing visible content. Never interactive.
          <div
            ref={measureRef}
            aria-hidden="true"
            className={cn(tabsListVariants({ variant, layout: 'inline', size }))}
            style={{ position: 'fixed', top: -9999, left: -9999, visibility: 'hidden', pointerEvents: 'none' }}
          >
            {allItems.map((item) => (
              <span
                key={item.props.value}
                className={cn(tabsTriggerVariants({ variant: variant ?? 'underline', size: size ?? 'default' }))}
              >
                {item.props.children}
              </span>
            ))}
          </div>
        )}
        <TabsPrimitive.List
          ref={setRefs}
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
                      className={cn(
                        tabsTriggerVariants({ variant: variant ?? 'underline', size: size ?? 'default' }),
                        'shrink-0 gap-1 text-steel-soft',
                      )}
                    >
                      More
                      <ChevronDown className="size-[13px]" aria-hidden="true" />
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
