import * as React from "react"

const SIDEBAR_STORAGE_KEY = "sidebar:state"
/** What the person chose while the window was narrow (kept apart so a narrow window never rewrites the wide-screen choice). */
const SIDEBAR_NARROW_STORAGE_KEY = "sidebar:state:narrow"

function readBoolean(key: string): boolean | null {
  try {
    const stored = localStorage.getItem(key)
    return stored === null ? null : stored === "true"
  } catch {
    return null
  }
}

function useWindowAtOrBelow(limit?: number): boolean {
  const [below, setBelow] = React.useState(() => limit !== undefined && typeof window !== "undefined" && window.innerWidth <= limit)
  React.useEffect(() => {
    if (limit === undefined) {
      setBelow(false)
      return
    }
    const check = () => setBelow(window.innerWidth <= limit)
    check()
    window.addEventListener("resize", check)
    return () => window.removeEventListener("resize", check)
  }, [limit])
  return below
}

/**
 * Whether the app navigation is open, and how to change it. Remembered in the browser; at or below `collapseBelow` (px) it is
 * the icon rail until the person opens it, and what they choose there is remembered apart from the wide-screen choice.
 */
export function useSidebarOpenState(
  defaultOpen: boolean,
  collapseBelow: number | undefined,
  openProp: boolean | undefined,
  setOpenProp: ((open: boolean) => void) | undefined,
): [boolean, (value: boolean | ((value: boolean) => boolean)) => void] {
  const narrow = useWindowAtOrBelow(collapseBelow)
  const [wide, setWide] = React.useState(() => readBoolean(SIDEBAR_STORAGE_KEY) ?? defaultOpen)
  const [narrowChoice, setNarrowChoice] = React.useState<boolean | null>(() => readBoolean(SIDEBAR_NARROW_STORAGE_KEY))
  const open = openProp ?? (narrow ? narrowChoice ?? false : wide)
  const setOpen = React.useCallback(
    (value: boolean | ((value: boolean) => boolean)) => {
      const openState = typeof value === "function" ? value(open) : value
      if (setOpenProp) setOpenProp(openState)
      else if (narrow) setNarrowChoice(openState)
      else setWide(openState)
      try {
        localStorage.setItem(narrow ? SIDEBAR_NARROW_STORAGE_KEY : SIDEBAR_STORAGE_KEY, String(openState))
      } catch {
        void 0
      }
    },
    [setOpenProp, open, narrow]
  )
  return [open, setOpen]
}
