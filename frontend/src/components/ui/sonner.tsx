import { Toaster as Sonner } from "sonner"
import { useInRouterContext, useLocation } from "react-router-dom"
import { useViewport } from "@/lib/ui/responsive"
import { toastPosition } from "@/lib/ui/toastPosition"

type ToasterProps = React.ComponentProps<typeof Sonner>

function Base({ pathname, ...props }: ToasterProps & { pathname: string }) {
  const { isPhone } = useViewport()
  return (
    <Sonner
      className="toaster group"
      position={toastPosition(pathname, isPhone)}
      visibleToasts={5}
      expand
      gap={8}
      duration={3000}
      closeButton
      {...props}
    />
  )
}

function Routed(props: ToasterProps) {
  return <Base pathname={useLocation().pathname} {...props} />
}

/**
 * Toasts sit at the bottom centre of the screen (index.css keeps them clear of an open side panel or sheet). On a flow's canvas
 * they sit at the bottom right instead: the overview map is at the bottom left and bottom centre is where a long flow ends.
 * On a phone they move to the top: the bottom edge belongs to the sticky Approve / Reject bar and the sheets.
 */
const Toaster = (props: ToasterProps) => {
  const inRouter = useInRouterContext()
  return inRouter ? <Routed {...props} /> : <Base pathname="" {...props} />
}

export { Toaster }
