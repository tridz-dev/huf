export function ShortcutKey({ children }: { children: React.ReactNode }) {
    return (
        <kbd className="flex items-center gap-2 font-sans border border-zinc-300 rounded px-1">
            {children}
        </kbd>
    )
}