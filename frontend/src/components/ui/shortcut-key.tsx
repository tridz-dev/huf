import { cn } from "@/lib/utils"

interface ShortcutKeyProps {
    children?: React.ReactNode
    /** Render one badge per key label (e.g. ["⌘", "K"]) instead of `children`. */
    keys?: string[]
    size?: "sm" | "md"
    className?: string
}

export function ShortcutKey({ children, keys, size = "md", className }: ShortcutKeyProps) {
    const badgeClasses = cn(
        "flex items-center gap-2 font-sans border border-zinc-300 rounded px-1",
        size === "sm" && "text-[10px] px-1 leading-4",
        className
    )

    if (keys) {
        return (
            <span className="inline-flex items-center gap-1">
                {keys.map((key, index) => (
                    <kbd key={`${key}-${index}`} className={badgeClasses}>
                        {key}
                    </kbd>
                ))}
            </span>
        )
    }

    return <kbd className={badgeClasses}>{children}</kbd>
}
