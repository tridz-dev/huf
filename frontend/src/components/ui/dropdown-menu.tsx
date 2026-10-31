import * as React from 'react';
import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu';
import {
  CheckIcon,
  ChevronRightIcon,
  DotFilledIcon,
} from '@radix-ui/react-icons';

import { useClosingGuard, withGuard } from '@/hooks/useClosingGuard';

import { cn } from '@/lib/utils';

/**
 * The menu keeps its own open state (controlled or not) so Tab can close it from inside, and remembers its trigger and which
 * way Tab was pressed, so focus can move on to the next (Shift+Tab: previous) tabbable item after the trigger.
 */
interface MenuContext {
  close: () => void;
  triggerRef: React.MutableRefObject<HTMLElement | null>;
  tabDirection: React.MutableRefObject<1 | -1 | 0>;
}
const MenuCtx = React.createContext<MenuContext | null>(null);

function DropdownMenu({ open, defaultOpen, onOpenChange, ...props }: React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Root>) {
  const [inner, setInner] = React.useState(defaultOpen ?? false);
  const controlled = open !== undefined;
  const isOpen = controlled ? open : inner;
  const change = React.useCallback(
    (next: boolean) => {
      if (!controlled) setInner(next);
      onOpenChange?.(next);
    },
    [controlled, onOpenChange]
  );
  const triggerRef = React.useRef<HTMLElement | null>(null);
  const tabDirection = React.useRef<1 | -1 | 0>(0);
  const ctx = React.useMemo<MenuContext>(() => ({ close: () => change(false), triggerRef, tabDirection }), [change]);
  return (
    <MenuCtx.Provider value={ctx}>
      <DropdownMenuPrimitive.Root open={isOpen} onOpenChange={change} {...props} />
    </MenuCtx.Provider>
  );
}

const DropdownMenuTrigger = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Trigger>
>(({ ...props }, forwardedRef) => {
  const ctx = React.useContext(MenuCtx);
  const ref = React.useCallback(
    (node: HTMLButtonElement | null) => {
      if (ctx) ctx.triggerRef.current = node;
      if (typeof forwardedRef === 'function') forwardedRef(node);
      else if (forwardedRef) forwardedRef.current = node;
    },
    [ctx, forwardedRef]
  );
  return <DropdownMenuPrimitive.Trigger ref={ref} {...props} />;
});
DropdownMenuTrigger.displayName = DropdownMenuPrimitive.Trigger.displayName;

const TABBABLE = 'a[href], button, input, select, textarea, summary, [tabindex], [contenteditable="true"]';

/** The tabbable element after (dir 1) or before (dir -1) `from` in page order, skipping hidden, disabled and menu contents. */
export function tabbableNeighbour(from: HTMLElement, dir: 1 | -1): HTMLElement | null {
  const all = Array.from(document.querySelectorAll<HTMLElement>(TABBABLE)).filter((el) => {
    if (el !== from && el.closest('[role="menu"], [data-radix-popper-content-wrapper]')) return false;
    if ((el as HTMLButtonElement).disabled || el.tabIndex < 0 || el.closest('[inert], [aria-hidden="true"]')) return false;
    return el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  });
  const at = all.indexOf(from);
  return at < 0 ? null : all[at + dir] ?? null;
}

/** Tab inside an open menu: close the whole menu (submenus too) and remember the direction for onCloseAutoFocus. */
function useTabLeaves() {
  const ctx = React.useContext(MenuCtx);
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.defaultPrevented || event.key !== 'Tab' || !ctx) return;
    event.preventDefault();
    event.stopPropagation();
    ctx.tabDirection.current = event.shiftKey ? -1 : 1;
    ctx.close();
  };
  const onCloseAutoFocus = (event: Event) => {
    const dir = ctx?.tabDirection.current ?? 0;
    if (!ctx || dir === 0) return;
    ctx.tabDirection.current = 0;
    const trigger = ctx.triggerRef.current;
    const target = trigger ? tabbableNeighbour(trigger, dir) : null;
    // No neighbour (the trigger is the last or first tabbable thing): Radix puts focus back on the trigger, as for Escape.
    if (target) {
      event.preventDefault();
      target.focus();
    }
  };
  return { onKeyDown, onCloseAutoFocus };
}

const DropdownMenuGroup = DropdownMenuPrimitive.Group;

const DropdownMenuPortal = DropdownMenuPrimitive.Portal;

const DropdownMenuSub = DropdownMenuPrimitive.Sub;

const DropdownMenuRadioGroup = DropdownMenuPrimitive.RadioGroup;

const DropdownMenuSubTrigger = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.SubTrigger>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.SubTrigger> & {
    inset?: boolean;
  }
>(({ className, inset, children, ...props }, ref) => (
  <DropdownMenuPrimitive.SubTrigger
    ref={ref}
    className={cn(
      'flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none focus:bg-accent data-[state=open]:bg-accent',
      inset && 'pl-8',
      className
    )}
    {...props}
  >
    {children}
    <ChevronRightIcon className="ml-auto h-4 w-4" />
  </DropdownMenuPrimitive.SubTrigger>
));
DropdownMenuSubTrigger.displayName =
  DropdownMenuPrimitive.SubTrigger.displayName;

const DropdownMenuSubContent = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.SubContent>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.SubContent>
>(({ className, onKeyDown, ...props }, ref) => {
  const leave = useTabLeaves();
  return (
  <DropdownMenuPrimitive.SubContent
    ref={ref}
    onKeyDown={(event) => {
      onKeyDown?.(event);
      leave.onKeyDown(event);
    }}
    className={cn(
      'z-50 min-w-[8rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2',
      className
    )}
    {...props}
  />
  );
});
DropdownMenuSubContent.displayName =
  DropdownMenuPrimitive.SubContent.displayName;

const DropdownMenuContent = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Content>
>(({ className, sideOffset = 4, onInteractOutside, onKeyDown, onCloseAutoFocus, ...props }, forwardedRef) => {
  const { ref, guard } = useClosingGuard(forwardedRef);
  const leave = useTabLeaves();
  return (
  <DropdownMenuPrimitive.Portal>
    <DropdownMenuPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      onInteractOutside={withGuard(onInteractOutside, guard)}
      // Radix swallows Tab inside a menu, which left the menu open with the page behind it inert. Tab closes the menu and moves
      // focus on to the next tabbable item after the trigger (Shift+Tab: the previous one).
      onKeyDown={(event) => {
        onKeyDown?.(event);
        leave.onKeyDown(event);
      }}
      onCloseAutoFocus={(event) => {
        onCloseAutoFocus?.(event);
        if (!event.defaultPrevented) leave.onCloseAutoFocus(event);
      }}
      className={cn(
        'z-50 min-w-[8rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md',
        'data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2',
        className
      )}
      {...props}
    />
  </DropdownMenuPrimitive.Portal>
  );
});
DropdownMenuContent.displayName = DropdownMenuPrimitive.Content.displayName;

const DropdownMenuItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item> & {
    inset?: boolean;
    variant?: 'default' | 'destructive';
  }
>(({ className, inset, variant = 'default', ...props }, ref) => (
  <DropdownMenuPrimitive.Item
    ref={ref}
    className={cn(
      'relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
      inset && 'pl-8',
      variant === 'destructive' && 'text-destructive focus:bg-destructive-tint focus:text-destructive',
      className
    )}
    {...props}
  />
));
DropdownMenuItem.displayName = DropdownMenuPrimitive.Item.displayName;

const DropdownMenuCheckboxItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.CheckboxItem>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.CheckboxItem>
>(({ className, children, checked, ...props }, ref) => (
  <DropdownMenuPrimitive.CheckboxItem
    ref={ref}
    className={cn(
      'relative flex cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
      className
    )}
    checked={checked}
    {...props}
  >
    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
      <DropdownMenuPrimitive.ItemIndicator>
        <CheckIcon className="h-4 w-4" />
      </DropdownMenuPrimitive.ItemIndicator>
    </span>
    {children}
  </DropdownMenuPrimitive.CheckboxItem>
));
DropdownMenuCheckboxItem.displayName =
  DropdownMenuPrimitive.CheckboxItem.displayName;

const DropdownMenuRadioItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.RadioItem>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.RadioItem>
>(({ className, children, ...props }, ref) => (
  <DropdownMenuPrimitive.RadioItem
    ref={ref}
    className={cn(
      'relative flex cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
      className
    )}
    {...props}
  >
    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
      <DropdownMenuPrimitive.ItemIndicator>
        <DotFilledIcon className="h-4 w-4 fill-current" />
      </DropdownMenuPrimitive.ItemIndicator>
    </span>
    {children}
  </DropdownMenuPrimitive.RadioItem>
));
DropdownMenuRadioItem.displayName = DropdownMenuPrimitive.RadioItem.displayName;

const DropdownMenuLabel = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Label>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Label> & {
    inset?: boolean;
  }
>(({ className, inset, ...props }, ref) => (
  <DropdownMenuPrimitive.Label
    ref={ref}
    className={cn(
      'px-2 py-1.5 text-sm font-semibold',
      inset && 'pl-8',
      className
    )}
    {...props}
  />
));
DropdownMenuLabel.displayName = DropdownMenuPrimitive.Label.displayName;

const DropdownMenuSeparator = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Separator>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Separator>
>(({ className, ...props }, ref) => (
  <DropdownMenuPrimitive.Separator
    ref={ref}
    className={cn('-mx-1 my-1 h-px bg-muted', className)}
    {...props}
  />
));
DropdownMenuSeparator.displayName = DropdownMenuPrimitive.Separator.displayName;

const DropdownMenuShortcut = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) => {
  return (
    <span
      className={cn('ml-auto text-xs tracking-widest opacity-60', className)}
      {...props}
    />
  );
};
DropdownMenuShortcut.displayName = 'DropdownMenuShortcut';

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuRadioItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuGroup,
  DropdownMenuPortal,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuRadioGroup,
};
