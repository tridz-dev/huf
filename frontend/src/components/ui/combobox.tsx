import * as React from 'react';
import { Combobox as ComboboxPrimitive } from '@base-ui/react/combobox';
import { Check, ChevronsUpDown, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { LinkFieldAction } from '@/components/ui/link-field-control';
import { cn } from '@/lib/utils';

export interface ComboboxOption {
  value: string;
  label: string;
  subtitle?: string;
  action?: () => void;
}

type LegacyComboboxProps = Omit<
  ComboboxPrimitive.Root.Props<string, false>,
  'children' | 'items' | 'value' | 'defaultValue' | 'onValueChange'
> & {
  options: ComboboxOption[];
  value?: string | null;
  defaultValue?: string | null;
  onValueChange?: (value: string) => void;
  placeholder?: string;
  emptyText?: string;
  searchPlaceholder?: string;
  linkTo?: (value: string) => string | undefined;
  onSearchChange?: (search: string) => void;
  shouldFilter?: boolean;
  className?: string;
};

type CompoundSingleComboboxProps = Omit<
  ComboboxPrimitive.Root.Props<string, false>,
  'onValueChange' | 'value' | 'defaultValue'
> & {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
};
type CompoundMultipleComboboxProps = ComboboxPrimitive.Root.Props<string, true>;

export type ComboboxProps =
  | LegacyComboboxProps
  | CompoundSingleComboboxProps
  | CompoundMultipleComboboxProps;

export function Combobox(props: LegacyComboboxProps): React.JSX.Element;
export function Combobox(props: CompoundSingleComboboxProps): React.JSX.Element;
export function Combobox(props: CompoundMultipleComboboxProps): React.JSX.Element;
export function Combobox(
  props: ComboboxProps
): React.JSX.Element {
  const [open, setOpen] = React.useState(false);

  if (!('options' in props)) {
    if (props.multiple === true) {
      return <ComboboxPrimitive.Root {...(props as CompoundMultipleComboboxProps)} />;
    }

    const { onValueChange, ...rootProps } = props as CompoundSingleComboboxProps;
    return (
      <ComboboxPrimitive.Root
        {...rootProps}
        onValueChange={(nextValue) => onValueChange?.(nextValue || '')}
      />
    );
  }

  const {
    id,
    options = [],
    value,
    onValueChange,
    placeholder = 'Select option...',
    disabled = false,
    emptyText = 'No option found.',
    searchPlaceholder = 'Search...',
    linkTo,
    onSearchChange,
    shouldFilter,
    className,
    ...rootProps
  } = props;
  const selectedOption = options.find((option) => option.value === value);
  const href = typeof value === 'string' && linkTo ? linkTo(value) : undefined;
  const showLink = Boolean(href) && !disabled;

  return (
    <ComboboxPrimitive.Root
      {...rootProps}
      items={options.map((option) => option.value)}
      value={typeof value === 'string' ? value : null}
      open={open}
      onOpenChange={setOpen}
      onValueChange={(nextValue) => {
        const option = options.find((item) => item.value === nextValue);
        if (option?.action) {
          option.action();
          setOpen(false);
          return;
        }
        onValueChange?.(typeof nextValue === 'string' ? nextValue : '');
        setOpen(false);
      }}
      itemToStringLabel={(optionValue) =>
        options.find((option) => option.value === optionValue)?.label || optionValue
      }
      filter={
        shouldFilter === false
          ? null
          : (optionValue, query) => {
              const option = options.find((item) => item.value === optionValue);
              return `${option?.label || ''} ${option?.subtitle || ''}`
                .toLocaleLowerCase()
                .includes(query.toLocaleLowerCase());
            }
      }
      onInputValueChange={onSearchChange}
    >
      <ComboboxPrimitive.Trigger
        id={id}
        className={cn(
          'flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-2 text-sm font-normal shadow-sm outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
          className
        )}
        disabled={disabled}
      >
        <ComboboxPrimitive.Value>
          {selectedOption ? (
            <span className="min-w-0 flex-1 truncate text-left">{selectedOption.label}</span>
          ) : (
            <span className="min-w-0 flex-1 truncate text-left text-muted-foreground">{placeholder}</span>
          )}
        </ComboboxPrimitive.Value>
        <span className="flex shrink-0 items-center gap-0.5">
          {showLink && href ? <LinkFieldAction href={href} /> : null}
          <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
        </span>
      </ComboboxPrimitive.Trigger>
      <ComboboxContent className="w-[var(--anchor-width)] p-0">
        <ComboboxPrimitive.Input placeholder={searchPlaceholder} className="h-9 w-full border-b bg-transparent px-3 text-sm outline-none placeholder:text-muted-foreground" />
        <ComboboxEmpty>{emptyText}</ComboboxEmpty>
        <ComboboxList>
          {(optionValue: string) => {
            const option = options.find((item) => item.value === optionValue);
            if (!option) return null;

            return (
            <ComboboxItem key={option.value} value={option.value}>
              <span className="flex min-w-0 flex-col">
                <span className="truncate">{option.label}</span>
                {option.subtitle ? (
                  <span className="truncate text-xs text-muted-foreground">{option.subtitle}</span>
                ) : null}
              </span>
            </ComboboxItem>
            );
          }}
        </ComboboxList>
      </ComboboxContent>
    </ComboboxPrimitive.Root>
  );
}

export function ComboboxValue(props: React.ComponentProps<typeof ComboboxPrimitive.Value>) {
  return <ComboboxPrimitive.Value data-slot="combobox-value" {...props} />;
}

export const ComboboxChips = React.forwardRef<
  React.ElementRef<typeof ComboboxPrimitive.Chips>,
  React.ComponentPropsWithoutRef<typeof ComboboxPrimitive.Chips>
>(function ComboboxChips({ className, ...props }, ref) {
  return (
    <ComboboxPrimitive.Chips
      ref={ref}
      data-slot="combobox-chips"
      className={cn(
        'flex min-h-9 w-full flex-wrap items-center gap-1.5 rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm shadow-sm focus-within:ring-1 focus-within:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      {...props}
    />
  );
});
ComboboxChips.displayName = 'ComboboxChips';

export function ComboboxChip({
  className,
  children,
  showRemove = true,
  removeLabel = 'Remove',
  ...props
}: React.ComponentProps<typeof ComboboxPrimitive.Chip> & {
  showRemove?: boolean;
  removeLabel?: string;
}) {
  return (
    <ComboboxPrimitive.Chip
      data-slot="combobox-chip"
      className={cn(
        'flex h-6 w-fit items-center gap-1 rounded-sm bg-secondary px-1.5 text-xs font-medium text-secondary-foreground',
        className
      )}
      {...props}
    >
      {children}
      {showRemove ? (
        <ComboboxPrimitive.ChipRemove
          aria-label={removeLabel}
          render={<Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0" />}
          className="opacity-60 hover:opacity-100"
        >
          <X className="h-3 w-3" aria-hidden="true" />
        </ComboboxPrimitive.ChipRemove>
      ) : null}
    </ComboboxPrimitive.Chip>
  );
}

export function ComboboxChipsInput({
  className,
  ...props
}: React.ComponentProps<typeof ComboboxPrimitive.Input>) {
  return (
    <ComboboxPrimitive.Input
      data-slot="combobox-chips-input"
      className={cn('min-w-16 flex-1 bg-transparent outline-none placeholder:text-muted-foreground', className)}
      {...props}
    />
  );
}

type ComboboxContentProps = React.ComponentProps<typeof ComboboxPrimitive.Popup> &
  Pick<
    React.ComponentProps<typeof ComboboxPrimitive.Positioner>,
    'side' | 'align' | 'sideOffset' | 'alignOffset' | 'anchor'
  > & {
    portalContainer?: React.ComponentProps<typeof ComboboxPrimitive.Portal>['container'];
  };

export function ComboboxContent({
  className,
  side = 'bottom',
  sideOffset = 4,
  align = 'start',
  alignOffset = 0,
  anchor,
  portalContainer,
  ...props
}: ComboboxContentProps) {
  return (
    <ComboboxPrimitive.Portal container={portalContainer}>
      <ComboboxPrimitive.Positioner
        side={side}
        sideOffset={sideOffset}
        align={align}
        alignOffset={alignOffset}
        anchor={anchor}
        className="z-50"
      >
        <ComboboxPrimitive.Popup
          data-slot="combobox-content"
          className={cn(
            'z-50 max-h-80 min-w-[var(--anchor-width)] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md',
            className
          )}
          {...props}
        />
      </ComboboxPrimitive.Positioner>
    </ComboboxPrimitive.Portal>
  );
}

export function ComboboxEmpty(props: React.ComponentProps<typeof ComboboxPrimitive.Empty>) {
  return (
    <ComboboxPrimitive.Empty
      data-slot="combobox-empty"
      className={cn('hidden w-full justify-center py-2 text-center text-sm text-muted-foreground', props.className)}
      {...props}
    />
  );
}

export function ComboboxList({
  className,
  ...props
}: React.ComponentProps<typeof ComboboxPrimitive.List>) {
  return (
    <ComboboxPrimitive.List
      data-slot="combobox-list"
      className={cn('max-h-72 overflow-y-auto p-1', className)}
      {...props}
    />
  );
}

export function ComboboxItem({
  className,
  children,
  ...props
}: React.ComponentProps<typeof ComboboxPrimitive.Item>) {
  return (
    <ComboboxPrimitive.Item
      data-slot="combobox-item"
      className={cn(
        'relative flex w-full cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
        className
      )}
      {...props}
    >
      {children}
      <ComboboxPrimitive.ItemIndicator
        render={<span className="pointer-events-none absolute right-2 flex h-4 w-4 items-center justify-center" />}
      >
        <Check className="h-4 w-4" />
      </ComboboxPrimitive.ItemIndicator>
    </ComboboxPrimitive.Item>
  );
}

export function useComboboxAnchor() {
  return React.useRef<HTMLDivElement | null>(null);
}