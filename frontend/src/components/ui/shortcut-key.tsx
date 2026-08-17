import { cn } from "@/lib/utils"

interface ShortcutKeyProps {
    children?: React.ReactNode
    /** Render one badge per key label (e.g. ["⌘", "K"]) instead of `children`. */
    keys?: string[]
    size?: "sm" | "md"
    className?: string
    /**
     * Hide the badge until an ancestor is hovered/focused. Use for shortcut
     * hints attached to an actionable element (a button, a menu item) — not
     * for standalone informational text. `true` matches a plain `group`
     * ancestor; `"shortcut-hint"` matches a named `group/shortcut-hint`
     * ancestor (needed when that ancestor already uses plain `group` for
     * something else, e.g. sidebar collapse state).
     */
    hoverOnly?: boolean | "shortcut-hint"
}

export function ShortcutKey({ children, keys, size = "md", className, hoverOnly }: ShortcutKeyProps) {
    const badgeClasses = cn(
        "flex items-center gap-2 font-sans border border-line rounded px-1",
        size === "sm" && "text-[10px] px-1 leading-4",
        className
    )

    const wrapperClasses = cn(
        "inline-flex items-center gap-1",
        hoverOnly === true &&
            "opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100",
        hoverOnly === "shortcut-hint" &&
            "opacity-0 transition-opacity duration-150 group-hover/shortcut-hint:opacity-100 group-focus-within/shortcut-hint:opacity-100"
    )

    if (keys) {
        return (
            <span className={wrapperClasses}>
                {keys.map((key, index) => (
                    <kbd key={`${key}-${index}`} className={badgeClasses}>
                        {key}
                    </kbd>
                ))}
            </span>
        )
    }

    return <kbd className={cn(badgeClasses, wrapperClasses)}>{children}</kbd>
}
